import test from 'node:test';
import assert from 'node:assert/strict';
import {WakeWordSession} from '../src/wake-word.ts';
import {commandFromTranscript} from '../src/voice.ts';

const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));

function fixture({createRecognizer, onCommand=async()=>true}={}) {
  const calls={starts:0,stops:0,aborts:0,commands:[]};
  const recognizers=[];
  const create=createRecognizer??(()=>{
    const recognizer={
      lang:'',continuous:false,interimResults:false,onstart:null,onresult:null,onerror:null,onend:null,
      start(){calls.starts++;this.onstart?.();},
      stop(){calls.stops++;queueMicrotask(()=>this.onend?.());},
      abort(){calls.aborts++;},
      say(transcript,isFinal=true){this.onresult?.({resultIndex:0,results:[Object.assign([{transcript}],{isFinal})]});},
      end(){this.onend?.();},
      fail(error){this.onerror?.({error});},
    };
    recognizers.push(recognizer);
    return recognizer;
  });
  const wake=new WakeWordSession({
    createRecognizer:create,
    normalizeCommand:commandFromTranscript,
    onCommand:async text=>{calls.commands.push(text);return onCommand(text);},
  });
  return {wake,calls,recognizers};
}

test('wake phrase with command submits once and resumes listening',async()=>{
  const f=fixture();assert.equal(f.wake.start(),true);
  assert.equal(f.wake.getSnapshot().status,'listening');
  f.recognizers[0].say('Hey Orion, open YouTube');
  await delay(0);
  assert.deepEqual(f.calls.commands,['open YouTube']);
  assert.equal(f.wake.getSnapshot().status,'starting');
  await delay(350);
  assert.equal(f.calls.starts,2);assert.equal(f.wake.getSnapshot().status,'listening');
  f.wake.stop();assert.equal(f.wake.getSnapshot().status,'off');f.wake.dispose();
});

test('separate wake phrase and command utterances submit the command',async()=>{
  const f=fixture();f.wake.start();
  f.recognizers[0].say('Hey Orion');await delay(0);
  assert.equal(f.calls.starts,2);assert.equal(f.wake.getSnapshot().status,'capturing');
  f.recognizers[1].say('play Rick Astley on YouTube');
  f.recognizers[1].end();
  await delay(0);
  assert.deepEqual(f.calls.commands,['play Rick Astley on YouTube']);
  assert.equal(f.wake.getSnapshot().status,'starting');
  f.wake.stop();f.wake.dispose();
});

test('interim wake text does not trigger until recognized as final',async()=>{
  const f=fixture();f.wake.start();f.recognizers[0].say('Hey Orion',false);
  await delay(0);assert.equal(f.calls.starts,1);assert.equal(f.calls.commands.length,0);
  f.wake.stop();f.wake.dispose();
});

test('unsupported recognition reports an actionable state',()=>{
  const f=fixture({createRecognizer:()=>undefined});
  assert.equal(f.wake.start(),false);assert.equal(f.wake.getSnapshot().status,'unavailable');
  assert.match(f.wake.getSnapshot().notice,/Use Push to talk/);f.wake.dispose();
});

test('denied or unavailable online recognition stops instead of silently retrying',async()=>{
  for(const error of ['not-allowed','network']){
    const f=fixture();f.wake.start();f.recognizers[0].fail(error);
    assert.equal(f.wake.getSnapshot().status,'error');
    assert.match(f.wake.getSnapshot().notice,error==='network'?/recognition service/:/permission was denied/);
    f.recognizers[0].end();await delay(350);
    assert.equal(f.calls.starts,1);f.wake.dispose();
  }
});

test('stop cancels a pending recognition restart',async()=>{
  const f=fixture();f.wake.start();f.recognizers[0].end();f.wake.stop();await delay(350);
  assert.equal(f.calls.starts,1);assert.equal(f.wake.getSnapshot().status,'off');f.wake.dispose();
});
