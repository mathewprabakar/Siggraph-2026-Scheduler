import { drawQR } from './qr.js';

/* ===== SIGGRAPH 2026 Timetable Builder — v2 =====
   Served over HTTP (GitHub Pages): the catalog and floor-plan maps are
   fetched from sibling files rather than inlined. Filters mirror the
   schedule site (Program / Interest Area / Keyword / Registration / Day).
   Clashing sessions are laid out by priority: High -> left. */

const DAYS=[
  {iso:'2026-07-19',wd:'Sun',d:19},{iso:'2026-07-20',wd:'Mon',d:20},
  {iso:'2026-07-21',wd:'Tue',d:21},{iso:'2026-07-22',wd:'Wed',d:22},
  {iso:'2026-07-23',wd:'Thu',d:23},
];
const WEEKDAY_BY_ISO=Object.fromEntries(DAYS.map(x=>[x.iso,x.wd]));
const GRID_START=8*60, GRID_END=24*60, PXPERMIN=64/60;

/* ---- site taxonomy (verbatim from the schedule filters) ---- */
const T_PROGRAM=["ACM SIGGRAPH 365","ACM SIGGRAPH Award Talks","Appy Hour","Art Gallery","Art Papers","Birds of a Feather","Computer Animation Festival","Courses","Educator's Day Sessions","Educator's Forum","Emerging Technologies","Exhibition","Frontiers","Games Summit","Immersive Pavilion","Industry Sessions","Keynote Speakers","Panels","Pathfinders","Posters","Production Sessions","Real-Time Live!","Spatial Storytelling","Stage Sessions","Talks","Technical Papers","Technical Workshops"];
const T_KEYWORD=["Animation","Art","Artificial Intelligence/Machine Learning","Audio","Augmented Reality","Capture/Scanning","Chapters","Computer Vision","Digital Twins","Display","Diversity, Equity and Inclusion","Dynamics","Education","Ethics and Society","Fabrication","Games","Generative AI","Geometry","Graphics Systems Architecture","Haptics","Hardware","History","Image Processing","Industry Insight","Lighting","Math Foundations and Theory","Modeling","Networking","Performance","Physical AI","Pioneers","Pipeline Tools and Work","Real-Time","Rendering","Robotics","Scientific Visualization","Simulation","Spatial Computing","Virtual Reality","Visual Effects"];
const T_IA=["Arts & Design","Gaming & Interactive","New Technologies","Production & Animation","Research & Education"];
const T_REG=["Full Conference Supporter","Full Conference","Experience","Discover"];

/* Per-theme program colors for the day-grid event blocks; keyed by theme name.
   Alternate palettes are registered by later theme definitions. */
const PALETTES={
  siggraph:{
    "Technical Papers":"#1d90a3","Courses":"#2e7d5f","Games Summit":"#c26a2e","Birds of a Feather":"#6c8f3a",
    "Production Sessions":"#b0486b","Talks":"#5f5aa8","Keynote Speakers":"#2a4249","Real-Time Live!":"#8c2837",
    "Art Gallery":"#a8842c","Art Papers":"#a8842c","Computer Animation Festival":"#7d5a34","Educator's Forum":"#3f7a8c",
    "Educator's Day Sessions":"#3f7a8c","Spatial Storytelling":"#6d4fa3","Panels":"#4f7d46","Frontiers":"#9a3b6c",
    "Emerging Technologies":"#23867c","Immersive Pavilion":"#7a4a9e","Industry Sessions":"#4a5f7a","Posters":"#7d8578",
    "Technical Workshops":"#33708c","Appy Hour":"#ab5232","Stage Sessions":"#5e6b3a","Pathfinders":"#7a5a2b",
    "ACM SIGGRAPH 365":"#55616a","ACM SIGGRAPH Award Talks":"#3a4a52","Exhibition":"#55616a"
  },
  light:{
    "Technical Papers":"#0000cc","Courses":"#0aa3bf","Games Summit":"#e0672a","Birds of a Feather":"#2f9e57",
    "Production Sessions":"#c0407e","Talks":"#7b52d6","Keynote Speakers":"#111827","Real-Time Live!":"#cc0000",
    "Art Gallery":"#b8862b","Art Papers":"#b8862b","Computer Animation Festival":"#8a5a2b","Educator's Forum":"#3f7a8c",
    "Educator's Day Sessions":"#3f7a8c","Spatial Storytelling":"#6a4ac0","Panels":"#417a3f","Frontiers":"#9a3b6c",
    "Emerging Technologies":"#0e8f8f","Immersive Pavilion":"#7a3fb0","Industry Sessions":"#4a5a7a","Posters":"#8a8f9e",
    "Technical Workshops":"#2f6f8f","Appy Hour":"#b3552f","Stage Sessions":"#5a6a3f","Pathfinders":"#7a5a2b",
    "ACM SIGGRAPH 365":"#556","ACM SIGGRAPH Award Talks":"#3a3f52","Exhibition":"#556"
  }
};
PALETTES.dark=PALETTES.siggraph;
const PALETTE_FALLBACK={siggraph:"#5f6e70",dark:"#5f6e70",light:"#5b6070"};
const THEME_KEY='s2026-theme', THEMES=['siggraph','light','dark'];
function curTheme(){return document.documentElement.dataset.theme||'siggraph';}
let PROGRAM_COLORS=PALETTES[curTheme()]||PALETTES.siggraph;
function colorFor(p){return PROGRAM_COLORS[p]||PALETTE_FALLBACK[curTheme()]||"#5f6e70";}
function applyTheme(name){
  if(!THEMES.includes(name))name='siggraph';
  document.documentElement.dataset.theme=name;
  PROGRAM_COLORS=PALETTES[name]||PALETTES.siggraph;
  try{localStorage.setItem(THEME_KEY,name);}catch(e){}
  const sel=document.getElementById('themeSelect');if(sel)sel.value=name;
  if(typeof renderCatalog==='function'){renderCatalog();renderTimetable();}
}

