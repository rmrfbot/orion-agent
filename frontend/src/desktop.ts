import { RequestError } from "./commands";
type NativeCore = {
  invoke<T>(command: string, args: Record<string, unknown> | ArrayBuffer | Uint8Array): Promise<T>;
};

export function desktopCore(): NativeCore | undefined {
  return (window as Window & { __TAURI__?: { core: NativeCore } }).__TAURI__?.core;
}

export async function desktopRequest(path: string, init?: RequestInit): Promise<unknown> {
  const core = desktopCore();
  if (!core) throw new Error("Desktop connection is unavailable");
  try {
    return await core.invoke("orion_request", {
      path, method: init?.method ?? "GET",
      body: typeof init?.body === "string" ? JSON.parse(init.body) : null,
    });
  } catch (error) {
    const detail = error as { message?: string; status?: number };
    throw new RequestError(detail?.message ?? "Cannot connect to the local ORION backend.", detail?.status);
  }
}



export async function apiRequest<T>(path: string, init?: RequestInit, token = ""): Promise<T> {
  if (desktopCore()) return await desktopRequest(path, init) as T;
  const response = await fetch(path, {
    ...init, signal: AbortSignal.timeout(10_000),
    headers: { ...init?.headers, "X-ORION-Token": token.trim() },
  });
  if (!response.ok) {
    const message = response.status === 401
      ? "ORION authentication failed. Check the local token used by the backend and app."
      : `ORION returned HTTP ${response.status}.`;
    throw new RequestError(message, response.status);
  }
  return response.json() as Promise<T>;
}


export async function transcribeAudio(audio: Uint8Array, token: string, signal: AbortSignal): Promise<{text:string;elapsed_ms?:number}> {
  const core=desktopCore();
  if(core){
    try{return await core.invoke('orion_transcribe',audio);}catch(error){const detail=error as {message?:string;status?:number};throw new RequestError(detail?.message??'Transcription unavailable',detail?.status);}
  }
  const response=await fetch('/api/voice/transcribe',{method:'POST',body:new Blob([audio as Uint8Array<ArrayBuffer>],{type:'audio/wav'}),
    headers:{'Content-Type':'audio/wav','X-ORION-Token':token.trim()},signal:AbortSignal.any([signal,AbortSignal.timeout(35000)])});
  if(!response.ok){const detail=await response.json().catch(()=>({}));throw new RequestError(typeof detail.detail==='string'?detail.detail:'Transcription unavailable',response.status);}
  return response.json();
}

export async function synthesizeAudio(text:string,token:string,signal:AbortSignal):Promise<Blob>{
  const core=desktopCore();
  if(core){
    try{const audio=await core.invoke<ArrayBuffer>('orion_speak',{text});return new Blob([audio],{type:'audio/mpeg'});}
    catch(error){const detail=error as {message?:string;status?:number};throw new RequestError(detail?.message??'Speech unavailable',detail?.status);}
  }
  const response=await fetch('/api/voice/speak',{method:'POST',headers:{'Content-Type':'application/json','X-ORION-Token':token.trim()},
    body:JSON.stringify({text}),signal:AbortSignal.any([signal,AbortSignal.timeout(35000)])});
  if(!response.ok){const detail=await response.json().catch(()=>({}));throw new RequestError(typeof detail.detail==='string'?detail.detail:'Speech unavailable',response.status);}
  return response.blob();
}

export async function listenNative(event:string,handler:()=>void):Promise<()=>void>{
  const api=(window as Window & {__TAURI__?:{event?:{listen:(event:string,handler:()=>void)=>Promise<()=>void>}}}).__TAURI__?.event;
  return api?api.listen(event,handler):()=>{};
}
