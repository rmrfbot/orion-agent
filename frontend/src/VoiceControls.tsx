import {Mic, Square, Volume2, VolumeX, X, Play} from 'lucide-react';
import type {VoiceSession, VoiceSnapshot} from './voice';

export function VoiceControls({voice,state,available,disabled,onMute}:{voice:VoiceSession;state:VoiceSnapshot;available:boolean;disabled:boolean;onMute:()=>void}){
  const recording=state.phase==='recording';
  const capturing=['requesting','recording','transcribing'].includes(state.phase);
  return <section className="voice-controls" aria-label="Voice controls">
    <div className="voice-buttons">
      <button type="button" className={`mic-button ${recording?'listening':''}`}
        aria-label={recording?'Stop recording':'Start recording'} aria-pressed={recording}
        title={available?'Click to record; click again to transcribe and execute':'Configure ELEVENLABS_API_KEY in the backend .env'}
        disabled={!recording&&(disabled||!available||state.phase!=='idle')}
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
      {(recording||state.speech==='speaking')&&<span className="audio-bars" aria-hidden="true"><i/><i/><i/><i/><i/></span>}
      {({idle:available?'Microphone off':'Voice setup required',requesting:'Requesting microphone permission...',recording:'Listening — click Stop & send, or Cancel',transcribing:'Transcribing with ElevenLabs...',executing:'Voice command executing...'}[state.phase])}
      {state.speech==='synthesizing'&&' · Preparing spoken response'}
      {state.speech==='speaking'&&' · Speaking'}
    </div>
    {state.notice&&<p className="voice-notice" role="status">{state.notice}</p>}
    {state.transcript&&<div className="transcript"><span>HEARD</span><p>{state.transcript}</p></div>}
  </section>;
}
