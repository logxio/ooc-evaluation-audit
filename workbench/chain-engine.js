(function(root){
  'use strict';
  const E=typeof module!=='undefined'?require('./engine.js'):root.WorkbenchEngine;
  const S=typeof module!=='undefined'?require('./stats.js'):root.WorkbenchStats;
  function parse(text){
    const first=text.trim().split(/[\r\n]/)[0],seen=new Set();
    const rows=E.csv(text,first.includes('\t')?'\t':',');
    if(rows.length>10000)throw Error('Use up to 10,000 patient rows.');
    return rows.map((r,i)=>{
      if(!Object.hasOwn(r,'patient')||!Object.hasOwn(r,'readout1'))throw Error('Use patient,readout1, with optional readout2,baseline_readout,response.');
      if(Object.keys(r).some(k=>!['patient','readout1','readout2','baseline_readout','response'].includes(k)))throw Error('Accepted columns: patient,readout1,readout2,baseline_readout,response.');
      if(!r.patient||r.patient.length>100||seen.has(r.patient))throw Error(`Row ${i+2}: use a unique coded patient ID (up to 100 characters).`);
      seen.add(r.patient);
      const value=k=>{if(!r[k]?.trim())return null;const n=Number(r[k]);if(!Number.isFinite(n))throw Error(`Row ${i+2}: ${k} must be finite or empty.`);return n;};
      const a=value('readout1'),b=value('readout2'),base=value('baseline_readout'),y=value('response');
      if(a===null&&b===null)throw Error(`Row ${i+2}: supply a readout.`);
      if(y!==null&&y!==0&&y!==1)throw Error(`Row ${i+2}: response must be 0, 1 or empty.`);
      return {patient:r.patient,readout1:a,readout2:b,baseline_readout:base,response:y};
    });
  }
  function validate(p){
    if(p.schema!=='workbench.result.v1'||!['two_readout_v2','precomputed'].includes(p.rule?.kind))throw Error('Use a workbench.result.v1 packet.');
    const cert=p.rule.certificate,m=cert?.model;
    if(p.rule.kind==='two_readout_v2'&&(!m||m.cutoffs?.length!==2||m.reference?.length!==2||!m.cutoffs.every(Number.isFinite)||!m.reference.every(a=>a.length&&a.every(Number.isFinite))||!Number.isFinite(cert.margin)))throw Error('The result packet needs finite frozen cutoffs, references and release margin.');
    if(!p.baseline||!['readout1','readout2','baseline_readout'].includes(p.baseline.field)||!Number.isFinite(p.baseline.cutoff)||!['readout1','readout2'].includes(p.baseline.fallback_field)||!Number.isFinite(p.baseline.fallback_cutoff))throw Error('The result packet needs a fixed single-readout baseline and fallback.');
    if(!Number.isFinite(p.cost?.retest)||p.cost.retest<0)throw Error('The result packet needs a nonnegative retest cost.');
    parse(E.toCSV(p.rows,['patient','readout1','readout2','baseline_readout','response']));
    if(!Array.isArray(p.cases)||p.cases.length!==p.rows.length||p.cases.some((c,i)=>c.patient!==p.rows[i].patient||!['0','1','retest'].includes(c.action)||!['0','1','retest'].includes(c.baseline_action)||c.calls?.length!==2||c.calls.some(v=>v!==null&&v!==0&&v!==1)))throw Error('Supply one prediction and baseline action per input patient, in input order.');
    return p;
  }
  function predict(packet,rows){
    if(packet.rule.kind==='precomputed')throw Error('This packet contains CLI predictions. Run its method on your new table and open the resulting packet.');
    const cert=packet.rule.certificate;
    const baseline=rows.every(r=>r[packet.baseline.field]!==null)?
      {field:packet.baseline.field,cutoff:packet.baseline.cutoff,name:packet.baseline.name,selection:packet.baseline.selection}:
      {field:packet.baseline.fallback_field,cutoff:packet.baseline.fallback_cutoff,name:packet.baseline.fallback_name,selection:packet.baseline.fallback_selection};
    const cases=rows.map(r=>{
      if(r.readout1!==null&&r.readout2!==null){const a=E.predict(cert,[r])[0];return {...a,action:E.action(a),reason:a.released?'Calls agree beyond the frozen margin':a.agree?'Inside the retest margin':'Readouts disagree'};}
      return {patient:r.patient,calls:[r.readout1,r.readout2].map((v,j)=>v===null?null:Number(v<=cert.model.cutoffs[j])),agree:false,margin:null,released:false,prediction:null,action:'retest',reason:'A second readout is needed for agreement'};
    }).map((c,i)=>({...c,baseline_action:rows[i][baseline.field]===null?'retest':String(Number(rows[i][baseline.field]<=baseline.cutoff))}));
    return {cases,baseline};
  }
  function fromPacket(p){return {cases:p.cases.map(c=>({...c,released:c.action!=='retest',reason:c.reason||(c.action==='retest'?'Frozen rule requests retest':'Frozen rule releases this call')})),baseline:{field:p.baseline.field,cutoff:p.baseline.cutoff,name:p.baseline.name,selection:p.baseline.selection}};}
  function measure(rows,actions,revealed,cost){
    const total=E.metrics(rows,actions,null,cost);
    const pairs=rows.map((r,i)=>({r,a:actions[i]})).filter(x=>revealed&&x.r.response!==null);
    const known=pairs.map(x=>x.r),truth=Object.fromEntries(known.map(r=>[r.patient,r.response]));
    const observed=known.length?E.metrics(known,pairs.map(x=>x.a),truth,cost):null;
    return {...total,scored:known.length,scored_released:observed?.released??0,scored_retests:observed?.retests??0,
      wrong_released:observed?.wrong_released??null,overall_wrong_release:observed?.overall_wrong_release??null,
      released_error_rate:observed?.released_error_rate??null,loss:observed?.loss??null,total_cost:observed?.total_cost??null};
  }
  function summary(packet,rows,pred,revealed,cost=packet.cost.retest){
    const ours=measure(rows,pred.cases.map(c=>c.action),revealed,cost),baseline=measure(rows,pred.cases.map(c=>c.baseline_action),revealed,cost);
    const plans=revealed&&ours.scored_released?[.1,.2].map(a=>S.budget(ours.scored_released,ours.wrong_released,a)):[];
    return {ours,baseline,plans,conflicts:pred.cases.filter(c=>c.calls.every(v=>v!==null)&&c.calls[0]!==c.calls[1]).length,
      failures:revealed?pred.cases.filter((c,i)=>rows[i].response!==null&&c.action!=='retest'&&Number(c.action)!==rows[i].response).map(c=>c.patient):[],
      baseline_wins:revealed?pred.cases.filter((c,i)=>rows[i].response!==null&&c.baseline_action!=='retest'&&Number(c.baseline_action)===rows[i].response&&c.action!=='retest'&&Number(c.action)!==rows[i].response).map(c=>c.patient):[]};
  }
  const api={parse,validate,predict,fromPacket,measure,summary};if(typeof module!=='undefined')module.exports=api;root.ChainEngine=api;
})(typeof globalThis!=='undefined'?globalThis:this);
