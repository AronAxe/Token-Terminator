/** Execute the ESM contribution with a scoped SDK double and REAL React SSR.
 * The host/Popover routing contract is tested, not a running Electron instance.
 * Run: node --experimental-vm-modules scripts/smoke_dashboard.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const React = require('react');
const jsxRuntime = require('react/jsx-runtime');
const {renderToStaticMarkup} = require('react-dom/server');

let profile='default',connectionId='local',gateway='open',mode='local',targetProfile='default';
let recorded=[],data,queryError=false,routeCalls=0;
const host={state:{
  profile:{get:()=>profile},connectionId:{get:()=>connectionId},gateway:{get:()=>gateway}
},profileRoutes:async()=>{routeCalls++;return [{profile,connectionId,mode,targetProfile}];}};
let requests=[],opened=[];
const ctx={register:c=>recorded.push(c),rest:async(path,opts)=>{requests.push([path,opts]);return data;},os:{openExternal:url=>opened.push(url)}};
let queryConfigs=[];
const sdk={host,STATUSBAR_AREAS:{right:'statusBar.right'},useValue:atom=>atom.get(),
  useQuery:config=>{
    queryConfigs.push(config);
    return config.queryKey[1]==='routes' ? {data:[{profile,connectionId,mode,targetProfile}],isError:false} : {data,isError:queryError};
  },
  Popover:({children})=>React.createElement('div',null,children),
  PopoverTrigger:({children})=>children,
  PopoverContent:({children,style})=>React.createElement('section',{style},children)
};
const context=vm.createContext({Intl,Date,Error,console});
const source=fs.readFileSync(new URL('../src/rtk_hermes_plus/dashboard_assets/plugin.js',import.meta.url),'utf8');
const mod=new vm.SourceTextModule(source,{context});
assert.deepEqual([...mod.dependencySpecifiers].sort(),['@hermes/plugin-sdk','react/jsx-runtime']);
await mod.link(async id=>{
  const exports=id==='@hermes/plugin-sdk'?sdk:jsxRuntime;
  const m=new vm.SyntheticModule(Object.keys(exports),function(){for(const [k,v] of Object.entries(exports))this.setExport(k,v);},{context});
  return m;
});
await mod.evaluate();
const plugin=mod.namespace.default;
assert.equal(plugin.id,'token-terminator');assert.equal(plugin.defaultEnabled,false);
plugin.register(ctx);assert.equal(recorded.length,1);assert.equal(recorded[0].area,'statusBar.right');
assert.equal(routeCalls,0);assert.equal(requests.length,0);
function render(){queryConfigs=[];return renderToStaticMarkup(recorded[0].render());}
function tree(){return recorded[0].render().type({ctx});}
function flatten(element,all=[]){if(!element||typeof element!=='object')return all;all.push(element);for(const child of [].concat(element.props?.children||[]))flatten(child,all);return all;}
data={schema_version:1,scope:{profile:'default'},generated_at:new Date().toISOString(),profiles:[{
  available:true,input:{saved:2400,prepared:1600,observed:1600},output:{observed:200},
  value:{saved_api_equivalent_usd:.0048,output_api_equivalent_usd:.0016},billing:'subscription',issues:[]
}]};
const html=render();assert.match(html,/TT ↓ 2.4K/i);assert.match(html,/Output saved/);assert.match(html,/Not measured/);assert.match(html,/not a subscription discount/);
const [routes,summary]=queryConfigs;
assert.equal(routes.retry,false);assert.equal(summary.retry,false);assert.equal(summary.refetchInterval,10000);
assert.equal(routes.refetchInterval,60000);
await routes.queryFn();assert.equal(routeCalls,1);
await summary.queryFn();assert.equal(requests.length,1);assert.equal(requests[0][0],'/summary');
assert.deepEqual(Array.from(summary.queryKey),['token-terminator','summary','local','default','default']);
const popup=tree().props.children[1];assert.equal(popup.props.side,'top');assert.equal(popup.props.align,'end');
const button=flatten(tree()).find(e=>e.type==='button'&&e.props.children==='Open dashboard · localhost:7474');
button.props.onClick();assert.deepEqual(opened,['http://localhost:7474']);
// Exact active scope is checked again on click and at both request boundaries.
profile='brain';button.props.onClick();assert.equal(opened.length,1);
await assert.rejects(()=>summary.queryFn(),/Profile changed/);
profile='default';let finish;ctx.rest=()=>new Promise(resolve=>{finish=resolve;});
const pending=summary.queryFn();connectionId='remote-a';finish(data);await assert.rejects(()=>pending,/Profile changed/);
mode='remote';queryError=true;data.scope.profile='default';
const remoteHtml=render();assert.match(remoteHtml,/Remote connection/);assert.doesNotMatch(remoteHtml,/Open dashboard/);assert.match(remoteHtml,/last snapshot/);
assert.deepEqual(Array.from(queryConfigs[1].queryKey),['token-terminator','summary','remote-a','default','default']);
// Same profile on a second remote must have a different cache identity.
connectionId='remote-b';render();assert.equal(queryConfigs[1].queryKey[2],'remote-b');
gateway='idle';render();assert.equal(queryConfigs[1].enabled,false);
assert.equal(opened.length,1);
console.log(JSON.stringify({desktop_esm:true,real_react_ssr:true,statusbar_slot:true,popup_above:true,opt_in:true,
  async_route_inventory:true,connection_profile_keys:true,profile_switch_race:true,stale_state:true,
  no_remote_localhost:true,no_provider_calls:true,electron_click_test:false}));
