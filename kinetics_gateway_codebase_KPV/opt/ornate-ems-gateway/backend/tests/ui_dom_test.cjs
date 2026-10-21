const fs=require('fs');
const assert=require('assert/strict');
const {JSDOM,VirtualConsole}=require('jsdom');
const path=require('path');
const hmi=path.resolve(__dirname,'../hmi');
const html=fs.readFileSync(path.join(hmi,'index.html'),'utf8');
const script=fs.readFileSync(path.join(hmi,'app.js'),'utf8');
const errors=[],requests=[],intervals=new Map();let timer=0,mainFailure=false,meterFailure=false,expired=false;
const consoleSink=new VirtualConsole();consoleSink.on('jsdomError',e=>errors.push(String(e)));
const dom=new JSDOM(html,{url:'http://localhost/hmi/',runScripts:'outside-only',virtualConsole:consoleSink});
const w=dom.window,doc=w.document;
w.setInterval=(fn,ms)=>{intervals.set(++timer,{fn,ms});return timer;};
w.clearInterval=id=>intervals.delete(id);
const at=()=>new Date().toISOString();
const point=(value,unit='')=>({value,quality:'good',timestamp:at(),unit});
let meter={asset_id:'acrel_meter_1',label:'ACREL APM520',online:true,status:'online',source:'hardware',location:'unassigned',timestamp:at(),last_attempt_at:at(),scaling_validated:false,read_errors:[],telemetry:{}};
for(const p of ['a','b','c'])Object.assign(meter.telemetry,{
 ['voltage_'+p+'_v']:point(231.5),['current_'+p+'_a']:point(10.25),['active_power_'+p+'_kw']:point(4.1),['reactive_power_'+p+'_kvar']:point(.2),['power_factor_'+p]:point(.98),
});
for(const p of ['ab','bc','ca'])meter.telemetry['voltage_'+p+'_v']=point(400.5);
Object.assign(meter.telemetry,{
 active_power_total_kw:point(12.3),reactive_power_total_kvar:point(.6),power_factor_total:point(.98),frequency_hz:point(50.01),
 active_energy_total_kwh:point(1567.25),active_energy_forward_kwh:point(1500),active_energy_reverse_kwh:point(67.25),
 reactive_energy_total_kvarh:point(200),reactive_energy_forward_kvarh:point(180),reactive_energy_reverse_kvarh:point(20),apparent_energy_total_kvah:point(1600),
 apparent_power_total_kva:point(12.5),current_neutral_a:point(0),
});
const sample=JSON.parse(JSON.stringify(meter));
let empty=false,emptyHistory=false;
w.fetch=async(path,options={})=>{
 requests.push({path,method:options.method||'GET'});
 if(path==='/api/auth/login')return {ok:true,status:200,json:async()=>({access_token:'ui-fixture-token',role:'customer'})};
 if(expired)return {ok:false,status:401};
 if(meterFailure&&path==='/api/meters')return {ok:false,status:503};
 if(mainFailure&&path==='/api/control-sequence/status/all/compact')return {ok:false,status:530};
 let body;
 if(path==='/api/meters')body={meters:empty?{}:{acrel_meter_1:meter}};
 else if(path.startsWith('/api/meters/acrel_meter_1/history'))body={samples:emptyHistory?[]:[{timestamp:at(),payload:sample}]};
 else if(path==='/api/normalized/snapshot')body={timestamp:at(),gateway_id:'kalpa-ui-test',pairs:{},battery_system:{online:true,soc_percent:55},battery_racks:{},pcs:{}};
 else if(path==='/api/health')body={status:'ok',assets_online:13,assets_total:13,network:{field_interface:'eth1'},mode:'mock'};
 else if(path.startsWith('/api/alarms'))body={alarms:[]};
 else if(path.startsWith('/api/control-sequence'))body={pairs:{}};
 else throw new Error('Unexpected request '+path);
 return {ok:true,status:200,json:async()=>JSON.parse(JSON.stringify(body))};
};
const settle=()=>new Promise(resolve=>setTimeout(resolve,20));
const get=id=>doc.getElementById(id).textContent;
async function tick(){for(const item of intervals.values())if(item.ms===5000)item.fn();await settle();}
async function run(){
 w.eval(script);
 assert.equal(get('meter-status'),'Waiting');
 doc.getElementById('password').value='fixture-only';
 doc.getElementById('login-form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await settle();
 assert.equal(doc.getElementById('password').value,'');
 assert.equal(get('meter-overview-status'),'ONLINE');
 assert.equal(get('soc'),'55.0%');
 assert.equal(get('meter-active'),'12.3 kW');
 doc.getElementById('open-meter').click();await settle();
 assert.equal(get('page-title'),'Energy meter');
 assert(doc.getElementById('view-meter').classList.contains('active'));
 assert.equal(doc.querySelectorAll('#meter-phase-table tbody tr').length,3);
 assert.equal(doc.querySelectorAll('#meter-energy .metric').length,7);
 assert(get('meter-energy').includes('1500.00 kWh'));
 assert(get('meter-notice').includes('await comparison'));
 assert(get('meter-history-table').includes('12.30 kW'));
 assert(get('meter-history-message').includes('not live telemetry'));
 meter.online=false;meter.status='offline';await tick();
 assert.equal(get('meter-status'),'OFFLINE');assert.equal(get('meter-active'),'—');
 assert(!get('meter-phase-table').includes('231.5'));
 assert(!get('meter-energy').includes('1500.00'));
 assert(get('meter-history-table').includes('12.30 kW')); // explicitly historical values retained
 meter.online=true;meter.status='online';await tick();assert.equal(get('meter-active'),'12.3 kW');
 meter.status='degraded';meter.telemetry.active_energy_forward_kwh.quality='bad';await tick();
 assert.equal(get('meter-status'),'DEGRADED');assert(!get('meter-energy').includes('1500.00'));
 assert.equal(get('meter-frequency'),'50.01 Hz');
 meter.telemetry.active_energy_forward_kwh.quality='good';meter.status='online';
 meterFailure=true;await tick();assert.equal(get('meter-status'),'API UNAVAILABLE');assert.equal(get('meter-active'),'—');
 assert.equal(get('soc'),'55.0%');
 meterFailure=false;mainFailure=true;await tick();assert.equal(get('meter-active'),'12.3 kW');assert.equal(get('badge'),'CONNECTION LOST');
 mainFailure=false;meter.source='mock';await tick();assert.equal(get('meter-status'),'SIMULATED · ONLINE');assert(get('meter-notice').includes('SIMULATED DATA'));
 meter.source='hardware';meter.label='<img src=x onerror=alert(1)>';await tick();assert.equal(doc.querySelectorAll('#meter-label img').length,0);
 empty=true;await tick();assert.equal(get('meter-status'),'NOT ENABLED');assert.equal(get('meter-active'),'—');
 empty=false;emptyHistory=true;doc.getElementById('meter-history-refresh').click();await settle();assert(get('meter-history-message').includes('No stored meter samples'));
 expired=true;await tick();assert(!doc.getElementById('login').classList.contains('inactive'));assert.equal(get('meter-active'),'—');assert(get('login-error').includes('expired'));
 assert(requests.every(r=>r.method==='GET'||r.path==='/api/auth/login'));
 assert(!requests.some(r=>r.path.startsWith('/api/control/')));
 assert.deepEqual(errors,[]);
 console.log('PASS: Meter HMI DOM/API-flow checks: login, navigation, online readings, phase table, energy, history, offline masking, recovery, degraded energy, API failure isolation, simulation, escaping, disabled, empty history, session expiry, read-only requests.');
 dom.window.close();
}
run().catch(error=>{console.error(error);dom.window.close();process.exit(1)});
