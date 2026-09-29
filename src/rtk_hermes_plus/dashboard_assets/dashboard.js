'use strict';
const byId = (id) => document.getElementById(id);
const number = (value) => value == null ? '—' : new Intl.NumberFormat(undefined, {maximumFractionDigits:0}).format(value);
const money = (value) => value == null ? '—' : new Intl.NumberFormat(undefined, {style:'currency',currency:'USD',maximumFractionDigits:4}).format(value);
const text = (id, value) => { byId(id).textContent = value; };
const sumKnown = (values) => { const xs = values.filter(x => x != null); return xs.length ? xs.reduce((a,b) => a+b,0) : null; };
function cell(row, value, className='') { const td=document.createElement('td'); td.textContent=value; td.className=className; row.append(td); return td; }
let state=null, selected='', timer, sequence=0;
function render(data) {
  state=data;
  const options=byId('profile');
  options.replaceChildren(new Option('All profiles',''),...data.profiles.map(p=>new Option(p.label,p.id)));
  if (!data.profiles.some(p=>p.id===selected)) selected='';
  options.value=selected;
  const ps=data.profiles.filter(p=>!selected || p.id===selected);
  text('saved',number(sumKnown(ps.map(p=>p.input.saved))));
  text('prepared',number(sumKnown(ps.map(p=>p.input.prepared))));
  text('input-observed',number(sumKnown(ps.map(p=>p.input.observed))));
  text('output',number(sumKnown(ps.map(p=>p.output.observed))));
  text('value',money(sumKnown(ps.map(p=>p.value.saved_api_equivalent_usd))));
  text('actual',money(sumKnown(ps.map(p=>p.value.actual_cost_usd))));
  const outputValue=sumKnown(ps.map(p=>p.value.output_api_equivalent_usd)), outputPriced=sumKnown(ps.map(p=>p.value.output_priced_tokens));
  text('output-value',money(outputValue));
  text('average-output',outputPriced ? money(outputValue*1000000/outputPriced) : 'Not priced');
  const measured=ps.reduce((n,p)=>n+p.input.measured_requests,0), fallback=ps.reduce((n,p)=>n+p.input.estimated_requests,0);
  const baseline=sumKnown(ps.map(p=>p.input.before)), savedTotal=sumKnown(ps.map(p=>p.input.saved));
  text('requests',`${baseline ? (100*savedTotal/baseline).toFixed(1)+'% reduction · ' : ''}${number(measured)} measured request identities`);
  text('coverage',measured+fallback ? `${(100*measured/(measured+fallback)).toFixed(1)}%` : 'No measurements');
  text('estimated',number(sumKnown(ps.map(p=>p.input.estimated_saved))));
  text('recoveries',number(sumKnown(ps.map(p=>p.usage?.recovery_reads))));
  const saved=sumKnown(ps.map(p=>p.input.saved)), priced=sumKnown(ps.map(p=>p.value.priced_saved_tokens));
  text('average-input',priced ? money(sumKnown(ps.map(p=>p.value.saved_api_equivalent_usd))*1000000/priced) : 'Not priced');
  const valueCoverage=saved ? `${(100*priced/saved).toFixed(1)}% of saved tokens priced` : 'No priced savings yet';
  text('value-caption',`${valueCoverage}${ps.some(p=>p.billing==='subscription') ? ' · not subscription cash savings' : ' · gross estimate'}`);
  const issues=ps.flatMap(p=>p.issues.map(i=>`${p.label}: ${i.replaceAll('_',' ')}`));
  if(ps.some(p=>p.usage?.unavailable_sessions>0)) issues.push('Some host usage was unavailable; recorded usage and costs are partial.');
  if(ps.some(p=>p.output.observed>0 && p.value.output_price_coverage_pct !== 100)) issues.push('Output valuation covers only priced, single-model sessions.');
  if(ps.some(p=>p.usage && p.value.actual_cost_coverage_pct<100)) issues.push('Recorded actual cost covers only sessions with available cost accounting.');
  byId('notice').hidden=!issues.length; text('notice',issues.join(' '));
  const body=byId('profiles'); body.replaceChildren();
  ps.forEach(p=>{ const tr=document.createElement('tr'), first=cell(tr,''); const button=document.createElement('button'); button.className='profile-button'; button.type='button'; const badge=document.createElement('span'); badge.className='profile-icon'; badge.textContent=p.label.slice(0,2).toUpperCase(); button.append(badge,document.createTextNode(p.label)); button.addEventListener('click',()=>{selected=p.id;render(state);}); first.append(button); cell(tr,number(p.input.saved),'saved'); cell(tr,number(p.input.prepared)); cell(tr,number(p.output.observed)); cell(tr,money(p.value.saved_api_equivalent_usd)); cell(tr,`${money(p.value.output_api_equivalent_usd)}${p.value.output_price_coverage_pct == null ? '' : ' · '+p.value.output_price_coverage_pct+'% priced'}`); const bill=cell(tr,''); const tag=document.createElement('span'); tag.className=`badge ${p.billing}`; tag.textContent=p.billing; bill.append(tag); body.append(tr); });
  text('profile-count',`${ps.length} PROFILE${ps.length===1?'':'S'}`);
  byId('profiles-empty').hidden=ps.some(p=>p.available);
  const models=byId('models'); models.replaceChildren();
  ps.forEach(p=>p.models.forEach(m=>{const tr=document.createElement('tr'); cell(tr,m.model||'Unknown model'); cell(tr,p.label); cell(tr,number(m.saved),'saved'); cell(tr,money(m.input_usd_per_million)); cell(tr,money(m.output_usd_per_million)); cell(tr,m.rate_as_of||'Not set'); models.append(tr);}));
  const definitions=byId('definitions'); definitions.replaceChildren(...data.notes.map(n=>{const p=document.createElement('p');p.textContent=n;return p;}));
  const days=new Map(); ps.forEach(p=>p.trend.forEach(r=>days.set(r.day,(days.get(r.day)||0)+r.saved)));
  const dayList=Array.from({length:14},(_,i)=>{const d=new Date();d.setUTCDate(d.getUTCDate()-13+i);return d.toISOString().slice(0,10);});
  const chart=byId('chart');chart.replaceChildren(); const max=Math.max(1,...dayList.map(d=>days.get(d)||0));
  if(days.size) dayList.forEach(d=>{const v=days.get(d)||0,wrap=document.createElement('div'),bar=document.createElement('div'),label=document.createElement('span');wrap.className='bar-wrap';bar.className='bar';bar.style.height=`${100*v/max}%`;wrap.title=`${d}: ${number(v)} input tokens saved`;label.textContent=d.slice(5);wrap.append(bar,label);chart.append(wrap);});
  chart.setAttribute('aria-label',days.size ? dayList.map(d=>`${d}: ${number(days.get(d)||0)}`).join('; ') : 'No measured daily savings yet');
  byId('chart-empty').hidden=days.size>0;
  text('version',`Token Terminator ${data.version} · Observatory`);
  text('updated',`Snapshot ${new Date(data.generated_at).toLocaleTimeString()}`);
}
async function refresh() {
  clearTimeout(timer);
  if(document.hidden) {timer=setTimeout(refresh,5000);return;}
  const seq=++sequence, controller=new AbortController(), timeout=setTimeout(()=>controller.abort(),8000);
  let delay=5000;
  try {const response=await fetch('/api/v1/summary',{signal:controller.signal,cache:'no-store',credentials:'same-origin'});if(!response.ok) throw new Error('unavailable'); const data=await response.json();if(seq!==sequence)return;render(data);text('status','Local · live');byId('dot').classList.add('live');}
  catch {delay=15000;text('status',state?'Offline · last snapshot':'Accounting unavailable');byId('dot').classList.remove('live');byId('notice').hidden=false;text('notice','Cannot refresh accounting. Previous numbers, if shown, are stale. No estimates have been substituted.');}
  finally {clearTimeout(timeout);if(seq===sequence)timer=setTimeout(refresh,delay);}
}
byId('profile').addEventListener('change',e=>{selected=e.target.value;if(state)render(state);});
refresh();
