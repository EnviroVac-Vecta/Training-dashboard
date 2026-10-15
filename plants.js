/* ---------- Plant Sites: TAPPISAFE readiness per mill ----------
   Rule: to be ready for a mill an employee needs
     1. TAPPISAFE Basic Orientation (any language) or Basic Refresher, passed and not expired
     2. that mill's orientation, passed and not expired
     3. that mill's PSM orientation too, when the mill has one ("Mill and PSM" courses cover 2 and 3 together).
   Green = all current. Yellow = all current but something expires within 30 days.
   Red = something missing, expired or failed. */
(function(){
const $ = id => document.getElementById(id);
const esc = s => String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SOON = 30;
const LIGHT = {
  green:{label:'Ready', c:'--s-current'},
  yellow:{label:'Ready, expires within 30 days', c:'--s-d30'},
  red:{label:'Not ready', c:'--s-expired'},
};
const RANK = {green:0, yellow:1, red:2};
const today = new Date(); today.setHours(0,0,0,0);
const toDate = v => { if(!v) return null; const m=String(v).match(/^(\d{4})-(\d{2})-(\d{2})/); if(m) return new Date(+m[1],m[2]-1,+m[3]);
  const u=String(v).match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); return u? new Date(+u[3],u[1]-1,+u[2]) : null; };
const fmt = d => d ? d.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '';
const days = d => Math.round((d-today)/86400000);

// "International Paper - Rome Mill and PSM Orientatio (12TIPROM)" -> {mill:'International Paper - Rome', kind:'millpsm'}
function classify(desc){
  const name = String(desc||'').replace(/\s*\([^)]*\)\s*$/,'').replace(/[–—]/g,'-').replace(/\s+/g,' ').trim();
  if(/^TAPPISAFE Basic (Refresher )?Orientation/i.test(name)) return {kind:'basic', name};
  if(/^TAPPISAFE|^COVID/i.test(name)) return null;
  const m = name.match(/^(.*?)\s*-\s*(.*)$/); if(!m) return null;
  const sm = m[2].match(/^(.*?)\s+(Mill\b|PSM\b|Escorted|Visitor|Security|Modified|Utilities)(.*)$/i);
  if(!sm) return null;
  const mill = m[1].trim()+' - '+sm[1].trim();
  const tail = (sm[2]+sm[3]).trim();
  const kind = /^Mill and P/i.test(tail) ? 'millpsm' : /^Mill\b/i.test(tail) ? 'mill' : /^PSM/i.test(tail) ? 'psm' : 'other';
  return {kind, mill, name};
}
const millKey = m => m.toLowerCase();
const nameKey = n => { n=String(n||''); if(n.includes(',')){ const [l,f]=n.split(','); n=f+' '+l; }
  const t=n.toLowerCase().replace(/[^a-z ]/g,' ').split(/\s+/).filter(x=>x.length>1); return t.length? t[0]+' '+t[t.length-1] : ''; };

const PEOPLE = new Map(), MILLS = new Map(); let ROWS = [];
const S = {mill:'', q:'', lights:[], view:'site', sort:['light',-1]};
try{ Object.assign(S, JSON.parse(localStorage.getItem('evtd-sites-v1')||'{}')); }catch(e){}
const save = () => { try{ localStorage.setItem('evtd-sites-v1', JSON.stringify({mill:S.mill, view:S.view})); }catch(e){} };

