/* ROOT = 대시보드 뷰. A4 뷰는 같은 내용의 사본이라, 전역으로 잡으면 정렬·펼침이
   두 벌에 걸려 엉킨다. 인쇄물에서는 눌릴 수도 없다. */
var ROOT=document.querySelector('.view-dash')||document;
ROOT.querySelectorAll('.t-map tr.xr').forEach(function(r){function t(){var d=document.getElementById(r.dataset.x);var o=d.hidden;d.hidden=!o;r.setAttribute('aria-expanded',o?'true':'false');}
r.addEventListener('click',t);r.addEventListener('keydown',function(e){if(e.key==='Enter'||e.key===' '){e.preventDefault();t();}});});
function s2(v){ROOT.querySelectorAll('.s2t').forEach(function(b){var on=b.dataset.s2===v;b.setAttribute('aria-selected',on?'true':'false');b.classList.toggle('on',on);});
ROOT.querySelectorAll('#t-uni tr[data-s2]').forEach(function(r){r.hidden=r.dataset.s2!==v;});}
ROOT.querySelectorAll('.s2t').forEach(function(b){b.addEventListener('click',function(){s2(b.dataset.s2);});});
var f0=document.querySelector('.s2t');if(f0)s2(f0.dataset.s2);ROOT.querySelectorAll('.modesw .chip-f').forEach(function(b){
  b.addEventListener('click',function(){
    var t=document.getElementById(b.dataset.for); if(!t) return;
    t.setAttribute('data-mode',b.dataset.mode);
    b.parentNode.querySelectorAll('.chip-f').forEach(function(o){o.classList.toggle('on',o===b);});
  });
});
