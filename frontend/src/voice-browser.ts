import { recordingToWav } from './audio';
import { transcribeAudio, synthesizeAudio } from './desktop';
import type { VoiceIO } from './voice';

export function browserVoiceIO(token=''): VoiceIO {
  return {
    getUserMedia:()=>{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Microphone capture requires a supported WebView2 or localhost browser.');
      return navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
    },
    recorder:stream=>{
      if(typeof MediaRecorder==='undefined')throw new Error('Microphone recording is unsupported in this WebView.');
      const mime=['audio/webm;codecs=opus','audio/webm','audio/mp4'].find(type=>MediaRecorder.isTypeSupported(type));
      if(!mime)throw new Error('No supported microphone recording format is available.');
      return new MediaRecorder(stream,{mimeType:mime,audioBitsPerSecond:48000});
    },
    encode:recordingToWav,
    transcribe:(audio,signal)=>transcribeAudio(audio,token,signal),
    synthesize:(text,signal)=>synthesizeAudio(text,token,signal),
    audio:url=>new Audio(url),createURL:blob=>URL.createObjectURL(blob),revokeURL:url=>URL.revokeObjectURL(url),now:()=>performance.now(),
  };
}
