"""UI integration with real synthetic MediaRecorder audio and mocked native services.
Run from the repository root with Vite on port 5173. No physical microphone,
paid provider requests, or real browser tasks are activated.
"""
from pathlib import Path
Path('test_output').mkdir(exist_ok=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={'width':420,'height':540})
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.add_init_script('''
    window.fixture={compact:true,posts:0,transcriptions:0,speech:0,plays:0,height:0};
    window.__TAURI__={event:{listen:async()=>()=>{}},core:{invoke:async(command,args)=>{
      const info=()=>({compact:fixture.compact,shortcut:'Ctrl+Shift+Space',shortcut_error:null});
      if(command==='orion_window_info')return info();
      if(command==='orion_window_mode'){fixture.compact=args.compact;return info();}
      if(command==='orion_compact_height'){fixture.height=args.requested;return;}
      if(command==='orion_shortcut')return info();
      if(command==='orion_window_action')return;
      if(command==='orion_transcribe'){
        if(!(args instanceof Uint8Array)||new DataView(args.buffer,args.byteOffset).getUint32(24,true)!==16000)throw Error('binary WAV transport failed');
        fixture.transcriptions++;return {text:'ORION, open YouTube.',elapsed_ms:25};
      }
      if(command==='orion_speak'){fixture.lastSpeech=args.text;fixture.speech++;return new Uint8Array([73,68,51,1,2,3]).buffer;}
      if(args.path==='/health')return {browser_worker:true,browser_state:'ready',voice:{transcription:true,speech:true}};
      if(args.method==='POST'){fixture.posts++;return {task_id:'fixture-task',instruction:args.body.instruction,status:'queued',result:null,error:null};}
      return {task_id:'fixture-task',instruction:'open YouTube.',status:'finished',result:{message:'Website opened.',elapsed_ms:10,actions_taken:1,tabs:{tabs:[]}},error:null};
    }}};
    Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
      const context=new AudioContext();const oscillator=context.createOscillator();const sink=context.createMediaStreamDestination();
      oscillator.frequency.value=440;oscillator.connect(sink);oscillator.start();await context.resume();
      const track=sink.stream.getAudioTracks()[0];const original=track.stop.bind(track);
      track.stop=()=>{original();oscillator.stop();void context.close();};return sink.stream;
    }});
    window.Audio=class{constructor(url){this.src=url;this.onended=null;this.onerror=null;}play(){fixture.plays++;return Promise.resolve();}pause(){}};
    ''')
    page.goto('http://127.0.0.1:5173')
    page.get_by_text('Connected',exact=True).wait_for()
    assert page.locator('.floating-shell').is_visible()
    page.screenshot(path='test_output/hybrid-compact.png')
    page.get_by_role('button',name='Start recording').click()
    page.get_by_role('button',name='Stop recording').wait_for()
    page.wait_for_timeout(600)
    page.get_by_role('button',name='Stop recording').click()
    page.get_by_text('ORION, open YouTube.',exact=True).wait_for(timeout=15000)
    assert page.evaluate('fixture.lastSpeech') == 'Website opened.'
    page.wait_for_function('fixture.plays===1')
    assert page.evaluate('fixture.posts')==1
    assert page.evaluate('fixture.transcriptions')==1
    assert page.evaluate('fixture.speech')==1
    page.screenshot(path='test_output/hybrid-voice-result.png')
    page.get_by_role('button',name='Stop speaking').click()
    page.get_by_role('button',name='Expand Mission Control').click()
    page.set_viewport_size({'width':1366,'height':768})
    page.get_by_text('MISSION TELEMETRY',exact=True).wait_for()
    assert page.get_by_role('textbox',name='Browser command').evaluate('(el)=>document.activeElement===el')
    page.screenshot(path='test_output/hybrid-expanded.png')
    page.get_by_role('button',name='Collapse to floating mode').click()
    page.set_viewport_size({'width':420,'height':540})
    page.get_by_text('ORION, open YouTube.',exact=True).wait_for()
    assert page.evaluate('fixture.posts')==1
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert not errors,errors
    print('PASS: real synthetic MediaRecorder -> PCM WAV -> mocked native STT -> single task -> mocked audio playback; expand/collapse preserves transcript/task and focus')
    browser.close()
