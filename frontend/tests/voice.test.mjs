import test from 'node:test';
import assert from 'node:assert/strict';
import {VoiceSession,commandFromTranscript,spokenResponse} from '../src/voice.ts';
import {pcmWav} from '../src/audio.ts';
import {WindowSession} from '../src/window-session.ts';
import {CommandSession} from '../src/commands.ts';

const tick=()=>new Promise(resolve=>setImmediate(resolve));
const task=(status='finished',message='Website opened.')=>({task_id:'fixture-voice',instruction:'open YouTube',status,result:{message},error:null});
function fixture(overrides={}){
  const calls={media:0,stops:0,submitted:[],transcriptions:0,synthesis:[],played:0,paused:0,revoked:[]};let clock=1000;
  const track={onended:null,stop(){calls.stops++;}};
  const stream={getTracks:()=>[track],getAudioTracks:()=>[track]};
  const recorder={state:'inactive',mimeType:'audio/webm',ondataavailable:null,onstop:null,onerror:null,
    start(){this.state='recording';},stop(){this.state='inactive';this.ondataavailable?.({data:new Blob(['fixture'])});this.onstop?.();}};
  const players=[];
  const io={getUserMedia:async()=>{calls.media++;return stream;},recorder:()=>recorder,encode:async()=>new Uint8Array([1,2,3]),
    transcribe:async()=>{calls.transcriptions++;return{text:'ORION, open YouTube.',elapsed_ms:10};},
    synthesize:async(text)=>{calls.synthesis.push(text);return new Blob(['ID3fixture']);},
    audio:()=>{const audio={src:'blob:fixture',onended:null,onerror:null,play:async()=>{calls.played++;},pause:()=>{calls.paused++;}};players.push(audio);return audio;},
    createURL:()=>`blob:fixture-${players.length}`,revokeURL:url=>calls.revoked.push(url),now:()=>clock,...overrides};
  const voice=new VoiceSession({io,submit:async text=>{calls.submitted.push(text);return true;},canSubmit:()=>true});
  voice.setSpeechEnabled(true);
  return {voice,io,calls,recorder,track,players,advance:()=>{clock+=400;},stop:()=>{clock+=400;voice.stop();}};
}

