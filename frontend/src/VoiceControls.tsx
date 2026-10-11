import {Mic, Radio, Square, Volume2, VolumeX, X, Play} from 'lucide-react';
import type {VoiceSession, VoiceSnapshot} from './voice';
import type {WakeSnapshot, WakeWordSession} from './wake-word';

export function VoiceControls({voice,state,available,disabled,onMute,wake,wakeState,wakeSupported}:{voice:VoiceSession;state:VoiceSnapshot;available:boolean;disabled:boolean;onMute:()=>void;wake:WakeWordSession;wakeState:WakeSnapshot;wakeSupported:boolean}){
  const recording=state.phase==='recording';
  const capturing=['requesting','recording','transcribing'].includes(state.phase);
  const wakeActive=['starting','listening','capturing','working'].includes(wakeState.status);
  return <section className="voice-controls" aria-label="Voice controls">
    <div className="voice-buttons">
      <button type="button" className={`mic-button ${wakeState.status==='listening'?'listening':''}`}
        aria-label={wakeActive?'Disable Hey Orion wake phrase':'Enable Hey Orion wake phrase'} aria-pressed={wakeActive}
        title={wakeSupported?'Chrome speech recognition may use an online service to detect the wake phrase.':'Wake phrase requires Chrome speech recognition.'}
        disabled={wakeActive?false:(disabled||!wakeSupported)}
        onClick={()=>{if(wakeActive)wake.stop();else wake.start();}}>
        <Radio size={17}/>{wakeActive?'Disable Hey Orion':'Enable Hey Orion'}
      </button>
      <button type="button" className={`mic-button ${recording?'listening':''}`}
        aria-label={recording?'Stop recording':'Start recording'} aria-pressed={recording}
        title={available?'Click to record; click again to transcribe and execute':'Configure ELEVENLABS_API_KEY in the backend .env'}
        disabled={!recording&&(disabled||!available||state.phase!=='idle'||wakeActive)}
        onClick={()=>{if(recording)voice.stop();else void voice.begin();}}>
        {recording?<Square size={17}/>:<Mic size={19}/>}
        {recording?'Stop & send':'Push to talk'}
      </button>
      {capturing&&<button type="button" onClick={()=>voice.cancel()} title="Discard audio without executing" aria-label="Cancel recording"><X size={17}/>Cancel</button>}
      <button type="button" onClick={onMute} aria-label={state.muted?'Unmute spoken responses':'Mute spoken responses'} aria-pressed={state.muted} title="Spoken responses">
        {state.muted?<VolumeX size={18}/>:<Volume2 size={18}/>}
      </button>
      {state.speech!=='idle'&&<button type="button" onClick={()=>voice.stopSpeaking()} aria-label="Stop speaking" title="Stop speech and discard pending audio"><Square size={16}/></button>}
      {state.canReplay&&state.speech==='idle'&&!state.muted&&<button type="button" onClick={()=>voice.replay()} aria-label="Play response"><Play size={16}/></button>}
    </div>
    <div className="voice-indicator" role="status">
      {({off:'Wake phrase off',starting:'Starting Chrome wake-phrase recognition...',listening:'Say “Hey Orion” to start a command.',capturing:'Wake phrase heard. Say your command now.',working:'Command heard; ORION is working.',error:'Wake phrase recognition stopped.',unavailable:wakeState.notice}[wakeState.status])}
    </div>
    <p className="voice-notice">Chrome wake and command recognition may send audio to an online service. It starts only when enabled; say “Hey Orion,” then your command. Push-to-talk transcription separately requires ElevenLabs.</p>
    {wakeState.status==='error'&&<p className="voice-notice" role="status">{wakeState.notice}</p>}
    <div className="voice-indicator" role="status">
      {(recording||state.speech==='speaking')&&<span className="audio-bars" aria-hidden="true"><i/><i/><i/><i/><i/></span>}
      {({idle:available?'Microphone off':'Push-to-talk setup required',requesting:'Requesting microphone permission...',recording:'Listening — click Stop & send, or Cancel',transcribing:'Transcribing with ElevenLabs...',executing:'Voice command executing...'}[state.phase])}
      {state.speech==='synthesizing'&&' · Preparing spoken response'}
      {state.speech==='speaking'&&' · Speaking'}
    </div>
    {state.notice&&<p className="voice-notice" role="status">{state.notice}</p>}
    {state.transcript&&<div className="transcript"><span>HEARD</span><p>{state.transcript}</p></div>}
  </section>;
}
