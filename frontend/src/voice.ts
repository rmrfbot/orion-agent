import type { BrowserTask } from './commands';

export type VoicePhase = 'idle' | 'requesting' | 'recording' | 'transcribing' | 'executing';
export type VoiceSnapshot = {
  phase: VoicePhase; speech: 'idle' | 'synthesizing' | 'speaking'; transcript: string;
  notice: string; muted: boolean; canReplay: boolean; transcriptionMs?: number; synthesisMs?: number;
};
export type VoiceIO = {
  getUserMedia: () => Promise<MediaStream>;
  recorder: (stream: MediaStream) => MediaRecorder;
  encode: (blob: Blob) => Promise<Uint8Array>;
  transcribe: (audio: Uint8Array, signal: AbortSignal) => Promise<{text: string; elapsed_ms?: number}>;
  synthesize: (text: string, signal: AbortSignal) => Promise<Blob>;
  audio: (url: string) => HTMLAudioElement;
  createURL: (blob: Blob) => string;
  revokeURL: (url: string) => void;
  now: () => number;
};
type Options = { io: VoiceIO; submit: (text: string) => Promise<boolean>; canSubmit: () => boolean; muted?: boolean };

export function commandFromTranscript(text: string) {
  return text.replace(/^\s*(?:hey\s+)?orion\b[\s,.:!-]*/i, '').trim();
}
export function spokenResponse(task: BrowserTask): string {
  if (!['finished', 'incomplete', 'failed', 'paused'].includes(task.status)) return '';
  return task.result?.message || task.error || `Task ${task.status === 'finished' ? 'completed' : task.status === 'paused' ? 'human verification required' : task.status}.`;
}

