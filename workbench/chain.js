(()=>{'use strict';const $=id=>document.getElementById(id),E=WorkbenchEngine,C=ChainEngine,start=performance.now(),root=document.documentElement;
let packet=C.validate(WORKBENCH_RESULT),rows=[],pred=null,revealed=false,source='own_data',events=[],result=null;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const log=(type,data={})=>events.push({type,elapsed_ms:Math.round(performance.now()-start),at:new Date().toISOString(),...data});
const pc=v=>(100*v).toFixed(2)+'%';
const call=v=>v===null?'Missing':Number(v)?'Sensitive':'Resistant';
const action=v=>v==='retest'?'Retest':'Report '+call(v).toLowerCase();
const fmt=v=>Number(v).toFixed(4);
// Secondary text lives in aria-description; each stylesheet shows it on hover or focus.
const tip=t=>t?` aria-description="${esc(t)}"`:'';
const wait='<span aria-description="Awaiting outcomes">—</span>';
const tone=v=>v===null?'none':Number(v)?'sens':'resi',act=a=>a==='retest'?'retest':tone(a);
function fail(e){$('error').hidden=false;$('error').textContent=e.message;log('input_error',{message:e.message});}
function save(name,body,type){const u=URL.createObjectURL(new Blob([body],{type})),a=document.createElement('a');a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);log('download',{file:name});}
function describe(){const m=packet.rule.certificate?.model,s=packet.study.split,src=$('source-note');
src.textContent=packet.study.title;src.setAttribute('aria-description',`${packet.study.status} · ${packet.version}`);
if(/^https?:\/\//.test(packet.study.url||''))src.href=packet.study.url;else src.removeAttribute('href');
$('example').textContent=`Load ${packet.rows.length} published patients`;
$('rule-note').textContent=packet.rule.description||`${packet.rule.name}: lower values mean sensitive. Frozen cutoffs: ${m?.cutoffs.join(' / ')||'See result packet'}; margin: ${packet.rule.certificate?.margin??'See result packet'}. ${s.training} training, ${s.calibration} calibration, ${s.test} held-out patients. Error among all patients and error among reported calls are separate quantities.`;
$('study-note').textContent=packet.study.input_note;
$('cost').value=packet.cost.retest;}
function render(){
  const cost=Number($('cost').value);if(!Number.isFinite(cost)||cost<0||!$('cost').value.trim())throw Error('Use a finite nonnegative retest cost.');
  result=C.summary(packet,rows,pred,revealed,cost);const m=result.ours,b=result.baseline,f=result.failures;
  $('results').hidden=false;root.dataset.stage=revealed?(root.dataset.stage==='done'?'done':'revealed'):'predicted';
  const split=pred.cases.filter(c=>c.calls.every(v=>v!==null)&&c.calls[0]!==c.calls[1]).map(c=>c.patient);
  $('counts').innerHTML=[['report','Report',m.released,'Predicted report actions'],['retest','Retest',m.retests,`Predicted retests · retest cost ${fmt(m.retest_cost)} at ${cost} each`],['split','Disagree',result.conflicts,'Readouts disagree: '+(split.join(', ')||'none')]].map(c=>`<div class="metric ${c[0]}"${tip(c[3])}><span>${c[1]}</span><strong>${c[2]}</strong></div>`).join('');
  const known=rows.some(r=>r.response!==null);
  $('reveal').disabled=revealed||!known;
  $('reveal').textContent=revealed?`${m.scored} outcomes revealed`:'Reveal outcomes';
  $('reveal').setAttribute('aria-description',revealed?`${rows.length-m.scored} outcomes pending. Predictions stay fixed; scores use patients with known outcomes.`:known?'Predictions are fixed. Reveal the saved clinical outcomes to score them.':'Add a patient,response CSV when clinical outcomes arrive.');
  const rate=(v,n)=>n?`${v}/${n}`:'—',best=b.loss!==null&&m.loss!==null&&b.loss!==m.loss?(m.loss<b.loss?0:1):-1;
  // Bar lengths for stylesheets that chart the two rules: each metric scaled to the larger of the pair.
  const bar=x=>' style="'+['overall_wrong_release','released_error_rate','loss','total_cost'].map((k,j)=>`--v${j}:${(x[k]??0)/(Math.max(m[k]??0,b[k]??0)||1)}`).join(';')+'"';
  const metric=(name,x,t,i)=>`<tr${i===best?' class="best"':''}${bar(x)}><th${tip(t)}>${esc(name)}</th><td>${x.released} / ${x.retests}</td><td>${x.scored?rate(x.wrong_released,x.scored)+' · '+pc(x.overall_wrong_release):wait}</td><td>${x.scored_released?rate(x.wrong_released,x.scored_released)+' · '+pc(x.released_error_rate):x.scored?'<span aria-description="No reported patients with outcomes">—</span>':wait}</td><td>${x.loss===null?wait:fmt(x.loss)}</td><td>${x.total_cost===null?wait:fmt(x.total_cost)}</td></tr>`;
  const base=`${pred.baseline.selection} Sensitive at or below ${pred.baseline.cutoff}.${pred.baseline.field==='baseline_readout'?' This comparator uses a measured combined-regimen assay; the two-readout rule uses separate irradiation and 5-FU assays.':''}`;
  $('comparison').innerHTML=`<table><thead><tr><th>Rule</th><th${tip('Predicted actions')}>Report / retest</th><th${tip('Wrong reported calls / all patients with outcomes')}>Wrong calls · all</th><th${tip('Wrong reported calls / reported patients with outcomes')}>Wrong calls · reported</th><th${tip('(Wrong reported calls + retest cost × retests) / patients with outcomes. One wrong call costs 1 unit; the retest cost is a planning assumption in the same units.')}>Cost / patient</th><th${tip('Wrong reported calls + retest cost × retests')}>Total cost</th></tr></thead><tbody>`+metric(packet.rule.name,m,'',0)+metric(pred.baseline.name,b,base,1)+'</tbody></table>';
  $('failure').hidden=!revealed;
  $('failure').textContent=revealed?(f.length?`${f.length} wrong reported call${f.length>1?'s':''}: ${f.join(', ')}. Baseline right on ${result.baseline_wins.length} of ${f.length}.`:'Zero wrong reported calls.')+(best<0?b.loss!==null&&m.loss!==null?' Observed cost ties.':'':` Lower cost: ${best?pred.baseline.name:packet.rule.name}.`):'';
  const ids=rows.map(r=>r.patient),pre=ids.reduce((p,s)=>{while(!s.startsWith(p))p=p.slice(0,-1);return p;},ids[0]||'').replace(/\d+$/,'');
  const id=s=>pre&&s.length>pre.length?`<span class="pre">${esc(pre)}</span>${esc(s.slice(pre.length))}`:esc(s);
  const sorted=pred.cases.map((c,i)=>({c,r:rows[i]}));
  const outcome=(a,y)=>!revealed||y===null?'':a==='retest'?'Retest':Number(a)===y?'Correct':'Wrong';
  const mark={'':'none',Retest:'retest',Correct:'ok',Wrong:'bad'};
  const res=o=>`<td class="${mark[o]}">${o||'—'}</td>`;
  $('patients').innerHTML=sorted.map(({c,r})=>{const o=outcome(c.action,r.response),y=revealed?r.response:null;
    return `<tr data-action="${act(c.action)}" data-result="${mark[o]}"${o==='Wrong'?` style="--i:${f.indexOf(c.patient)}"`:''}${tip(`${r.patient} · ${action(c.action)}${o?' · '+o.toLowerCase():''}`)}><td>${id(r.patient)}</td><td class="${tone(c.calls[0])}">${call(c.calls[0])}</td><td class="${tone(c.calls[1])}">${call(c.calls[1])}</td><td class="${act(c.action)}">${action(c.action)}</td><td class="${act(c.baseline_action)}">${action(c.baseline_action)}</td><td class="${tone(y)}">${y===null?'—':call(y)}</td>${res(o)}${res(outcome(c.baseline_action,r.response))}</tr>`;}).join('');
  const release=pred.cases.filter(c=>c.action!=='retest').map(c=>c.patient),retest=pred.cases.filter(c=>c.action==='retest').map(c=>c.patient);
  $('download').setAttribute('aria-description',`${release.length} to report, ${retest.length} to retest. One row per patient: calls, action, reason, baseline action and outcome.`+(revealed&&f.length?` Review the ${f.length} wrong reported calls before using the rule in a new study.`:''));
  $('release-label').textContent=`Report list · ${release.length}`;$('release-list').textContent=release.join(', ')||'Empty';
  $('retest-label').textContent=`Retest list · ${retest.length}`;$('retest-list').textContent=retest.join(', ')||'Empty';
  $('plans').innerHTML=result.plans.map(p=>`<a class="metric plan" href="sample.html"${tip(`${p.additional??'Over 10 million'} more reported validation patients with zero further wrong calls, ${p.total??'>10M'} in total. One-sided 95% exact binomial upper bound, now ${pc(p.upper)}. Open to change the target.`)}><span>≤${100*p.alpha}% wrong calls</span><strong>+${p.additional??'>10M'}</strong></a>`).join('');
}
function run(data,origin){rows=data;source=origin;pred=origin==='published_example'?C.fromPacket(packet):C.predict(packet,rows);revealed=false;$('error').hidden=true;log('predictions_fixed',{source,patients:rows.length,version:packet.version});render();}
function invalidate(){pred=null;result=null;revealed=false;$('results').hidden=true;root.dataset.stage='input';log('input_changed');}
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
$('download').onclick=()=>{if(!pred)return;save('patient-actions.csv',E.toCSV(pred.cases.map((c,i)=>({patient:c.patient,call1:c.calls[0],call2:c.calls[1],action:c.action,reason:c.reason,baseline_action:c.baseline_action,response:revealed?rows[i].response:null,wrong_release:revealed&&rows[i].response!==null&&c.action!=='retest'?Number(Number(c.action)!==rows[i].response):null})),['patient','call1','call2','action','reason','baseline_action','response','wrong_release']),'text/csv');if(revealed)root.dataset.stage='done';};
$('export').onclick=()=>{log('analysis_exported');save('patient-analysis.json',JSON.stringify({schema:'workbench.analysis.v1',record_type:'local_analysis',version:packet.version,source,model_sha256:packet.rule.certificate?.model.model_sha256??packet.rule.model_sha256,revealed,cost:Number($('cost').value),summary:result,events},null,2),'application/json');};
describe();log('page_open');})();
