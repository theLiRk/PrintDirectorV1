const DEFAULT_SETTINGS={theme:'dark',background_color:'#0b0e14',text_color:'#f5f7fa',accent_color:'#38bdf8',panel_opacity:0.92,font_family:'system-ui',font_scale:1,show_filename:true,show_state:true,show_eta:true,show_temps:true,show_layers:true};
let overlaySettings={...DEFAULT_SETTINGS};
let socket=null;
let reconnectDelay=500;
let reconnectTimer=null;

const clamp=(value,min,max)=>Math.min(Math.max(value,min),max);
const fmt=s=>s==null?'--':`${Math.floor(s/3600)}:${String(Math.floor(s/60)%60).padStart(2,'0')}`;
const numeric=value=>Number.isFinite(Number(value))?Number(value):null;
const temp=(a,b)=>`${numeric(a)==null?'--':numeric(a).toFixed(0)}° / ${numeric(b)==null?'--':numeric(b).toFixed(0)}°`;

function getToken(){
  const saved=localStorage.getItem('printdirector-token');
  if(saved&&saved.trim())return saved.trim();
  const fromQuery=new URLSearchParams(location.search).get('token');
  return fromQuery?fromQuery.trim():null;
}
function authHeaders(){const token=getToken();return token?{Authorization:`Bearer ${token}`}:{ };}

function applySettings(settings){
  overlaySettings={...DEFAULT_SETTINGS,...settings,printer_overrides:settings.printer_overrides||{}};
  const s=overlaySettings;
  document.body.setAttribute('data-theme',s.theme);
  document.body.classList.toggle('dashboard-light',document.body.classList.contains('dashboard-page')&&s.theme==='light');
  document.body.style.setProperty('--accent',s.accent_color);
  document.body.style.setProperty('--card-bg',`rgba(13,18,28,${s.panel_opacity})`);
  document.body.style.color=s.text_color;
  document.body.style.background=document.body.classList.contains('dashboard-page')?'':(s.theme==='light'?'#f8fafc':'transparent');
  document.body.style.fontFamily=s.font_family||'system-ui';
  document.body.style.fontSize=`${Number(s.font_scale||1).toFixed(2)}rem`;
}

function resolvePrinterSettings(p,settings=overlaySettings){
  const override=(settings.printer_overrides||{})[p.printer_id]||{};
  return {...DEFAULT_SETTINGS,...settings,...override};
}

function ensureCard(el){
  if(el.dataset.initialized==='true')return;
  el.dataset.initialized='true';
  el.classList.add('card');
  const header=document.createElement('div'); header.className='meta';
  const name=document.createElement('span'); name.className='name'; name.dataset.field='name';
  const state=document.createElement('span'); state.className='state'; state.dataset.field='state';
  header.append(name,state);
  const file=document.createElement('div'); file.className='file'; file.dataset.field='file';
  const bar=document.createElement('div'); bar.className='bar';
  const fill=document.createElement('i'); fill.dataset.field='progress-bar'; bar.append(fill);
  const progressRow=document.createElement('div'); progressRow.className='meta';
  const percentage=document.createElement('span'); percentage.dataset.field='percentage';
  const eta=document.createElement('span'); eta.dataset.field='eta'; progressRow.append(percentage,eta);
  const tempRow=document.createElement('div'); tempRow.className='meta'; tempRow.dataset.row='temps';
  const hotend=document.createElement('span'); hotend.dataset.field='hotend';
  const bed=document.createElement('span'); bed.dataset.field='bed'; tempRow.append(hotend,bed);
  const layer=document.createElement('div'); layer.dataset.field='layer';
  el.append(header,file,bar,progressRow,tempRow,layer);
}

function setText(el,selector,value){const node=el.querySelector(selector);if(node&&node.textContent!==value)node.textContent=value;}
function setVisible(el,selector,visible){const node=el.querySelector(selector);if(node)node.style.display=visible?'':'none';}

