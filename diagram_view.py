from html import escape
import math
import streamlit.components.v1 as components

def diagram(nodes, links, targets, fields=(), height=460):
    # Fixed-size nodes and explicit pixel canvas: never stretch a small graph.
    nodes=list(nodes)
    adjacency={n:[] for n in nodes}
    for edge in links:
        adjacency[edge.child].append(edge.parent)
        adjacency[edge.parent].append(edge.child)
    levels={}
    root=next((t for t in targets if t in adjacency),nodes[0])
    queue=[root]; levels[root]=0
    for current in queue:
        for other in adjacency[current]:
            if other not in levels:
                levels[other]=levels[current]+1;queue.append(other)
    for n in nodes:
        levels.setdefault(n,0)
    node_width=max(370,max(len(n) for n in nodes)*9+32)
    counts={};positions={}
    for n in nodes:
        level=levels[n]; row=counts.get(level,0);counts[level]=row+1
        positions[n]=(40+level*(node_width+220),60+row*210)
    width=(max(levels.values())+1)*(node_width+220)+80
    total_height=max(counts.values())*210+100
    parts=[]
    for i,e in enumerate(links):
        x,y=positions[e.child];u,v=positions[e.parent]
        if x <= u:
            x+=node_width
        else:
            u+=node_width
        y+=35;v+=35
        bend=35+(i%4)*18
        parts.append(f'<path d="M{x},{y} Q{(x+u)/2},{(y+v)/2-bend} {u},{v}" stroke="#6cbcaa" stroke-width="1.6" fill="none"/>')
        label=escape(f'{e.child_column} = {e.parent_column}')
        parts.append(f'<text x="{(x+u)/2}" y="{(y+v)/2-bend/2}" text-anchor="middle" fill="#d2e8e1" font-size="13" paint-order="stroke" stroke="#151918" stroke-width="4">{label}</text>')
    for n,(x,y) in positions.items():
        color = '#293326' if n in targets else '#222a2a'
        border = '#d8f87a' if n in targets else '#507d73'
        parts.append(f'<title>{escape(n)}</title>')
        parts.append(f'<rect x="{x}" y="{y}" width="{node_width}" height="70" rx="12" fill="{color}" stroke="{border}"/>')
        parts.append(f'<text x="{x+12}" y="{y+26}" fill="#f4f5ef" font-weight="700" font-size="15">{escape(n)}</text>')
        selected=', '.join(f.rpartition('.')[2] for f in fields if f.rpartition('.')[0]==n)
        parts.append(f'<text x="{x+12}" y="{y+49}" fill="#a5d2c6" font-size="13">{escape(selected[:45])}</text>')
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}" viewBox="0 0 {width} {total_height}">'+''.join(parts)+'</svg>'
    components.html('''<style>
@font-face { font-family: Manrope; src: url("./app/static/manrope.ttf") format("truetype"); font-weight: 200 800; font-display: swap; }
* { box-sizing: border-box; }
html { color-scheme: dark; }
body { margin: 0; color: #f4f5ef; background: #151918; font: 13px Manrope, "Segoe UI", sans-serif; }
.shell { height: 100vh; overflow: hidden; border: 1px solid #343b38; border-radius: 13px; display: flex; flex-direction: column; }
nav { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; padding: 7px; background: #212624; border-bottom: 1px solid #363d38; }
button { font: inherit; color: #eef2e8; background: #292e2b; border: 1px solid #414942; border-radius: 7px; padding: 6px 8px; cursor: pointer; transition: background .15s, color .15s; }
button:hover { background: #35402b; color: #d8f87a; }
button:focus-visible { outline: 2px solid #d8f87a; outline-offset: 2px; }
nav span { margin-left: auto; color: #d8f87a; font-variant-numeric: tabular-nums; padding-inline: 3px; }
#viewport { flex: 1; overflow: auto; background: radial-gradient(circle, #77918536 1px, transparent 1.3px) 0 0 / 21px 21px, #151918; }
svg { display: block; max-width: none; max-height: none; font-family: "Cascadia Mono", Consolas, monospace; }
@media (max-width: 370px) { nav { gap: 4px; } button { padding-inline: 6px; font-size: 11px; } }
@media (prefers-reduced-motion: reduce) { button { transition: none; } }
</style><div class="shell"><nav><button aria-label="Уменьшить масштаб" onclick="scaleBy(.8)">−</button><button aria-label="Увеличить масштаб" onclick="scaleBy(1.25)">+</button><button onclick="setScale(1)">Сбросить масштаб</button><button onclick="fit()">Вместить</button><span id="value"></span></nav><div id="viewport">'''+svg+'''</div></div><script>
const svg=document.querySelector('svg'),vp=document.getElementById('viewport');
const w=Number(svg.getAttribute('width')),h=Number(svg.getAttribute('height'));let scale=1;const storageKey='navigator_graph_'+w+'_'+h+'_'+svg.textContent;try{scale=Number(sessionStorage.getItem(storageKey))||1}catch(e){}
function setScale(n){scale=Math.max(.25,Math.min(3,n));svg.style.width=w*scale+'px';svg.style.height=h*scale+'px';document.getElementById('value').textContent=Math.round(scale*100)+'%';try{sessionStorage.setItem(storageKey,scale)}catch(e){}}
function scaleBy(n){setScale(scale*n)}function fit(){setScale(Math.min(1,(vp.clientWidth-16)/w,(vp.clientHeight-16)/h))}
let dragging=false,startX=0,startY=0,scrollX=0,scrollY=0;
vp.addEventListener('pointerdown',e=>{dragging=true;startX=e.clientX;startY=e.clientY;scrollX=vp.scrollLeft;scrollY=vp.scrollTop;vp.setPointerCapture(e.pointerId)});
vp.addEventListener('pointermove',e=>{if(dragging){vp.scrollLeft=scrollX-e.clientX+startX;vp.scrollTop=scrollY-e.clientY+startY}});
vp.addEventListener('pointerup',()=>dragging=false);vp.style.cursor='grab';
setScale(scale);</script>''',height=height,scrolling=False)
