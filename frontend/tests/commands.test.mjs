import test from 'node:test';
import assert from 'node:assert/strict';
import { CommandSession, RequestError } from '../src/commands.ts';
const task = (status = 'finished') => ({task_id:'fixture-123',instruction:'list tabs',status,result:{message:'Fixture response'},error:null});
const storage = () => { const data = new Map(); return {getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)}; };
const tick = () => new Promise(resolve=>setImmediate(resolve));
test('duplicate clicks cannot submit twice while polling', async()=>{
  let posts=0, resolve;
  const pending=new Promise(r=>{resolve=r});
  const session=new CommandSession({request:async(path)=>{if(path==='/api/tasks'){posts++;return task('queued')}return pending}});
  session.start(); const first=session.submit('list tabs'); await tick();
  assert.equal(await session.submit('list tabs'),false); assert.equal(posts,1);
  resolve(task()); await first; assert.equal(session.getSnapshot().busy,false);
});
test('disconnect reconnects GET without replaying POST; incomplete remains incomplete', async()=>{
  let posts=0, gets=0, responses=0;
  const session=new CommandSession({wait:async()=>{},onResponse:()=>{responses++;throw Error('consumer failure')},request:async(path)=>{
    if(path==='/api/tasks'){posts++;return task('queued')}
    if(++gets===1)throw Error('offline'); return task('incomplete');
  }});
  session.start();await session.submit('list tabs');
  assert.equal(posts,1);assert.equal(gets,2);assert.equal(responses,1);
  assert.equal(session.getSnapshot().task.status,'incomplete');assert.equal(session.getSnapshot().busy,false);
});
test('restarting restores task ID without submitting another command',async()=>{
  const saved=storage();saved.setItem('orion.pending-task','fixture-123');let posts=0;
  const session=new CommandSession({storage:saved,request:async(path)=>{assert.equal(path,'/api/tasks/fixture-123');if(path==='/api/tasks')posts++;return task()}});
  session.start();await tick();assert.equal(posts,0);assert.equal(saved.getItem('orion.pending-task'),undefined);assert.equal(session.getSnapshot().task.status,'finished');
});
test('missing task ends tracking with unknown completion and no automatic replay',async()=>{
  const saved=storage();saved.setItem('orion.pending-task','fixture-123');
  const session=new CommandSession({storage:saved,request:async()=>{throw new RequestError('missing',404)}});
  session.start();await tick();assert.equal(session.getSnapshot().busy,false);assert.match(session.getSnapshot().notice,/completion is unknown/);assert.equal(session.getSnapshot().task,null);
});
test('failed POST does not retry; retry requires explicit submission',async()=>{
  let posts=0;const session=new CommandSession({request:async()=>{posts++;throw Error('offline')}});
  session.start();await session.submit('list tabs');assert.equal(posts,1);assert.match(session.getSnapshot().notice,/may have reached/);
  await session.submit('list tabs');assert.equal(posts,2);
});
test('closing controller preserves pending task without cancelling backend',async()=>{
  const saved=storage();let resolve;const pending=new Promise(r=>{resolve=r});
  const session=new CommandSession({storage:saved,request:async(path)=>path==='/api/tasks'?task('queued'):pending});
  session.start();const submitted=session.submit('list tabs');await tick();session.stop();resolve(task());await submitted;
  assert.equal(saved.getItem('orion.pending-task'),'fixture-123');
});
