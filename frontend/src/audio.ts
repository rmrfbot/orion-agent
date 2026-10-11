/** Convert WebView2 MediaRecorder output to bounded mono PCM16 WAV in memory. */
export function pcmWav(samples: Float32Array, sampleRate: number): Uint8Array {
  const rate=16000;
  const length=Math.floor(samples.length*rate/sampleRate);
  if(!Number.isFinite(sampleRate)||sampleRate<=0||length<1600||length>rate*30)throw new Error('Recording must be between 0.1 and 30 seconds.');
  const bytes=new Uint8Array(44+length*2);const view=new DataView(bytes.buffer);
  const text=(at:number,value:string)=>[...value].forEach((char,index)=>view.setUint8(at+index,char.charCodeAt(0)));
  text(0,'RIFF');view.setUint32(4,bytes.length-8,true);text(8,'WAVE');text(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,rate,true);view.setUint32(28,rate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  text(36,'data');view.setUint32(40,length*2,true);
  let energy=0;
  for(let i=0;i<length;i++){
    const start=Math.floor(i*sampleRate/rate),end=Math.max(start+1,Math.floor((i+1)*sampleRate/rate));
    let sum=0;for(let j=start;j<end&&j<samples.length;j++)sum+=samples[j];
    const sample=Math.max(-1,Math.min(1,sum/(end-start)));energy+=sample*sample;
    view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true);
  }
  if(Math.sqrt(energy/length)<0.0005)throw new Error('No microphone audio was detected. Nothing was submitted.');
  return bytes;
}

export async function recordingToWav(blob: Blob): Promise<Uint8Array> {
  const context=new AudioContext();
  try {
    const decoded=await context.decodeAudioData(await blob.arrayBuffer());
    const mono=new Float32Array(decoded.length);
    for(let c=0;c<decoded.numberOfChannels;c++){
      const channel=decoded.getChannelData(c);
      for(let i=0;i<mono.length;i++)mono[i]+=channel[i]/decoded.numberOfChannels;
    }
    return pcmWav(mono,decoded.sampleRate);
  } catch(error) {
    throw new Error(error instanceof Error && /Recording|microphone/.test(error.message)?error.message:'This microphone audio format could not be decoded. Try another microphone or use typed commands.', {cause:error});
  } finally { await context.close(); }
}