/* ---- seed: real S2026 sessions, fully tagged ---- */
const AIML="Artificial Intelligence/Machine Learning";
const SEED=[
 {t:"'Battlefield 6': How We Brought The Franchise Vision To Life With Our Destruction System Debut",program:"Games Summit",day:"2026-07-19",s:"11:30am",e:"12:00pm",room:"411 Theatre",ia:["Arts & Design","Gaming & Interactive"],kw:["Art","Games","Performance","Real-Time","Rendering","Simulation"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"AI Score Hallucination in Vision-Language Models (Poster)",program:"Posters",day:"2026-07-19",s:"9:00am",e:"5:30pm",room:"West Hall Lobby",ia:["Research & Education"],kw:[AIML,"Generative AI"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"Fast Modal Dynamics for Hairy and Scaly Surfaces on the GPU (Poster)",program:"Posters",day:"2026-07-19",s:"9:00am",e:"5:30pm",room:"West Hall Lobby",ia:["Research & Education"],kw:["Real-Time","Simulation","Dynamics"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"See/Saw: Embodied Probing of Vision Transformer Attention in VR (Poster)",program:"Posters",day:"2026-07-19",s:"9:00am",e:"5:30pm",room:"West Hall Lobby",ia:["Research & Education"],kw:[AIML,"Virtual Reality","Computer Vision"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"Real-Time Light Field Tracing via Display-Architecture Alignment (Poster)",program:"Posters",day:"2026-07-19",s:"9:00am",e:"5:30pm",room:"West Hall Lobby",ia:["Research & Education"],kw:["Real-Time","Rendering","Display","Hardware"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"顫杵 (sensho) — kinetic sculpture",program:"Art Gallery",day:"2026-07-20",s:"10:30am",e:"5:00pm",room:"Concourse Foyer",ia:["Arts & Design","Gaming & Interactive","New Technologies","Production & Animation","Research & Education"],kw:["Art","Display"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"3D Gaussian Splatting I — Interactive Discussion",program:"Technical Papers",day:"2026-07-20",s:"3:00pm",e:"3:30pm",room:"Room 408 A",ia:["Research & Education"],kw:[AIML,"Geometry","Modeling","Real-Time","Rendering"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"3DGS in Web Gaming: 'The Shadow of the Czar'",program:"Spatial Storytelling",day:"2026-07-20",s:"3:00pm",e:"3:45pm",room:"Concourse Hall",ia:["Arts & Design","Gaming & Interactive","New Technologies"],kw:["Art","Games","Generative AI","Lighting","Pipeline Tools and Work","Real-Time","Rendering","Spatial Computing","Virtual Reality"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"18 Months",program:"Computer Animation Festival",day:"2026-07-20",s:"6:30pm",e:"8:30pm",room:"Hall K",ia:["Arts & Design","Production & Animation"],kw:["Animation"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"3D Jobs Outside of Entertainment — A Panel by The 3D Artist Community",program:"Birds of a Feather",day:"2026-07-21",s:"9:00am",e:"10:30am",room:"Room 513",ia:["Arts & Design","Production & Animation"],kw:["Animation","Digital Twins","Games","Industry Insight"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"3D Assets: New Features, Tooling, and What Comes Next",program:"Birds of a Feather",day:"2026-07-21",s:"10:00am",e:"11:00am",room:"Room 518",ia:["Gaming & Interactive","New Technologies","Production & Animation","Research & Education"],kw:["Animation","Digital Twins","Games","Graphics Systems Architecture","Modeling","Pipeline Tools and Work","Real-Time","Spatial Computing","Virtual Reality"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"3D challenges in .MIL",program:"Birds of a Feather",day:"2026-07-21",s:"10:00am",e:"11:00am",room:"Room 512",ia:["Arts & Design"],kw:["Modeling"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"3D Generation — Interactive Discussion",program:"Technical Papers",day:"2026-07-21",s:"11:55am",e:"12:25pm",room:"Room 403 B",ia:["Research & Education"],kw:[AIML,"Geometry","Modeling"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"'Live from LA!': Immersive Youth Theater",program:"Educator's Forum",day:"2026-07-21",s:"2:00pm",e:"2:20pm",room:"Room 501 ABC",ia:["Arts & Design","Gaming & Interactive","New Technologies","Production & Animation","Research & Education"],kw:["Animation","Art","Augmented Reality","Capture/Scanning","Education","Ethics and Society","Generative AI","Math Foundations and Theory","Modeling","Performance","Pipeline Tools and Work","Real-Time","Rendering","Spatial Computing","Virtual Reality"],reg:["Full Conference Supporter","Full Conference","Experience"]},
 {t:"2D Gaussian Splatting for Bézier Spline Line Art Vectorization",program:"Technical Papers",day:"2026-07-22",s:"10:55am",e:"11:05am",room:"Room 403 A",ia:["Research & Education"],kw:["Geometry","Hardware","Modeling","Real-Time","Rendering"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"4D Human-Scene Reconstruction from Low-Overlap Captures",program:"Technical Papers",day:"2026-07-22",s:"2:10pm",e:"2:20pm",room:"Room 403 A",ia:["Research & Education"],kw:["Animation",AIML,"Geometry","Modeling","Rendering","Simulation"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"4D Humans — Interactive Discussion",program:"Technical Papers",day:"2026-07-22",s:"2:50pm",e:"3:20pm",room:"Room 403 A",ia:["Research & Education"],kw:["Animation",AIML,"Geometry","Modeling","Rendering","Simulation"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"'Dear Upstairs Neighbors': Artist-Centered, AI-Assisted Animation",program:"Production Sessions",day:"2026-07-23",s:"11:15am",e:"12:15pm",room:"Petree D",ia:["Arts & Design","New Technologies","Production & Animation"],kw:["Animation","Art",AIML,"Generative AI"],reg:["Full Conference Supporter","Full Conference"]},
 {t:"3D Gaussian Splatting II — Interactive Discussion",program:"Technical Papers",day:"2026-07-23",s:"3:00pm",e:"3:30pm",room:"Room 408 A",ia:["Research & Education"],kw:[AIML,"Geometry","Modeling","Rendering"],reg:["Full Conference Supporter","Full Conference"]},
];

/* ---- time helpers ---- */
function parseTime(str){
  if(str==null)return null;
  const m=String(str).trim().toLowerCase().match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$/);
  if(!m)return null;
  let h=parseInt(m[1],10);const min=m[2]?parseInt(m[2],10):0;const ap=m[3];
  if(ap==='pm'&&h!==12)h+=12; if(ap==='am'&&h===12)h=0; if(!ap&&h<8)h+=12;
  return h*60+min;
}
function fmtTime(mins){let h=Math.floor(mins/60),m=mins%60;const ap=h>=12?'pm':'am';let hh=h%12;if(hh===0)hh=12;return hh+(m?(':'+String(m).padStart(2,'0')):'')+ap;}
function uid(ev){return (ev.day+'|'+ev.s+'|'+ev.t).toLowerCase().replace(/\s+/g,' ').slice(0,140);}
function norm(ev){
  const s0=parseTime(ev.s), e0=ev.e!=null?parseTime(ev.e):null;
  const programs=(ev.programs&&ev.programs.length)?ev.programs:[ev.program||ev.type||'Session'];
  const o={t:ev.t,program:programs[0],programs,day:ev.day,s:ev.s,e:ev.e||(s0!=null?fmtTime(s0+30):''),
    room:ev.room||'',url:ev.url||'',ia:ev.ia||[],kw:ev.kw||[],reg:ev.reg||[],s0,e0:(e0!=null?e0:(s0!=null?s0+30:null)),pr:ev.pr||2};
  o.id=ev.id||uid(o);
  o.hay=(o.t+' '+o.programs.join(' ')+' '+o.room+' '+o.ia.join(' ')+' '+o.kw.join(' ')).toLowerCase();
  return o;
}

/* ---- state ---- */
const STORE_KEY='siggraph2026_timetable_v2';
let catalog=SEED.map(norm);      // replaced by the fetched catalog at startup; SEED is the offline fallback
let picked=new Map();            // id -> normalized event (with pr)
let activeDay=DAYS[0].iso;
let filterDay='';
const F={program:new Set(),ia:new Set(),kw:new Set(),reg:new Set(),room:new Set()};
let searchQ='';
let storageOK=true;
const RENDER_CAP=500;
/* distinct rooms, for the Filters panel's Room group (recomputed after the catalog loads) */
let T_ROOM=deriveRooms(catalog);
function deriveRooms(list){return [...new Set(list.map(c=>c.room).filter(Boolean))].sort((a,b)=>a.localeCompare(b));}

/* The full session catalog lives in siggraph2026-catalog.json (the same file refresh_siggraph.py
   writes) and is fetched at startup so there's a single source of truth. SEED above is a tiny
   built-in fallback used only if the fetch fails (e.g. opened without a server). */
async function loadCatalog(){
  try{
    const res=await fetch('siggraph2026-catalog.json',{cache:'no-cache'});
    if(!res.ok)throw new Error('HTTP '+res.status);
    const data=await res.json();
    const arr=Array.isArray(data)?data:data.catalog;
    if(Array.isArray(arr)&&arr.length){
      catalog=arr.map(norm);
      T_ROOM=deriveRooms(catalog);
    }
  }catch(e){
    console.warn('Catalog fetch failed; using the built-in seed instead.',e);
  }
}

function loadState(){
  try{
    const raw=localStorage.getItem(STORE_KEY);
    if(raw){
      const data=JSON.parse(raw);
      if(Array.isArray(data.catalog)&&data.catalog.length) catalog=data.catalog.map(norm);
      (data.picked||[]).forEach(ev=>{const n=norm(ev);picked.set(n.id,n);});
    }
  }catch(e){storageOK=false;}
  updateSaveNote();
}
function saveState(){
  try{localStorage.setItem(STORE_KEY,JSON.stringify({catalog:catalog,picked:[...picked.values()]}));storageOK=true;}
  catch(e){storageOK=false;}
  updateSaveNote();
}
function updateSaveNote(){
  const n=document.getElementById('saveNote');
  n.textContent=storageOK?(picked.size?('Saved · '+picked.size+' picked · '+catalog.length+' in catalog'):('Saved · '+catalog.length+' in catalog')):'Storage off — use Export picks';
  n.style.color=storageOK?'':'var(--amber)';
}

/* ---- build filter UI ---- */
function countForOption(group,val){
  return catalog.reduce((a,c)=>{
    if(group==='program') return a+((c.programs||[c.program]).includes(val)?1:0);
    if(group==='ia') return a+(c.ia.includes(val)?1:0);
    if(group==='kw') return a+(c.kw.includes(val)?1:0);
    if(group==='reg') return a+(c.reg.includes(val)?1:0);
    if(group==='room') return a+(c.room===val?1:0);
    return a;
  },0);
}
function buildFilterGroups(){
  const defs=[['program',T_PROGRAM],['ia',T_IA],['kw',T_KEYWORD],['reg',T_REG],['room',T_ROOM]];
  defs.forEach(([g,opts])=>{
    const list=document.querySelector(`.fgroup[data-group="${g}"] .checklist`);
    list.innerHTML='';
    opts.forEach(val=>{
      const cnt=countForOption(g,val);
      const row=document.createElement('label');row.className='checkitem';
      row.innerHTML=`<input type="checkbox" value="${esc(val)}"><span>${esc(val)}</span><span class="cnt">${cnt}</span>`
        +(g==='room'?`<button type="button" class="room-pin" title="Show ${esc(val)} on the map">📍</button>`:'');
      const cb=row.querySelector('input');
      cb.checked=F[g].has(val);
      cb.onchange=()=>{cb.checked?F[g].add(val):F[g].delete(val);renderCatalog();syncFilterCounts();};
      if(g==='room'){
        const pin=row.querySelector('.room-pin');
        pin.onclick=(ev)=>{ev.preventDefault();ev.stopPropagation();showLocation(val,pin);};
      }
      list.appendChild(row);
    });
  });
  syncFilterCounts();
}
function refreshFilterCounts(){
  document.querySelectorAll('.fgroup').forEach(fg=>{
    const g=fg.dataset.group;
    fg.querySelectorAll('.checkitem').forEach(row=>{
      const val=row.querySelector('input').value;
      row.querySelector('.cnt').textContent=countForOption(g,val);
    });
  });
}
function syncFilterCounts(){
  let total=0;
  document.querySelectorAll('.fgroup').forEach(fg=>{
    const g=fg.dataset.group;const n=F[g].size;total+=n;
    const badge=fg.querySelector('summary .n');
    badge.textContent=n;badge.classList.toggle('show',n>0);
  });
  document.getElementById('fcount').textContent=total;
}

/* ---- day controls ---- */
function buildDayControls(){
  const chips=document.getElementById('dayChips');
  const mk=(label,val)=>{
    const b=document.createElement('button');b.className='chip';b.textContent=label;b.dataset.val=val;
    b.setAttribute('aria-pressed',String(filterDay===val));
    b.onclick=()=>{filterDay=val;syncDayChips();renderCatalog();};
    chips.appendChild(b);
  };
  const lb=document.createElement('button');lb.className='chip live';lb.id='liveChip';lb.dataset.val='live';lb.title='Sessions happening right now';
  lb.innerHTML='<span class="livedot"></span>Live';
  lb.setAttribute('aria-pressed',String(filterDay==='live'));
  lb.onclick=()=>{filterDay='live';syncDayChips();renderCatalog();};
  chips.appendChild(lb);
  mk('All days','');
  DAYS.forEach(d=>mk(d.wd+' '+d.d,d.iso));
  updateLiveChip();

  const tabs=document.getElementById('dayTabs');
  DAYS.forEach(d=>{
    const b=document.createElement('button');b.className='day-tab';b.dataset.iso=d.iso;
    b.innerHTML=`<span class="wd">${d.wd}</span><span class="dm">${d.d}</span><span class="badge">0</span><span class="dot">!</span>`;
    b.onclick=()=>{activeDay=d.iso;renderTimetable();syncDayTabs();};
    tabs.appendChild(b);
  });
  const fday=document.getElementById('fDay');
  DAYS.forEach(d=>{const o=document.createElement('option');o.value=d.iso;o.textContent=`${d.wd} ${d.d} Jul`;fday.appendChild(o);});
  const dl=document.getElementById('typeList');
  T_PROGRAM.forEach(p=>{const o=document.createElement('option');o.value=p;dl.appendChild(o);});
}

/* ---- browse list ---- */
function matchesFilters(c){
  if(filterDay==='live'){if(!isLiveNow(c))return false;}
  else if(filterDay&&c.day!==filterDay)return false;
  if(F.program.size&&!(c.programs||[c.program]).some(x=>F.program.has(x)))return false;
  if(F.ia.size&&!c.ia.some(x=>F.ia.has(x)))return false;
  if(F.kw.size&&!c.kw.some(x=>F.kw.has(x)))return false;
  if(F.reg.size&&!c.reg.some(x=>F.reg.has(x)))return false;
  if(F.room.size&&!F.room.has(c.room))return false;
  if(searchQ){const q=searchQ.trim().toLowerCase();if(q&&!c.hay.includes(q))return false;}
  return true;
}
function renderSessionCard(c){
  const wd=WEEKDAY_BY_ISO[c.day]||'';
  const el=document.createElement('div');
  el.className='cat-item'+(picked.has(c.id)?' picked':'');
  el.innerHTML=`<span class="swatch" style="background:${colorFor(c.program)}"></span>
    <div class="cat-body"><p class="cat-title">${c.url?`<a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer" title="View on the SIGGRAPH schedule site" onclick="event.stopPropagation()">${esc(c.t)} <span class="ext-arrow">↗</span></a>`:esc(c.t)}</p>
    <div class="cat-meta"><span class="tag">${esc(c.program)}</span><span>${wd} · ${c.s0!=null?fmtTime(c.s0):'—'}–${c.e0!=null?fmtTime(c.e0):''}</span>${c.room?`<span class="room-link" title="Show on floor plan">📍 ${esc(c.room)}</span>`:''}</div></div>
    <button class="add-btn" title="${picked.has(c.id)?'Remove':'Add to my day'}">${picked.has(c.id)?'✓':'+'}</button>`;
  el.querySelector('.add-btn').onclick=()=>togglePick(c);
  const roomLink=el.querySelector('.room-link');
  if(roomLink)roomLink.onclick=(ev)=>{ev.stopPropagation();showLocation(c.room,roomLink);};
  return el;
}
function renderCatalog(){
  const box=document.getElementById('catalog');
  let list=catalog.filter(matchesFilters);
  list.sort((a,b)=>a.day.localeCompare(b.day)||(a.s0-b.s0)||a.t.localeCompare(b.t));
  document.getElementById('catCount').textContent=list.length+' shown';
  if(!list.length){box.innerHTML='<div class="empty">No sessions match these filters. Loosen a filter, or add one below.</div>';return;}
  const capped=list.slice(0,RENDER_CAP);
  box.innerHTML='';
  const frag=document.createDocumentFragment();
  capped.forEach(c=>frag.appendChild(renderSessionCard(c)));
  box.appendChild(frag);
  if(list.length>RENDER_CAP){
    const m=document.createElement('div');m.className='more-note';
    m.textContent=`Showing first ${RENDER_CAP} of ${list.length}. Narrow with search or filters to see the rest.`;
    box.appendChild(m);
  }
}

/* ---- pick / priority ---- */
function togglePick(ev){
  if(picked.has(ev.id)){picked.delete(ev.id);toast('Removed');}
  else{const n=norm({...ev,pr:2});picked.set(n.id,n);activeDay=ev.day;toast('Added to '+(WEEKDAY_BY_ISO[ev.day]||'day'));}
  saveState();renderCatalog();renderTimetable();syncDayTabs();
}
function setPriority(id,pr){const e=picked.get(id);if(!e)return;e.pr=pr;saveState();renderTimetable();}

/* ---- timetable ---- */
function eventsForDay(iso){return [...picked.values()].filter(e=>e.day===iso&&e.s0!=null&&e.e0!=null).sort((a,b)=>a.s0-b.s0||a.e0-b.e0);}
function findConflicts(evs){const c=new Set();for(let i=0;i<evs.length;i++)for(let j=i+1;j<evs.length;j++){if(evs[i].s0<evs[j].e0&&evs[j].s0<evs[i].e0){c.add(evs[i].id);c.add(evs[j].id);}}return c;}
function clusters(evs){
  const out=[];let cur=[],end=-1;
  evs.forEach(e=>{if(cur.length&&e.s0>=end){out.push(cur);cur=[];end=-1;}cur.push(e);end=Math.max(end,e.e0);});
  if(cur.length)out.push(cur);return out;
}
function layoutCluster(cluster){
  // priority first (1=High -> leftmost), then start, then title
  const order=[...cluster].sort((a,b)=>a.pr-b.pr||a.s0-b.s0||a.t.localeCompare(b.t));
  const colEnds=[];const colOf=new Map();
  order.forEach(e=>{
    let placed=false;
    for(let i=0;i<colEnds.length;i++){if(e.s0>=colEnds[i]){colOf.set(e.id,i);colEnds[i]=e.e0;placed=true;break;}}
    if(!placed){colOf.set(e.id,colEnds.length);colEnds.push(e.e0);}
  });
  return {cols:colEnds.length,colOf};
}
const PR_LABEL={1:'High',2:'Med',3:'Low'};
function renderTimetable(){
  const grid=document.getElementById('grid');
  const evs=eventsForDay(activeDay);
  document.getElementById('dayCount').textContent=evs.length?(evs.length+' session'+(evs.length>1?'s':'')):'';
  let html='<div class="hours">';
  for(let m=GRID_START;m<GRID_END;m+=60)html+=`<div class="hour"><span class="lbl mono">${fmtTime(m)}</span></div>`;
  html+='</div><div class="lane" id="lane"></div>';
  grid.innerHTML=html;
  const lane=document.getElementById('lane');
  const totalH=(GRID_END-GRID_START)*PXPERMIN;lane.style.height=totalH+'px';
  for(let m=GRID_START+30;m<GRID_END;m+=60){const l=document.createElement('div');l.className='halfline';l.style.top=((m-GRID_START)*PXPERMIN)+'px';lane.appendChild(l);}

  if(!evs.length){
    const e=document.createElement('div');e.className='grid-empty';e.style.height=totalH+'px';
    e.innerHTML='Nothing planned for this day yet.<br>Pick sessions on the left, or tap another day above.';
    lane.appendChild(e);
  }else{
    const conf=findConflicts(evs);const gutter=6;
    clusters(evs).forEach(cl=>{
      const {cols,colOf}=layoutCluster(cl);const wPct=100/cols;
      cl.forEach(e=>{
        const col=colOf.get(e.id);
        const top=Math.max(0,(e.s0-GRID_START))*PXPERMIN;
        const h=Math.max(22,(e.e0-e.s0)*PXPERMIN-2);
        const el=document.createElement('div');
        const short=h<40;
        el.className='ev'+(conf.has(e.id)?' conflict':'')+(e.pr===1?' p-high':'')+(e.pr===3?' p-low':'')+(short?' compact':'');
        el.dataset.id=e.id;
        el.style.top=top+'px';el.style.height=h+'px';
        el.style.left=`calc(${col*wPct}% + ${col?gutter/2:0}px)`;
        el.style.width=`calc(${wPct}% - ${gutter}px)`;
        el.style.background=colorFor(e.program);
        el.innerHTML=`<span class="et">${esc(e.t)}</span>
          ${short?'':`<span class="em">${esc(e.room||'')}</span>`}
          <span class="em">${fmtTime(e.s0)}–${fmtTime(e.e0)}${short&&e.room?(' · '+esc(e.room)):''}</span>`;
        el.onclick=(ev)=>{ev.stopPropagation();openPop(e,el);};
        lane.appendChild(el);
      });
    });
    const strip=document.getElementById('conflictStrip');
    if(conf.size){strip.className='conflict-strip show';strip.innerHTML=`⚠ <strong>${conf.size} sessions clash</strong> on this day — outlined in red. The higher-priority one sits on the left; tap any session to set High / Med / Low.`;}
    else{strip.className='conflict-strip';strip.innerHTML='';}
  }
  updateNowLine();
  renderLegend(evs);
}
function pdtNow(){const d=new Date(Date.now()-7*3600*1000);return{iso:d.toISOString().slice(0,10),min:d.getUTCHours()*60+d.getUTCMinutes()};}
function updateNowLine(){
  const lane=document.getElementById('lane');if(!lane)return;
  let nl=lane.querySelector('.nowline');
  const {iso,min}=pdtNow();
  if(iso!==activeDay||min<GRID_START||min>=GRID_END){if(nl)nl.remove();return;}
  if(!nl){nl=document.createElement('div');nl.className='nowline';nl.innerHTML='<span class="nowdot"></span><span class="nowlbl mono"></span>';lane.appendChild(nl);}
  nl.style.top=((min-GRID_START)*PXPERMIN)+'px';
  nl.querySelector('.nowlbl').textContent=fmtTime(min);
}
function isLiveNow(c){const {iso,min}=pdtNow();return c.day===iso&&c.s0!=null&&c.e0!=null&&c.s0<=min&&min<c.e0;}
function syncDayChips(){
  document.querySelectorAll('#dayChips .chip').forEach(c=>c.setAttribute('aria-pressed',String(c.dataset.val===filterDay)));
}
function updateLiveChip(){
  const chip=document.getElementById('liveChip');if(!chip)return;
  const n=catalog.filter(isLiveNow).length;
  chip.classList.toggle('show',n>0);
  if(filterDay==='live'){
    if(!n){filterDay='';syncDayChips();}
    renderCatalog();
  }
}
setInterval(()=>{updateNowLine();updateLiveChip();},30000);
function renderLegend(evs){
  const leg=document.getElementById('legend');
  const progs=[...new Set(evs.map(e=>e.program))];
  leg.innerHTML=progs.length?progs.map(p=>`<span class="l"><span class="sw" style="background:${colorFor(p)}"></span>${esc(p)}</span>`).join(''):'';
}
function syncDayTabs(){
  document.querySelectorAll('.day-tab').forEach(tab=>{
    const iso=tab.dataset.iso;tab.setAttribute('aria-pressed',String(iso===activeDay));
    const evs=eventsForDay(iso);const conf=findConflicts(evs);
    tab.querySelector('.badge').textContent=evs.length;
    tab.classList.toggle('hasconflict',conf.size>0);
    tab.querySelector('.badge').style.display=evs.length?'':'none';
  });
}

/* ---- priority popover ---- */
const pop=document.getElementById('pop');
function openPop(e,anchor){
  closeMapPop();
  closeSharePop();
  renderPriorityPop(e,anchor);
}
function renderPriorityPop(e,anchor){
  pop.innerHTML=`<h4>${esc(e.t)}</h4>
    <div class="pm">${esc(e.program)} · ${fmtTime(e.s0)}–${fmtTime(e.e0)}${e.room?(' · '+esc(e.room)):''}</div>
    ${(e.url||e.room)?`<div class="pop-actions">
      ${e.url?`<a class="pop-link" href="${esc(e.url)}" target="_blank" rel="noopener noreferrer">↗ View on schedule site</a>`:''}
      ${e.room?`<button class="pop-link" id="popFloorBtn" type="button">📍 Show on floor plan</button>`:''}
    </div>`:''}
    <div class="plabel">Priority when it clashes</div>
    <div class="pri-btns">
      <button data-pr="1" aria-pressed="${e.pr===1}">High</button>
      <button data-pr="2" aria-pressed="${e.pr===2}">Medium</button>
      <button data-pr="3" aria-pressed="${e.pr===3}">Low</button>
    </div>
    <div class="hint">Higher priority sits to the left when sessions overlap. Low priority also dims slightly.</div>
    <button class="remove">Remove from my day</button>`;
  pop.querySelectorAll('.pri-btns button').forEach(b=>b.onclick=()=>{setPriority(e.id,parseInt(b.dataset.pr,10));pop.querySelectorAll('.pri-btns button').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));});
  pop.querySelector('.remove').onclick=()=>removeWithUndo(e);
  const popFloorBtn=pop.querySelector('#popFloorBtn');
  if(popFloorBtn)popFloorBtn.onclick=()=>showLocation(e.room,popFloorBtn);
  pop.classList.add('show');
  positionPop(anchor);
}
function positionPop(anchor){
  const r=anchor.getBoundingClientRect();
  const pw=250, ph=pop.offsetHeight||210;
  let left=window.scrollX+r.left; if(left+pw>window.scrollX+window.innerWidth-10)left=window.scrollX+window.innerWidth-pw-10;
  let top=window.scrollY+r.bottom+6; if(top+ph>window.scrollY+window.innerHeight-10)top=window.scrollY+r.top-ph-6;
  pop.style.left=Math.max(10,left)+'px';pop.style.top=Math.max(10,top)+'px';
}
function removeWithUndo(e){
  picked.delete(e.id);saveState();renderCatalog();renderTimetable();syncDayTabs();
  closePop();
  toastWithUndo('Removed from My Day',()=>{
    picked.set(e.id,e);saveState();renderCatalog();renderTimetable();syncDayTabs();
    toast('Restored');
  });
}
function closePop(){pop.classList.remove('show');}
document.addEventListener('click',e=>{if(!e.composedPath().includes(pop))closePop();});
window.addEventListener('resize',closePop);

/* ---- off-site venues: Google Maps tooltip ----
   Sessions held away from the LACC (hotel ballrooms, bars, event spaces) have no
   floor to highlight, so instead of opening the LACC map we show a small popover
   with an embedded Google Maps preview + a link to open the full map. */
const OFFSITE_VENUES=[
  {match:/exchange la/i,name:'Exchange LA',address:'618 S. Spring Street, Los Angeles, CA 90014'},
  {match:/hotel per la/i,name:'Hotel Per La, Autograph Collection',address:'649 S Olive St, Los Angeles, CA 90014'},
  {match:/jw marriott/i,name:'JW Marriott Los Angeles L.A. LIVE',address:'900 W Olympic Blvd, Los Angeles, CA 90015'},
  {match:/prank bar/i,name:'Prank Bar',address:'1100 S. Hope St., Los Angeles, CA 90015'},
];
function findOffsiteVenue(roomStr){
  const s=normRoomKey(roomStr);
  if(!s)return null;
  return OFFSITE_VENUES.find(v=>v.match.test(s))||null;
}
const mapPop=document.getElementById('mapPop');
function openMapPop(venue,anchor){
  closePop();
  closeSharePop();
  const q=encodeURIComponent(venue.address);
  mapPop.innerHTML=`<div class="venue-name">${esc(venue.name)}</div>
    <div class="venue-addr">${esc(venue.address)}</div>
    <iframe loading="lazy" referrerpolicy="no-referrer-when-downgrade" src="https://www.google.com/maps?q=${q}&output=embed"></iframe>
    <a class="pop-link" href="https://www.google.com/maps/search/?api=1&query=${q}" target="_blank" rel="noopener noreferrer">↗ Open in Google Maps</a>`;
  mapPop.classList.add('show');
  const r=anchor.getBoundingClientRect();
  const pw=280,ph=mapPop.offsetHeight||280;
  let left=window.scrollX+r.left; if(left+pw>window.scrollX+window.innerWidth-10)left=window.scrollX+window.innerWidth-pw-10;
  let top=window.scrollY+r.bottom+6; if(top+ph>window.scrollY+window.innerHeight-10)top=window.scrollY+r.top-ph-6;
  mapPop.style.left=Math.max(10,left)+'px';mapPop.style.top=Math.max(10,top)+'px';
}
function closeMapPop(){mapPop.classList.remove('show');}
document.addEventListener('click',e=>{if(!mapPop.contains(e.target))closeMapPop();});
window.addEventListener('resize',closeMapPop);
function showLocation(roomStr,anchor){
  const venue=findOffsiteVenue(roomStr);
  if(venue){openMapPop(venue,anchor);return;}
  openFloorPlan(roomStr);
}

/* ---- floor plan: LA Convention Center ----
   Uses the official SIGGRAPH 2026 venue map SVGs (s2026.conference-schedule.org/map/).
   Each level (~250 KB) is fetched from lacc-level{1,2}.svg only when the map is first
   opened, so it never loads for the many visitors who never open it. Those SVGs ship as
   outlined vector art with no machine-readable room labels, so the highlight rects below
   were positioned by probing the map's own paths in a real browser (getBBox() on the path
   under each room, cross-checked against the rendered labels) rather than by tracing
   coordinates by hand. Both maps share one coordinate space: viewBox 0 0 4000 4000. */
const ROOM_ALIAS={'Hall K Lobby':'Hall K','Petree D Lobby':'Petree D','Room 411':'411 Theatre'};
const LACC_ZONES={
  'Hall K':{level:1,zone:'hallk',points:'1595.15 1705.56 1335.08 1445.49 1159.17 1464.94 739.46 1884.1 1223.47 2342.47 1573.5 1995.58 1597.91 1971.16 1595.15 1705.56'},
  'Concourse Hall':{level:1,zone:'concourse-hall',x:2150,y:2343,w:490,h:209},
  'Concourse Foyer':{level:1,zone:'concourse-foyer',points:'2650.7 2343.5 2870.3 2343.5 2870.3 2378.37 2738.69 2496.66 2753.08 2510.89 2663.31 2600.19 2650.7 2587.51'},
  'Petree C':{level:1,zone:'petree-c',x:3228,y:1842,w:154,h:233},
  'Petree D':{level:1,zone:'petree-d',x:3398,y:1842,w:189,h:233},
  'West Hall Lobby':{level:1,zone:'west-hall-lobby',d:'M2855.1,2426.3 Q3053.9,2600.5 3265.1,2426.3 L3140.7,2300.2 L3141.9,2120.2 L3171.9,2068.4 L2947.3,2068.4 L2984.0,2124.2 L2982.7,2301.8 Z'},
  'West Hall A':{level:1,zone:'west-hall-a',x:2962.15,y:1082.35,w:624.62,h:651.28},
  'Room 308':{level:2,zone:'r308',points:'1649.9 2109.4 1608.7 2150.5 1536.4 2078.2 1577.6 2037.1 1649.9 2109.4'},
  'Room 403 A':{level:2,zone:'r403a',x:1944,y:2294,w:91,h:204},
  'Room 403 B':{level:2,zone:'r403b',x:2044,y:2294,w:96,h:204},
  'Room 404 AB':{level:2,zone:'r404ab',x:2160.9,y:2204.7,w:83.5,h:293.8},
  'Room 406 AB':{level:2,zone:'r406ab',x:2254.1,y:2205.7,w:83.5,h:292},
  'Room 408 A':{level:2,zone:'r408a',x:2365,y:2294,w:83,h:204},
  'Room 408 B':{level:2,zone:'r408b',x:2459,y:2294,w:84,h:205},
  'Room 409 AB':{level:2,zone:'r409ab',x:2573,y:2294,w:84,h:207},
  '411 Theatre':{level:2,zone:'r411',points:'2667.6 2204 2897 2204 2897 2279.5 2667.6 2496.7 2667.6 2204'},
  'Room 501 ABC':{level:2,zone:'r501abc',x:2773,y:1824,w:98,h:168},
  'Room 502A':{level:2,zone:'r502a',x:2525,y:1823,w:113,h:169},
  'Room 502B':{level:2,zone:'r502b',x:2649,y:1823,w:113,h:169},
  'Room 510':{level:2,zone:'r510',x:3146,y:1642,w:57,h:68},
  'Room 511C':{level:2,zone:'r511c',x:3144.1,y:1944.5,w:73.8,h:52.5},
  'Room 512':{level:2,zone:'r512',x:3210, y:1642,w:55,h:68},
  'Room 513':{level:2,zone:'r513',x:3272,y:1642,w:56,h:68},
  'Room 515 A':{level:2,zone:'r515a',x:3225,y:1823,w:109,h:208},
  'Room 518':{level:2,zone:'r518',x:3454.5,y:1823.1,w:73.8,h:115.3},
};
function fpBuildOverlay(levelN){
  const wrap=document.getElementById('fpLevel'+levelN+'Wrap');
  const svg=wrap.querySelector('svg');
  const g=document.createElementNS('http://www.w3.org/2000/svg','g');
  g.setAttribute('id','fpOverlayG'+levelN);
  Object.values(LACC_ZONES).filter(z=>z.level===levelN).forEach(z=>{
    let shape;
    if(z.d){
      shape=document.createElementNS('http://www.w3.org/2000/svg','path');
      shape.setAttribute('d',z.d);
    }else if(z.points){
      shape=document.createElementNS('http://www.w3.org/2000/svg','polygon');
      shape.setAttribute('points',z.points);
    }else{
      shape=document.createElementNS('http://www.w3.org/2000/svg','rect');
      shape.setAttribute('x',z.x);shape.setAttribute('y',z.y);
      shape.setAttribute('width',z.w);shape.setAttribute('height',z.h);
    }
    shape.setAttribute('class','fp-zone-outline');
    shape.dataset.zone=z.zone;
    g.appendChild(shape);
  });
  svg.appendChild(g);
}
/* Fetch + inject a level's SVG the first time it's needed, then draw its overlay. */
const fpBuilt={1:false,2:false};
async function ensureFpLevel(n){
  if(fpBuilt[n])return true;
  const wrap=document.getElementById('fpLevel'+n+'Wrap');
  try{
    const res=await fetch('lacc-level'+n+'.svg',{cache:'force-cache'});
    if(!res.ok)throw new Error('HTTP '+res.status);
    wrap.innerHTML=await res.text();
    fpBuildOverlay(n);
    fpBuilt[n]=true;
    return true;
  }catch(e){
    document.getElementById('fpNote').textContent='Could not load the floor-plan map.';
    console.warn('Floor-plan SVG load failed for level '+n,e);
    return false;
  }
}
async function showFpLevel(n){
  const ok=await ensureFpLevel(n);
  setFpLevel(n);
  return ok;
}
function normRoomKey(s){return String(s||'').replace(/\s+/g,' ').trim();}
function findZone(roomStr){
  let s=ROOM_ALIAS[normRoomKey(roomStr)]||normRoomKey(roomStr);
  return LACC_ZONES[s]||null;
}
function setFpLevel(n){
  document.getElementById('fpLevel1Wrap').style.display=n===1?'block':'none';
  document.getElementById('fpLevel2Wrap').style.display=n===2?'block':'none';
  document.getElementById('fpLv1').setAttribute('aria-pressed',String(n===1));
  document.getElementById('fpLv2').setAttribute('aria-pressed',String(n===2));
}
async function openFloorPlan(roomStr){
  const z=findZone(roomStr);
  document.getElementById('fpRoomLabel').textContent=roomStr||'';
  const note=document.getElementById('fpNote');
  note.textContent=(roomStr&&!z)
    ? "This session's location isn't part of the LACC floor plan (it's an off-site venue) — no room to highlight."
    : '';
  // Show the modal immediately, then load the map for the level we need.
  document.getElementById('fpOverlay').classList.add('show');
  closePop();
  closeMapPop();
  closeSharePop();
  const level=z?z.level:1;
  await showFpLevel(level);
  document.querySelectorAll('.fp-zone-outline.hl').forEach(el=>el.classList.remove('hl'));
  if(z){
    const el=document.querySelector(`#fpOverlayG${z.level} [data-zone="${z.zone}"]`);
    if(el){el.classList.add('hl'); el.scrollIntoView({block:'center',inline:'center',behavior:'smooth'});}
  }
}
function closeFloorPlan(){document.getElementById('fpOverlay').classList.remove('show');}

/* ---- paste parser ---- */
function parsePaste(text){
  const raw=text.replace(/\s+/g,' ').trim();if(!raw)return null;
  const re=/(\d{1,2}(?::\d{2})?\s*[ap]m)\s*[-–]\s*(\d{1,2}(?::\d{2})?\s*[ap]m)\s*(?:PDT|PST|PT)?\s*(Sunday|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday),?\s*(\d{1,2})\s+July\s+2026\s*(.*)/i;
  const m=raw.match(re);if(!m)return null;
  const s=m[1].replace(/\s+/g,''),e=m[2].replace(/\s+/g,'');
  const dnum=parseInt(m[4],10);const dayObj=DAYS.find(d=>d.d===dnum);const day=dayObj?dayObj.iso:DAYS[0].iso;
  let title=raw.slice(0,m.index).trim();let program='';
  for(const kt of T_PROGRAM.concat(["Technical Paper","Production Session","Poster","Course","Panel","Talk"])){
    if(title.toLowerCase().startsWith(kt.toLowerCase())){program=kt;title=title.slice(kt.length).trim();break;}
  }
  const progMap={"Technical Paper":"Technical Papers","Production Session":"Production Sessions","Poster":"Posters","Course":"Courses","Panel":"Panels","Talk":"Talks"};
  program=progMap[program]||program;
  let tail=(m[5]||'').trim();
  tail=tail.split(new RegExp(T_IA.concat(T_REG,["Description","Experience","Discover"]).map(x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|'),'i'))[0].trim();
  return {title,program,day,s,e,room:tail.slice(0,60).trim()};
}

/* ---- ICS ---- */
function pad(n){return String(n).padStart(2,'0');}
function icsStamp(iso,mins){const [Y,M,D]=iso.split('-').map(Number);const dt=new Date(Date.UTC(Y,M-1,D,Math.floor(mins/60)+7,mins%60,0));return dt.getUTCFullYear()+pad(dt.getUTCMonth()+1)+pad(dt.getUTCDate())+'T'+pad(dt.getUTCHours())+pad(dt.getUTCMinutes())+'00Z';}
function exportICS(){
  const evs=[...picked.values()].filter(e=>e.s0!=null&&e.e0!=null);
  if(!evs.length){toast('Nothing to export yet');return;}
  let out=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//S2026 My Timetable//EN','CALSCALE:GREGORIAN','METHOD:PUBLISH'];
  const now=new Date();const stamp=now.getUTCFullYear()+pad(now.getUTCMonth()+1)+pad(now.getUTCDate())+'T'+pad(now.getUTCHours())+pad(now.getUTCMinutes())+pad(now.getUTCSeconds())+'Z';
  evs.forEach((e,i)=>{out.push('BEGIN:VEVENT','UID:s2026-'+i+'-'+Math.abs(hash(e.id))+'@timetable','DTSTAMP:'+stamp,'DTSTART:'+icsStamp(e.day,e.s0),'DTEND:'+icsStamp(e.day,e.e0),'SUMMARY:'+icsEsc(e.t));
    if(e.room)out.push('LOCATION:'+icsEsc(e.room+', Los Angeles Convention Center'));
    out.push('DESCRIPTION:'+icsEsc((e.program||'SIGGRAPH 2026')+' · priority '+PR_LABEL[e.pr]),'END:VEVENT');});
  out.push('END:VCALENDAR');
  download('siggraph2026-schedule.ics',out.join('\r\n'),'text/calendar');
  toast('Calendar file downloaded — open it to add '+evs.length+' sessions');
}
function icsEsc(s){return String(s).replace(/\\/g,'\\\\').replace(/;/g,'\\;').replace(/,/g,'\\,').replace(/\n/g,'\\n');}
function hash(s){let h=0;for(let i=0;i<s.length;i++){h=(h<<5)-h+s.charCodeAt(i);h|=0;}return h;}

/* ---- JSON import / export ---- */
function exportJSON(){download('siggraph2026-picks.json',JSON.stringify({v:2,picked:[...picked.values()].map(stripInternal)},null,2),'application/json');toast('Saved your picks to file');}
function stripInternal(e){const {hay,s0,e0,...rest}=e;return rest;}
function importJSON(file){
  const r=new FileReader();
  r.onload=()=>{
    try{
      const data=JSON.parse(r.result);
      let msg=[];
      const arr=Array.isArray(data)?data:(data.catalog||data.sessions);
      if(Array.isArray(arr)&&arr.length){catalog=arr.map(norm);msg.push(catalog.length+' sessions in catalog');}
      if(Array.isArray(data.picked)&&data.picked.length){data.picked.forEach(ev=>{const n=norm(ev);picked.set(n.id,n);});msg.push(data.picked.length+' picks');}
      saveState();buildFilterGroups();renderCatalog();renderTimetable();syncDayTabs();
      toast(msg.length?('Loaded '+msg.join(' + ')):'Nothing importable found in that file');
    }catch(e){toast('Could not read that file');}
  };
  r.readAsText(file);
}

const sharePop=document.getElementById('sharePop');
function openSharePop(anchor){
  closePop();closeMapPop();
  const url=location.href;
  sharePop.innerHTML=`<div class="share-title">Scan to open this page</div>
    <canvas id="qrCanvas"></canvas>
    <div class="share-url mono">${esc(url)}</div>
    <div class="pop-actions">
      <button class="pop-link" id="btnCopyLink" type="button">⧉ Copy link</button>
      ${navigator.share?'<button class="pop-link" id="btnNativeShare" type="button">↗ Share…</button>':''}
    </div>`;
  try{drawQR(document.getElementById('qrCanvas'),url);}
  catch(e){document.getElementById('qrCanvas').replaceWith('QR code unavailable for this link');}
  document.getElementById('btnCopyLink').onclick=()=>{
    navigator.clipboard.writeText(url).then(()=>toast('Link copied')).catch(()=>toast('Could not copy — copy it from the address bar'));};
  const nsBtn=document.getElementById('btnNativeShare');
  if(nsBtn)nsBtn.onclick=()=>{navigator.share({title:document.title,url}).catch(()=>{});};
  sharePop.classList.add('show');
  const r=anchor.getBoundingClientRect();
  const pw=236,ph=sharePop.offsetHeight||300;
  let left=window.scrollX+r.right-pw; if(left<10)left=window.scrollX+10;
  let top=window.scrollY+r.bottom+6; if(top+ph>window.scrollY+window.innerHeight-10)top=window.scrollY+r.top-ph-6;
  sharePop.style.left=Math.max(10,left)+'px';sharePop.style.top=Math.max(10,top)+'px';
}
function closeSharePop(){sharePop.classList.remove('show');}
document.addEventListener('click',e=>{if(!sharePop.contains(e.target)&&e.target.id!=='btnShare')closeSharePop();});
window.addEventListener('resize',closeSharePop);

/* ---- utils ---- */
function esc(s){return String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function download(name,text,mime){const b=new Blob([text],{type:mime});const u=URL.createObjectURL(b);const a=document.createElement('a');a.href=u;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(u),1500);}
let toastT;
function toast(msg){
  const t=document.getElementById('toast');
  t.textContent=msg;
  t.classList.remove('with-action');
  t.classList.add('show');
  clearTimeout(toastT);
  toastT=setTimeout(()=>t.classList.remove('show'),2000);
}
function toastWithUndo(msg,onUndo){
  const t=document.getElementById('toast');
  t.innerHTML=`<span>${esc(msg)}</span><button class="toast-undo" type="button">Undo</button>`;
  t.classList.add('show','with-action');
  clearTimeout(toastT);
  t.querySelector('.toast-undo').onclick=()=>{
    clearTimeout(toastT);
    t.classList.remove('show','with-action');
    onUndo();
  };
  toastT=setTimeout(()=>t.classList.remove('show','with-action'),5000);
}

/* ---- manual add ---- */
function addCustomFromForm(){
  const t=document.getElementById('fTitle').value.trim();
  const sRaw=document.getElementById('fStart').value.trim(),eRaw=document.getElementById('fEnd').value.trim();
  const s=parseTime(sRaw);if(!t){toast('Add a title first');return;}if(s==null){toast('Check the start time (e.g. 2:00pm)');return;}
  const n=norm({t,program:document.getElementById('fType').value.trim()||'Session',day:document.getElementById('fDay').value,s:sRaw,e:eRaw||fmtTime(s+30),room:document.getElementById('fRoom').value.trim(),pr:2});
  picked.set(n.id,n);
  if(!catalog.find(c=>c.id===n.id))catalog.push(n);
  activeDay=n.day;saveState();refreshFilterCounts();renderCatalog();renderTimetable();syncDayTabs();
  ['fTitle','fStart','fEnd','fRoom','pasteBox'].forEach(id=>document.getElementById(id).value='');
  toast('Added “'+t.slice(0,30)+(t.length>30?'…':'')+'”');
}

/* ---- wire up ---- */
document.addEventListener('DOMContentLoaded',async ()=>{
  await loadCatalog();
  buildDayControls();
  loadState();
  buildFilterGroups();
  renderCatalog();renderTimetable();syncDayTabs();

  const themeSel=document.getElementById('themeSelect');
  if(themeSel){themeSel.value=curTheme();themeSel.onchange=()=>applyTheme(themeSel.value);}
  document.getElementById('search').addEventListener('input',e=>{searchQ=e.target.value;renderCatalog();});
  document.getElementById('ftoggle').onclick=()=>{const p=document.getElementById('filterPanel');const open=p.classList.toggle('open');document.getElementById('ftoggle').setAttribute('aria-expanded',String(open));};
  document.getElementById('btnAddSession').onclick=()=>{const p=document.getElementById('adderD');const open=p.classList.toggle('open');document.getElementById('btnAddSession').setAttribute('aria-expanded',String(open));if(open)p.scrollIntoView({block:'nearest',behavior:'smooth'});};
  document.getElementById('clearFilters').onclick=()=>{Object.values(F).forEach(s=>s.clear());filterDay='';syncDayChips();document.querySelectorAll('.fgroup input').forEach(cb=>cb.checked=false);renderCatalog();syncFilterCounts();toast('Filters cleared');};

  document.getElementById('btnIcs').onclick=exportICS;
  document.getElementById('btnExportJson').onclick=exportJSON;
  document.getElementById('btnFloorPlan').onclick=()=>openFloorPlan('');
  document.getElementById('btnShare').onclick=(e)=>{sharePop.classList.contains('show')?closeSharePop():openSharePop(e.currentTarget);};
  document.getElementById('fpClose').onclick=closeFloorPlan;
  document.getElementById('fpOverlay').addEventListener('click',e=>{if(e.target.id==='fpOverlay')closeFloorPlan();});
  document.getElementById('fpLv1').onclick=()=>showFpLevel(1);
  document.getElementById('fpLv2').onclick=()=>showFpLevel(2);
  document.addEventListener('keydown',e=>{if(e.key==='Escape')closeFloorPlan();});
  document.getElementById('btnLoadFile').onclick=()=>document.getElementById('fileInput').click();
  document.getElementById('fileInput').addEventListener('change',e=>{if(e.target.files[0])importJSON(e.target.files[0]);e.target.value='';});
  document.getElementById('btnClear').onclick=()=>{if(!picked.size){toast('Timetable is already empty');return;}if(confirm('Remove all picked sessions? Your browse catalog stays.')){picked.clear();saveState();renderCatalog();renderTimetable();syncDayTabs();toast('Cleared picks');}};
  document.getElementById('btnAddCustom').onclick=addCustomFromForm;
  document.getElementById('btnClearForm').onclick=()=>{['fTitle','fStart','fEnd','fRoom','fType','pasteBox'].forEach(id=>document.getElementById(id).value='');};
  document.getElementById('btnParse').onclick=()=>{
    const p=parsePaste(document.getElementById('pasteBox').value);
    if(!p){toast('Could not find a time + date in that paste');return;}
    document.getElementById('fTitle').value=p.title;document.getElementById('fType').value=p.program;document.getElementById('fDay').value=p.day;document.getElementById('fStart').value=p.s;document.getElementById('fEnd').value=p.e;document.getElementById('fRoom').value=p.room;
    toast('Read — check the fields, then Add');
  };

  const swB=document.getElementById('swBrowse'),swD=document.getElementById('swDay');
  const setView=w=>{swB.setAttribute('aria-pressed',String(w==='browse'));swD.setAttribute('aria-pressed',String(w==='day'));document.getElementById('browseCol').dataset.hidden=String(w!=='browse');document.getElementById('dayCol').dataset.hidden=String(w!=='day');};
  swB.onclick=()=>setView('browse');swD.onclick=()=>setView('day');
  if(window.matchMedia('(max-width:920px)').matches)setView('browse');
  window.addEventListener('resize',()=>{const mobile=window.matchMedia('(max-width:920px)').matches;if(!mobile){document.getElementById('browseCol').dataset.hidden='false';document.getElementById('dayCol').dataset.hidden='false';}});
});

/* Minimal surface for the check_page.py smoke tests (ES module scope hides the app's internals from the global namespace). */
window.App = {
  get catalog(){ return catalog; },
  get picked(){ return picked; },
  get pop(){ return pop; },
  togglePick,
  openFloorPlan,
};
