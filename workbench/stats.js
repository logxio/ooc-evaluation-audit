(function(root){
  'use strict';
  function cdf(e,n,p){
    if(e===n||p===0)return 1;if(p===1)return 0;
    let term=n*Math.log1p(-p),largest=term,sum=1;
    for(let k=1;k<=e;k++){term+=Math.log((n-k+1)/k)+Math.log(p)-Math.log1p(-p);if(term>largest){sum=sum*Math.exp(largest-term)+1;largest=term;}else sum+=Math.exp(term-largest);}
    return Math.min(1,Math.exp(largest)*sum);
  }
  function upper(e,n,eta=.05){
    if(!Number.isInteger(n)||!Number.isInteger(e)||e<0||n<e||!(eta>0&&eta<1))throw Error('Use integer counts with 0 ≤ errors ≤ patients.');
    if(n===0||e===n)return 1;if(e===0)return -Math.expm1(Math.log(eta)/n);
    let lo=0,hi=1;for(let i=0;i<64;i++){const m=(lo+hi)/2;if(cdf(e,n,m)>eta)lo=m;else hi=m;}return hi;
  }
  function interval(success,n){return n?{low:success===0?0:1-upper(n-success,n,.025),high:success===n?1:upper(success,n,.025)}:null;}
  function budget(n,e,alpha){
    if(!(alpha>0&&alpha<1)||n>100000||e>10000)throw Error('Use a target between 0 and 1, up to 100,000 pilot cases and 10,000 errors.');
    const current=upper(e,n);
    if(n&&current<=alpha)return {n,e,alpha,upper:current,total:n,additional:0,assumption:'No further errors; independent released validation patients for a rule fixed in advance.'};
    let lo=Math.max(n,e),hi=Math.max(lo+1,Math.ceil(Math.log(.05)/Math.log1p(-alpha)));
    while(cdf(e,hi,alpha)>.05){hi*=2;if(hi>10000000)return {n,e,alpha,upper:current,total:null,additional:null,assumption:'Required total exceeds 10 million in this planning calculation.'};}
    while(hi-lo>1){const m=Math.floor((lo+hi)/2);if(cdf(e,m,alpha)<=.05)hi=m;else lo=m;}
    return {n,e,alpha,upper:current,total:hi,additional:hi-n,assumption:'No further errors; independent released validation patients for a rule fixed in advance.'};
  }
  function threshold(scores,truth){
    const ordered=scores.map((v,i)=>[v,truth[i]]).sort((a,b)=>a[0]-b[0]);const pos=truth.reduce((a,b)=>a+b,0),neg=truth.length-pos;
    if(!pos||!neg)throw Error('Threshold fitting needs both clinical outcome classes.');
    let tp=0,tn=neg,best=.5,cut=ordered[0][0]-1;
    for(let i=0;i<ordered.length;){const value=ordered[i][0];while(i<ordered.length&&ordered[i][0]===value){if(ordered[i][1])tp++;else tn--;i++;}const c=i<ordered.length?(value+ordered[i][0])/2:value+1;const ba=(tp/pos+tn/neg)/2;if(ba>best){best=ba;cut=c;}}
    return cut;
  }
  function median(v){const s=[...v].sort((a,b)=>a-b);return s.length%2?s[(s.length-1)/2]:(s[s.length/2-1]+s[s.length/2])/2;}
  function analyse(rows,higher=false){
    const sign=higher?-1:1;const paired=rows.some(r=>r.readout2!==null);const channels=paired?2:1;
    const models=[];
    for(let j=0;j<channels;j++){
      const key='readout'+(j+1),lab=rows.filter(r=>r[key]!==null&&r.response!==null);
      const positives=lab.filter(r=>r.response===1).length,negatives=lab.length-positives;
      const loo=positives>=2&&negatives>=2;
      const full=loo?threshold(lab.map(r=>sign*r[key]),lab.map(r=>r.response)):median(rows.filter(r=>r[key]!==null).map(r=>sign*r[key]));
      const calls=rows.map(r=>{if(r[key]===null)return null;const train=lab.filter(x=>x!==r);const cut=loo&&r.response!==null?threshold(train.map(x=>sign*x[key]),train.map(x=>x.response)):full;return {call:Number(sign*r[key]<=cut),cutoff:sign*cut};});
      const known=rows.map((r,i)=>({r,c:calls[i]})).filter(x=>x.r.response!==null&&x.c);const correct=known.filter(x=>x.r.response===x.c.call).length;
      models.push({key,loo,full_cutoff:sign*full,calls,n:known.length,correct,interval:interval(correct,known.length)});
    }
    const actions=rows.map((r,i)=>{
      const c=models.map(m=>m.calls[i]);const complete=c.length===2&&c.every(Boolean);const conflict=complete&&c[0].call!==c[1].call;
      return {patient:r.patient,call1:c[0]?.call??null,call2:c[1]?.call??null,cutoff1:c[0]?.cutoff??null,cutoff2:c[1]?.cutoff??null,
        action:complete&&!conflict?String(c[0].call):'retest',reason:conflict?'Readouts disagree':!complete?'Single or missing readout':'Two calls agree',response:r.response};
    });
    const labelled=actions.filter(a=>a.response!==null),accepted=labelled.filter(a=>a.action!=='retest'),wrong=accepted.filter(a=>Number(a.action)!==a.response).length;
    const agreementCorrect=accepted.length-wrong;
    return {rows:actions,models,patients:rows.length,paired,conflicts:actions.filter(a=>a.reason==='Readouts disagree').length,
      releases:actions.filter(a=>a.action!=='retest').length,scored:labelled.length,scored_released:accepted.length,wrong,
      agreement_correct:agreementCorrect,agreement_interval:interval(agreementCorrect,accepted.length),
      overall:labelled.length?wrong/labelled.length:null,conditional:accepted.length?wrong/accepted.length:null,
      targets:accepted.length?[.1,.2].map(a=>budget(accepted.length,wrong,a)):[],
      approach:models.every(m=>m.loo)?'Leave-one-patient-out':'Cohort-median exploration for channels with insufficient labelled cases'};
  }
  const api={cdf,upper,interval,budget,threshold,analyse};if(typeof module!=='undefined')module.exports=api;root.WorkbenchStats=api;
})(typeof globalThis!=='undefined'?globalThis:this);
