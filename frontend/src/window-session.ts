type WindowInfo = {compact:boolean;shortcut:string;shortcut_error:string|null};
type Options = {native:boolean;invoke:<T>(command:string,args:Record<string,unknown>)=>Promise<T>;storage?:Pick<Storage,'getItem'|'setItem'>};
export class WindowSession {
  private options:Options;
  private state:WindowInfo & {pending:boolean}={compact:false,shortcut:'Ctrl+Shift+Space',shortcut_error:null,pending:false};
  private listeners=new Set<()=>void>();
  constructor(options:Options){this.options=options;this.state.compact=options.native;}
  getSnapshot=()=>this.state;
  subscribe=(fn:()=>void)=>{this.listeners.add(fn);return()=>{this.listeners.delete(fn);};};
  private update(value:Partial<typeof this.state>){this.state={...this.state,...value};this.listeners.forEach(fn=>fn());}
  async load(){
    if(!this.options.native)return;
    try{
      this.update(await this.options.invoke<WindowInfo>('orion_window_info',{}));
      let saved:string|null=null;try{saved=this.options.storage?.getItem('orion.shortcut')??null;}catch{/* Optional preference. */}
      if(saved&&saved!==this.state.shortcut)await this.setShortcut(saved);
    }catch(error){this.update({shortcut_error:error instanceof Error?error.message:String(error)});}
  }
  async setMode(compact:boolean){
    if(this.state.pending||this.state.compact===compact)return false;
    this.update({pending:true});
    try{
      if(this.options.native)this.update(await this.options.invoke<WindowInfo>('orion_window_mode',{compact}));
      else this.update({compact});
      return true;
    }catch(error){this.update({shortcut_error:error instanceof Error?error.message:String(error)});return false;}
    finally{this.update({pending:false});}
  }
  async action(action:'drag'|'minimize'|'show'){
    if(!this.options.native)return;
    try{await this.options.invoke('orion_window_action',{action});}catch(error){this.update({shortcut_error:String(error)});}
  }
  async setHeight(requested:number){
    if(this.options.native&&this.state.compact){try{await this.options.invoke('orion_compact_height',{requested});}catch{/* Window may be closing. */}}
  }
  async setShortcut(shortcut:string){
    if(!this.options.native){this.update({shortcut_error:'Global shortcuts require the native desktop app.'});return false;}
    try{
      this.update(await this.options.invoke<WindowInfo>('orion_shortcut',{shortcut}));
      try{this.options.storage?.setItem('orion.shortcut',shortcut);}catch{/* Optional preference. */}
      return true;
    }catch(error){this.update({shortcut_error:error instanceof Error?error.message:String(error)});return false;}
  }
}