// Best record of a kind: a pass with the latest expiration wins; a failure only counts when there is no pass.
function best(list){
  const pass = list.filter(r=>r.pass).sort((a,b)=>(b.exp||0)-(a.exp||0) || (b.date||0)-(a.date||0));
  if(pass.length) return pass[0];
  return list.length ? list.slice().sort((a,b)=>(b.date||0)-(a.date||0))[0] : null;
}
function reqState(rec, label){
  if(!rec) return {s:'red', label, text:'Missing'};
  if(!rec.pass) return {s:'red', label, text:'Failed '+fmt(rec.date), rec};
  if(rec.exp && rec.exp < today) return {s:'red', label, text:'Expired '+fmt(rec.exp), rec};
  if(rec.exp && days(rec.exp) <= SOON) return {s:'yellow', label, text:'Expires '+fmt(rec.exp)+' ('+days(rec.exp)+' days)', rec};
  return {s:'green', label, text: rec.exp ? 'Good to '+fmt(rec.exp) : 'Complete '+fmt(rec.date), rec};
}
function readiness(p, m){
  const atMill = p.recs.filter(r=>r.mk===m.key);
  const reqs = [
    reqState(best(p.recs.filter(r=>r.kind==='basic')), 'TAPPISAFE Basic or Refresher'),
    reqState(best(atMill.filter(r=>r.kind==='mill'||r.kind==='millpsm')), 'Mill orientation'),
  ];
  if(m.psm) reqs.push(reqState(best(atMill.filter(r=>r.kind==='psm'||r.kind==='millpsm')), 'PSM'));
  const light = reqs.reduce((a,r)=>RANK[r.s]>RANK[a]?r.s:a,'green');
  return {light, reqs};
}

window.initPlantSites = function(tappi, hsiRecs){
  const ci = Object.fromEntries(tappi.cols.map((c,i)=>[c,i]));
  const hsiLoc = new Map(); (hsiRecs||[]).forEach(r=>{ const k=nameKey(r.name); if(k && r.loc && !hsiLoc.has(k)) hsiLoc.set(k, r.loc); });
  tappi.rows.forEach(row=>{
    const c = classify(row[ci.course]); if(!c) return;
    const name = (String(row[ci.first]||'').trim()+' '+String(row[ci.last]||'').trim()).replace(/\s*,\s*/g,' ').replace(/\s+/g,' ').trim();
    const id = String(row[ci.id]||''), key = id || nameKey(name);
    const p = PEOPLE.get(key) || PEOPLE.set(key,{key, id, name, loc:hsiLoc.get(nameKey(name))||'', recs:[]}).get(key);
    const r = {kind:c.kind, course:c.name, mk:c.mill?millKey(c.mill):'', date:toDate(row[ci.date]), exp:toDate(row[ci.exp]), pass:/^\(P\)|pass/i.test(String(row[ci.grade]||''))};
    p.recs.push(r);
    if(c.mill){
      const m = MILLS.get(r.mk) || MILLS.set(r.mk,{key:r.mk, name:c.mill, psm:false, people:new Set(), courses:new Set()}).get(r.mk);
      if(c.kind==='psm'||c.kind==='millpsm') m.psm = true;
      m.people.add(key); m.courses.add(c.name);
    }
  });
  const mills = sortedMills();
  if(!MILLS.has(S.mill)) S.mill = mills.length ? mills[0].key : '';
  $('ps-mill').innerHTML = mills.map(m=>'<option value="'+esc(m.key)+'"'+(m.key===S.mill?' selected':'')+'>'+esc(m.name)+(m.psm?' (PSM)':'')+' · '+m.people.size+'</option>').join('');
  $('ps-mill').addEventListener('change',e=>{ S.mill=e.target.value; S.lights=[]; save(); draw(); });
  $('ps-q').addEventListener('input',e=>{ S.q=e.target.value; draw(); });
  $('ps-v-site').addEventListener('click',()=>{ S.view='site'; save(); draw(); });
  $('ps-v-grid').addEventListener('click',()=>{ S.view='grid'; save(); draw(); });
  $('ps-lights').addEventListener('click',e=>{ const b=e.target.closest('.light'); if(!b) return; const k=b.dataset.k; S.lights = S.lights.includes(k)? S.lights.filter(x=>x!==k) : [...S.lights,k]; draw(); });
  $('ps-tbl').addEventListener('click',e=>{
    const s=e.target.closest('[data-sort]'); if(s){ const k=s.dataset.sort; S.sort=[k, S.sort[0]===k? -S.sort[1] : (k==='light'?-1:1)]; draw(); return; }
    const g=e.target.closest('[data-mill]'); if(g){ S.mill=g.dataset.mill; S.view='site'; S.lights=[]; $('ps-mill').value=S.mill; if(g.dataset.who){ S.q=g.dataset.who; $('ps-q').value=S.q; } save(); draw(); }
  });
  $('ps-export').addEventListener('click', exportCSV);
  draw();
};
const sortedMills = () => [...MILLS.values()].sort((a,b)=>b.people.size-a.people.size || a.name.localeCompare(b.name));
function matchQ(p){ const q=S.q.trim().toLowerCase().split(/\s+/).filter(Boolean); return !q.length || q.every(t=>(p.name+' '+p.id+' '+p.loc).toLowerCase().includes(t)); }

