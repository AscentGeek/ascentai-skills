/* 화면 문구는 렌더러가 심어 둔 LMBC_L(리포트 언어)에서 꺼낸다. 키가 없으면 두 번째 인자로 떨어진다. */
function L(k,d){ try{ return (window.LMBC_L&&window.LMBC_L[k])||d; }catch(e){ return d; } }
/* ROOT = 대시보드 뷰. A4 뷰는 같은 내용의 사본이라, 전역으로 잡으면 정렬·펼침이
   두 벌에 걸려 엉킨다. 인쇄물에서는 눌릴 수도 없다. */
var ROOT=document.querySelector('.view-dash')||document;
/* 정렬 + 페이지네이션 — 한 곳에서만 행의 표시 여부를 정한다.
   S0 지도는 펼침 행(tr.xd)이 본행(tr.xr)에 붙어 다녀야 해서 '단위'로 묶어 움직인다. */
(function(){
function units(t){
  var u=[],rows=Array.prototype.slice.call(t.tBodies[0].rows);
  rows.forEach(function(r){
    if(r.classList.contains('xd')||r.classList.contains('cd')) { if(u.length) u[u.length-1].push(r); return; }
    u.push([r]);
  });
  return u;
}
function num(v){ return v===''||v==null?-Infinity:parseFloat(v); }
function render(t,st){
  var size=parseInt(t.dataset.page,10)||0, u=st.u, pages=size?Math.max(1,Math.ceil(u.length/size)):1;
  st.pg=Math.min(Math.max(1,st.pg),pages);
  u.forEach(function(g,i){
    var on=!size||(i>=(st.pg-1)*size&&i<st.pg*size);
    g.forEach(function(r,j){ r.hidden=!on||(j>0&&r.dataset.open!=='1'); });
  });
  var bar=t.parentElement.parentElement.querySelector('.pager[data-for="'+t.dataset.t+'"]');
  if(!bar) return;
  var o=['<span class="pg-n">'+L('js.rows','{n}행').replace('{n}',u.length)+'</span>'];
  if(pages>1){ o.push('<span class="pg-b">');
    o.push('<button class="pg-btn" data-go="'+(st.pg-1)+'"'+(st.pg===1?' disabled':'')+'>&lsaquo;</button>');
    for(var i=1;i<=pages;i++) o.push('<button class="pg-btn'+(i===st.pg?' on':'')+'" data-go="'+i+'">'+i+'</button>');
    o.push('<button class="pg-btn" data-go="'+(st.pg+1)+'"'+(st.pg===pages?' disabled':'')+'>&rsaquo;</button></span>');
  }
  bar.innerHTML=o.join('');
  bar.querySelectorAll('.pg-btn').forEach(function(b){ b.addEventListener('click',function(){ st.pg=parseInt(b.dataset.go,10); render(t,st); t.scrollIntoView({block:'nearest'}); }); });
}
function sort(t,st,k,dir){
  st.u.sort(function(a,b){ var x=num(a[0].dataset[k]),y=num(b[0].dataset[k]); return dir*(y-x); });
  var body=t.tBodies[0]; st.u.forEach(function(g){ g.forEach(function(r){ body.appendChild(r); }); });
  t.querySelectorAll('th[data-k]').forEach(function(h){ h.dataset.on=h.dataset.k===k?(dir>0?'desc':'asc'):''; });
  st.k=k; st.dir=dir; st.pg=1; render(t,st);
}
ROOT.querySelectorAll('table[data-t]').forEach(function(t){
  var st={u:units(t),pg:1};
  t.querySelectorAll('th[data-k]').forEach(function(h){
    h.classList.add('sortable');
    h.addEventListener('click',function(){ sort(t,st,h.dataset.k, st.k===h.dataset.k&&st.dir>0?-1:1); });
  });
  if(t.dataset.sort) sort(t,st,t.dataset.sort,1); else render(t,st);
  t.addEventListener('click',function(e){ var r=e.target.closest('tr.xr,tr.cr'); if(!r) return;
    var d=document.getElementById(r.dataset.x||r.dataset.c); if(d) d.dataset.open=d.hidden?'0':'1'; });
});
(function(){var w=document.querySelector('.bwrap'); if(!w) return; var tip=w.querySelector('.btip');
function show(c){ var d=c.dataset, bw=c.closest('.bwrap')||document;
  tip.innerHTML='<b>'+d.n+'</b> <span class="jd '+d.jc+'">'+d.j+'</span>'
   +'<table><tr><th>'+L('col.catVolume','카테고리 검색량')+'</th><td>'+d.vol+'</td></tr>'
   +'<tr><th>'+L('js.ownCombo','{own} 결합').replace('{own}',bw.dataset.brand||L('js.ownFallback','자사'))+'</th><td>'+d.own+' <small>('+d.rate+'%)</small></td></tr>'
   +'<tr><th>'+L('col.rival1','경쟁사 1위')+'</th><td>'+d.top+' <small>('+d.toprate+'%)</small></td></tr>'
   +'<tr><th>'+L('js.relLead','상대 우위')+'</th><td>'+L('js.times','{n}배').replace('{n}',d.ratio)+'</td></tr></table>';
  tip.hidden=false;
  var r=c.getBoundingClientRect(), b=w.getBoundingClientRect();
  var x=r.left-b.left+r.width/2, y=r.top-b.top;
  tip.style.left=Math.max(4,Math.min(x-tip.offsetWidth/2,b.width-tip.offsetWidth-4))+'px';
  tip.style.top=Math.max(4,y-tip.offsetHeight-8)+'px';
}
w.querySelectorAll('circle.bcz').forEach(function(c){
  c.addEventListener('mouseenter',function(){ show(c); c.style.fillOpacity='.5'; });
  c.addEventListener('mouseleave',function(){ tip.hidden=true; c.style.fillOpacity='.22'; });
  c.addEventListener('click',function(){ show(c); });
});
})();
ROOT.querySelectorAll('[data-more]').forEach(function(w){
  var n=parseInt(w.dataset.more,10), items=Array.prototype.slice.call(w.children), btn=document.querySelector('.more-btn[data-for="'+w.dataset.mid+'"]');
  function show(k){ items.forEach(function(el,i){ el.hidden=i>=k; }); if(btn) btn.textContent=k>=items.length?L('js.collapse','접기'):L('js.showMore','더 보기 ({n}장 남음)').replace('{n}',items.length-k); btn && (btn.dataset.k=k); }
  show(n);
  if(btn) btn.addEventListener('click',function(){ var k=parseInt(btn.dataset.k,10); show(k>=items.length?n:items.length); });
});
})();
