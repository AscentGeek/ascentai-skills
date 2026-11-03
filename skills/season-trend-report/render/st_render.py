#!/usr/bin/env python3
"""st_render.py · data.json(숫자, 코드) + narrative.json(문장, 분석자) → 시즌·트렌드 분석 HTML (대시보드/A4).

  python3 st_render.py --data data.json --narrative narrative.json --facts facts.md --out report.html

구성은 고정이다 — 표지(배경과 목적 + 요약) · 탭 1 시즌 패턴(월별 시즌 키워드 → 테마별 시즌 캘린더 · 키워드를 누르면 근거 창)
· 탭 2 최근 1년 트렌드(주요 트렌드 → 테마별 트렌드) · 탭 3 최근 3개월 상승·하락(QoQ 순 · QoQ+YoY).
HTML/CSS 를 손으로 고치지 않는다. 문장은 narrative.json 의 정해진 칸에만 들어간다.
lint · 금지어가 있으면 exit 4 (렌더하지 않음). facts.md 에 없는 숫자는 경고만 한다.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from inline_styles import inline_styles  # noqa: E402
from style_order import SKILL_STYLES  # noqa: E402
import st_common as C  # noqa: E402

# 웹폰트 · 다른 스킬 render_report.py 와 같은 값
FONT_HREF = {
    "kr": "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;900&display=swap",
    "jp": "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;900&display=swap",
    "us": "https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700;900&display=swap",
}

# 템플릿의 {{INLINE_SCRIPT}} · 탭 토글 · 대시/A4 보기 전환 · 검색량 뱃지 툴팁 (형제 스킬과 같은 코드)
BASE_SCRIPT = r"""
(function(){
  var tabs = document.querySelectorAll('.dash-tab');
  var panels = document.querySelectorAll('.dash-tab-panel');
  tabs.forEach(function(tab){
    tab.addEventListener('click', function(){
      var idx = tab.getAttribute('data-panel');
      tabs.forEach(function(t){
        var on = t.getAttribute('data-panel') === idx;
        t.classList.toggle('active', on);
        t.setAttribute('aria-selected', on ? 'true' : 'false');
      });
      panels.forEach(function(p){
        p.classList.toggle('active', p.getAttribute('data-panel') === idx);
      });
    });
  });
  var viewBtns = document.querySelectorAll('.mini-toolbar__view button');
  viewBtns.forEach(function(btn){
    btn.addEventListener('click', function(){
      var mode = btn.getAttribute('data-view');
      document.body.classList.toggle('view-mode-dash', mode === 'dash');
      document.body.classList.toggle('view-mode-a4',   mode === 'a4');
      viewBtns.forEach(function(b){ b.classList.toggle('active', b === btn); });
    });
  });

  // 검색량 뱃지 툴팁 — 클릭 토글, X·바깥클릭으로 닫기.
  document.querySelectorAll('.persona-card__volbadge').forEach(function(badge){
    var tip = badge.querySelector('.volbadge-tip');
    var close = badge.querySelector('.volbadge-tip__close');
    badge.addEventListener('click', function(e){
      if (tip && tip.contains(e.target)) { e.stopPropagation(); return; }
      e.stopPropagation();
      badge.classList.toggle('tip-open');
    });
    badge.addEventListener('keydown', function(e){
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); badge.classList.toggle('tip-open'); }
    });
    if (close) {
      close.addEventListener('click', function(e){
        e.stopPropagation(); e.preventDefault();
        badge.classList.remove('tip-open');
      });
    }
  });
  document.addEventListener('click', function(){
    document.querySelectorAll('.persona-card__volbadge.tip-open').forEach(function(b){
      b.classList.remove('tip-open');
    });
  });
})();
"""


def _apply(template, blocks):
    # 한 번에 치환한다 · 치환된 글자 안의 "{{…}}" 가 다시 치환되지 않게
    pattern = re.compile("|".join(re.escape(k) for k in blocks))
    return pattern.sub(lambda m: blocks[m.group(0)], template)


def spark_html(values, *, width=108, height=26):
    """표 안에 넣는 초소형 추이선."""
    vals = []
    for v in values or []:
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            vals.append(0.0)
    if len(vals) < 2:
        return '<span class="mf-spark mf-spark--empty">—</span>'
    peak = max(vals) or 1
    step = width / (len(vals) - 1)
    pts = " ".join(f"{i * step:.1f},{height - (v / peak) * height:.1f}" for i, v in enumerate(vals))
    return (f'<svg class="mf-spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
            f'<polyline fill="none" stroke="var(--chart-1, #2563eb)" stroke-width="1.5" '
            f'vector-effect="non-scaling-stroke" points="{pts}"/></svg>')

PKG = HERE.parent
esc = html.escape
fmt = C.fmt
kv = lambda n: C.kv(n)
ym = lambda m: m.replace("-", ".")
HTML_LANG = {"kr": "ko", "jp": "ja", "us": "en"}
NUM_LOCALE = {"kr": "ko-KR", "jp": "ja-JP", "us": "en-US"}
# 리포트를 쓸 수 있는 언어 · 시장(gl)과 독립이다 (미국 시장을 일본어로 쓸 수 있다)
REPORT_LANGS = ("kr", "jp", "us")
# lint 금지어 · 리포트 언어별 (판단 · 예측 · 과장 · 원인 단정 · '옮겨갔다'). us 는 소문자로 비교한다
BANNED = {
    "kr": ["기회", "추천합니다", "해야 합니다", "예측", "전망", "확실히", "폭망", "몰락", "충격", "대박", "거짓말", "때문에", "의 영향으로", "옮겨갔", "넘어갔", "대체했"],  # i18n-ok · lint 계약값
    "jp": ["チャンス", "おすすめします", "すべきです", "予測", "見通し", "確実に", "激減", "崩壊", "衝撃", "大ヒット", "のせいで", "の影響で", "移った", "乗り換えた", "取って代わった"],
    "us": ["opportunity", "we recommend", "you should", "should be", "predict", "forecast", "outlook", "certainly", "collapse", "plummet", "shocking", "skyrocket", "because of", "due to", "driven by", "shifted to", "moved to", "replaced"],
}

LB = {}


def L(key, **kw):
    s = LB.get(key, key)
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


def josa_wa(word):
    """kr 조사 와/과 · 받침이 있으면 과. jp · us 틀에는 {wa} 가 없다."""
    ch = (word or " ")[-1]
    if "가" <= ch <= "힣":  # i18n-ok · 한글 음절 범위
        return "과" if (ord(ch) - 0xAC00) % 28 else "와"  # i18n-ok · kr 조사
    return "와"  # i18n-ok · kr 조사 (영문 · 숫자로 끝나면 와)


def MN(m):
    """월 이름 · kr 9월 · jp 9月 · us Sep."""
    return LB["fmt.months"].split(",")[int(m) - 1]


def span_lab(span):
    """st_build 의 시즌 구간(계약값 '9–10월' · '9월') → 리포트 언어 표기."""
    ms = [int(x) for x in re.findall(r"\d+", str(span))]
    if len(ms) >= 2:
        return L("fmt.monthRange", a=ms[0], b=ms[-1], A=MN(ms[0]), B=MN(ms[-1]))
    return MN(ms[0]) if ms else str(span)


def years_of(ny, n):
    return L("fmt.yearsOf", ny=ny, n=n)


def stl_script(lang):
    """근거 창 스크립트가 쓰는 라벨 · 월 이름 · 숫자 단위 (한 번만 심으면 된다 · 두 번 심어도 같은 값)."""
    js = {k: v for k, v in LB.items() if k.startswith("js.") or k in ("yc.aria", "yc.yearPeak")}
    stl = dict(t=js, mo=LB["fmt.months"].split(","), u=C.UNIT_10K.get(lang, ""), loc=NUM_LOCALE[lang])
    return "<script>window.STL=" + json.dumps(stl, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/") + ";</script>"

# 근거 창 스크립트 · 문구는 STL(라벨 · 월 이름 · 숫자 단위)에서 온다 (stl_script 가 먼저 심는다)
EV_JS = r"""<script>(function(){
var D=null,dlg=null;
function f(n){return Math.round(n).toLocaleString(STL.loc)}
function kv(n){n=Math.round(n);if(!STL.u)return n>=1e6?(n/1e6).toFixed(1).replace('.0','')+'M':n>=1e4?Math.round(n/1e3).toLocaleString(STL.loc)+'K':n.toLocaleString(STL.loc);return n>=1e4?(n/1e4).toFixed(n>=1e5?0:1).replace('.0','')+STL.u:n.toLocaleString(STL.loc)}
function F(k,o){return STL.t[k].replace(/\{(\w+)\}/g,function(a,b){return o[b]})}
function M(m){return STL.mo[m-1]}
function el(t,c,h){var e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e}
window.stEv=function(b){
 if(!D){D=JSON.parse(document.getElementById('st-ev-data').textContent)}
 var root=b.closest('.view-dash,.view-a4')||document;dlg=root.querySelector('.st-ev:not(.st-tr)')||document.querySelector('.st-ev:not(.st-tr)');
 if(dlg.parentNode!==document.body)document.body.appendChild(dlg);
 var x=D.items[b.dataset.ev],mo=D.mo,W=x.w,S=x.s;
 var Y=[0,1,2,3].map(function(e){var v=S.slice(e*12,e*12+12),sm=v.reduce(function(a,b){return a+b},0);
   var pk=sm>0?mo[v.indexOf(Math.max.apply(null,v))]:null;return {v:v,sum:sm,pk:pk,hit:pk!=null&&W.indexOf(pk)>=0}});
 var H=W.filter(function(m){return Y.some(function(y){return y.pk===m})});
 var best=W.reduce(function(a,m){return x.ci[m-1]>x.ci[a-1]?m:a},W[0]);
 dlg.querySelector('.st-ev__t').textContent=x.k;
 dlg.querySelector('.st-ev__sub').textContent=F('js.evSub',{t:x.t,span:x.span});
 var chk=dlg.querySelector('.st-ev__chk');chk.innerHTML='';
 var need=x.ny>=4?3:x.ny;
 chk.appendChild(el('li','ok','<b>'+F('js.c1h',{span:x.span,years:x.years})+'</b><span>'+F('js.c1b',{need:need,list:Y.map(function(y,i){return y.pk?('<em class="'+(y.hit?'hit':'miss')+'">'+D.yrs[i]+' '+M(y.pk)+'</em>'):''}).filter(Boolean).join(' ')})+'</span>'));
 chk.appendChild(el('li','ok','<b>'+F('js.c2h',{m:M(best),v:x.ci[best-1].toFixed(2)})+'</b><span>'+F('js.c2b',{v:x.ci[best-1].toFixed(1)})+'</span>'));
 chk.appendChild(el('li','',"<b>"+F('js.c3h',{m:M(best),vol:f(x.vol)})+"</b><span>"+F('js.c3b',{m:M(best)})+"</span>"));
 /* chart */
 var w=640,h=220,L=44,R=12,T=14,B=26,iw=w-L-R,ih=h-T-B,mx=Math.max.apply(null,S)||1;
 var xs=function(i){return L+iw*(i+.5)/12},ys=function(v){return T+ih*(1-v/mx)};
 var o='<svg viewBox="0 0 '+w+' '+h+'" class="st-ev__svg" role="img" aria-label="'+STL.t['yc.aria']+'">';
 mo.forEach(function(m,i){if(H.indexOf(m)>=0)o+='<rect x="'+(L+iw*i/12)+'" y="'+T+'" width="'+(iw/12)+'" height="'+ih+'" class="st-ev__band"/>'});
 [0,.5,1].forEach(function(g){var yy=ys(mx*g);o+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+yy+'" y2="'+yy+'" class="st-ev__grid"/><text x="'+(L-6)+'" y="'+(yy+4)+'" class="st-ev__ax" text-anchor="end">'+kv(mx*g)+'</text>'});
 mo.forEach(function(m,i){o+='<text x="'+xs(i)+'" y="'+(h-8)+'" class="st-ev__ax'+(H.indexOf(m)>=0?' on':'')+'" text-anchor="middle">'+M(m)+'</text>'});
 Y.forEach(function(y,e){if(!y.sum)return;var d=y.v.map(function(v,i){return(i?'L':'M')+xs(i).toFixed(1)+' '+ys(v).toFixed(1)}).join(' ');
  o+='<path d="'+d+'" class="st-ev__ln y'+e+'"/>';
  y.v.forEach(function(v,i){var p=mo[i]===y.pk;o+='<circle cx="'+xs(i)+'" cy="'+ys(v)+'" r="'+(p?5:2.5)+'" class="st-ev__pt y'+e+(p?' pk':'')+'"><title>'+D.yrs[e]+' · '+M(mo[i])+' '+f(v)+'</title></circle>'})});
 o+='</svg><ul class="st-ev__lg">'+Y.map(function(y,e){return '<li><i class="y'+e+'"></i>'+D.yrs[e]+'</li>'}).join('')+'<li><i class="band"></i>'+F('js.band',{span:x.span})+'</li><li><i class="pk"></i>'+STL.t['yc.yearPeak']+'</li></ul>';
 dlg.querySelector('.st-ev__ch').innerHTML=o;
 /* table */
 var tb='<table class="st-ev__tb"><thead><tr><th>'+STL.t['js.year']+'</th>'+mo.map(function(m){return '<th class="'+(H.indexOf(m)>=0?'on':'')+'">'+M(m)+'</th>'}).join('')+'<th>'+STL.t['js.peak']+'</th></tr></thead><tbody>';
 Y.forEach(function(y,e){tb+='<tr><th>'+D.yrs[e]+'</th>'+y.v.map(function(v,i){var c=(H.indexOf(mo[i])>=0?'on':'')+(mo[i]===y.pk&&y.sum?' pk':'');return '<td class="'+c+'">'+(v?kv(v):'–')+'</td>'}).join('')+'<td class="'+(y.hit?'hit':'miss')+'">'+(y.pk?M(y.pk)+' '+(y.hit?'✓':'✗'):'–')+'</td></tr>'});
 tb+='<tr class="ix"><th>'+STL.t['js.ci']+'<small>'+STL.t['js.ciSub']+'</small></th>'+mo.map(function(m){var v=x.ci[m-1];return '<td class="'+(H.indexOf(m)>=0?'on':'')+(v>=D.thr?' hi':'')+'">'+v.toFixed(1)+'</td>'}).join('')+'<td></td></tr></tbody></table>';
 dlg.querySelector('.st-ev__tw').innerHTML=tb;
 if(dlg.showModal)dlg.showModal();else dlg.setAttribute('open','');
};
document.addEventListener('click',function(e){if(e.target&&e.target.classList&&e.target.classList.contains('st-ev'))e.target.close()});
})();</script>"""

TR_JS = r"""<script>(function(){
var D=null;
function f(n){return Math.round(n).toLocaleString(STL.loc)}
function kv(n){n=Math.abs(Math.round(n));if(!STL.u)return n>=1e6?(n/1e6).toFixed(1).replace('.0','')+'M':n>=1e4?Math.round(n/1e3).toLocaleString(STL.loc)+'K':n.toLocaleString(STL.loc);return n>=1e4?(n/1e4).toFixed(n>=1e5?0:1).replace('.0','')+STL.u:n.toLocaleString(STL.loc)}
function F(k,o){return STL.t[k].replace(/\{(\w+)\}/g,function(a,b){return o[b]})}
function M(m){return STL.mo[m-1]}
function sg(n){return (n>0?'+':n<0?'−':'')+kv(n)}
function el(t,c,h){var e=document.createElement(t);if(c)e.className=c;if(h!=null)e.innerHTML=h;return e}
window.stTr=function(b){
 if(!D)D=JSON.parse(document.getElementById('st-tr-data').textContent);
 var root=b.closest('.view-dash,.view-a4')||document,dlg=root.querySelector('.st-tr')||document.querySelector('.st-tr'),x=D.items[b.dataset.tr];
 if(dlg.parentNode!==document.body)document.body.appendChild(dlg);
 var A=x.s.slice(0,12),B=x.s.slice(12,24),d=x.e4-x.e3,pc=x.e3?((x.e4/x.e3-1)*100):null;
 var hi=0;for(var i=0;i<12;i++)if(B[i]>A[i])hi++;
 dlg.querySelector('.st-ev__t').textContent=x.k;
 dlg.querySelector('.st-ev__sub').textContent=x.t+(x.c==='new'?F('js.trNew',{f:x.f}):'');
 var chk=dlg.querySelector('.st-ev__chk');chk.innerHTML='';chk.style.display=b.classList.contains('tr-kw')?'none':'';  /* 탭 2(최근 1년 트렌드)에서 열면 YoY·QoQ·12개월 상자 숨김 — 아래 표의 합계·차이로 충분 */
 var y0=A[9]+A[10]+A[11],q0=B[6]+B[7]+B[8],q1=B[9]+B[10]+B[11];
 function pr(n,dn){return dn?((n/dn-1)*100>0?'+':'')+((n/dn-1)*100).toFixed(0)+'%':'—'}
 chk.appendChild(el('li',q1>y0?'ok':'dn','<b>YoY <em class="st-ev__q">'+STL.t['js.yoyQ']+'</em> '+pr(q1,y0)+'</b><span>'+F('js.yoyB',{a:f(q1),b:f(y0)})+'</span>'));
 chk.appendChild(el('li',q1>q0?'ok':'dn','<b>QoQ <em class="st-ev__q">'+STL.t['js.qoqQ']+'</em> '+pr(q1,q0)+'</b><span>'+F('js.qoqB',{a:f(q1),b:f(q0)})+'</span>'));
 var p0=A[6]+A[7]+A[8];var ya=y0?q1/y0-1:null,yb=p0?q0/p0-1:null;
 /* 12개월 상자는 빼고 YoY·QoQ 두 개만 — 3탭 선별 기준 STEP 1·2와 맞춤 (12개월 변화는 아래 표 합계에 있음) */
 var w=640,h=210,L=48,R=12,T=14,B2=26,iw=w-L-R,ih=h-T-B2,mx=Math.max.apply(null,x.s)||1;
 var xs=function(i){return L+iw*(i+.5)/12},ys=function(v){return T+ih*(1-v/mx)};
 var o='<svg viewBox="0 0 '+w+' '+h+'" class="st-ev__svg" role="img" aria-label="'+STL.t['js.trAria']+'">';
 [0,.5,1].forEach(function(g){var yy=ys(mx*g);o+='<line x1="'+L+'" x2="'+(w-R)+'" y1="'+yy+'" y2="'+yy+'" class="st-ev__grid"/><text x="'+(L-6)+'" y="'+(yy+4)+'" class="st-ev__ax" text-anchor="end">'+kv(mx*g)+'</text>'});
 D.mo.forEach(function(m,i){o+='<text x="'+xs(i)+'" y="'+(h-8)+'" class="st-ev__ax" text-anchor="middle">'+M(m)+'</text>'});
 [[A,'pv',D.e3],[B,'cu',D.e4]].forEach(function(z){var d2=z[0].map(function(v,i){return(i?'L':'M')+xs(i).toFixed(1)+' '+ys(v).toFixed(1)}).join(' ');
  o+='<path d="'+d2+'" class="st-tr__ln '+z[1]+'"/>';z[0].forEach(function(v,i){o+='<circle cx="'+xs(i)+'" cy="'+ys(v)+'" r="3" class="st-tr__pt '+z[1]+'"><title>'+z[2]+' · '+M(D.mo[i])+' '+f(v)+'</title></circle>'})});
 o+='</svg><ul class="st-ev__lg"><li><i class="st-tr__sw pv"></i>'+D.e3+'</li><li><i class="st-tr__sw cu"></i>'+D.e4+'</li></ul>';
 dlg.querySelector('.st-ev__ch').innerHTML=o;
 var tb='<table class="st-ev__tb"><thead><tr><th></th>'+D.mo.map(function(m){return '<th>'+M(m)+'</th>'}).join('')+'<th>'+STL.t['js.sum']+'</th></tr></thead><tbody>';
 tb+='<tr><th>'+D.e3+'</th>'+A.map(function(v){return '<td>'+(v?kv(v):'–')+'</td>'}).join('')+'<td><b>'+kv(x.e3)+'</b></td></tr>';
 tb+='<tr><th>'+D.e4+'</th>'+B.map(function(v){return '<td>'+(v?kv(v):'–')+'</td>'}).join('')+'<td><b>'+kv(x.e4)+'</b></td></tr>';
 tb+='<tr class="df"><th>'+STL.t['js.diff']+'</th>'+B.map(function(v,i){var q=v-A[i];return '<td class="'+(q>0?'hit':q<0?'neg':'')+'">'+(q?sg(q):'0')+'</td>'}).join('')+'<td class="'+(d>0?'hit':'neg')+'"><b>'+sg(d)+'</b></td></tr></tbody></table>';
 dlg.querySelector('.st-ev__tw').innerHTML=tb;
 if(dlg.showModal)dlg.showModal();else dlg.setAttribute('open','');
};
})();</script>"""


def chg(v, d=1, big=False):
    if v is None:
        return f'<b class="mf-chg">{L("common.new")}</b>'
    if big and v >= 10:
        return f'<b class="mf-chg is-up">{L("chg.big")}</b>'
    c = "is-up" if v > 0.0005 else "is-down" if v < -0.0005 else ""
    return f'<b class="mf-chg {c}">{v*100:+.{d}f}%</b>'


def insight(text, label=None):
    """다른 LM 리포트(audience · search-demand)와 같은 인사이트 상자 — 보라 왼쪽 선 · 라벨 · 본문."""
    if not text:
        return ""
    label = label or L("common.insight")
    return (f'<div class="persona-insight st-ins"><div class="persona-insight__label">{label}</div>'
            f'<div class="persona-insight__text">{text}</div></div>')


def card(title, body, badge=None, note=None):
    side = (f'<span class="dash-card__badge">{esc(badge)}</span>' if badge else "") + \
           (f'<span class="dash-card__note">{esc(note)}</span>' if note else "")
    return (f'<div class="dash-card"><div class="dash-card__head"><h3 class="dash-card__title">{esc(title)}</h3>{side}</div>'
            f'<div class="dash-card__body">{body}</div></div>')


def steps(title, items, numbered=True, foot=None):
    """설명 카드: items = [(제목, 본문)] — numbered 가 True 면 STEP n, 문자열이면 그 꼬리표("보기 {n}"), False 면 꼬리표 없음."""
    cards = "".join(
        f'<div class="st-step">'
        + (f'<span class="st-step__n">{"STEP {n}" if numbered is True else numbered}</span>'.format(n=i) if numbered else "")
        + f'<b class="st-step__h">{h}</b><p class="st-step__p">{b}</p></div>'
        for i, (h, b) in enumerate(items, 1))
    return (f'<div class="st-steps"><div class="st-steps__t">{esc(title)}</div>'
            f'<div class="st-steps__g st-steps__g--{min(len(items), 4)}">{cards}</div>'
            + (f'<p class="st-steps__f">{foot}</p>' if foot else "") + "</div>")


def explain(q, *ps):
    return f'<div class="mf-explain"><b class="mf-explain__q">{esc(q)}</b>' + "".join(f"<p>{p}</p>" for p in ps) + "</div>"


# ───────────── lint ─────────────
NUM = re.compile(r"[+−-]?\d[\d,]*(?:\.\d+)?(?:만|万|K|M|%p|%)?")  # i18n-ok · 숫자 단위 (계약값)


def lint(nar, facts_text, lang="kr"):
    texts = []

    def walk(o):
        if isinstance(o, str):
            texts.append(o)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(nar)
    words = BANNED.get(lang, BANNED["kr"])
    bad = sorted({w for t in texts for w in words if w in (t.lower() if lang == "us" else t)})
    known = set()
    for tok in NUM.findall(facts_text or ""):
        known.add(tok.lstrip("+−-").replace(",", ""))
    warn = []
    for t in texts:
        for tok in NUM.findall(re.sub(r"<[^>]+>", "", t)):
            core = tok.lstrip("+−-").replace(",", "")
            plain = re.sub(r"(만|万|K|M|%p|%)$", "", core)  # i18n-ok · 숫자 단위
            if not plain or len(plain) <= 1 or plain in {"10", "12", "24", "48"}:
                continue
            if core not in known and plain not in {re.sub(r"(만|万|K|M|%p|%)$", "", k) for k in known}:  # i18n-ok · 숫자 단위
                warn.append(tok)
    return bad, sorted(set(warn))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data", required=True)
    p.add_argument("--narrative", required=True)
    p.add_argument("--facts")
    p.add_argument("--out", required=True)
    p.add_argument("--lang", choices=REPORT_LANGS, help="리포트 언어 · 없으면 data.json meta.lang (없으면 kr)")  # i18n-ok · 콘솔
    a = p.parse_args()
    D = json.loads(Path(a.data).read_text(encoding="utf-8"))
    lang = a.lang or D["meta"].get("lang") or "kr"
    gl = D["meta"].get("gl") or "kr"
    LB.update(json.loads((PKG / "labels" / f"season-trend.{lang}.json").read_text(encoding="utf-8")))
    C.set_lang(lang)
    N = json.loads(Path(a.narrative).read_text(encoding="utf-8"))
    facts_text = Path(a.facts).read_text(encoding="utf-8") if a.facts and Path(a.facts).exists() else ""
    bad, warn = lint(N, facts_text, lang)
    if bad:
        print("❌ lint · 금지어: " + ", ".join(bad) + " — narrative.json 을 고치세요 (references/narrative.md)", file=sys.stderr)
        return 4
    if warn:
        print("⚠️ lint · facts.md 에서 찾지 못한 숫자 (계산한 비율이면 괜찮고, 아니면 고치세요): " + ", ".join(warn[:40]))

    meta = D["meta"]
    seed = meta["seed"]
    M = meta["months"]
    NOWM = meta["now"]
    MKT, M3 = D["mkt"], D["mkt3"]
    ERA3 = f"{ym(M[24])} ~ {ym(M[35])}"
    ERA4 = f"{ym(M[36])} ~ {ym(M[47])}"
    THEMES = D["themes"]
    TN = {t["id"]: t["name"] for t in THEMES}
    ROWS = D["rows"]
    SKW = D["skw"]
    TK = D["tkw"]
    Y0, Y1 = M[36], M[47]

    # ───────────── 탭 1 · 시즌 패턴 ─────────────
    MON = {int(k): v for k, v in D["months"].items()}
    MO = [int(m[5:]) for m in M[:12]]
    YRS = [f"{M[e*12][2:4]}.{M[e*12][5:]}–{M[e*12+11][2:4]}.{M[e*12+11][5:]}" for e in range(4)]
    EV, seq = {}, [0]

    KID = {}

    def reg(x):
        if x["k"] in KID:
            return KID[x["k"]]
        seq[0] += 1
        i = f"k{seq[0]}"
        KID[x["k"]] = i
        EV[i] = dict(k=x["k"], t=TN.get(x.get("t"), L("common.themeNone")), s=x["s"], ci=x["ci"], w=x["w"], span=span_lab(x["span"]),
                     n=x["n"], ny=x["ny"], years=years_of(x["ny"], x["n"]), ix=x["ix"], vol=x["vol"])
        return i

    def li(x):
        i = reg(x)
        return (f'<li><button type="button" class="tr-mk__k" data-ev="{i}" onclick="stEv(this)">'
                f'<b>{esc(x["k"])}</b><span>{L("mk.item", years=years_of(x["ny"], x["n"]), span=span_lab(x["span"]), new=L("mk.itemNew") if x.get("new") else "", vol=fmt(x["vol"]))}</span></button></li>')

    # ── 테마별 시즌 캘린더 ──
    SEEDN = C.norm_kw(seed)

    def short(k):
        s = re.sub(r"\(\s*" + re.escape(seed) + r"\s*\)", " ", k, flags=re.I)
        # jp 검색어는 띄어 쓰지 않는 경우가 많다 (ナイキパーカー) · jp 시장만 경계 없이 뺀다
        lb, rb = ("", "") if gl == "jp" else (r"(?<!\S)", r"(?!\S)")
        s = re.sub(r"\s+", " ", re.sub(lb + re.escape(seed) + rb, " ", s, flags=re.I)).strip(" ()")
        return s if s and C.norm_kw(s) != SEEDN else k

    byt = {}
    for m, Lm in MON.items():
        for x in Lm:
            if x.get("t"):
                byt.setdefault(x["t"], {}).setdefault(m, []).append(x)
    cal_rows = sorted([(tid, d) for tid, d in byt.items() if sum(len(v) for v in d.values()) >= 1],
                      key=lambda z: -sum(len(v) for v in z[1].values()))

    def chip(x, lab):
        i = reg(x)
        return (f'<button type="button" class="st-cal__k" data-ev="{i}" onclick="stEv(this)" '
                f'title="{esc(L("cal.chipTitle", k=x["k"], years=years_of(x["ny"], x["n"]), span=span_lab(x["span"]), vol=fmt(x["vol"])))}">{esc(lab)}</button>')

    head = f'<tr><th scope="col" class="st-cal__th">{L("cal.theme")}</th>' + "".join(
        f'<th scope="col" class="{"is-now" if m == NOWM else ""}">{MN(m)}{"<span>" + L("common.now") + "</span>" if m == NOWM else ""}</th>' for m in range(1, 13)) + "</tr>"
    body = ""
    for tid, d in cal_rows:
        n = sum(len(v) for v in d.values())
        tds = ""
        for m in range(1, 13):
            Lm = d.get(m, [])
            if not Lm:
                tds += f'<td class="{"is-now" if m == NOWM else ""}"></td>'
                continue
            seen = set()
            cs = []
            for x in Lm:
                lab = short(x["k"])
                cs.append(chip(x, x["k"] if lab in seen else lab))
                seen.add(lab)
            inner = "".join(cs[:3])
            if len(cs) > 3:
                inner += (f'<details class="st-cal__more"><summary>+{len(cs)-3}</summary>' + "".join(cs[3:]) + "</details>")
            tds += f'<td class="on{" is-now" if m == NOWM else ""}">{inner}</td>'
        body += f'<tr><th scope="row" class="st-cal__th">{esc(TN[tid])}<small>{L("fmt.count", n=n)}</small></th>{tds}</tr>'
    nt = sum(1 for x in MON.values() for y in x if not y.get("t"))
    cal_card = card(L("cal.title"),
        insight(N.get("calendar_note"))
        + (f'<div class="st-cal-wrap"><table class="st-cal"><thead>{head}</thead><tbody>{body}</tbody></table></div>' if cal_rows
           else f'<p class="st-trd-none">{L("cal.none")}</p>'),
        badge=L("cal.badge", n=len(cal_rows)) if cal_rows else None)

    cards = ""
    for m in range(1, 13):
        Lm = MON.get(m, [])
        items = "".join(li(x) for x in Lm[:4]) or f'<li class="tr-mk__none">{L("mk.none")}</li>'
        more = (f'<details class="tr-mk__more"><summary>{L("mk.more", n=len(Lm)-4)}</summary><ul>' + "".join(li(x) for x in Lm[4:]) + "</ul></details>") if len(Lm) > 4 else ""
        cards += (f'<li class="tr-mk{" is-now" if m == NOWM else ""}"><div class="tr-mk__hd"><span class="tr-mk__m">{MN(m)}</span>'
                  f'{"<span class=tr-mk__now>" + L("common.now") + "</span>" if m == NOWM else ""}<span class="tr-mk__ph">{L("mk.count", n=len(Lm))}</span></div><ul>{items}</ul>{more}</li>')
    evdata = json.dumps(dict(mo=MO, yrs=YRS, thr=1.4, items=EV), ensure_ascii=False, separators=(",", ":"))
    evsafe = evdata.replace("</", "<\\/")
    dialog = (f'<dialog class="st-ev" aria-label="{L("ev.aria")}"><div class="st-ev__in">'
              '<div class="st-ev__hd"><div><div class="st-ev__t"></div><div class="st-ev__sub"></div></div>'
              f'<button type="button" class="st-ev__x" aria-label="{L("common.close")}" onclick="this.closest(\'dialog\').close()">✕</button></div>'
              '<ul class="st-ev__chk"></ul><div class="st-ev__ch"></div><div class="st-ev__tw"></div>'
              f'<p class="st-ev__foot">{L("ev.foot")}</p></div></dialog>')
    month_card = card(L("mk.title"),
        steps(L("common.criteria"), [
                (L("mk.s1h"), L("mk.s1b")),
                (L("mk.s2h"), L("mk.s2b")),
                (L("mk.s3h"), L("mk.s3b"))])
        + insight(N.get("month_note"))
        + f'<ul class="tr-mks">{cards}</ul>'
        + dialog + f'<script type="application/json" id="st-ev-data">{evsafe}</script>' + stl_script(lang) + EV_JS,
        badge=L("fmt.count", n=sum(len(v) for v in MON.values())))
    # 4년 월별 검색량 — 연도별 선을 겹쳐 해마다 같은 달에 오르는지 본다 (분석한 검색어 전체 합)
    SEED = D["meta"]["seed"]
    def year_chart():
        T = D.get("seed_s")
        if not T or not sum(T):
            return ""
        w, h, LM, R_, Tp, B = 900, 170, 52, 14, 12, 24
        iw, ih = w - LM - R_, h - Tp - B
        # 세로축 — 데이터가 있는 구간만(선 그래프는 위치로 읽으므로 0부터 시작하지 않는다)
        vals = [x for e in range(4) for x in T[e*12:e*12+12] if sum(T[e*12:e*12+12])]
        vmin, vmax = min(vals), max(vals)
        rng = (vmax - vmin) or vmax or 1
        raw = rng / 3
        mag = 10 ** (len(str(int(raw))) - 1) if raw >= 1 else 1
        step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
        y0 = max(0, int(vmin // step) * step)
        y1 = (int(vmax // step) + 1) * step
        xs = lambda i: LM + iw * (i + .5) / 12
        ys = lambda v: Tp + ih * (1 - (v - y0) / ((y1 - y0) or 1))
        o = [f'<svg viewBox="0 0 {w} {h}" class="st-ev__svg st-yc__svg" role="img" aria-label="{L("yc.aria")}">']
        t = y0
        while t <= y1 + 1e-9:
            yy = ys(t)
            o.append(f'<line x1="{LM}" x2="{w-R_}" y1="{yy:.1f}" y2="{yy:.1f}" class="st-ev__grid"/>'
                     f'<text x="{LM-6}" y="{yy+4:.1f}" class="st-ev__ax" text-anchor="end">{kv(t)}</text>')
            t += step
        for i, m in enumerate(MO):
            o.append(f'<text x="{xs(i):.1f}" y="{h-8}" class="st-ev__ax" text-anchor="middle">{MN(m)}</text>')
        lg = []
        for e in range(4):
            v = T[e*12:e*12+12]
            if not sum(v):
                continue
            pi = v.index(max(v))
            d = " ".join(f'{"L" if i else "M"}{xs(i):.1f} {ys(x):.1f}' for i, x in enumerate(v))
            o.append(f'<path d="{d}" class="st-ev__ln y{e}{" st-yc__last" if e == 3 else ""}"/>')
            for i, x in enumerate(v):
                p = i == pi
                o.append(f'<circle cx="{xs(i):.1f}" cy="{ys(x):.1f}" r="{5 if p else 2.5}" class="st-ev__pt y{e}{" pk" if p else ""}"/>')
            lg.append(f'<li><i class="y{e}"></i>{YRS[e]} <span>{L("yc.peakAt", m=MN(MO[pi]))}</span></li>')
        # 마우스를 올리면 세로선 + 그 달의 4년 값(최근 해부터)
        tips = []
        for i in range(12):
            rows = "".join(f'<li><i class="y{e}"></i>{YRS[e]}<b>{T[e*12+i]:,}</b></li>'
                           for e in range(3, -1, -1) if sum(T[e*12:e*12+12]))
            tips.append(f'<div class="st-yc__tt">{MN(MO[i])}</div><ul>{rows}</ul>')
            o.append(f'<rect x="{LM + iw*i/12:.1f}" y="{Tp}" width="{iw/12:.1f}" height="{ih}" class="st-yc__hit" data-i="{i}"/>')
        o.append(f'<line x1="0" x2="0" y1="{Tp}" y2="{Tp+ih}" class="st-yc__cross"/>')
        o.append('</svg>')
        js = ("<script>(function(){var b=document.currentScript.previousElementSibling,s=b.querySelector('svg'),"
              "c=s.querySelector('.st-yc__cross'),tp=b.querySelector('.st-yc__tip'),T=" + json.dumps(tips, ensure_ascii=False) + ";"
              "s.querySelectorAll('.st-yc__hit').forEach(function(r){r.addEventListener('mouseenter',function(){"
              "var i=+r.dataset.i,x=+r.getAttribute('x')+(+r.getAttribute('width'))/2,W=s.viewBox.baseVal.width;"
              "c.setAttribute('x1',x);c.setAttribute('x2',x);c.style.opacity=1;tp.innerHTML=T[i];"
              "tp.style.left=(x/W*100)+'%';tp.classList.toggle('r',x>W*.6);tp.style.opacity=1});"
              "r.addEventListener('mouseleave',function(){c.style.opacity=0;tp.style.opacity=0})})})();</script>")
        return (f'<div class="st-yc__wrap">{"".join(o)}<div class="st-yc__tip"></div></div>' + js
                + f'<ul class="st-ev__lg">{"".join(lg)}<li><i class="pk"></i>{L("yc.yearPeak")}</li></ul>'
                + f'<p class="st-yc__foot">{L("yc.foot", seed=esc(SEED))}</p>')
    _yc = year_chart()
    year_card = card(L("yc.title", seed=SEED), _yc) if _yc else ""
    panel_season = year_card + month_card + cal_card

    # ───────────── 탭 2 · 트렌드 ─────────────
    TR, tseq = {}, [0]

    def treg(r):
        key = r["k"]
        if key in TR:
            return TR[key]["id"]
        tseq[0] += 1
        i = f"t{tseq[0]}"
        TR[key] = dict(id=i, k=r["k"], t=TN.get(r.get("t"), L("common.themeNone")), e3=r["e3"], e4=r["e4"], c=r["c"],
                       f=ym(r["f"]), s=r.get("s") or r.get("sp"), y3=r["y3"])
        return i

    import math
    Q1 = f"{ym(M[45])}–{M[47][5:]}"
    Q0 = f"{ym(M[42])}–{M[44][5:]}"
    Y0 = f"{ym(M[33])}–{M[35][5:]}"
    BASE = 10

    def badge(r):
        return f'<span class="mf-badge is-new">{L("badge.new", f=ym(r["f"]))}</span>' if r["c"] == "new" else ""

    def qs(r):
        s = r.get("s") or r.get("sp")
        return sum(s[9:12]), sum(s[18:21]), sum(s[21:24])      # 전년 동기 · 직전 3개월 · 최근 3개월

    def rates(r):
        y0, q0, q1 = qs(r)
        return (q1 / y0 - 1 if y0 else None), (q1 / q0 - 1 if q0 else None)

    def dirn(r, both):
        """QoQ 순(both=False) — 상승 'up' = QoQ>0 / 하락 'dn' = QoQ<0.
        QoQ+YoY(both=True) — 상승 = QoQ>0 · YoY>0 / 하락 = QoQ<0 · YoY<0. 그 외 None."""
        y0, q0, q1 = qs(r)
        if q0 < BASE or (both and y0 < BASE):
            return None
        qq = q1 / q0 - 1
        yy = q1 / y0 - 1 if y0 else 0
        if qq > 0 and (not both or yy > 0):
            return "up"
        if qq < 0 and (not both or yy < 0):
            return "dn"
        return None

    def pct_(v):
        return "—" if v is None else f"{v*100:+.0f}%"

    def dyy(r):
        y0, _, q1 = qs(r)
        d = q1 - y0
        return ("+" if d > 0 else "−") + kv(abs(d))

    ALL = []
    for tid, v in TK.items():
        ALL += v["up"] + v["dn"]
    ALL += D.get("untk", [])          # 미분류 검색어도 상승·하락 후보 — "테마 구분 없이 전체에서"
    seen_k, POOL = set(), []
    for r in ALL:
        if r["k"] not in seen_k:
            seen_k.add(r["k"])
            POOL.append(r)
    gain = lambda r: qs(r)[2] - qs(r)[1]          # QoQ 증감량 — 정렬 기준
    UPQ = sorted([r for r in POOL if dirn(r, False) == "up"], key=lambda r: -gain(r))
    DNQ = sorted([r for r in POOL if dirn(r, False) == "dn"], key=lambda r: gain(r))
    UP = sorted([r for r in POOL if dirn(r, True) == "up"], key=lambda r: -gain(r))
    DN = sorted([r for r in POOL if dirn(r, True) == "dn"], key=lambda r: gain(r))

    # ① 상승·하락 키워드
    def top_list(Lk):
        def cell(d, pc, on):
            c = "is-grow" if d > 0 else "is-drop"
            return (f'<td class="{c}{" kt-on" if on else ""}"><b>{"+" if d > 0 else "−"}{fmt(abs(d))}</b>'
                    f'<small>{pct_(pc)}</small></td>')
        rows = ""
        for n, r in enumerate(Lk[:20], 1):
            y0, q0, q1 = qs(r)
            yy, qq = rates(r)
            rows += (f'<tr><td class="kt-n">{n}</td>'
                     f'<td class="kt-name"><button type="button" class="kt-k" data-tr="{treg(r)}" onclick="stTr(this)">{esc(r["k"])}</button>{badge(r)}</td>'
                     f'<td class="kt-spark">{spark_html(r.get("s") or r.get("sp"), width=96, height=24)}</td>'
                     f'<td><b>{fmt(q1)}</b></td>'
                     + cell(q1 - q0, qq, True) + cell(q1 - y0, yy, False) + '</tr>')
        if not rows:
            return f'<p class="tr-sp__none">{L("kt.none")}</p>'
        return (f'<div class="kt-wrap"><table class="kt kt--2"><thead><tr><th></th><th>{L("common.keyword")}</th><th class="kt-spark">{L("kt.spark")}</th><th>{L("kt.recent3")}</th>'
                f'<th class="kt-on">QoQ ▼<span>{L("kt.qoqSub")}</span></th>'
                f'<th>YoY<span>{L("kt.yoySub")}</span></th></tr></thead><tbody>{rows}</tbody></table></div>')

    S1 = (L("ud.s1h"), L("ud.s1b"))
    S2 = (L("ud.s2h"), L("ud.s2b"))
    FOOT = L("ud.foot")

    top_card = card(L("ud.title"),
        steps(L("common.criteria"), [S1, S2], numbered=L("ud.viewN"))
        + f'<p class="st-steps__f" style="margin:-10px 0 4px">{FOOT}</p>'
        + insight(N.get("updown_note"))
        + '<div class="tr-ctl">'
          f'<div class="tr-seg tr-seg--dir" role="tablist" aria-label="{L("ud.dirAria")}" data-k="d">'
          f'<button type="button" role="tab" aria-selected="true" class="is-on" data-v="up" onclick="trPick(this)">{L("ud.up")}</button>'
          f'<button type="button" role="tab" aria-selected="false" data-v="dn" onclick="trPick(this)">{L("ud.dn")}</button></div>'
          f'<div class="tr-sort"><span>{L("ud.view")}</span><div class="tr-seg tr-seg--sort" role="tablist" aria-label="{L("ud.view")}" data-k="s">'
          f'<button type="button" role="tab" aria-selected="true" class="is-on" data-v="qoq" onclick="trPick(this)">{L("ud.viewQoq")}</button>'
          f'<button type="button" role="tab" aria-selected="false" data-v="both" onclick="trPick(this)">{L("ud.viewBoth")}</button></div></div></div>'
        + f'<div class="tr-segp" data-p="up-qoq">{top_list(UPQ)}</div>'
        + f'<div class="tr-segp" data-p="up-both" hidden>{top_list(UP)}</div>'
        + f'<div class="tr-segp" data-p="dn-qoq" hidden>{top_list(DNQ)}</div>'
        + f'<div class="tr-segp" data-p="dn-both" hidden>{top_list(DN)}</div>'
        + '<script>function trPick(b){var g=b.parentNode,c=b.closest(".dash-card");g.querySelectorAll("button").forEach(function(x){var on=x===b;x.classList.toggle("is-on",on);x.setAttribute("aria-selected",on)});'
          'var d=c.querySelector(\'.tr-seg[data-k="d"] .is-on\').dataset.v,s=c.querySelector(\'.tr-seg[data-k="s"] .is-on\').dataset.v;'
          'c.querySelectorAll(".tr-segp").forEach(function(x){x.hidden=x.dataset.p!==d+"-"+s})}</script>'
        + (f'<p class="mf-note mf-note--lead">{N["top_note"]}</p>' if N.get("top_note") else ""),
        badge="Top 20", note=L("ud.note", q=Q1))

    import st_build as SB
    KMAP = {r["k"]: r for r in POOL}

    # ⓪-2 주요 트렌드 — market-flow-report trends 규칙(같은 갈래 안에서 2개 이상 · 최대 5개 · 쓴 차례대로)
    TP = SB.trend_pool(POOL)
    BR = {r["k"]: g for g, Lk in TP.items() for r in Lk}

    def tr_section(x):
        mem = [k for k in (x.get("memberKeywords") or []) if k in BR]
        if not mem:
            return None
        side = lambda k: "dn" if BR[k] == "falling" else "up"      # new · growing 은 같은 방향(오름)으로 본다
        g = side(mem[0])
        mem = [k for k in mem if side(k) == g]
        if len(mem) < 2:
            return None
        rows = ""
        for k in mem[:10]:
            r = KMAP[k]
            d = r["e4"] - r["e3"]
            pc = f'{d / r["e3"] * 100:+.0f}%' if r["e3"] else L("common.new")
            cls = "is-grow" if d > 0 else "is-drop"
            rows += (f'<tr><th scope="row"><button type="button" class="tr-kw" data-tr="{treg(r)}" onclick="stTr(this)">{esc(k)}</button>{badge(r)}</th>'
                     f'<td>{fmt(r["e3"]) if r["e3"] else "–"}</td><td><b class="{cls}">{fmt(r["e4"])}</b></td>'
                     f'<td class="{cls}">{"+" if d > 0 else "−"}{fmt(abs(d))}<span class="tr-dim-s">{pc}</span></td></tr>')
        return (max(max(KMAP[k]["e3"], KMAP[k]["e4"]) for k in mem),
                '<section class="mf-trend st-trd">'
                f'<h4 class="mf-trend__title">{esc(x.get("title", ""))}</h4>'
                + (f'<p class="mf-trend__sub">{esc(x["basis"])}</p>' if x.get("basis") else "")
                + (f'<p class="st-trd__ins">{x["insight"]}</p>' if x.get("insight") else "")
                + f'<div class="mf-table-wrap"><table class="mf-table tr-sp__tbl st-trd__tbl"><thead><tr><th scope="col">{L("common.keyword")}</th>'
                f'<th scope="col">{YRS[2]}</th><th scope="col">{YRS[3]}</th><th scope="col">{L("common.change")}</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div></section>')

    _secs = [s for s in (tr_section(x) for x in (N.get("years_trends") or [])) if s]
    if len(_secs) > 5:
        keep = set(sorted(range(len(_secs)), key=lambda i: -_secs[i][0])[:5])
        _secs = [s for i, s in enumerate(_secs) if i in keep]
    trends_card = card(L("trd.title"),
        f'<p class="st-steps__f" style="margin:0 0 4px">{L("trd.lead")}</p>'
        + ('<div class="st-trd-list">' + "".join(s[1] for s in _secs) + '</div>' if _secs
           else f'<p class="st-trd-none">{L("trd.none")}</p>'),
        badge=L("fmt.count", n=len(_secs)) if _secs else None, note=L("common.yearNote"))

    # ① 테마별 최근 1년 트렌드 (최근 12개월 vs 직전 12개월)
    def yr_row(r, kind, extra):
        d = r["e4"] - r["e3"]
        pc = f'{d / r["e3"] * 100:+.0f}%' if r["e3"] else L("common.new")
        cls = "is-grow" if kind == "up" else "is-drop"
        return (f'<tr{" class=\"tr-x\"" if extra else ""}><th scope="row"><button type="button" class="tr-kw" data-tr="{treg(r)}" onclick="stTr(this)">{esc(r["k"])}</button>{badge(r)}</th>'
                f'<td>{fmt(r["e3"])} → <b class="{cls}">{fmt(r["e4"])}</b></td>'
                f'<td class="{cls}">{"+" if d > 0 else "−"}{fmt(abs(d))}<span class="tr-dim-s">{pc}</span></td></tr>')

    def yr_half(Lk, kind):
        head = L("yr.headUp") if kind == "up" else L("yr.headDn")
        if not Lk:
            none = L("yr.noneUp") if kind == "up" else L("yr.noneDn")
            return f'<div class="tr-sp__half"><h5 class="tr-sp__h tr-sp__h--{kind}">{head}</h5><p class="tr-sp__none">{none}</p></div>'
        rows = "".join(yr_row(r, kind, i >= 5) for i, r in enumerate(Lk[:20]))
        return (f'<div class="tr-sp__half"><div class="mf-table-wrap"><table class="mf-table tr-sp__tbl tr-sp__tbl--{kind}">'
                f'<thead><tr><th scope="col">{head}</th><th scope="col">{YRS[2]} → {YRS[3]}</th><th scope="col">{L("common.change")}</th></tr></thead>'
                f'<tbody>{rows}</tbody></table></div></div>')


    def yr_section(t):
        U, Dn = TK[t["id"]]["up"], TK[t["id"]]["dn"]
        more = max(min(len(U), 20), min(len(Dn), 20)) > 5
        return (f'<section class="tr-sp"><div class="tr-sp__hd"><div><h4 class="mf-topic__title">{esc(t["name"])}</h4>'
                f'<span class="mf-topic__meta">{L("yr.count", n=t["n"])}</span></div></div>'
                + f'<div class="tr-sp__grid">{yr_half(U, "up")}{yr_half(Dn, "dn")}</div>'
                + (f'<button type="button" class="tr-xbtn" data-more="{esc(L("yr.more"))}" data-less="{esc(L("yr.less"))}" onclick="var s=this.closest(\'.tr-sp\'),o=s.classList.toggle(\'is-open\');this.firstChild.textContent=o?this.dataset.less:this.dataset.more">{L("yr.more")}</button>' if more else "")
                + '</section>')

    year_card = card(L("yr.title"),
        '<div class="tr-sp-list">' + "".join(yr_section(t) for t in sorted(THEMES, key=lambda t: -t["e4"])) + "</div>",
        note=L("common.yearNote"))

    MO4 = [int(m[5:]) for m in M[36:48]]
    trdata = json.dumps(dict(mo=MO4, e3=YRS[2], e4=YRS[3], items={v["id"]: v for v in TR.values()}), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    trdlg = (f'<dialog class="st-ev st-tr" aria-label="{L("tr.aria")}"><div class="st-ev__in">'
             '<div class="st-ev__hd"><div><div class="st-ev__t"></div><div class="st-ev__sub"></div></div>'
             f'<button type="button" class="st-ev__x" aria-label="{L("common.close")}" onclick="this.closest(\'dialog\').close()">✕</button></div>'
             '<ul class="st-ev__chk"></ul><div class="st-ev__ch"></div><div class="st-ev__tw"></div>'
             f'<p class="st-ev__foot">{L("tr.foot", engines=L("engines." + gl))}</p></div></dialog>')
    panel_updown = top_card
    panel_trend = trends_card + year_card + trdlg + f'<script type="application/json" id="st-tr-data">{trdata}</script>' + stl_script(lang) + TR_JS

    # ───────────── 셸 ─────────────
    TABS = [L("tab.season"), L("tab.trend"), L("tab.updown")]
    PANELS = [panel_season, panel_trend, panel_updown]
    tabs = ('<nav class="dash-tabs" aria-label="tabs"><div class="dash-tabs__inner" role="tablist">' + "".join(
        f'<button type="button" class="dash-tab{" active" if i == 0 else ""}" role="tab" id="dash-tab-{i}" aria-selected="{"true" if i == 0 else "false"}" data-panel="{i}">{esc(t)}</button>'
        for i, t in enumerate(TABS)) + "</div></nav>")
    panels = "".join(f'<section class="dash-tab-panel{" active" if i == 0 else ""}" data-panel="{i}" role="tabpanel">{p}</section>' for i, p in enumerate(PANELS))
    ov = N.get("overview") or {}
    overview = "".join(f'<span class="st-ov"><strong>{lab}</strong> — {ov[k]}</span>'
                       for k, lab in (("season", L("tab.season")), ("trend", L("tab.trend")), ("updown", L("tab.updown"))) if ov.get(k))
    TITLE = L("report.title")
    MARKET = L("market." + gl)
    KEPT = f'{meta["kept"]:,}'
    cover = ('<div class="dash-cover-block"><div class="dash-card"><div class="dash-cover-gradient">'
             f'<div class="dash-cover-eyebrow">{L("cover.eyebrow", title=TITLE, market=MARKET)}</div><div class="dash-cover-title">{TITLE}</div>'
             f'<div class="dash-cover-category">{esc(seed)}</div>'
             f'<div class="dash-cover-meta">{L("cover.meta", date=esc(meta["collected"]), n=KEPT)}</div></div>'
             f'<div class="mr-summary-box mr-summary-box--dash"><div class="mr-summary-box__title">{L("cover.bgTitle")}</div>'
             f'<p class="mr-summary-text">{L("cover.bg", seed=esc(seed), wa=josa_wa(seed), market=MARKET, engines=L("engines." + gl))}</p>'
             f'<p class="mr-summary-text mr-overview">{overview}</p></div></div></div>')

    def a4_page(no, eyebrow, title, desc, body):
        return (f'<div class="rpt-page" id="page-{no}"><div class="page-hd"><span class="page-hd__brand">ListeningMind.AI</span>'
                f'<span class="page-hd__report">{TITLE} · {esc(seed)}</span><span class="page-hd__num">{no:02d}</span></div>'
                f'<div class="page-body"><div class="sec-hd"><div class="sec-eyebrow"><span class="sec-eyebrow__line"></span><span class="sec-eyebrow__text">{esc(eyebrow)}</span></div>'
                f'<div class="sec-title">{esc(title)}</div><div class="sec-desc">{esc(desc)}</div></div>{body}</div></div>')
    a4_cover = ('<div class="rpt-page rpt-page--cover" id="page-0"><div class="cover-body"><div><div class="cover-lm">ListeningMind.AI</div>'
                f'<div class="cover-title">{TITLE}</div><div class="cover-category">{esc(seed)}</div>'
                f'<div class="cover-meta"><span>{esc(meta["collected"])}</span><span class="cover-meta-sep">|</span><span>{L("a4.coverMeta", n=KEPT, new=len(D["new"]))}</span></div></div></div></div>')
    A4DESC = [L("a4.desc.season"), L("a4.desc.trend"), L("a4.desc.updown")]
    a4_body = "".join(a4_page(i + 1, f"SECTION {i+1:02d}", t, A4DESC[i], p) for i, (t, p) in enumerate(zip(TABS, PANELS)))

    tpl = (PKG / "templates" / "season-trend.html").read_text(encoding="utf-8")
    blocks = {
        "{{LANG}}": HTML_LANG[lang], "{{FONT_HREF}}": FONT_HREF[lang], "{{CATEGORY}}": esc(seed), "{{REPORT_TITLE}}": TITLE,
        "{{TOOLBAR_DASH_BTN}}": L("toolbar.dash"), "{{TOOLBAR_A4_LABEL}}": "A4",
        "{{INLINED_CSS}}": inline_styles(PKG / "styles", "season-trend", SKILL_STYLES),
        "{{INLINE_SCRIPT}}": BASE_SCRIPT,
        "{{DASH_COVER}}": cover, "{{DASH_TABS}}": tabs, "{{DASH_PANELS}}": panels,
        "{{A4_COVER_PAGE}}": a4_cover, "{{A4_BODY_PAGE}}": a4_body,
    }
    out = _apply(tpl, blocks)
    if "{{" in out:
        print("❌ 템플릿 자리표시자가 남았습니다", file=sys.stderr)
        return 1
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(out, encoding="utf-8")
    print(f"✅ {a.out} ({len(out):,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
