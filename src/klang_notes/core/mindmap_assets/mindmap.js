// Compute the complete layout once per style, before applying branch visibility.
const $ = id => document.getElementById(id);
const variants = {A: ['Radial rings','LECTURE OVERVIEW','A place for every idea.'], C: ['Topic circles','LECTURE OVERVIEW','A place for every idea.']};
// Each group has a readable accent, a quiet surface, and a saturated focus fill.
// The 15 hues sit at least 20 degrees apart; neighbouring groups get far-apart hues.
const palette = [
 ['#58735a','#e7ece0','#3d5e42'],['#96713d','#f0e7d6','#795522'],
 ['#62758e','#e5e9ef','#445d7d'],['#9a6870','#f1e3e3','#7b4752'],
 ['#80708d','#eae4ee','#645071'],['#547c75','#e1ece6','#38635a'],
 ['#5a7e87','#e2ecee','#39616a'],['#87635a','#eee4e2','#6a4339'],
 ['#5c5a87','#e2e2ee','#3c396a'],['#78875a','#eaeee2','#5b6a39'],
 ['#875a75','#eee2e9','#6a3956'],['#5a876d','#e2eee7','#396a4e'],
 ['#87845a','#eeeee2','#6a6839'],['#865a87','#eee2ee','#69396a'],
 ['#67875a','#e5eee2','#486a39']
];
// The main topic stays in the Linen neutrals so no group shares its colour.
const mainTopicColors = ['#756a59','#f8f4ec','#433b31'];
const nodes = DATA.map(n => ({...n,children:[],depth:0,group:-1,x:0,y:0,w:220,h:96}));
nodes.forEach(n=>{if(n.parent!==null){nodes[n.parent].children.push(n.id);n.depth=nodes[n.parent].depth+1;n.group=n.depth===1?nodes[0].children.indexOf(n.id):nodes[n.parent].group;}});
let variant = new URLSearchParams(location.search).get('variant');
if(!variants[variant]) variant='A';
let depth = new URLSearchParams(location.search).get('depth') || '2';
if(!['1','2','all'].includes(depth)) depth='2';
// The opening view never zooms out past the point where group labels stop being readable.
const OPENING_MIN_SCALE=.55,WHOLE_MIN_SCALE=.02;
let collapsed=new Set(),selected=null,scale=1,tx=0,ty=0,drag=null,minScale=OPENING_MIN_SCALE;
const svgNS='http://www.w3.org/2000/svg';
function el(tag,attrs={}) {const e=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e;}
function groupColors(group) {
  if (group < 0) return mainTopicColors;
  if (group < palette.length) return palette[group];
  const hue = (group * 137.508) % 360;
  return [`hsl(${hue} 24% 38%)`, `hsl(${hue} 26% 91%)`, `hsl(${hue} 30% 30%)`];
}
function visible(n){if(n.parent===null)return true;return !collapsed.has(n.parent)&&visible(nodes[n.parent]);}
function resetDepth(){collapsed=new Set(nodes.filter(n=>n.children.length&&depth!=='all'&&n.depth>=Number(depth)).map(n=>n.id));}
function coordinates(){
  const sizes=[[400,190],[310,148],[260,120],[220,100]];
  nodes.forEach(n=>{n.x=0;n.y=0;[n.w,n.h]=sizes[Math.min(n.depth,sizes.length-1)];});
  const leaves=id=>nodes[id].children.length?nodes[id].children.reduce((sum,c)=>sum+leaves(c),0):1;
  const polar=(n,r,a)=>{n.x=Math.cos(a)*r;n.y=Math.sin(a)*r*.76;};
  if(variant==='A'){
    // Reserve angular sectors for the complete tree, including folded descendants.
    const total=leaves(0),step=Math.PI*2/total;
    const place=(id,start)=>{const n=nodes[id],count=leaves(id);n.angle=-Math.PI/2+(start+count/2)*step;
      if(id!==0)polar(n,(n.depth < 3 ? [0,520,1040][n.depth] : 1480+(n.depth-3)*440),n.angle);
      let cursor=start;n.children.forEach(c=>{place(c,cursor);cursor+=leaves(c);});};
    place(0,0);
  }else{
    // Each topic is the centre of a complete local ring of its own children.
    // The same rule applies recursively to subtopics such as the exercise group.
    const surround=id=>{
      const n=nodes[id],p=nodes[n.parent],count=n.children.length;
      const radiusX=Math.max(n.children.some(c=>nodes[c].children.length)?560:350,count*70);
      const radiusY=Math.max(260,count*45);
      // The edge from the parent arrives along `inward`. Rotating the ring so that
      // direction falls midway between two children keeps the edge off them.
      const inward=Math.atan2(p.y-n.y,p.x-n.x);
      const start=Math.atan2(Math.sin(inward)*radiusX,Math.cos(inward)*radiusY)+Math.PI/count;
      n.children.forEach((cid,j)=>{
        const angle=start+j*Math.PI*2/count,c=nodes[cid];
        c.x=n.x+Math.cos(angle)*radiusX;c.y=n.y+Math.sin(angle)*radiusY;
        surround(cid);
      });
    };
    nodes[0].children.forEach((id,i)=>{
      const angle=-Math.PI/2+i*Math.PI*2/nodes[0].children.length,n=nodes[id];
      const radius=Math.max(1200,nodes[0].children.length*200);
      n.x=Math.cos(angle)*radius;n.y=Math.sin(angle)*radius*.75;
      // Pairs sit either side of the parent's edge; larger groups form a complete ring.
      surround(id);
    });
  }
  separateNodes();
}
function separateNodes(){
  const gapX=24,gapY=20,placed=[];
  const overlaps=(n,m,x=n.x,y=n.y)=>Math.abs(x-m.x)<(n.w+m.w)/2+gapX&&Math.abs(y-m.y)<(n.h+m.h)/2+gapY;
  const moveBranch=(id,dx,dy)=>{const n=nodes[id];n.x+=dx;n.y+=dy;n.children.forEach(child=>moveBranch(child,dx,dy));};
  nodes.forEach(n=>{
    if(placed.some(m=>overlaps(n,m))){
      const candidates=placed.flatMap(m=>[
        {x:m.x+(m.w+n.w)/2+gapX,y:n.y},
        {x:m.x-(m.w+n.w)/2-gapX,y:n.y},
        {x:n.x,y:m.y+(m.h+n.h)/2+gapY},
        {x:n.x,y:m.y-(m.h+n.h)/2-gapY}
      ]);
      const free=candidates.filter(p=>placed.every(m=>!overlaps(n,m,p.x,p.y)));
      free.sort((a,b)=>Math.hypot(a.x-n.x,a.y-n.y)-Math.hypot(b.x-n.x,b.y-n.y));
      moveBranch(n.id,free[0].x-n.x,free[0].y-n.y);
    }
    placed.push(n);
  });
}
function connection(p,n){
  if(variant==='A'){
    const r=Math.hypot(n.x,n.y),pr=Math.hypot(p.x,p.y),bend=(r-pr)*.48;
    const a=Math.atan2(n.y,n.x),pa=p.id===0?a:Math.atan2(p.y,p.x);
    return `M ${p.x} ${p.y} C ${p.x+Math.cos(pa)*bend} ${p.y+Math.sin(pa)*bend},${n.x-Math.cos(a)*bend} ${n.y-Math.sin(a)*bend},${n.x} ${n.y}`;
  }
  const dx=n.x-p.x,dy=n.y-p.y;
  // Connect each satellite directly to its own topic, with a slight soft bow.
  return `M ${p.x} ${p.y} Q ${p.x+dx*.5-dy*.06} ${p.y+dy*.5+dx*.06} ${n.x} ${n.y}`;
}
function syncURL(){const url=new URL(location.href);url.searchParams.set('variant',variant);url.searchParams.set('depth',depth);history.replaceState(null,'',url);}
function render(){
  const world=$('world');world.replaceChildren();
  nodes.filter(visible).forEach(n=>{
    if(n.parent===null)return;
    const p=nodes[n.parent];const edge=el('path',{class:'edge'});edge.style.setProperty('--group',groupColors(n.group)[0]);
    edge.setAttribute('d',connection(p,n));
    world.append(edge);
  });
  nodes.filter(visible).forEach(n=>{
    const group=el('foreignObject',{x:n.x-n.w/2,y:n.y-n.h/2,width:n.w,height:n.h,class:`node ${n.id===0?'root':''}`,'data-node':n.id,'data-depth':Math.min(n.depth,3)});
    const shell=document.createElement('div');shell.setAttribute('xmlns','http://www.w3.org/1999/xhtml');shell.className='node-shell';
    const [color,tint]=groupColors(n.group);shell.style.setProperty('--group',color);shell.style.setProperty('--tint',tint);shell.style.setProperty('--fill',(groupColors(n.group))[2]);
    const card=document.createElement('div');card.className='node-card'+(n.id===selected?' selected':'');
    const label=document.createElement('button');label.className='node-label';label.textContent=n.label;label.lang='sv';label.setAttribute('aria-label',`Explore ${n.label}`);label.setAttribute('aria-pressed',String(n.id===selected));label.onclick=()=>select(n.id);
    const footer=document.createElement('div');footer.className='node-footer';
    const stamps=document.createElement('span');stamps.className='node-stamps';
    n.links.forEach(timestamp=>{
      const link=document.createElement('a');link.className='stamp';link.href=timestamp.url;
      link.target='_blank';link.rel='noopener';link.textContent=timestamp.text;
      link.setAttribute('aria-label',`Open Source at ${timestamp.text}`);stamps.append(link);
    });
    footer.append(stamps);
    if(n.children.length){const toggle=document.createElement('button');toggle.className='branch-toggle';toggle.textContent=collapsed.has(n.id)?`+ ${n.children.length}`:'−';toggle.setAttribute('aria-expanded',String(!collapsed.has(n.id)));toggle.setAttribute('aria-label',`${collapsed.has(n.id)?'Reveal':'Hide'} children of ${n.label}`);toggle.onclick=()=>{if(collapsed.has(n.id))collapsed.delete(n.id);else collapsed.add(n.id);render();};footer.append(toggle);}
    card.append(label,footer);shell.append(card);group.append(shell);world.append(group);
  });
  transform();
}
function transform(){
  $('world').setAttribute('transform',`translate(${tx} ${ty}) scale(${scale})`);
  $('zoom').textContent=`${Math.round(scale*100)}%`;
}
function fit(floor=minScale){
  minScale=floor;
  const shown=nodes.filter(visible),rect=$('canvas').getBoundingClientRect();
  const minX=Math.min(...shown.map(n=>n.x-n.w/2)),maxX=Math.max(...shown.map(n=>n.x+n.w/2));
  const minY=Math.min(...shown.map(n=>n.y-n.h/2)),maxY=Math.max(...shown.map(n=>n.y+n.h/2));
  const horizontalMargin=50,verticalMargin=100,root=nodes[0];
  const halfWidth=Math.max(root.x-minX,maxX-root.x),halfHeight=Math.max(root.y-minY,maxY-root.y);
  scale=Math.max(floor,Math.min(1.15,(rect.width/2-horizontalMargin)/halfWidth,(rect.height/2-verticalMargin)/halfHeight));
  centre(root);
}
function centre(n){const rect=$('canvas').getBoundingClientRect();tx=rect.width/2-n.x*scale;ty=rect.height/2-n.y*scale;transform();}
function select(id){
  selected=id;const n=nodes[id];$('panel').hidden=false;
  document.body.style.setProperty('--selected-color',(groupColors(n.group))[0]);
  const path=[];let p=n.parent;while(p!==null){path.unshift(nodes[p].label);p=nodes[p].parent;}
  $('panel-path').textContent=path.join(' / ')||'Lecture overview';$('panel-title').textContent=n.label;$('explanation').textContent=n.explanation||'Open the Source to explore this idea in context.';
  const timestamp=n.links[0];
  $('panel-source').href=timestamp?timestamp.url:PAGE.source_url;
  $('panel-source').textContent=timestamp?`▶  Open Source at ${timestamp.text} ↗`:'Open Source ↗';
  $('related').replaceChildren();
  const related=n.children.length?n.children:(n.parent===null?[]:nodes[n.parent].children.filter(c=>c!==id));
  related.slice(0,4).forEach(cid=>{const b=document.createElement('button');b.textContent=nodes[cid].label;b.lang='sv';b.onclick=()=>{let p=nodes[cid].parent;while(p!==null){collapsed.delete(p);p=nodes[p].parent;}select(cid);};$('related').append(b);});
  document.querySelector('.related').hidden=!related.length;
  $('panel').scrollTop=0;render();centre(n);
}
function zoom(factor,x,y){const rect=$('canvas').getBoundingClientRect();x??=rect.width/2;y??=rect.height/2;const next=Math.max(.02,Math.min(2,scale*factor));tx=x-(x-tx)*next/scale;ty=y-(y-ty)*next/scale;scale=next;transform();}
function choose(key){variant=key;document.body.dataset.variant=key;document.body.style.setProperty('--selected-color',groupColors(selected===null?-1:nodes[selected].group)[0]);document.querySelectorAll('input[name="mindmap-style"]').forEach(input=>{input.checked=input.value===key;});$('map-kicker').textContent=variants[key][1];$('map-intro').textContent=variants[key][2];syncURL();coordinates();render();fit(OPENING_MIN_SCALE);}
function setSettings(open,restoreFocus=false){
  $('mindmap-settings').hidden=!open;
  $('settings-toggle').setAttribute('aria-expanded',String(open));
  if(open)$(variant==='C'?'style-topic-circles':'style-radial-rings').focus();
  else if(restoreFocus)$('settings-toggle').focus();
}
$('settings-toggle').onclick=()=>setSettings($('mindmap-settings').hidden);
document.querySelectorAll('input[name="mindmap-style"]').forEach(input=>{
  input.addEventListener('change',()=>{if(input.checked)choose(input.value);});
});
document.addEventListener('pointerdown',e=>{if(!$('settings').contains(e.target))setSettings(false);});
$('depth').value=depth;
$('depth').onchange=e=>{depth=e.target.value;resetDepth();syncURL();render();fit(OPENING_MIN_SCALE);};
$('reopen').onclick=()=>{selected=null;$('panel').hidden=true;resetDepth();render();fit(OPENING_MIN_SCALE);};
$('fit').onclick=()=>{collapsed.clear();render();fit(WHOLE_MIN_SCALE);};
$('close').onclick=()=>{selected=null;$('panel').hidden=true;render();};
$('in').onclick=()=>zoom(1.2);$('out').onclick=()=>zoom(1/1.2);
$('canvas').addEventListener('wheel',e=>{e.preventDefault();const r=$('canvas').getBoundingClientRect();zoom(Math.exp(-e.deltaY*.002),e.clientX-r.left,e.clientY-r.top);},{passive:false});
$('canvas').addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button,a'))return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,tx,ty};$('canvas').setPointerCapture(e.pointerId);$('canvas').classList.add('dragging');});
$('canvas').addEventListener('pointermove',e=>{if(!drag)return;tx=drag.tx+e.clientX-drag.x;ty=drag.ty+e.clientY-drag.y;transform();});
function stopDrag(){drag=null;$('canvas').classList.remove('dragging');}
$('canvas').addEventListener('pointerup',stopDrag);$('canvas').addEventListener('pointercancel',stopDrag);
document.addEventListener('keydown',e=>{
  if(e.key!=='Escape')return;
  if(!$('mindmap-settings').hidden){e.preventDefault();setSettings(false,true);}
  else if(!$('panel').hidden)$('close').click();
});
window.addEventListener('resize',()=>{if(selected!==null)centre(nodes[selected]);else fit();});
resetDepth();choose(variant);