/** Browser-independent lifecycle controller; injected IO makes permission/audio races testable. */
export class VoiceSession {
  private options: Options;
  private state: VoiceSnapshot;
  private listeners = new Set<() => void>();
  private generation = 0;
  private speechGeneration = 0;
  private stream?: MediaStream;
  private recorder?: MediaRecorder;
  private chunks: Blob[] = [];
  private recordingStarted = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private transcription?: AbortController;
  private synthesis?: AbortController;
  private player?: HTMLAudioElement;
  private audioURL?: string;
  private speechEnabled = false;
  constructor(options: Options) {
    this.options = options;
    this.state = {phase:'idle',speech:'idle',transcript:'',notice:'',muted:options.muted ?? false,canReplay:false};
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private update(changes: Partial<VoiceSnapshot>) { this.state = {...this.state,...changes}; this.listeners.forEach(fn=>fn()); }
  setTransport(io: Pick<VoiceIO, 'transcribe' | 'synthesize'>) { Object.assign(this.options.io, io); }
  setSpeechEnabled(enabled: boolean) { this.speechEnabled = enabled; }
  private release() {
    if (this.timer) clearTimeout(this.timer);
    this.timer = undefined;
    this.stream?.getTracks().forEach(track=>{track.onended=null;track.stop();});
    this.stream=undefined;
  }
  async begin() {
    if (this.state.phase !== 'idle' || !this.options.canSubmit()) return false;
    const generation = ++this.generation;
    this.stopSpeaking();
    this.update({phase:'requesting',notice:'',transcript:''});
    try {
      const stream = await this.options.io.getUserMedia();
      if (generation !== this.generation) { stream.getTracks().forEach(track=>track.stop()); return false; }
      this.stream = stream;
      const recorder = this.options.io.recorder(stream);
      this.recorder = recorder;
      this.chunks=[];
      recorder.ondataavailable = event => {
        if (generation === this.generation && event.data.size) this.chunks.push(event.data);
        if (this.chunks.reduce((size,blob)=>size+blob.size,0)>3_000_000) this.cancel('Recording exceeded the size limit. Use a shorter command.');
      };
      recorder.onerror = () => { if(generation===this.generation)this.cancel('Recording interrupted. No command was submitted.'); };
      recorder.onstop = () => { void this.finishRecording(generation, recorder.mimeType); };
      stream.getAudioTracks().forEach(track=>{track.onended=()=>this.cancel('Microphone disconnected. No command was submitted.');});
      this.recordingStarted = this.options.io.now();
      recorder.start(250);
      this.update({phase:'recording'});
      this.timer = setTimeout(()=>this.cancel('Recording canceled at 30 seconds. Use a shorter command.'),30_000);
      return true;
    } catch (error) {
      if (generation !== this.generation) return false;
      const name = error instanceof Error ? error.name : '';
      const notice = name === 'NotAllowedError' ? 'Microphone permission denied. Allow ORION in Windows/WebView2 microphone settings.'
        : name === 'NotFoundError' ? 'No microphone is available. Typed commands remain available.'
        : error instanceof Error ? error.message : 'Cannot start the microphone.';
      this.cancel(notice);
      return false;
    }
  }
  stop() {
    if (this.state.phase !== 'recording' || !this.recorder) return;
    this.update({phase:'transcribing'});
    try { this.recorder.stop(); } catch { this.cancel('Recording interrupted. No command was submitted.'); }
    finally { this.release(); }
  }
  private async finishRecording(generation: number, mime: string) {
    if (generation !== this.generation || this.state.phase !== 'transcribing') {
      if (generation === this.generation) this.cancel('Recording interrupted. No command was submitted.');
      return;
    }
    this.release();
    const chunks=this.chunks;
    this.chunks=[];
    const duration = this.options.io.now()-this.recordingStarted;
    try {
      if (!chunks.length || duration<100 || duration>30_500) throw new Error('Recording is empty or outside the duration limit. Try a short command.');
      const audio=await this.options.io.encode(new Blob(chunks,{type:mime}));
      if (generation !== this.generation) return;
      this.transcription = new AbortController();
      const result=await this.options.io.transcribe(audio,this.transcription.signal);
      if (generation !== this.generation) return;
      const raw=result.text.trim();
      const text=commandFromTranscript(raw);
      this.update({transcript:raw,transcriptionMs:result.elapsed_ms});
      if (!text) throw new Error('No command was detected. Nothing was submitted.');
      if (!this.options.canSubmit()) throw new Error('Another task is running. Your transcript is preserved; nothing was submitted.');
      this.update({phase:'executing'});
      const accepted = await this.options.submit(text);
      if (generation !== this.generation) return;
      this.update({phase:'idle',notice:accepted?'':'Command was not submitted. Your transcript is preserved.'});
    } catch (error) {
      if (generation === this.generation) this.update({phase:'idle',notice:error instanceof Error?error.message:'Voice transcription failed. Typed commands remain available.'});
    } finally { if (generation === this.generation) this.transcription=undefined; }
  }
  cancel(notice='Recording canceled. Nothing was submitted.') {
    if (this.state.phase === 'executing') return; // Browser tasks are not recording operations.
    ++this.generation;
    this.transcription?.abort();this.transcription=undefined;
    const recorder=this.recorder;this.recorder=undefined;
    if(recorder){recorder.onstop=null;recorder.ondataavailable=null;recorder.onerror=null;
      if(recorder.state!=='inactive')try{recorder.stop();}catch{/* Already stopped. */}}
    this.release();this.chunks=[];
    this.update({phase:'idle',notice});
  }
  suspend() { if (['requesting','recording','transcribing'].includes(this.state.phase)) this.cancel('Recording canceled because ORION was minimized or hidden.'); this.stopSpeaking(); }
  dispose() { this.cancel(''); ++this.generation; this.stopSpeaking(); }
  setMuted(muted: boolean) { this.update({muted});if(muted)this.stopSpeaking(); }
  stopSpeaking() {
    ++this.speechGeneration;
    this.synthesis?.abort();this.synthesis=undefined;
    if(this.player){this.player.onended=null;this.player.onerror=null;this.player.pause();this.player.src='';this.player=undefined;}
    if(this.audioURL)this.options.io.revokeURL(this.audioURL);
    this.audioURL=undefined;
    this.update({speech:'idle',canReplay:false});
  }
  async speak(task: BrowserTask) {
    this.stopSpeaking();
    if(this.state.muted)return;
    if(!this.speechEnabled){this.update({notice:'Spoken response unavailable. Configure the backend ElevenLabs voice; the text result is ready.'});return;}
    const text=spokenResponse(task);
    if(!text)return;
    const generation=this.speechGeneration;
    const started=this.options.io.now();
    this.synthesis=new AbortController();
    this.update({speech:'synthesizing'});
    try {
      const blob=await this.options.io.synthesize(text,this.synthesis.signal);
      if(generation!==this.speechGeneration || this.state.muted)return;
      if(!blob.size)throw new Error('Speech service returned empty audio.');
      this.update({synthesisMs:Math.round(this.options.io.now()-started)});
      this.audioURL=this.options.io.createURL(blob);
      this.player=this.options.io.audio(this.audioURL);
      this.player.onended=()=>this.stopSpeaking();
      this.player.onerror=()=>{this.stopSpeaking();this.update({notice:'Audio playback failed. The text result is available.'});};
      this.update({canReplay:true});
      await this.play(generation);
    } catch(error) {
      if(generation===this.speechGeneration){this.stopSpeaking();this.update({notice:error instanceof Error?error.message:'Speech unavailable. The text result is ready.'});}
    }
  }
  private async play(generation: number) {
    try {
      await this.player?.play();
      if(generation===this.speechGeneration)this.update({speech:'speaking',notice:''});
    } catch {
      if(generation===this.speechGeneration)this.update({speech:'idle',notice:'Audio playback was blocked. Click Play response to listen.',canReplay:true});
    }
  }
  replay() { if(this.player && !this.state.muted)void this.play(this.speechGeneration); }
}