function updateCard(el,p,settings=overlaySettings){
  ensureCard(el);
  const s=resolvePrinterSettings(p,settings);
  const progress=clamp(Number(p.progress||0),0,1);
  el.dataset.printerId=p.printer_id;
  el.classList.toggle('offline',!p.online);
  el.classList.toggle('stale',Boolean(p.stale));
  el.style.borderColor=p.stale?'#fbbf24':s.accent_color;
  el.style.fontFamily=s.font_family||'system-ui';
  el.style.color=s.text_color;
  setText(el,'[data-field="name"]',s.label_override||p.printer_name||'Unknown printer');
  setText(el,'[data-field="state"]',p.stale?'stale telemetry':(p.state||'offline'));
  setText(el,'[data-field="file"]',p.filename||'No active file');
  setText(el,'[data-field="percentage"]',`${(progress*100).toFixed(1)}%`);
  setText(el,'[data-field="eta"]',`ETA ${fmt(p.estimated_remaining)}`);
  setText(el,'[data-field="hotend"]',`Hotend ${temp(p.hotend_temperature,p.hotend_target)}`);
  setText(el,'[data-field="bed"]',`Bed ${temp(p.bed_temperature,p.bed_target)}`);
  setText(el,'[data-field="layer"]',`Layer ${p.current_layer??'--'} / ${p.total_layers??'--'}`);
  const fill=el.querySelector('[data-field="progress-bar"]');
  if(fill){fill.style.width=`${(progress*100).toFixed(2)}%`;fill.style.background=p.stale?'#fbbf24':s.accent_color;}
  setVisible(el,'[data-field="state"]',s.show_state);
  setVisible(el,'[data-field="file"]',s.show_filename);
  setVisible(el,'[data-field="eta"]',s.show_eta);
  setVisible(el,'[data-row="temps"]',s.show_temps);
  setVisible(el,'[data-field="layer"]',s.show_layers&&p.current_layer!=null);
}

function render(data){
  const printers=Array.isArray(data.printers)?data.printers:[];
  const single=document.querySelector('#printer');
  if(single){
    const p=printers.find(x=>x.printer_id===single.dataset.id);
    if(p)updateCard(single,p,overlaySettings);
  }
  const overview=document.querySelector('#overview');
  if(overview){
    const wanted=new Set(printers.map(p=>p.printer_id));
    overview.querySelectorAll('[data-printer-id]').forEach(el=>{if(!wanted.has(el.dataset.printerId))el.remove();});
    printers.forEach(p=>{
      let el=overview.querySelector(`[data-printer-id="${CSS.escape(p.printer_id)}"]`);
      if(!el){el=document.createElement('section');el.dataset.printerId=p.printer_id;overview.appendChild(el);}
      updateCard(el,p,overlaySettings);
    });
  }
  const director=document.querySelector('#director');
  if(director){
    const d=data.director||{};
    const state=d.obs_stream_state||(d.obs_streaming?'streaming':'off');
    director.textContent=`Auto: ${d.auto_enabled?'ON':'OFF'} | OBS: ${d.obs_connected?'connected':'offline'} | Scene: ${d.current_scene||'--'} | Stream: ${state}`;
  }
  window.dispatchEvent(new CustomEvent('printdirector-update',{detail:data}));
}

async function fetchSnapshot(){
  try{
    const res=await fetch('/api/printers',{headers:authHeaders()});
    if(!res.ok)return;
    const printers=await res.json();
    const directorRes=await fetch('/api/director/status',{headers:authHeaders()});
    let director={auto_enabled:false,obs_connected:false,current_scene:'--',obs_streaming:false,obs_stream_state:'unknown'};
    if(directorRes.ok)director=await directorRes.json();
    render({printers,director});
  }catch(err){console.warn('Overlay refresh failed',err);}
}

async function loadSettings(){
  try{
    const res=await fetch('/api/settings',{headers:authHeaders()});
    if(!res.ok)return;
    const settings=await res.json();
    applySettings(settings);
  }catch(err){console.warn('Overlay settings unavailable',err);}
}

function socketUrl(){
  const protocol=location.protocol==='https:'?'wss:':'ws:';
  const url=new URL(`${protocol}//${location.host}/ws/printers`);
  const token=getToken();
  if(token)url.searchParams.set('token',token);
  return url.toString();
}

function scheduleReconnect(){
  if(reconnectTimer)return;
  reconnectTimer=setTimeout(()=>{reconnectTimer=null;connectSocket();},reconnectDelay);
  reconnectDelay=Math.min(reconnectDelay*2,5000);
}

function connectSocket(){
  if(socket&&(socket.readyState===WebSocket.OPEN||socket.readyState===WebSocket.CONNECTING))return;
  socket=new WebSocket(socketUrl());
  socket.onopen=()=>{reconnectDelay=500;};
  socket.onmessage=event=>{try{render(JSON.parse(event.data));}catch(err){console.warn('Invalid overlay update',err);}};
  socket.onclose=()=>{socket=null;scheduleReconnect();};
  socket.onerror=()=>{if(socket)socket.close();};
}

loadSettings().finally(connectSocket);
setInterval(()=>{if(!socket||socket.readyState!==WebSocket.OPEN)fetchSnapshot();},10000);
