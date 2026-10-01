(()=>{'use strict';const $=id=>document.getElementById(id),E=WorkbenchEngine,C=ChainEngine,start=performance.now();
let packet=C.validate(WORKBENCH_RESULT),rows=[],pred=null,revealed=false,source='own_data',events=[],result=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const log=(type,data={})=>events.push({type,elapsed_ms:Math.round(performance.now()-start),at:new Date().toISOString(),...data});
const pc=v=>v===null?'Awaiting outcomes':(100*v).toFixed(2)+'%';
const call=v=>v===null?'Missing':Number(v)?'Sensitive':'Resistant';
const action=v=>v==='retest'?'Retest':'Report '+call(v).toLowerCase();
const fmt=v=>Number(v).toFixed(4);
function fail(e){$('error').hidden=false;$('error').textContent=e.message;log('input_error',{message:e.message});}
function save(name,body,type){const u=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);log('download',{file:name});}
function describe(){const m=packet.rule.certificate?.model,s=packet.study.split;
$('source-note').textContent=`${packet.study.title}. ${packet.study.status}`;
$('rule-note').textContent=packet.rule.description||`${packet.rule.name}: lower values mean sensitive. Frozen cutoffs: ${m?.cutoffs.join(' / ')||'See result packet'}; release margin: ${packet.rule.certificate?.margin??'See result packet'}. ${s.training} training, ${s.calibration} calibration, ${s.test} held-out patients. Overall-risk calibration and observed error among releases are separate quantities.`;
$('study-note').textContent=packet.study.input_note;
$('cost').value=packet.cost.retest;}
function render(){
  const cost=Number($('cost').value);if(!Number.isFinite(cost)||cost<0||!$('cost').value.trim())throw Error('Use a finite nonnegative retest cost.');
  result=C.summary(packet,rows,pred,revealed,cost);const m=result.ours,b=result.baseline;
  $('results').hidden=false;$('prediction-status').textContent=`${rows.length} input patients · ${packet.version}`;
  $('counts').innerHTML=[['Report candidates',m.released,'predicted actions'],['Retest',m.retests,'predicted actions'],['Readouts disagree',result.conflicts,'predicted call conflicts'],['Retest cost',fmt(m.retest_cost),'calculated from assumed cost']].map(c=>`<div class="metric"><span>${c[0]}</span><strong>${c[1]}</strong><small>${c[2]}</small></div>`).join('');
  $('reveal').disabled=revealed||!rows.some(r=>r.response!==null);
  $('reveal').textContent=revealed?'Outcomes revealed':'Reveal outcomes';
  $('truth-heading').textContent=revealed?`${m.scored} measured outcomes revealed`:'Reveal clinical outcomes';
  $('truth-note').textContent=revealed?`${rows.length-m.scored} outcomes pending. Predictions remain fixed; scores use only patients with known outcomes.`:rows.some(r=>r.response!==null)?'Predictions are fixed. Reveal the saved clinical outcomes to score them.':'Add a patient,response CSV when clinical outcomes arrive.';
  const rate=(v,n)=>n?`${v}/${n}`:'—';
  const metric=(name,x)=>`<tr><th>${esc(name)}</th><td>${x.released} / ${x.retests}</td><td>${x.scored?rate(x.wrong_released,x.scored)+' · '+pc(x.overall_wrong_release):'Awaiting outcomes'}</td><td>${x.scored_released?rate(x.wrong_released,x.scored_released)+' · '+pc(x.released_error_rate):x.scored?'Undefined: zero labelled releases':'Awaiting outcomes'}</td><td>${x.loss===null?'Awaiting outcomes':fmt(x.loss)}</td><td>${x.total_cost===null?'Awaiting outcomes':fmt(x.total_cost)}</td></tr>`;
  $('comparison').innerHTML='<table><thead><tr><th>Rule</th><th>Report / retest<br>predicted</th><th>Wrong / all labelled<br>observed</th><th>Wrong / labelled released<br>observed</th><th>Loss / labelled patient<br>observed + assumed cost</th><th>Total labelled loss</th></tr></thead><tbody>'+metric(packet.rule.name,m)+metric(pred.baseline.name,b)+'</tbody></table>';
  $('baseline-note').textContent=`${pred.baseline.selection} Sensitive at or below ${pred.baseline.cutoff}. ${pred.baseline.field==='baseline_readout'?'This comparator uses a measured combined-regimen assay; the two-readout rule uses separate irradiation and 5-FU assays.':''}`;
  $('failure').hidden=!revealed;
  $('failure').textContent=revealed?(result.failures.length?`Our wrong releases: ${result.failures.join(', ')}. Baseline correct on ${result.baseline_wins.length} of these: ${result.baseline_wins.join(', ')||'none'}.`:'Our labelled releases have zero observed errors in this batch.')+(b.loss!==null&&m.loss!==null?` Observed loss: ${b.loss<m.loss?'the fixed single-readout baseline is lower':b.loss===m.loss?'both rules tie':'the two-readout rule is lower'}.`:''):'';
  const sorted=pred.cases.map((c,i)=>({c,r:rows[i]})).sort((a,b)=>Number(result.failures.includes(b.c.patient))-Number(result.failures.includes(a.c.patient)));
  const outcome=(a,y)=>!revealed||y===null?'Awaiting outcome':a==='retest'?'Retest':Number(a)===y?'Correct':'Wrong';
  $('patients').innerHTML=sorted.map(({c,r})=>`<tr><td>${esc(r.patient)}</td><td>${call(c.calls[0])}</td><td>${call(c.calls[1])}</td><td title="${esc(c.reason)}">${action(c.action)}</td><td>${action(c.baseline_action)}</td><td>${revealed&&r.response!==null?call(r.response):'Hidden / pending'}</td><td class="${outcome(c.action,r.response)==='Wrong'?'error-cell':''}">${outcome(c.action,r.response)}</td><td class="${outcome(c.baseline_action,r.response)==='Wrong'?'error-cell':''}">${outcome(c.baseline_action,r.response)}</td></tr>`).join('');
  const release=pred.cases.filter(c=>c.action!=='retest').map(c=>c.patient),retest=pred.cases.filter(c=>c.action==='retest').map(c=>c.patient);
  $('next-action').textContent=`${release.length} patient results can enter the research report under this frozen rule; ${retest.length} go to repeat measurement or assay review.`+(revealed&&result.failures.length?` Review the ${result.failures.length} observed wrong releases before deploying the rule in a new study.`:'');
  $('release-label').textContent=`Report list · ${release.length}`;$('release-list').textContent=release.join(', ')||'Empty';
  $('retest-label').textContent=`Retest list · ${retest.length}`;$('retest-list').textContent=retest.join(', ')||'Empty';
  $('conflicts').textContent='Discordant readouts: '+(pred.cases.filter(c=>c.calls.every(v=>v!==null)&&c.calls[0]!==c.calls[1]).map(c=>c.patient).join(', ')||'none');
  $('plans').innerHTML=result.plans.length?result.plans.map(p=>`<div class="metric"><span>${100*p.alpha}% released-error target · planning</span><strong>+${p.additional??'>10M'}</strong><small>released patients with zero further errors<br>${p.total??'>10M'} total; current 95% upper bound ${pc(p.upper)}</small></div>`).join(''):'Reveal outcomes for labelled releases to calculate the validation sample needed.';
}
function run(data,origin){rows=data;source=origin;pred=origin==='published_example'?C.fromPacket(packet):C.predict(packet,rows);revealed=false;$('error').hidden=true;log('predictions_fixed',{source,patients:rows.length,version:packet.version});render();}
function invalidate(){pred=null;result=null;revealed=false;$('results').hidden=true;log('input_changed');}
$('example').onclick=()=>{try{$('input').value=E.toCSV(packet.rows,['patient','readout1','readout2','baseline_readout']);$('input-details').open=false;run(C.parse(E.toCSV(packet.rows,['patient','readout1','readout2','baseline_readout','response'])),'published_example');}catch(e){fail(e);}};
$('predict').onclick=()=>{try{run(C.parse($('input').value),'own_data');}catch(e){fail(e);}};
$('input').oninput=invalidate;
$('reveal').onclick=()=>{if(!pred)return;revealed=true;log('outcomes_revealed',{labelled:rows.filter(r=>r.response!==null).length});render();};
$('cost').oninput=()=>{if(!pred)return;try{$('error').hidden=true;render();log('cost_changed',{value:Number($('cost').value)});}catch(e){fail(e);}};
async function read(f){if(!f)throw Error('Choose a file.');if(f.size>4*1024*1024)throw Error('Use a file smaller than 4 MB.');return f.text();}
async function csvFile(f){invalidate();const text=await read(f);$('input').value=text;$('input-details').open=true;run(C.parse(text),'own_data');}
$('csv-file').onchange=()=>csvFile($('csv-file').files[0]).catch(fail);
$('drop-zone').ondragover=e=>e.preventDefault();$('drop-zone').ondrop=e=>{e.preventDefault();csvFile(e.dataTransfer.files[0]).catch(fail);};
$('packet-file').onchange=async()=>{try{const next=C.validate(JSON.parse(await read($('packet-file').files[0])));packet=next;invalidate();describe();$('example').click();log('packet_loaded',{version:packet.version});}catch(e){fail(e);}};
$('outcome-file').onchange=async()=>{try{if(!pred)throw Error('Predict patient actions first.');const data=E.csv(await read($('outcome-file').files[0])),seen=new Set(),map=new Map(rows.map(r=>[r.patient,r]));for(const r of data){if(Object.keys(r).sort().join(',')!=='patient,response'||!['0','1'].includes(r.response)||!map.has(r.patient)||seen.has(r.patient))throw Error('Use unique matching patient IDs and response 0 or 1. A subset of patient outcomes is accepted.');seen.add(r.patient);}for(const r of data)map.get(r.patient).response=Number(r.response);revealed=false;log('outcomes_loaded',{count:data.length});render();}catch(e){fail(e);}};
$('download').onclick=()=>{if(!pred)return;save('patient-actions.csv',E.toCSV(pred.cases.map((c,i)=>({patient:c.patient,call1:c.calls[0],call2:c.calls[1],action:c.action,reason:c.reason,baseline_action:c.baseline_action,response:revealed?rows[i].response:null,wrong_release:revealed&&rows[i].response!==null&&c.action!=='retest'?Number(Number(c.action)!==rows[i].response):null})),['patient','call1','call2','action','reason','baseline_action','response','wrong_release']),'text/csv');};
$('export').onclick=()=>{log('analysis_exported');save('patient-analysis.json',JSON.stringify({schema:'workbench.analysis.v1',record_type:'local_analysis',version:packet.version,source,model_sha256:packet.rule.certificate?.model.model_sha256??packet.rule.model_sha256,revealed,cost:Number($('cost').value),summary:result,events},null,2),'application/json');};
describe();log('page_open');})();