function draw(){
  $('ps-v-site').setAttribute('aria-pressed', S.view==='site'); $('ps-v-grid').setAttribute('aria-pressed', S.view==='grid');
  $('ps-mill').disabled = S.view!=='site';
  S.view==='site' ? drawSite() : drawGrid();
}
function lightsBar(counts, total, noun){
  const L = $('ps-lights'); L.classList.toggle('dim', S.lights.length>0);
  L.innerHTML = ['green','yellow','red'].map(k=>'<button type="button" class="light" data-k="'+k+'" aria-pressed="'+S.lights.includes(k)+'" style="--c:var('+LIGHT[k].c+')"><i class="dot"></i><b>'+(counts[k]||0)+'</b><span>'+LIGHT[k].label+'</span></button>').join('')+
    '<span class="count" style="align-self:center">'+noun+'</span>';
}
function drawSite(){
  const m = MILLS.get(S.mill); if(!m) return;
  $('ps-rule').innerHTML = '<b>'+esc(m.name)+'</b> requires TAPPISAFE Basic Orientation or Basic Refresher, '+(m.psm?'the mill orientation and the PSM orientation':'and the mill orientation')+
    ', all passed and not expired. Courses on file for this site: '+esc([...m.courses].join('; '))+'.';
  let rows = [...m.people].map(k=>PEOPLE.get(k)).filter(matchQ).map(p=>Object.assign({p}, readiness(p,m)));
  const counts = {}; rows.forEach(r=>counts[r.light]=(counts[r.light]||0)+1);
  lightsBar(counts, rows.length, rows.length+' '+(rows.length===1?'person':'people')+' with a record for this site');
  if(S.lights.length) rows = rows.filter(r=>S.lights.includes(r.light));
  const [sk,sd] = S.sort;
  const val = r => sk==='light' ? RANK[r.light] : sk==='loc' ? (r.p.loc||'~') : r.p.name.toLowerCase();
  rows.sort((a,b)=>{ const x=val(a), y=val(b); const c = typeof x==='number'? x-y : String(x).localeCompare(String(y)); return c*sd || a.p.name.localeCompare(b.p.name); });
  ROWS = rows;
  const arr = k => S.sort[0]===k ? '<span class="arr">'+(S.sort[1]>0?'↑':'↓')+'</span>' : '';
  const reqCols = ['TAPPISAFE Basic or Refresher','Mill orientation'].concat(m.psm?['PSM']:[]);
  const T = $('ps-tbl'); T.className='';
  T.querySelector('thead').innerHTML = '<tr><th><button type="button" data-sort="light">Ready'+arr('light')+'</button></th><th><button type="button" data-sort="name">Employee'+arr('name')+'</button></th><th><button type="button" data-sort="loc">Location'+arr('loc')+'</button></th>'+
    reqCols.map(c=>'<th>'+esc(c)+'</th>').join('')+'<th>What to fix</th></tr>';
  T.querySelector('tbody').innerHTML = rows.map(r=>{
    const fix = r.reqs.filter(q=>q.s!=='green').map(q=>q.label+': '+q.text);
    return '<tr><td class="light-td"><i class="dot" style="--c:var('+LIGHT[r.light].c+')" title="'+LIGHT[r.light].label+'"></i></td>'+
      '<td><b>'+esc(r.p.name)+'</b><span class="sub">TAPPI '+esc(r.p.id||'—')+'</span></td><td>'+esc(r.p.loc||'—')+'</td>'+
      r.reqs.map(q=>'<td><div class="req" style="--c:var('+LIGHT[q.s].c+')"><span class="st">'+esc(q.text)+'</span>'+(q.rec?'<small>'+esc(q.rec.course)+'</small>':'')+'</div></td>').join('')+
      '<td class="fix'+(fix.length?'':' ok')+'">'+(fix.length? esc(fix.join(' · ')) : 'Nothing')+'</td></tr>';
  }).join('') || '<tr><td colspan="'+(4+reqCols.length)+'"><div class="empty">No one matches.</div></td></tr>';
}
function drawGrid(){
  const mills = sortedMills();
  $('ps-rule').innerHTML = 'Each dot is one person at one plant site: <b>green</b> ready, <b>yellow</b> ready but something expires within 30 days, <b>red</b> not ready. A blank means no TAPPISAFE record for that site. Click a dot or a site name for the details.';
  let people = [...PEOPLE.values()].filter(p=>matchQ(p) && mills.some(m=>m.people.has(p.key)));
  const counts = {}, cells = new Map();
  people.forEach(p=>mills.forEach(m=>{ if(m.people.has(p.key)){ const l=readiness(p,m).light; cells.set(p.key+'|'+m.key,l); counts[l]=(counts[l]||0)+1; } }));
  lightsBar(counts, people.length, people.length+' people · counts are person-site pairs');
  if(S.lights.length) people = people.filter(p=>mills.some(m=>S.lights.includes(cells.get(p.key+'|'+m.key))));
  people.sort((a,b)=>a.name.localeCompare(b.name));
  ROWS = people.map(p=>({p, cells: mills.map(m=>cells.get(p.key+'|'+m.key)||'')})); ROWS.mills = mills;
  const T = $('ps-tbl'); T.className='grid';
  T.querySelector('thead').innerHTML = '<tr><th>Employee</th>'+mills.map(m=>'<th class="mill"><button type="button" data-mill="'+esc(m.key)+'" title="Open '+esc(m.name)+'">'+esc(m.name)+(m.psm?' (PSM)':'')+'</button></th>').join('')+'</tr>';
  T.querySelector('tbody').innerHTML = people.map(p=>'<tr><td class="who-td"><b>'+esc(p.name)+'</b><span class="sub">'+esc(p.loc||('TAPPI '+(p.id||'—')))+'</span></td>'+
    mills.map(m=>{ const l=cells.get(p.key+'|'+m.key); if(!l || (S.lights.length && !S.lights.includes(l))) return '<td class="cell"></td>';
      return '<td class="cell"><button type="button" data-mill="'+esc(m.key)+'" data-who="'+esc(p.name)+'" title="'+esc(p.name+' · '+m.name+': '+LIGHT[l].label)+'"><i class="dot" style="--c:var('+LIGHT[l].c+')"></i></button></td>'; }).join('')+'</tr>').join('')
    || '<tr><td><div class="empty">No one matches.</div></td></tr>';
}
function exportCSV(){
  const q = v => { v = v==null?'':String(v); return /[",\n]/.test(v)?'"'+v.replace(/"/g,'""')+'"':v; };
  let lines, name;
  if(S.view==='site'){
    const m = MILLS.get(S.mill);
    lines = [['Ready','Employee','TAPPI ID','Location','TAPPISAFE Basic or Refresher','Mill orientation'].concat(m.psm?['PSM']:[]).concat(['What to fix'])]
      .concat(ROWS.map(r=>[LIGHT[r.light].label, r.p.name, r.p.id, r.p.loc].concat(r.reqs.map(x=>x.text)).concat([r.reqs.filter(x=>x.s!=='green').map(x=>x.label+': '+x.text).join('; ')])));
    name = 'Plant_Site_'+m.name.replace(/[^A-Za-z0-9]+/g,'_');
  } else {
    lines = [['Employee','TAPPI ID','Location'].concat(ROWS.mills.map(m=>m.name))].concat(ROWS.map(r=>[r.p.name, r.p.id, r.p.loc].concat(r.cells.map(c=>c?LIGHT[c].label:''))));
    name = 'Plant_Sites_All';
  }
  const csv = lines.map(l=>l.map(q).join(',')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv],{type:'text/csv'}));
  const a = document.createElement('a'); a.href=url; a.download=name+'_'+new Date().toISOString().slice(0,10)+'.csv';
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(()=>URL.revokeObjectURL(url),1000);
}
})();
