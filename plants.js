/* ---------- Plant site rules (TAPPISAFE) ----------
   To be ready for a mill an employee needs
     1. TAPPISAFE Basic Orientation (any language) or Basic Refresher, passed and not expired
     2. that mill's orientation, passed and not expired
     3. that mill's PSM orientation too, when the mill has one ("Mill and PSM" courses cover 2 and 3 together).
   Green = all current. Yellow = all current but something expires within 30 days.
   Red = something missing, expired or failed.
   The dashboard script (index.html) uses window.PLANT; this file loads first. */
window.PLANT = (function(){
const SOON = 30;
const LIGHT = {
  green:{label:'Ready', c:'--s-current'},
  yellow:{label:'Ready, expires within 30 days', c:'--s-d30'},
  red:{label:'Not ready', c:'--s-expired'},
};
const RANK = {green:0, yellow:1, red:2};
const fmt = d => d ? d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '';

// "International Paper - Rome Mill and PSM Orientatio" -> {kind:'millpsm', mill:'International Paper - Rome'}
function classify(course){
  const name = String(course||'').replace(/\s*\([^)]*\)\s*$/,'').replace(/[–—]/g,'-').replace(/\s+/g,' ').trim();
  if(/^TAPPISAFE Basic (Refresher )?Orientation/i.test(name)) return {kind:'basic', name};
  if(/^TAPPISAFE|^COVID/i.test(name)) return null;
  const m = name.match(/^(.*?)\s*-\s*(.*)$/); if(!m) return null;
  const sm = m[2].match(/^(.*?)\s+(Mill\b|PSM\b|Escorted|Visitor|Security|Modified|Utilities)(.*)$/i);
  if(!sm) return null;
  const mill = m[1].trim()+' - '+sm[1].trim();
  const tail = (sm[2]+sm[3]).trim();
  const kind = /^Mill and P/i.test(tail) ? 'millpsm' : /^Mill\b/i.test(tail) ? 'mill' : /^PSM/i.test(tail) ? 'psm' : 'other';
  return {kind, mill, mk: mill.toLowerCase(), name};
}

// Best record: a pass with the latest expiration wins; a failure only counts when there is no pass.
function best(list){
  const pass = list.filter(r=>!/fail/i.test(r.src)).sort((a,b)=>(b.expire||0)-(a.expire||0) || (b.completed||0)-(a.completed||0));
  if(pass.length) return pass[0];
  return list.length ? list.slice().sort((a,b)=>(b.completed||0)-(a.completed||0))[0] : null;
}
function req(rec, label, today){
  if(!rec) return {s:'red', label, text:'Missing'};
  if(/fail/i.test(rec.src)) return {s:'red', label, text:'Failed '+fmt(rec.completed), rec};
  if(rec.expire && rec.expire < today) return {s:'red', label, text:'Expired '+fmt(rec.expire), rec};
  const d = rec.expire ? Math.round((rec.expire-today)/86400000) : null;
  if(d!=null && d <= SOON) return {s:'yellow', label, text:'Expires '+fmt(rec.expire)+' ('+d+' day'+(d===1?'':'s')+')', rec};
  return {s:'green', label, text: rec.expire ? 'Good to '+fmt(rec.expire) : 'Complete '+fmt(rec.completed), rec};
}
// recs: every record for one employee (each TAPPI record carries .plant from classify). mill: {mk, name, psm}
function readiness(recs, mill, today){
  const t = recs.filter(r=>r.plant), at = t.filter(r=>r.plant.mk===mill.mk);
  const reqs = [
    req(best(t.filter(r=>r.plant.kind==='basic')), 'TAPPISAFE Basic or Basic Refresher', today),
    req(best(at.filter(r=>r.plant.kind==='mill'||r.plant.kind==='millpsm')), mill.name+' orientation', today),
  ];
  if(mill.psm) reqs.push(req(best(at.filter(r=>r.plant.kind==='psm'||r.plant.kind==='millpsm')), mill.name+' PSM', today));
  const light = reqs.reduce((a,r)=>RANK[r.s]>RANK[a]?r.s:a,'green');
  return {light, reqs};
}
return {classify, readiness, LIGHT, RANK};
})();
