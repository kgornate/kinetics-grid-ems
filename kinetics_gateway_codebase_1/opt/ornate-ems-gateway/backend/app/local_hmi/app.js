/* Ornate Local HMI — read-only. No fieldbus access, no write/control endpoints. */
(() => {
  'use strict';
  let token = null;
  let role = 'viewer';
  let timer = null;
  let inFlight = false;
  let lastSuccessful = 0;
  let currentTab = 'overview';
  let meter = null;
  let meterError = '';
  let meterLoaded = false;
  let meterInFlight = false;
  let historyInFlight = false;
  let historyFetchedAt = 0;
  const $ = id => document.getElementById(id);
  const text = (id, value) => { const e = $(id); if (e) e.textContent = String(value == null ? '—' : value); };
  const string = v => (v == null || v === '' ? '—' : String(v));
  const number = (v, n=1, unit='') => v === null || v === undefined || v === '' || !Number.isFinite(Number(v)) ? '—' : Number(v).toFixed(n) + unit;
  const metric = (label, value) => {
    const e = document.createElement('div'); e.className = 'metric';
    const a = document.createElement('span'); a.className = 'label'; a.textContent = label;
    const b = document.createElement('strong'); b.textContent = string(value);
    e.append(a, b); return e;
  };
  const cell = (tag, value) => { const e = document.createElement(tag); e.textContent = string(value); return e; };
  function makeTable(id, headers, rows) {
    const el = $(id); el.replaceChildren();
    if (!rows.length) { const blank = document.createElement('div'); blank.className = 'blank'; blank.textContent = 'No records available'; el.append(blank); return; }
    const table = document.createElement('table');
    const head = document.createElement('thead'); const tr = document.createElement('tr');
    headers.forEach(h => tr.append(cell('th',h))); head.append(tr); table.append(head);
    const body = document.createElement('tbody');
    rows.forEach(row => { const r = document.createElement('tr'); row.forEach(v => r.append(cell('td',v))); body.append(r); });
    table.append(body); el.append(table);
  }
  function setMetrics(id, items) { const el = $(id); el.replaceChildren(); items.forEach(([k,v]) => el.append(metric(k,v))); }
  function onlineLabel(v) { return v === true ? 'ONLINE' : v === false ? 'OFFLINE' : 'UNKNOWN'; }
  function statusForPair(p) { return p.online === true ? 'ONLINE' : p.online === false ? 'OFFLINE' : 'UNKNOWN'; }
  function updateClock() { const now = new Date(); text('clock-time',now.toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})); text('clock-date',now.toLocaleDateString([], {day:'2-digit',month:'short',year:'numeric'})); }
  function badge(state, message) { const e=$('badge'); e.className = 'pill ' + (state || 'muted-pill'); e.textContent = message; }
  function warning(message) { const el=$('warning'); el.textContent=message||''; el.classList.toggle('hidden',!message); }
  function signPower(v) { if (v == null || !Number.isFinite(Number(v))) return 'Power unavailable'; if (Math.abs(Number(v)) < .05) return 'Standby / Zero'; return Number(v) > 0 ? 'Discharging (+)' : 'Charging (−)'; }
  function allPairs(model) { return Object.values(model.pairs || {}).filter(p=>p&&typeof p==='object').sort((a,b)=>String(a.pair_id).localeCompare(String(b.pair_id),undefined,{numeric:true})); }
  function renderOverview(model, health, alarms) {
    const pairs=allPairs(model), bank=model.battery_system||{};
    text('gateway-id', 'Gateway: ' + string(model.gateway_id || health.gateway_id));
    const soc=bank.soc_percent;
    text('soc', number(soc,1,'%'));
    text('soc-source',bank.online ? 'BMS system telemetry' : 'BMS system offline / unknown');
    const validPower=pairs.filter(p=>p.enabled!==false && p.pcs && p.pcs.online && Number.isFinite(Number(p.pcs.active_power_kw)) && p.pcs.active_power_kw !== null);
    const totalPower=validPower.reduce((sum,p)=>sum+Number(p.pcs.active_power_kw),0);
    const showPower=validPower.length>0 && validPower.length===pairs.filter(p=>p.enabled!==false).length;
    text('power',showPower?number(totalPower,1,' kW'):'—');
    text('power-state',showPower ? signPower(totalPower) : 'Incomplete PCS telemetry');
    const enabledPairs=pairs.filter(p=>p.enabled!==false);
    text('online-pairs', `${enabledPairs.filter(p=>p.online===true).length} / ${enabledPairs.length}`);
    text('pair-total','BMS and PCS both connected');
    text('alarm-count',Array.isArray(alarms.alarms)?alarms.alarms.length:'—');
    const grid=$('pair-grid'); grid.replaceChildren();
    enabledPairs.forEach(p=>{
      const section=document.createElement('section'); section.className='panel pair';
      const heading=document.createElement('div'); heading.className='pair-title';
      const title=document.createElement('strong'); title.textContent = string(p.pair_id).replace('_',' ').toUpperCase();
      const state=document.createElement('span'); state.textContent=statusForPair(p); state.className='status '+(p.online?'good':'bad');
      heading.append(title,state); section.append(heading);
      const socline=document.createElement('div'); socline.className='soc-line'; const sa=cell('span','SOC'); const sb=cell('strong',number(p.battery?.soc_percent,1,'%')); socline.append(sa,sb);
      const track=document.createElement('div'); track.className='track'; const fill=document.createElement('div'); fill.className='fill';
      const sv=p.battery?.soc_percent; fill.style.width = sv != null && Number.isFinite(Number(sv)) ? Math.max(0,Math.min(100,Number(sv)))+'%' : '0%';
      track.append(fill); section.append(socline,track);
      const values=[['Actual power',number(p.pcs?.active_power_kw,1,' kW')],['Rack voltage',number(p.battery?.voltage_v,0,' V')],['Rack SOH',number(p.battery?.soh_percent,1,'%')],['PCS',p.pcs?.faulted?'FAULT':p.pcs?.running?'RUNNING':p.pcs?.standby?'STANDBY':'—']];
      const stats=document.createElement('div'); stats.className='pair-stats'; values.forEach(([k,v])=>stats.append(metric(k,v))); section.append(stats); grid.append(section);
    });
    setMetrics('system-summary', [['Voltage',number(bank.voltage_v,1,' V')],['Current',number(bank.current_a,1,' A')],['SOH',number(bank.soh_percent,1,'%')],['Charge limit',number(bank.max_charge_power_kw,1,' kW')],['Discharge limit',number(bank.max_discharge_power_kw,1,' kW')],['BMS state',bank.state||'—']]);
    setMetrics('connect-summary', [['Gateway',string(health.status)],['Modbus assets',`${health.assets_online ?? '—'} / ${health.assets_total ?? '—'}`],['Network',string(health.network?.field_interface)],['EMS mode',string(health.mode)],['Local storage',string(health.storage?.storage_mode || (health.storage?.root ? 'Available' : '—'))],['Internet', 'Not required']]);
  }
  function renderBattery(model) {
    const racks=Object.values(model.battery_racks||{}).sort((a,b)=>Number(a.rack_id)-Number(b.rack_id));
    makeTable('rack-table',['Rack','Link','SOC','SOH','Voltage','Current','State','Charge limit','Discharge limit','Contactors'],racks.map(r=>[
      'Rack '+string(r.rack_id),onlineLabel(r.online),number(r.soc_percent,1,'%'),number(r.soh_percent,1,'%'),number(r.voltage_v,1,' V'),number(r.current_a,1,' A'),string(r.state),number(r.max_charge_power_kw,1,' kW'),number(r.max_discharge_power_kw,1,' kW'),r.positive_contactor_closed===true && r.negative_contactor_closed===true?'Closed':r.positive_contactor_closed===false || r.negative_contactor_closed===false?'Open':'—'
    ]));
    const b=model.battery_system||{};
    setMetrics('battery-system-detail', [['System SOC',number(b.soc_percent,1,'%')],['System SOH',number(b.soh_percent,1,'%')],['Voltage',number(b.voltage_v,1,' V')],['Current',number(b.current_a,1,' A')],['Max cell V',number(b.max_cell_voltage_v,3,' V')],['Min cell V',number(b.min_cell_voltage_v,3,' V')],['Max cell temp',number(b.max_cell_temperature_c,1,' °C')],['Min cell temp',number(b.min_cell_temperature_c,1,' °C')],['Online',onlineLabel(b.online)],['Charge limit',number(b.max_charge_power_kw,1,' kW')],['Discharge limit',number(b.max_discharge_power_kw,1,' kW')],['Operational state',string(b.state)]]);
  }
  function renderPCS(model) {
    const pcs=Object.values(model.pcs||{}).sort((a,b)=>String(a.asset_id).localeCompare(String(b.asset_id),undefined,{numeric:true}));
    makeTable('pcs-table',['PCS','Link','Operating','Direction','Active power','Reactive power','DC voltage','DC current','Grid frequency','Fault'],pcs.map(p=>[
      p.asset_id,onlineLabel(p.online),p.running===true?'Running':p.standby===true?'Standby':p.running===false?'Stopped':'—',p.charging===true?'Charging':p.discharging===true?'Discharging':'—',number(p.active_power_kw,1,' kW'),number(p.reactive_power_kvar,1,' kVAr'),number(p.dc_voltage_v,1,' V'),number(p.dc_current_a,1,' A'),number(p.grid_frequency_hz,2,' Hz'),p.faulted===true?'Fault':p.faulted===false?'Clear':'—'
    ]));
    const grid=$('pcs-metrics');grid.replaceChildren();
    pcs.forEach(p=>{const card=document.createElement('section');card.className='panel';card.append(cell('strong',p.asset_id));
      const metrics=document.createElement('div');metrics.className='metrics-grid';
      [['Grid V AB',number(p.grid_voltage_ab_v,0,' V')],['Grid V BC',number(p.grid_voltage_bc_v,0,' V')],['Grid V CA',number(p.grid_voltage_ca_v,0,' V')],['DC bus',number(p.dc_bus_voltage_v,1,' V')],['DC power',number(p.dc_power_kw,1,' kW')],['Power factor',number(p.power_factor,3)]].forEach(([k,v])=>metrics.append(metric(k,v)));
      card.append(metrics);grid.append(card);});
  }
  function renderAlarms(alarms) {
    const items=Array.isArray(alarms.alarms)?alarms.alarms:[];
    makeTable('alarm-table',['Severity','Asset','Signal / alarm','Status','First seen','Last seen'],items.map(a=>[
      a.severity||'—',a.asset_id||'Gateway',a.alarm_key||a.code||a.signal_name||'—',a.state||'Active',a.first_seen_at||a.first_seen||a.timestamp||'—',a.last_seen_at||a.last_seen||a.timestamp||'—'
    ]));
  }
  function renderGateway(health,ctrl) {
    const storage=health.storage||{};
    setMetrics('gateway-health', [['Gateway ID',health.gateway_id],['Health',health.status],['Operational mode',health.mode],['Connected assets',`${health.assets_online??'—'} / ${health.assets_total??'—'}`],['Last poll error',health.last_poll_error||'None reported'],['Software initialized',health.startup?.ready===true?'Yes':health.startup?.ready===false?'No':'—'],['Field interface',health.network?.field_interface],['Wi-Fi interface',health.network?.wifi_interface],['Storage database',storage.database||'—'],['Storage mode',storage.storage_mode||'—'],['Control enabled',health.control_sequence?.enabled===true?'Yes':health.control_sequence?.enabled===false?'No':'—'],['Internet required','No']]);
    const pairs=Object.values(ctrl.pairs||{});
    makeTable('control-state',['Pair','Stage','Run status','Direction','Requested','Commanded','PCS actual','Blocked'],pairs.map(p=>[
      p.pair_id,p.stage,p.run_status,p.direction,number(p.requested_power_kw,1,' kW'),number(p.commanded_power_kw,1,' kW'),number(p.pcs_actual_power_kw,1,' kW'),p.hard_blocked===true?'Yes':p.hard_blocked===false?'No':'—'
    ]));
  }
  function localTime(value) {
    const date = new Date(value || '');
    return Number.isFinite(date.getTime()) ? date.toLocaleString() : '—';
  }
  function meterReading(key, digits=1, unit='') {
    const point = meter?.telemetry?.[key];
    if (meterError || !meter?.online || !point || !['good','mock'].includes(point.quality)) return '—';
    return number(point.value, digits, unit);
  }
  function renderMeter() {
    let label='Waiting', style='muted-pill';
    if (meterError) {label='API UNAVAILABLE';style='error';}
    else if (meterLoaded && !meter) {label='NOT ENABLED';}
    else if (meter) {
      label=String(meter.status || (meter.online?'online':'offline')).replaceAll('_',' ').toUpperCase();
      style=meter.online?(meter.status==='degraded'?'warn':''):'error';
      if (meter.source==='mock') {label='SIMULATED · '+label;style='warn';}
    }
    for (const id of ['meter-status','meter-overview-status']) {
      const node=$(id);node.textContent=label;node.className='pill '+style;
    }
    text('meter-label',meter?.label||'ACREL APM520');
    text('meter-subtitle',meter ? `${meter.location==='unassigned'?'Location not assigned':string(meter.location)} · ${meter.source==='hardware'?'Physical meter':meter.source==='mock'?'Simulation':'Unknown source'}` : 'Independent RS485 energy meter');
    let notice = meterError ? 'Meter API unavailable: '+meterError+'. Live values are hidden until communication recovers.' : '';
    if (!notice && !meterLoaded) notice='Waiting for meter data.';
    else if (!notice && !meter) notice='The meter is not enabled. Install or enable the meter integration on this gateway.';
    else if (!notice && !meter.online) notice='Meter '+label.toLowerCase()+'. Live readings are unavailable. Check meter power and the RS485 connection.';
    if (!notice && meter?.status==='degraded') notice='Some readings are unavailable or invalid. Unavailable values are shown as dashes.';
    if (meter?.source==='mock') notice=(notice?notice+' ':'')+'SIMULATED DATA: these readings are not from the physical meter.';
    if (meter?.online && !meter.scaling_validated) notice=(notice?notice+' ':'')+'Measurement scaling and power direction await comparison with the meter display.';
    const note=$('meter-notice');note.textContent=notice;note.classList.toggle('hidden',!notice);
    text('meter-active',meterReading('active_power_total_kw',1,' kW'));
    text('meter-reactive',meterReading('reactive_power_total_kvar',1,' kvar'));
    text('meter-pf',meterReading('power_factor_total',3));
    text('meter-frequency',meterReading('frequency_hz',2,' Hz'));
    setMetrics('meter-overview-values',[
      ['Active power',meterReading('active_power_total_kw',1,' kW')],
      ['Frequency',meterReading('frequency_hz',2,' Hz')],
      ['Forward active energy',meterReading('active_energy_forward_kwh',2,' kWh')],
      ['Last measurement',localTime(meter?.timestamp)],
    ]);
    makeTable('meter-phase-table',['Phase','L–N voltage','Line voltage','Current','Active power','Reactive power','Power factor'],['a','b','c'].map((phase,index)=>[
      'Phase '+phase.toUpperCase(),meterReading('voltage_'+phase+'_v',1,' V'),
      ['AB','BC','CA'][index]+': '+meterReading('voltage_'+['ab','bc','ca'][index]+'_v',1,' V'),
      meterReading('current_'+phase+'_a',2,' A'),meterReading('active_power_'+phase+'_kw',2,' kW'),
      meterReading('reactive_power_'+phase+'_kvar',2,' kvar'),meterReading('power_factor_'+phase,3),
    ]));
    setMetrics('meter-energy',[
      ['Total active energy',meterReading('active_energy_total_kwh',2,' kWh')],
      ['Forward active energy',meterReading('active_energy_forward_kwh',2,' kWh')],
      ['Reverse active energy',meterReading('active_energy_reverse_kwh',2,' kWh')],
      ['Total reactive energy',meterReading('reactive_energy_total_kvarh',2,' kvarh')],
      ['Forward reactive energy',meterReading('reactive_energy_forward_kvarh',2,' kvarh')],
      ['Reverse reactive energy',meterReading('reactive_energy_reverse_kvarh',2,' kvarh')],
      ['Total apparent energy',meterReading('apparent_energy_total_kvah',2,' kVAh')],
    ]);
    const errors=(meter?.read_errors||[]).map(error=>`${error.block||'Meter'}: ${error.error||'Read failed'}`).join('; ');
    setMetrics('meter-details',[
      ['Connection',label],['Data source',meter?.source==='hardware'?'Hardware':meter?.source==='mock'?'Simulation':'—'],
      ['Location',meter?.location==='unassigned'?'Not assigned':meter?.location],
      ['Last measurement',localTime(meter?.timestamp)],['Last read attempt',localTime(meter?.last_attempt_at)],
      ['Last energy reading',localTime(meter?.telemetry?.active_energy_total_kwh?.timestamp)],
      ['Apparent power',meterReading('apparent_power_total_kva',2,' kVA')],
      ['Neutral current',meterReading('current_neutral_a',2,' A')],
      ['Scaling verified',meter?.scaling_validated?'Yes':'Pending commissioning'],
      ['Read error',meterError||errors||'None reported'],
    ]);
  }
  async function meterRequest(path, session) {
    const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),10000);
    try {
      const response=await fetch(path,{headers:{Authorization:'Bearer '+session,Accept:'application/json'},cache:'no-store',signal:controller.signal});
      if(response.status===401) {if(token===session) logout('Session expired. Please sign in again.');throw new Error('Session expired');}
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {clearTimeout(timeout);}
  }
  async function refreshMeter() {
    if (!token || meterInFlight) return;
    const session=token;meterInFlight=true;
    try {
      const response=await meterRequest('/api/meters',session);
      if(token!==session)return;
      meter=response.meters?.acrel_meter_1||null;meterError='';meterLoaded=true;renderMeter();
    } catch(error) {
      if(token===session) {meterError=error.name==='AbortError'?'Request timed out':String(error.message||error);renderMeter();}
    } finally {meterInFlight=false;}
    if(token===session && currentTab==='meter' && Date.now()-historyFetchedAt>15000) refreshMeterHistory();
  }
  function historyReading(asset,key,digits,unit) {
    const point=asset.telemetry?.[key];
    if(!asset.online || !point || !['good','mock'].includes(point.quality))return '—';
    return number(point.value,digits,unit);
  }
  async function refreshMeterHistory() {
    if(!token || historyInFlight)return;
    const session=token;historyInFlight=true;$('meter-history-refresh').disabled=true;
    text('meter-history-message','Loading stored meter samples…');
    try {
      const response=await meterRequest('/api/meters/acrel_meter_1/history?limit=60',session);
      if(token!==session)return;
      const rows=Array.isArray(response.samples)?response.samples:[];
      makeTable('meter-history-table',['Stored at','Status','Source','Active power','Frequency','Forward kWh','Reverse kWh'],rows.map(row=>{
        const sample=row.payload||{};
        return [localTime(row.timestamp),sample.status||onlineLabel(sample.online),sample.source||'—',
          historyReading(sample,'active_power_total_kw',2,' kW'),historyReading(sample,'frequency_hz',2,' Hz'),
          historyReading(sample,'active_energy_forward_kwh',2,''),historyReading(sample,'active_energy_reverse_kwh',2,'')];
      }));
      text('meter-history-message',rows.length ? `${rows.length} stored samples. History follows the gateway storage interval; it is not live telemetry.` : 'No stored meter samples yet. History appears after the configured storage interval.');
      historyFetchedAt=Date.now();
    } catch(error) {
      if(token===session) {makeTable('meter-history-table',[],[]);text('meter-history-message','History unavailable: '+(error.name==='AbortError'?'Request timed out':String(error.message||error))+'.');historyFetchedAt=Date.now();}
    } finally {historyInFlight=false;$('meter-history-refresh').disabled=false;}
  }
  async function authorized(path) {
    const result=await fetch(path,{headers:{Authorization:'Bearer '+token,Accept:'application/json'},cache:'no-store'});
    if(result.status===401){ logout('Session expired. Please sign in again.'); throw new Error('session expired'); }
    if(!result.ok)throw new Error(`${path}: HTTP ${result.status}`);
    return result.json();
  }
  async function refresh() {
    if (!token || inFlight) return;
    inFlight=true;
    try {
      const values=await Promise.all([
        authorized('/api/normalized/snapshot'),authorized('/api/health'),authorized('/api/alarms?active_only=true&limit=100'),authorized('/api/control-sequence/status/all/compact')
      ]);
      if (!token)return;
      const [model,health,alarms,ctrl]=values;
      // Cache-backed API timestamps may legitimately stop advancing when a field device fails.
      const age=Date.now()-Date.parse(model.timestamp||'');
      if (!model.timestamp || !Number.isFinite(age) || age>20000 || age< -120000) {
        badge('warn','DATA STALE');warning('Gateway telemetry is stale or has an invalid timestamp. Last known values are not confirmed live.');
      } else if (health.status!=='ok') {badge('warn','GATEWAY DEGRADED'); warning('One or more field devices are offline or degraded. Inspect BMS, PCS and energy meter status.');}
      else {badge('','GATEWAY ONLINE');warning('');}
      renderOverview(model,health,alarms);renderBattery(model);renderPCS(model);renderAlarms(alarms);renderGateway(health,ctrl);
      text('last-update','Snapshot: '+new Date(model.timestamp).toLocaleTimeString()+' · Updated '+new Date().toLocaleTimeString());
      lastSuccessful=Date.now();
    } catch(e) {
      if(token) { badge('error','CONNECTION LOST');warning('Gateway API unavailable: '+String(e.message||e)+'. Values shown may be outdated.'); }
    } finally {inFlight=false;}
  }
  function logout(message='') {
    token=null;role='viewer';clearInterval(timer);timer=null;badge('muted-pill','Waiting for login');
    meter=null;meterError='';meterLoaded=false;historyFetchedAt=0;renderMeter();
    makeTable('meter-history-table',[],[]);text('meter-history-message','');
    $('login').classList.remove('inactive');$('password').value=''; $('login-error').textContent=message;
  }
  $('login-form').addEventListener('submit',async event=>{
    event.preventDefault();$('login-error').textContent='';
    try {
      const response=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:$('username').value.trim(),password:$('password').value}),cache:'no-store'});
      if(!response.ok)throw new Error('Invalid gateway credentials');
      const data=await response.json();if(!data.access_token)throw new Error('No access token received');
      token=data.access_token;role=data.role||'viewer';text('role-label',role.toUpperCase()+' · VIEW ONLY');
      $('login').classList.add('inactive');$('password').value='';
      clearInterval(timer);timer=setInterval(()=>{refresh();refreshMeter();},5000);refresh();refreshMeter();
    }catch(e){$('login-error').textContent=String(e.message||e);}
  });
  $('logout').addEventListener('click',()=>logout());
  function activateTab(name) {
    currentTab=name;
    document.querySelectorAll('.nav-btn').forEach(b=>b.classList.toggle('active',b.dataset.tab===currentTab));
    document.querySelectorAll('.view').forEach(v=>v.classList.toggle('active',v.id==='view-'+currentTab));
    const titles={overview:'Site overview',battery:'Battery / BMS',pcs:'PCS / Power',meter:'Energy meter',alarms:'Alarms and events',gateway:'Gateway health'};
    text('page-title',titles[currentTab]||'Site overview');
    if(currentTab==='meter') {refreshMeter();refreshMeterHistory();}
  }
  document.querySelectorAll('[data-tab]').forEach(button=>button.addEventListener('click',()=>activateTab(button.dataset.tab)));
  $('open-meter').addEventListener('click',()=>activateTab('meter'));
  $('meter-history-refresh').addEventListener('click',refreshMeterHistory);
  window.addEventListener('pagehide',()=>{token=null;clearInterval(timer);});
  setInterval(updateClock,10000);updateClock();renderMeter();
})();
