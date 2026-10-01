(() => {
  'use strict';
  const E=window.WorkbenchEngine, P=window.WORKBENCH_PACK, $=id=>document.getElementById(id);
  const origin=performance.now();
  const session={schema:'workbench.record.v1',session_id:crypto.randomUUID(),app_version:P.version,pack_sha256:P.pack_sha256,
    model_sha256:P.model_sha256,record_type:'exploration',participant:null,started_at:new Date().toISOString(),events:[],tasks:[]};
  let rows=[],truth=null,predictions=[],actions=[],locked=null,revealed=false,predicted=false,study=null,current=null,exported=false;
  const clone=x=>JSON.parse(JSON.stringify(x));
  const pct=v=>v===null?'NA':(v*100).toFixed(2)+'%';
  const label=a=>a==='retest'?'Retest':a==='1'?'Release: sensitive':a==='0'?'Release: resistant':'Choose action';
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function event(type,data={}){session.events.push({seq:session.events.length+1,type,at:new Date().toISOString(),elapsed_ms:Math.round(performance.now()-origin),task:current?.task||null,...data});exported=false;}
  function fail(error){$('error').textContent=error.message||String(error);$('error').hidden=false;event('error',{message:$('error').textContent});}
  function guard(fn){return async(...args)=>{try{$('error').hidden=true;await fn(...args);}catch(e){fail(e);}};}
  function cost(){return Number($('cost').value);}
  function checkCost(){if(!Number.isFinite(cost())||cost()<0||cost()>10)throw Error('Retest cost must be between 0 and 10 wrong-release units.');}
  function manual(){return current?.mode==='manual';}
  function csvInput(){return E.toCSV(rows,['patient','readout1','readout2']);}
  function cleanInputs(r){return r.map((v,i)=>({row:i+1,readout1:v.readout1,readout2:v.readout2}));}
  function load(r,y,task){rows=clone(r);truth=y?Object.fromEntries(y.map(v=>[v.patient,Number(v.response)])):null;predictions=E.predict(P.certificate,rows);actions=rows.map(()=> '');locked=null;revealed=false;predicted=false;
    $('csv-text').value=csvInput();$('workspace').hidden=false;$('finish-panel').hidden=true;
    for(const id of ['answer-overall','answer-conditional','answer-cost','answer-baseline'])$(id).value='';
    event('input_loaded',{example:task||null,rows:cleanInputs(rows),outcomes_available:!!truth});render();}
  function render(){
    document.body.classList.toggle('manual',manual());
    $('patient-table').querySelector('tbody').innerHTML=rows.map((r,i)=>{
      const a=predictions[i];const bad=revealed&&actions[i]!=='retest'&&Number(actions[i])!==truth[r.patient];
      return `<tr><td>${esc(r.patient)}</td><td>${r.readout1}</td><td>${r.readout2}</td><td class="prediction-cell">${predicted?label(E.action(a)):'—'}</td><td><select aria-label="Action for ${esc(r.patient)}" data-row="${i}" ${locked?'disabled':''}><option value="">Choose action</option>${['1','0','retest'].map(v=>`<option value="${v}" ${actions[i]===v?'selected':''}>${label(v)}</option>`).join('')}</select></td><td class="${bad?'error-cell':''}">${revealed?(truth[r.patient]?'Responder':'Non-responder'):'Hidden'}</td></tr>`;
    }).join('');
    $('patient-table').querySelectorAll('select').forEach(s=>s.addEventListener('change',()=>{const i=Number(s.dataset.row);event('action_change',{row:i+1,from:actions[i],to:s.value});actions[i]=s.value;renderMetrics();}));
    const trial=!!study;
    $('example-controls').hidden=trial;$('input-file').disabled=trial||!!locked;$('apply-input').disabled=trial||!!locked;$('csv-text').disabled=trial||!!locked;
    $('cost').disabled=trial||!!locked;$('outcome-upload').hidden=trial||!!locked;
    $('predict').hidden=manual();$('predict').disabled=!!locked;
    $('reveal').disabled=!!locked;$('download-outcomes').hidden=!revealed;
    $('mode-help').textContent=manual()?'Manual task: apply the printed frozen rule with your usual worksheet. Choose an action for every patient.':'Run the frozen rule, review each recommendation, and keep or change the patient actions.';
    $('fill-answers').hidden=manual();
    $('rule').open=manual();
    renderMetrics();
  }
  function renderMetrics(){
    const n=rows.length,chosen=actions.filter(Boolean).length,released=actions.filter(v=>v==='0'||v==='1').length,retests=actions.filter(v=>v==='retest').length;
    $('action-count').textContent=manual()?`${n} patients`:`${chosen}/${n} chosen · ${released} release · ${retests} retest`;
    let cards;
    if(manual())cards=[['Your worksheet','Manual','Count releases and retests'],['Wrong / all','Calculate','Reveal outcomes after locking actions'],['Wrong / released','Calculate','Use the released denominator'],['Cost / patient','Calculate','(wrong + cost × retests) / all']];
    else{
      const m=chosen===n?E.metrics(rows,actions,revealed?truth:null,cost()):null;
      cards=[['Release / retest',`${released} / ${retests}`,`${chosen} of ${n} actions selected`],['Wrong / all',revealed&&m?`${m.wrong_released}/${n} · ${pct(m.overall_wrong_release)}`:'Awaiting outcomes','Denominator: every patient'],['Wrong / released',revealed&&m?`${m.wrong_released}/${m.released} · ${pct(m.released_error_rate)}`:'Awaiting outcomes','Denominator: released patients'],['Cost / patient',revealed&&m?m.loss.toFixed(4):'Awaiting outcomes',`${(cost()*retests).toFixed(2)} retest-cost units${revealed&&m?`; total ${m.total_cost.toFixed(2)}`:''}`]];
    }
    $('metrics').innerHTML=cards.map(c=>`<div class="metric"><span>${c[0]}</span><strong>${c[1]}</strong><small>${c[2]}</small></div>`).join('');
    $('result-status').textContent=revealed?'Actions locked · outcomes revealed':'Outcomes are hidden';
    $('baseline-intro').textContent=`Readout 2 is the frozen strongest active baseline on calibration (${P.baseline.calibration_errors.readout2}/${P.baseline.calibration_n} errors). All five baselines use the same input and cost. The lowest observed cost after reveal is descriptive.`;
    let bases=Object.keys(E.names).map(key=>({key,name:E.names[key]}));
    if(revealed&&!manual())bases=E.compare(rows,predictions,truth,cost());
    $('baseline-table').querySelector('tbody').innerHTML=bases.map(b=>`<tr class="${revealed&&!manual()&&b.loss===bases[0].loss?'baseline-best':''}"><td>${esc(b.name)}</td><td>${revealed&&!manual()?`${b.released} / ${b.retests}`:'—'}</td><td>${revealed&&!manual()?`${b.wrong_released}/${b.patients} · ${pct(b.overall_wrong_release)}`:'—'}</td><td>${revealed&&!manual()?`${b.wrong_released}/${b.released} · ${pct(b.released_error_rate)}`:'—'}</td><td>${revealed&&!manual()?b.loss.toFixed(4):'—'}</td></tr>`).join('');
    if(revealed&&!manual()){
      const m=E.metrics(rows,actions,truth,cost()); const best=bases[0];
      const relation=m.loss>best.loss+1e-10?'A baseline wins':m.loss<best.loss-1e-10?'Your actions have lower cost':'Your actions tie the best baseline';
      $('winner').textContent=`${relation}: your cost ${m.loss.toFixed(4)}, ${best.name.toLowerCase()} ${best.loss.toFixed(4)} per patient.`;
    }else $('winner').textContent=manual()?'Use the manual worksheet to score each baseline after reveal.':'Reveal outcomes to compare the frozen rule, your final actions and all five baselines.';
  }
  function download(name,content,type){const url=URL.createObjectURL(new Blob([content],{type}));const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
  function exportRecord(){event('record_export',{completed_tasks:session.tasks.length});const output={...session,exported_at:new Date().toISOString(),complete:!!study&&session.tasks.length===6};download(`workbench-${session.record_type}-${session.participant||'explore'}-${session.session_id.slice(0,8)}.json`,JSON.stringify(output,null,2),'application/json');exported=true;$('export-status').textContent=`Record exported: ${session.tasks.length} completed tasks. Send this JSON file to your facilitator.`;}
  function elapsed(){if(!current?.started)return 0;return performance.now()-current.started-current.pausedMs-(current.pauseStart?performance.now()-current.pauseStart:0);}
  function timer(){const s=Math.floor(elapsed()/1000);$('timer').textContent=`${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;}
  function nextTask(){
    if(study.step===6){$('workspace').hidden=true;$('study-bar').hidden=true;$('completion').hidden=false;$('completion-summary').textContent=`${session.tasks.length} tasks saved in this tab. Record type: ${session.record_type}.`;event('study_complete');current=null;return;}
    const step=study.steps[study.step];current={...step,started:null,pausedMs:0,pauseStart:null};
    $('task-status').textContent=`Task ${study.step+1} of 6 · ${step.mode==='manual'?'Manual worksheet':'Tool-assisted'} · ${step.task}`;
    $('task-instruction').textContent='Choose actions, lock them, reveal outcomes, then submit both risk denominators, cost and the best baseline.';
    $('workspace').hidden=true;$('start-task').hidden=false;$('pause').hidden=true;$('timer').textContent='0:00';
  }
  function startTask(){current.started=performance.now();current.startedAt=new Date().toISOString();current.startEvent=session.events.length+1;
    event('task_start',{mode:current.mode,pair:current.pair,position:study.step+1});
    const t=P.tasks.find(t=>t.id===current.task);load(t.rows,t.outcomes,t.id);$('start-task').hidden=true;$('pause').hidden=false;$('pause').textContent='Pause';$('cost').value='.25';render();}
  function numeric(id,allowNA=false){const raw=$(id).value.trim();if(allowNA&&/^na$/i.test(raw))return null;if(!raw||!Number.isFinite(Number(raw)))throw Error('Complete each result field with a number, or NA for an undefined released error rate.');return Number(raw);}
  function finishTask(){
    if(!current?.started||!revealed)throw Error('Start the task, lock actions and reveal outcomes first.');
    if(current.pauseStart)throw Error('Resume the timer before finishing.');
    const answers={overall_percent:numeric('answer-overall'),conditional_percent:numeric('answer-conditional',true),loss:numeric('answer-cost'),best_baseline:$('answer-baseline').value};
    if(!Object.hasOwn(E.names,answers.best_baseline))throw Error('Choose the lowest-cost baseline.');
    const active=elapsed(),wall=performance.now()-current.started;
    event('task_end',{mode:current.mode,active_ms:Math.round(active),wall_ms:Math.round(wall),answers});
    session.tasks.push({task:current.task,pair:current.pair,mode:current.mode,position:study.step+1,started_at:current.startedAt,ended_at:new Date().toISOString(),active_ms:Math.round(active),wall_ms:Math.round(wall),paused_ms:Math.round(current.pausedMs),actions:clone(locked.actions),cost:locked.cost,answers,start_event:current.startEvent,end_event:session.events.length,model_sha256:P.model_sha256});
    study.step++;nextTask();}
  for(const t of P.tasks){$('example').add(new Option(`${t.id} · ${t.rows.length} patients`,t.id));}
  for(const [k,name]of Object.entries(E.names))$('answer-baseline').add(new Option(name,k));
  $('rule-body').innerHTML=`<p>1. Call readout 1 sensitive at or below <strong>${P.certificate.model.cutoffs[0]}</strong>; call readout 2 sensitive at or below <strong>${P.certificate.model.cutoffs[1]}</strong>. Values above a cutoff call resistant.</p><p>2. Release the shared call when the two calls agree. Retest when they disagree. This frozen certificate uses margin −1, so every agreement passes its margin.</p><p>3. After reveal, count wrong released calls. Divide by all patients and then by released patients. Cost = wrong releases + ${cost()} × retests; divide by all patients for cost per patient. A retest costs the chosen fraction of one wrong release.</p><p>Baselines release everyone according to readout 1, readout 2, both-sensitive (AND) or either-sensitive (OR); the fifth baseline retests everyone. Score them on the same outcomes.</p>`;
  $('provenance').textContent=`Pack ${P.version}. Frozen model SHA-256: ${P.model_sha256}. Core source SHA-256: ${P.core_sha256}. Training/calibration/test: 42/42/43 patients. The 36 task patients are disjoint from training and calibration; the tasks were curated using known outcomes. Eligible input uses the same assay, endpoints and units. Other assays need their own fitted certificate.`;
  $('load-example').onclick=guard(()=>{if(locked)event('review_reset');const t=P.tasks.find(t=>t.id===$('example').value);load(t.rows,t.outcomes,t.id);});
  $('example').onchange=()=>event('example_change',{value:$('example').value});
  $('csv-text').oninput=()=>event('csv_edit',{characters:$('csv-text').value.length});
  $('apply-input').onclick=guard(()=>{checkCost();load(E.inputs($('csv-text').value),null,null);});
  $('input-file').onchange=guard(async()=>{const f=$('input-file').files[0];if(!f)return;if(f.size>4*1024*1024)throw Error('Use an input CSV smaller than 4 MB.');load(E.inputs(await f.text()),null,null);event('input_file_opened',{bytes:f.size});$('input-file').value='';});
  $('outcome-file').onchange=guard(async()=>{const f=$('outcome-file').files[0];if(!f)return;if(f.size>4*1024*1024)throw Error('Use an outcome CSV smaller than 4 MB.');truth=E.outcomes(await f.text(),rows);event('outcomes_loaded',{patients:Object.keys(truth).length});$('export-status').textContent='Outcomes loaded. Lock actions to reveal them.';$('outcome-file').value='';});
  $('cost').oninput=guard(()=>{checkCost();event('cost_change',{value:cost()});renderMetrics();});
  $('predict').onclick=guard(()=>{checkCost();const old=clone(actions);actions=predictions.map(E.action);predicted=true;event('prediction_run',{model_sha256:P.model_sha256});actions.forEach((a,i)=>event('action_change',{row:i+1,from:old[i],to:a,source:'frozen_rule'}));render();});
  $('reveal').onclick=guard(()=>{checkCost();E.metrics(rows,actions,null,cost());if(!truth)throw Error('Load a matching outcome CSV before revealing outcomes.');locked={actions:clone(actions),cost:cost(),at:new Date().toISOString()};event('actions_locked',{actions:clone(actions),cost:cost()});revealed=true;event('outcomes_revealed');render();$('finish-panel').hidden=!study;});
  $('download-input').onclick=()=>{event('input_export');download('patient-input.csv',csvInput(),'text/csv');};
  $('download-outcomes').onclick=()=>{event('revealed_worksheet_export');download('revealed-worksheet.csv',E.toCSV(rows.map(r=>({...r,response:truth[r.patient]})),['patient','readout1','readout2','response']),'text/csv');};
  $('download-actions').onclick=guard(()=>{E.metrics(rows,actions,null,cost());event('actions_export');download('patient-actions.csv',E.toCSV(rows.map((r,i)=>({patient:r.patient,action:label(actions[i]),model_sha256:P.model_sha256})),['patient','action','model_sha256']),'text/csv');});
  $('explore-tab').onclick=guard(()=>{if(study)throw Error('Complete and export this study before starting a fresh exploration tab.');$('setup').hidden=true;$('workspace').hidden=false;$('explore-tab').setAttribute('aria-selected','true');$('study-tab').setAttribute('aria-selected','false');event('view_change',{view:'explore'});});
  $('study-tab').onclick=()=>{if(!study){$('setup').hidden=false;$('workspace').hidden=true;} $('study-tab').setAttribute('aria-selected','true');$('explore-tab').setAttribute('aria-selected','false');event('view_change',{view:'study'});};
  for(const id of ['participant','record-type','workflow'])$(id).onchange=()=>event('setup_change',{field:id,value:$(id).value});
  $('begin-study').onclick=guard(()=>{const s=P.schedule.find(s=>s.participant===$('participant').value);session.participant=s.participant;session.record_type=$('record-type').value;session.usual_workflow=$('workflow').value;session.schedule=clone(s.steps);study={step:0,steps:s.steps};event('study_start',{participant:session.participant,record_type:session.record_type});$('setup').hidden=true;$('study-bar').hidden=false;nextTask();});
  $('start-task').onclick=guard(startTask);
  $('pause').onclick=()=>{if(!current.pauseStart){current.pauseStart=performance.now();event('task_pause');document.body.classList.add('paused');$('pause').textContent='Resume';}else{current.pausedMs+=performance.now()-current.pauseStart;current.pauseStart=null;event('task_resume');document.body.classList.remove('paused');$('pause').textContent='Pause';}};
  for(const id of ['answer-overall','answer-conditional','answer-cost','answer-baseline'])$(id).addEventListener('input',()=>event('answer_change',{field:id,value:$(id).value}));
  $('fill-answers').onclick=()=>{const m=E.metrics(rows,locked.actions,truth,locked.cost);const b=E.compare(rows,predictions,truth,locked.cost)[0];const vals={'answer-overall':(100*m.overall_wrong_release).toFixed(2),'answer-conditional':m.released_error_rate===null?'NA':(100*m.released_error_rate).toFixed(2),'answer-cost':m.loss.toFixed(4),'answer-baseline':b.key};for(const [id,v]of Object.entries(vals)){$(id).value=v;event('answer_change',{field:id,value:v,source:'calculated_results'});}};
  $('finish-task').onclick=guard(finishTask);
  $('export').onclick=exportRecord;$('export-complete').onclick=exportRecord;
  document.addEventListener('visibilitychange',()=>event('visibility_change',{state:document.visibilityState}));
  window.addEventListener('beforeunload',e=>{if(!exported&&session.tasks.length){e.preventDefault();e.returnValue='';}});
  setInterval(timer,250);
  event('page_open');load(P.tasks[0].rows,P.tasks[0].outcomes,'T1');
})();