test('recording starts visibly, stops tracks, retains raw transcript, and submits once',async()=>{
  const f=fixture();await f.voice.begin();assert.equal(f.voice.getSnapshot().phase,'recording');
  assert.equal(await f.voice.begin(),false);f.stop();await tick();
  assert.equal(f.calls.media,1);assert.equal(f.calls.stops,1);assert.deepEqual(f.calls.submitted,['open YouTube.']);
  assert.equal(f.voice.getSnapshot().transcript,'ORION, open YouTube.');assert.equal(f.voice.getSnapshot().phase,'idle');f.voice.dispose();
});
test('permission denial, missing microphone and unsupported recorder release resources',async()=>{
  for(const name of ['NotAllowedError','NotFoundError']){
    const f=fixture({getUserMedia:async()=>{throw Object.assign(new Error('fixture'),{name});}});
    assert.equal(await f.voice.begin(),false);assert.equal(f.voice.getSnapshot().phase,'idle');assert.equal(f.calls.submitted.length,0);
  }
  const f=fixture({recorder:()=>{throw new Error('Unsupported audio MIME type');}});
  assert.equal(await f.voice.begin(),false);assert.equal(f.calls.stops,1);
});
test('cancel and device disconnection discard recordings without transcribing',async()=>{
  for(const mode of ['cancel','disconnect','suspend','interruption']){
    const f=fixture();await f.voice.begin();
    if(mode==='cancel')f.voice.cancel();else if(mode==='disconnect')f.track.onended();else if(mode==='interruption')f.recorder.onerror();else f.voice.suspend();
    await tick();assert.equal(f.calls.transcriptions,0);assert.equal(f.calls.submitted.length,0);assert.equal(f.calls.stops,1);
  }
});
test('permission prompt canceled before resolution never leaves microphone tracks running',async()=>{
  let resolve;const pending=new Promise(r=>{resolve=r});
  const f=fixture({getUserMedia:()=>pending});const started=f.voice.begin();f.voice.cancel();
  resolve({getTracks:()=>[f.track]});assert.equal(await started,false);assert.equal(f.calls.stops,1);assert.equal(f.calls.submitted.length,0);
});
test('empty recording and provider failures never execute commands',async()=>{
  const empty=fixture();empty.recorder.stop=function(){this.state='inactive';this.onstop?.();};await empty.voice.begin();empty.stop();await tick();
  assert.equal(empty.calls.transcriptions,0);assert.match(empty.voice.getSnapshot().notice,/empty/);
  const failure=fixture({transcribe:async()=>{throw new Error('ElevenLabs unavailable');}});await failure.voice.begin();failure.stop();await tick();
  assert.equal(failure.calls.submitted.length,0);assert.equal(failure.voice.getSnapshot().phase,'idle');assert.match(failure.voice.getSnapshot().notice,/ElevenLabs/);
});
test('canceling transcription discards a late result instead of submitting it',async()=>{
  let resolve;const pending=new Promise(r=>{resolve=r});const f=fixture({transcribe:()=>pending});
  await f.voice.begin();f.stop();await tick();f.voice.cancel();resolve({text:'open YouTube'});await tick();
  assert.equal(f.calls.submitted.length,0);assert.equal(f.voice.getSnapshot().phase,'idle');
});
test('mute and stop speaking prevent overlap and revoke audio URLs',async()=>{
  const f=fixture();f.voice.setMuted(true);await f.voice.speak(task());assert.equal(f.calls.synthesis.length,0);
  f.voice.setMuted(false);await f.voice.speak(task());assert.equal(f.voice.getSnapshot().speech,'speaking');assert.equal(f.calls.played,1);
  f.voice.stopSpeaking();assert.equal(f.calls.paused,1);assert.equal(f.calls.revoked.length,1);assert.equal(f.voice.getSnapshot().speech,'idle');
});
test('newer speech supersedes pending audio without playing stale responses',async()=>{
  const pending=[];const f=fixture({synthesize:()=>new Promise(resolve=>pending.push(resolve))});
  const first=f.voice.speak(task());const second=f.voice.speak(task('paused'));
  pending[1](new Blob(['new']));await second;pending[0](new Blob(['old']));await first;
  assert.equal(f.players.length,1);assert.equal(f.calls.played,1);f.voice.dispose();
});
test('autoplay denial keeps audio for explicit Play response without another API call',async()=>{
  const f=fixture();let allowed=false;f.io.audio=()=>({src:'blob:fixture',pause(){},play:async()=>{if(!allowed)throw Error('NotAllowed');}});
  await f.voice.speak(task());assert.equal(f.voice.getSnapshot().canReplay,true);assert.match(f.voice.getSnapshot().notice,/blocked/);
  allowed=true;f.voice.replay();await tick();assert.equal(f.voice.getSnapshot().speech,'speaking');assert.equal(f.calls.synthesis.length,1);f.voice.dispose();
});
test('spoken responses read successful answers and never read technical failures',async()=>{
  for (const status of ['finished']) {
    const message = 'Here are your results.\n1. A detailed answer with the requested information.';
    assert.equal(spokenResponse(task(status,message)),message);
  }
  assert.equal(spokenResponse({...task('failed'),result:null,error:'Website access denied.'}),'');
  assert.equal(spokenResponse(task('incomplete','Gemini API error 503: UNAVAILABLE')), '');
  assert.equal(spokenResponse(task('finished','Browser task failed: 503 UNAVAILABLE')), '');
  assert.match(spokenResponse(task('paused')), /Human verification/);
  assert.equal(spokenResponse(task('running')),'');
  assert.equal(commandFromTranscript('Hey ORION, open YouTube.'),'open YouTube.');
  const f=fixture();const message='A full response. '.repeat(100);
  await f.voice.speak(task('finished',message));
  assert.deepEqual(f.calls.synthesis,[message]);f.voice.dispose();
});
test('PCM WAV transport is mono 16k, bounded and rejects silent audio',()=>{
  const samples=Float32Array.from({length:4800},(_,i)=>Math.sin(i/10)*.2);const bytes=pcmWav(samples,48000);const view=new DataView(bytes.buffer);
  assert.equal(view.getUint32(24,true),16000);assert.equal(view.getUint16(22,true),1);assert.equal(bytes.length,3244);
  assert.throws(()=>pcmWav(new Float32Array(16000),16000),/No microphone/);
  assert.throws(()=>pcmWav(samples,0),/Recording/);
});
test('expand/collapse calls one native window and retains saved shortcut on conflict',async()=>{
  const calls=[];let compact=true;
  const shell=new WindowSession({native:true,invoke:async(command,args)=>{
    calls.push([command,args]);if(command==='orion_shortcut')throw Error('already in use');
    if(command==='orion_window_mode')compact=args.compact;
    return {compact,shortcut:'Ctrl+Shift+Space',shortcut_error:null};
  }});
  await shell.load();await shell.setMode(false);assert.equal(shell.getSnapshot().compact,false);
  await shell.setMode(true);assert.equal(shell.getSnapshot().compact,true);
  assert.equal(await shell.setShortcut('Ctrl+Shift+K'),false);assert.equal(shell.getSnapshot().shortcut,'Ctrl+Shift+Space');
  await shell.action('show');assert.equal(calls.at(-1)[1].action,'show');
});
test('rapid expand clicks submit one window transition',async()=>{
  let resolve,count=0;const pending=new Promise(r=>{resolve=r});
  const shell=new WindowSession({native:true,invoke:async()=>{count++;return pending;}});
  const first=shell.setMode(false);assert.equal(await shell.setMode(false),false);
  resolve({compact:false,shortcut:'Ctrl+Shift+Space',shortcut_error:null});await first;assert.equal(count,1);
});
test('voice and typed commands use the same session; both completions speak their results',async()=>{
  let posts=0;const sources=[];
  const session=new CommandSession({request:async(path)=>{if(path==='/api/tasks'){posts++;return task('queued');}return task();}});
  const f=fixture();const voice=new VoiceSession({io:f.io,canSubmit:()=>!session.getSnapshot().busy,submit:text=>session.submit(text,'voice')});voice.setSpeechEnabled(true);
  session.setResponseHandler((_text,result,source)=>{sources.push(source);void voice.speak(result);});session.start();
  await voice.begin();voice.cancel();await session.submit('open YouTube');assert.equal(f.calls.synthesis.length,1);
  await voice.begin();f.advance();voice.stop();await tick();await tick();
  assert.deepEqual(sources,['typed','voice']);assert.equal(posts,2);assert.equal(f.calls.synthesis.length,2);
  assert.equal(voice.getSnapshot().transcript,'ORION, open YouTube.');
  voice.dispose();f.voice.dispose();
  session.stop();
});
