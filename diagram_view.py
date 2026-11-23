from html import escape
import math
import streamlit.components.v1 as components

def diagram(nodes, links, targets, fields=(), height=340):
    # Fixed-size nodes and explicit pixel canvas: never stretch a small graph.
    nodes=list(nodes); columns=min(3,max(1,len(nodes))); rows=math.ceil(len(nodes)/columns)
    width=columns*380+80; total_height=rows*180+100
    positions={n:(40+(i%columns)*380,50+(i//columns)*180) for i,n in enumerate(nodes)}
    parts=[]
    for i,e in enumerate(links):
        x,y=positions[e.child];u,v=positions[e.parent]
        x+=145;y+=70;u+=145;v+=70
        bend=35+(i%4)*18
        parts.append(f'<path d="M{x},{y} Q{(x+u)/2},{(y+v)/2-bend} {u},{v}" stroke="#88a9c9" fill="none"/>')
        label=escape(f'{e.child_column} = {e.parent_column}')
        parts.append(f'<text x="{(x+u)/2}" y="{(y+v)/2-bend/2}" text-anchor="middle" fill="#d1e4f5" font-size="11" paint-order="stroke" stroke="#182331" stroke-width="4">{label}</text>')
    for n,(x,y) in positions.items():
        color='#225758' if n in targets else '#2b394d'
        parts.append(f'<rect x="{x}" y="{y}" width="290" height="70" rx="12" fill="{color}" stroke="#67b9b4"/>')
        parts.append(f'<text x="{x+12}" y="{y+26}" fill="#f2f7ff" font-size="12">{escape(n)}</text>')
        selected=', '.join(f.rpartition('.')[2] for f in fields if f.rpartition('.')[0]==n)
        parts.append(f'<text x="{x+12}" y="{y+49}" fill="#b5d5e0" font-size="10">{escape(selected[:45])}</text>')
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_height}" viewBox="0 0 {width} {total_height}">'+''.join(parts)+'</svg>'
    components.html('''<style>body{margin:0;background:#182331;color:#e9f3ff;font:13px Arial}button{background:#304159;color:#fff;border:1px solid #647e99;border-radius:7px;padding:7px 12px;cursor:pointer}#viewport{overflow:auto;height:calc(100vh - 42px)}svg{display:block;max-width:none;max-height:none}nav{height:40px;display:flex;align-items:center;gap:8px}</style><nav><button onclick="scaleBy(.8)">−</button><button onclick="scaleBy(1.25)">+</button><button onclick="setScale(1)">100%</button><button onclick="fit()">Вместить</button><span id="value"></span></nav><div id="viewport">'''+svg+'''</div><script>
const svg=document.querySelector('svg'),vp=document.getElementById('viewport');
const w=Number(svg.getAttribute('width')),h=Number(svg.getAttribute('height'));let scale=1;
function setScale(n){scale=Math.max(.15,Math.min(3,n));svg.style.width=w*scale+'px';svg.style.height=h*scale+'px';document.getElementById('value').textContent=Math.round(scale*100)+'%';}
function scaleBy(n){setScale(scale*n)}function fit(){setScale(Math.min(1,(vp.clientWidth-16)/w,(vp.clientHeight-16)/h))}fit();</script>''',height=height,scrolling=False)
