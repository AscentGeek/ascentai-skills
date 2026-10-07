# -*- coding: utf-8 -*-
"""카테고리 지도 HTML 을 만든다 — 한 장 요약 · 카테고리 지도 · 세부 수요 심층 · 종합 · 한계.

 입력은 회차 폴더 하나다 — config.json · work/curate.json · work/judge.json · work/walk.json
 · work/candidates.json · work/mods_<카테고리>.json · data/cat/*.json.

 브랜드 속성으로 분기하지 않는다. 화면이 갈리는 기준은 데이터 상태뿐이다.

 사용:  python3 build_report.py <회차> [--out report.html] [--meta "조회 조건 한 줄"]
        python3 build_report.py --selftest
"""
import json,html,re,math,sys,os,collections,argparse
from pathlib import Path
from collections import Counter,defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import components as ca                    # _core · t() escape_with_strong() format_count()
from inline_styles import inline_styles    # _core
from style_order import SKILL_STYLES       # this skill

PKG_ROOT      = os.path.dirname(os.path.dirname(HERE))   # lm-brand-competition/ inside the zip
STYLES_DIR    = Path(PKG_ROOT) / "_shared" / "styles"   # inline_styles() 가 Path 를 기대한다
LABELS_DIR    = os.path.join(PKG_ROOT, "_shared", "labels")
TEMPLATES_DIR = os.path.join(PKG_ROOT, "_shared", "templates")
SLUG = "brand-competition"

REPORT_LANGS = ("kr", "jp", "us")
HTML_LANG = {"kr": "ko", "jp": "ja", "us": "en"}
FONT_HREF = {
    "kr": "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;900&display=swap",
    "jp": "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;900&display=swap",
    "us": "https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700;900&display=swap",
}
LOCALE_FONT_OVERRIDE = {
    "kr": "",
    "jp": "html { --font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, Sans-serif; }",
    "us": "html { --font-family: 'Noto Sans', -apple-system, BlinkMacSystemFont, Sans-serif; }",
}
TOOLBAR_DASH_BTN  = {"kr": "대시보드", "jp": "ダッシュボード", "us": "Dashboard"}   # i18n-ok
TOOLBAR_PRINT_BTN = {"kr": "인쇄", "jp": "印刷", "us": "Print"}   # i18n-ok

def _asset(name):
    """templates/ 에 같이 실린 JS 를 읽는다 (build.sh 가 templates/* 를 통째로 복사한다)."""
    with open(os.path.join(TEMPLATES_DIR, name), encoding="utf-8") as f:
        return f.read()

def _load_labels(lang):
    """라벨 파일은 리포트 언어(--lang)로 고른다. 시장(--gl)과는 독립이다."""
    with open(os.path.join(LABELS_DIR, f"{SLUG}.{lang}.json"), encoding="utf-8") as f:
        return json.load(f)

LABELS = {}                              # 현재 회차의 라벨 · build() 가 채운다
def _t(key, **kw):
    """라벨 조회 + 자리표시자 치환. 값은 이미 안전한 문자열이라고 본다 —
       데이터는 넣는 쪽에서 esc() 하고 넘긴다(이중 escape 방지)."""
    v = ca.t(LABELS, key)
    for k, val in kw.items():
        v = v.replace("{" + k + "}", str(val))
    return v

def bn(b,tip=""):
    """브랜드명 머리글 — 열이 좁으면 「…」로 줄이고 마우스를 올리면 커스텀 툴팁으로 전체 이름을 띄운다.
    nowrap 머리글에 긴 브랜드명이 이웃 칸을 덮어 글자가 겹치던 문제. A4 에서는 CSS 가 줄바꿈으로 되돌린다."""
    return f'<span class="bn" data-full="{esc(b)}" data-tip="{esc(tip)}">{kw(b)}</span>'

def _ev0(v): return v if v else '<span class=na>0</span>'
def _st(v):
    return (_t("axis.step", n=v) if (v and v > 0) else (_t("axis.beforeSeed") if v else "-"))
esc=html.escape
# 검색어(시장 언어)를 찍는 자리. 번역이 넘어왔으면 원문·번역 두 벌을 심는다 —
# 속성값(title= · data-*)에는 쓰지 않는다. 브라우저 기본 툴팁은 태그를 글자로 찍는다.
kw=lambda v: ca.kw_html(v)
def n(v): return "-" if v is None else f"{v:,}"
def short(v):
    """큰 수를 줄여 쓴다. 자릿수 체계가 언어마다 달라 접미사만 바꿔서는 안 된다 —
       한국어·일본어는 만(10^4), 영어는 k·M(10^3·10^6)이다. num.system 라벨로 가른다."""
    if v is None: return "-"
    if _t("num.system")=="man":
        return _t("num.man", v=f"{v/10000:.1f}").replace(".0","") if v>=10000 else f"{v:,}"
    if v>=1000000: return _t("num.m", v=f"{v/1000000:.1f}").replace(".0","")
    if v>=1000:    return _t("num.k", v=f"{v/1000:.1f}").replace(".0","")
    return f"{v:,}"
def pct(v): return "-" if v is None else f"{v:.1f}%"

# ── 판정 · 내부값은 judge.py 가 쓰는 한국어 그대로 두고, 표시만 라벨로 간다.
#    JR·CLS·JC 를 표시 문자열로 키잡으면 번역하는 순간 전부 깨지므로 슬러그로 키잡는다.
VK   = {"우위":"owned","경합":"contested","열세":"trailing","없음":"unclaimed","없음 · 자사 1위":"unclaimed"}
WAK  = {"우위":"ahead","경합":"even","열세":"behind","없음":"none","보류":"hold"}
JR   = {"owned":0,"emerging":1,"contested":2,"trailing":3,"unclaimed":4}
CLS  = {"owned":"j-own","emerging":"j-pot","contested":"j-cmp","trailing":"j-low","unclaimed":"j-emp"}
VERDICTS = ("owned","emerging","contested","trailing","unclaimed")
def VNAME(slug): return _t("verdict."+slug)
BUCKETS = ("named","walked","absent")
def BN(slug):
    """판정 슬러그와 측정 축 버킷 슬러그를 한 함수로 표시 문자열로 바꾼다."""
    return _t("bucket."+slug) if slug in BUCKETS else VNAME(slug)
def WNAME(axis):  return _t("walk."+WAK.get(axis,"hold"))


def build(run, out, *, gl, lang, date, translations=None):
    global LABELS
    LABELS = _load_labels(lang)
    # 검색어 번역 — 시장 언어와 리포트 언어가 다를 때만 넘어온다. 없으면 kw() 는 원문만 찍는다.
    _tr = json.loads(Path(translations).read_text(encoding="utf-8")) if translations else {}
    ca.set_translations(_tr)
    meta = _t("cover.meta", market=_t(f"report.marketLabel.{gl.upper()}"), date=date)
    R=run.rstrip("/")+"/"
    cfg=json.load(open(R+"config.json")); OWN=cfg["brand"]
    # B2B 같은 브랜드 속성 플래그는 두지 않는다 — 분기는 데이터 상태로만 한다.
    hr=lambda x:(x["own_rate"] is not None) or any(c["rate"] is not None for c in x["comp"])   # 이 카테고리에서 점유율을 쟀나
    J=json.load(open(R+"work/judge.json"))
    C_=json.load(open(R+"work/curate.json")); C_.pop("_note",None)
    WK=json.load(open(R+"work/walk.json"))
    # 2-b 에서 범위를 좁혔으면 그 사실이 리포트에 남아야 한다 — 빠진 자리가 「없음」으로 읽힌다
    CAND=json.load(open(R+"work/candidates.json")) if os.path.exists(R+"work/candidates.json") else {}
    SKIP=sorted([k for k,v in CAND.items() if not v.get("chosen")],
                key=lambda k:-(CAND[k].get("vol") or 0))
    # 경로 모수는 회차의 path_finder limit 이다 — 문구에 숫자를 박지 않는다
    _np=[w.get("npaths") for w in WK.values() if w.get("npaths")]
    PL=collections.Counter(_np).most_common(1)[0][0] if _np else 300
    PLs=f"{PL:,}"; PF=max(6,round(PL*0.02)); PG=max(15,round(PL*0.05))
    SELFV=any(x.get("own_self") for x in J)   # 브랜드 총 검색량을 잰 회차인가
    RATED0=any(hr(x) for x in J)             # 점유율을 한 곳이라도 쟀나
    BI=len(json.load(open(R+f"data/cat/{OWN}_brand_intent.json"))["data"])
    SPL={}
    # 행의 정본은 judge.json 이다 — 지정 카테고리는 curate.json 에 라벨이 없을 수 있다
    for c in set(C_)|{x["term"] for x in J}:
        f=R+f"work/mods_{c}.json"
        SPL[c]=json.load(open(f)) if os.path.exists(f) else {"n":0,"mods":[]}
    # ── 판정: 이름 축(검색 점유율 2배 규칙) · 탐색 축은 보조
    # 라벨(참전·부분 참전·미판매·미확인)은 curate.json 의 내부값이다 — 표시만 번역한다
    PZC={"참전":"pz-in","부분 참전":"pz-part","미판매":"pz-no","미확인":"pz-unk"}
    PZK={"참전":"in","부분 참전":"part","미판매":"no","미확인":"unknown"}
    def _pz(x):
        p=x.get("presence")
        if not p: return ""
        return f'<small class="pz {PZC.get(p["label"],"pz-unk")}" title="{esc(p.get("note",""))}">{_t("presence."+PZK.get(p["label"],"unknown"))}</small>'
    def _bden(x): return (x.get("sos") or {}).get("denom",0)
    def _bsum(x):
        s=x.get("sos") or {}
        if not s: return '<td class="num na">-</td>'
        return f'<td class="num">{n(s.get("denom",0))}</td>'
    def ju(x):
        """판정 슬러그를 돌려준다(표시 문자열이 아니다) — 정렬·색·비교가 전부 이 값으로 간다."""
        b=VK[x["name"]]; w=x["walk"]
        if b=="unclaimed" and w and w["axis"]=="우위": b="emerging"
        return b
    def badge(x):
        # 탐색 축은 이름 축이 판정을 못 낸 곳(주인 없음·잠재 선점)에만 배지로 붙인다.
        # 둘 다 값을 내면 실측 35곳 중 14곳(40%)이 엇갈리는데 어느 쪽을 믿을지 규칙이 없어 소음이 된다.
        b=ju(x); w=x["walk"]
        t=WNAME(w["axis"]) if (w and b in ("unclaimed","emerging")) else ""
        return f'<span class="jd {CLS[b]}">{VNAME(b)}</span>'+(f'<span class="jt">{t}</span>' if t else "")
    # ── 세부 수요 판정 (자사 부착률만) — 경쟁사 결합은 조회하지 않았다
    WATCH=[b for b in cfg.get("watch_brands",[]) if b!=OWN]
    _WTAG=lambda: f' <span class="wtag">{_t("tag.watch")}</span>'
    wb=lambda b:(_WTAG() if b in WATCH else "")
    wc=lambda x:(_WTAG() if x.get("src")=="지정" else "")   # 카테고리 쪽 지정 배지
    # 0 으로 찍지 않는다 — `-` 쟀는데 검색량 데이터가 없다 · `·` 아예 안 쟀다
    def catvol(x):
        if x["vol12"]: return n(x["vol12"])
        _nd, _nq = _t("state.noData"), _t("state.notQueried")
        return (f'<span class="na" title="{_nd}">-</span>' if x.get("queried")
                else f'<span class="na" title="{_nq}">·</span>')
    WM={"우위":"owned","경합":"contested","열세":"trailing","없음":"unclaimed","보류":"hold"}
    DEEP=[x for x in J if x.get("deep")]
    # 세부 수요는 심층 대상 카테고리에서만 판정한다. '<세부 수요> <카테고리>' 를 시드로 따로 조회해야
    # 모수가 서고(경로 = 회차 limit) 카테고리와 같은 2배 규칙을 쓸 수 있다.
    def dq(q,ax): return ((q.get("deep") or {}).get(ax)) or {}
    def cbadge(a):
        k=WM.get(a,"hold"); return f'<span class="jd {CLS.get(k,"j-emp")}">{VNAME(k) if k in CLS else _t("walk.hold")}</span>'
    def cepsum(x):
        """심층 카테고리 세부 수요 한 줄 요약."""
        cs=[q for q in x["ceps"] if q["vol"]]
        if cs:
            tv=sum(q["vol"] for q in cs); top=sorted(cs,key=lambda q:-q["vol"])[:3]
            p1=_t("deep.demandConcentration", items=" · ".join(f'<b>{kw(q["cep"])}</b> {short(q["vol"])}({q["vol"]/tv*100:.0f}%)' for q in top))
        else: p1=_t("deep.noVolume", term=kw(x["term"]))
        won=[q for q in x["ceps"] if dq(q,"path").get("axis")=="우위" or dq(q,"intent").get("axis")=="우위"]
        lost=[q for q in x["ceps"] if dq(q,"path").get("axis")=="열세" or dq(q,"intent").get("axis")=="열세"]
        p2=(_t("deep.ownAhead", own=esc(OWN), items=" · ".join(f'<b>{kw(q["cep"])}</b>' for q in won[:3])) if won
            else _t("deep.ownAheadNone", own=esc(OWN)))
        p3=""
        if lost:
            q=sorted(lost,key=lambda t:-(t["vol"] or 0))[0]
            d=dq(q,"path") if dq(q,"path").get("axis")=="열세" else dq(q,"intent")
            p3=_t("deep.worstGap", cep=kw(q["cep"]), own=esc(OWN), ownN=d["own"], top=kw(d["top"]), topN=d["top_n"])
        return p1+p2+p3

    def topname(x,with_rep=True):
        cs=x["comp"]; co=x.get("co_top") or []
        if co:
            rs="·".join(f'{c["rate"]}%' for c in cs if c["brand"] in co)
            return _t("comp.tied", brands="·".join(kw(b) for b in co), rates=rs)
        t=cs[0]
        rep=(_t("comp.repKw", kw=kw(t.get("rep_kw") or ""), vol=n(t.get("rep_vol"))) if with_rep and t.get("rep_kw") else "")
        return f'{kw(t["brand"])} {t["rate"]}%{rep}'
    def why(x):
        t=x["comp"][0] if x["comp"] else None; o=x["own_rate"]
        if not hr(x):
            return _t("why.noBrandKw", term=kw(x["term"]))
        if not t: return _t("why.noCompetitor")
        if o is None: return _t("why.ownAbsent", own=esc(OWN), top=topname(x), verdict=VNAME(ju(x)))

        r=o/t["rate"] if t["rate"] else 0
        s=_t("why.lead", own=esc(OWN), rate=o, top=topname(x))
        if x["name"]=="우위": return s+_t("why.owned", own=esc(OWN), x=f"{r:.1f}")
        if x["name"]=="열세": return s+_t("why.trailing", x=f"{1/r:.1f}")
        if x["name"].startswith("없음"):
            return s+_t("why.unclaimed", ratio=(x.get("sos") or {}).get("name_ratio",0))
        return s+_t("why.contested", x=f"{max(r,1/r if r else 0):.1f}")
    GORD={g:i for i,g in enumerate(dict.fromkeys(x["group"] for x in J))}
    J.sort(key=lambda x:(GORD[x["group"]],-x["vol12"]))
    for _x in J: _x["co_top"]=[]   # 공동 1위 표시는 쓰지 않는다(팀 피드백)
    CID={x["term"]:f"c{k}" for k,x in enumerate(J)}
    _SH={x["term"]:((x.get("sos") or {}).get("brands") or {}) for x in J}
    _tot=defaultdict(int)
    for _c,_d in _SH.items():
        for _b,_v in _d.items(): _tot[_b]+=_v.get("vol") or 0
    _bc=Counter(b for _d in _SH.values() for b,v in _d.items() if v.get("vol"))
    # 여러 카테고리에 걸친 브랜드를 왼쪽에 — 가로로 훑을 때 교차 경쟁이 먼저 보인다
    BCOLS=[OWN]+[b for b,_ in sorted(_tot.items(),key=lambda t:(-_bc[t[0]],-t[1])) if b!=OWN and _tot[b]>0]
    try: BIN=len(json.load(open(R+f"data/cat/{OWN}_brand_intent.json"))["data"])
    except Exception: BIN='-'
    try: BPN=len(json.load(open(R+f"data/cat/{OWN}_brand_path.json"))["data"])
    except Exception: BPN='-'
    NTOP=10   # 원소주 + 두루 나온 경쟁 브랜드 10개만 기본으로 보인다
    def _top12(x):
        d=_SH.get(x["term"],{})
        tb=sorted([(v.get("vol") or 0,b) for b,v in d.items() if b!=OWN and v.get("vol")],reverse=True)[:2]
        if not tb: return '<td class="t12 sep"><span class="na">{_t("state.noBrandKw")}</span></td>'
        return ('<td class="t12 sep">'+" ".join(f'<span class="lg r{i+1}" title="{esc(b)} · {n(v)} · {d[b]["share"]}%">{kw(b)} <span class="mv">{short(v)}</span><span class="ms">{d[b]["share"]}%</span></span>' for i,(v,b) in enumerate(tb))+'</td>')
    def _bcells(x):
        d=_SH.get(x["term"],{}); co=x.get("co_top") or []
        vals=sorted([v.get("vol") or 0 for v in d.values() if v.get("vol")],reverse=True)
        out=[]
        for i_,b in enumerate(BCOLS):
            if i_==NTOP+1: out.append('<td class="bmore"></td>')
            # bc = 경쟁사 열 표식(A4 에서 접는다) · 자사 열은 인쇄물에도 남아야 하므로 달지 않는다
            ow=(" own" if b==OWN else " bc")+(" sep" if i_==1 else "")+(" bx" if i_>NTOP else "")
            t=d.get(b)
            if not t or not t.get("vol"):
                out.append(f'<td class="num empty{ow}">-</td>'); continue
            r=1+sum(1 for w in vals if w>t["vol"]); rc=" r1" if r==1 else (" r2" if r==2 else "")
            cc=" co" if b in co else ""
            out.append(f'<td class="num{rc}{ow}{cc}" title="{_t("tip.brandCell", brand=esc(b), share=t["share"], vol=n(t["vol"]), n=t["n_kw"], rank=r)}">'
                       f'<span class="mv">{short(t["vol"])}</span><span class="ms">{(str(t["share"])+"%") if t["share"]>=0.1 else "&lt;0.1%"}</span></td>')
        return "".join(out)
    # ── S0 행
    rows=[]
    for k,x in enumerate(J):
        if (not hr(x)) and x.get("own_self"):   # 부착률을 못 잰 곳에서만 참고값을 보인다
            sv=lambda q:(q.get("self_vol") or 0)
            mv=max([x.get("own_self") or 0]+[sv(c) for c in x["comp"]]) or 1
            bhead=_t("bars.brandTotalHead")
            bars=f'<div class="xb me"><span class="xn">{esc(OWN)}</span><span class="xt"><span class="xf" style="width:{(x.get("own_self") or 0)/mv*100:.1f}%"></span></span><span class="xv">{short(x.get("own_self") or 0)}</span></div>'
            bars+="".join(f'<div class="xb"><span class="xn">{kw(c["brand"])}{wb(c["brand"])}</span><span class="xt"><span class="xf" style="width:{sv(c)/mv*100:.1f}%"></span></span><span class="xv">{short(sv(c)) if sv(c) else "<span class=na>-</span>"}</span></div>' for c in x["comp"])
            bars+=f'<p class="xs">{_t("bars.brandTotalNote")}</p>'
        else:
            mx=max([x["own_rate"] or 0]+[c["rate"] or 0 for c in x["comp"]]) or 1
            _so=x.get('sos') or {}; bhead=_t("bars.shareHead", denom=n(_so.get("denom",0)))
            OWNV=cfg.get("own",[OWN])
            def _bar(name,rate,vol,kws,me=False,co=False):
                tag=(f' <i class="cot">{_t("comp.tiedTag")}</i>' if co else "")
                head=(f'<summary class="xb{" me" if me else ""}"><span class="xn">{kw(name)}{"" if me else wb(name)}{tag}</span>'
                      f'<span class="xt"><span class="xf" style="width:{(rate or 0)/mx*100:.1f}%"></span></span>'
                      f'<span class="xv">{pct(rate)} <small>{short(vol) if vol else ""}</small></span></summary>')
                _pw=(dict(x["walk"]["first"]).get(name,0) if x.get("walk") and x["walk"].get("first") else None)
                if not kws: return f'<details class="xbd"{"" if _pw else " disabled"}>{head}<div class="kwl na">'+_t("bars.noKwFor", brand=kw(name))+(_t("bars.butOnPath", n=_pw) if _pw else '')+'.</div></details>'
                mxv=max(v for _,v in kws) or 1
                def _hl(w):
                    e=esc(w)
                    for a in sorted(set([name]+(OWNV if me else [])),key=len,reverse=True):
                        if a and esc(a) in e: return e.replace(esc(a),f'<span class="bn">{esc(a)}</span>',1)
                    return e
                def _tier(v):
                    r=v/mxv
                    return "t1" if r>=0.5 else ("t2" if r>=0.1 else "t3")
                chips="".join(f'<span class="kc {_tier(v)}{" rep" if k==0 else ""}" title="{esc(w)} · {_t("kw.months12")} {n(v)}"><span class="kw">{_hl(w)}</span><span class="kv">{short(v)}</span></span>' for k,(w,v) in enumerate(kws))
                top3=sum(v for _,v in kws[:3])
                lead=('<p class="kwh">'+_t("kw.lead", brand=kw(name), n=len(kws), sum=n(vol))
                      +(_t("kw.top3", pct=f"{top3/(vol or 1)*100:.0f}") if len(kws)>3 else '')
                      +((_t("kw.onPath", n=dict(x["walk"]["first"]).get(name,0))+(_t("kw.firstAt", step=_st((x["walk"].get("steps") or {}).get(name))) if dict(x["walk"]["first"]).get(name) else '')) if x.get("walk") and x["walk"].get("first") else '')
                      +'</p>')
                return (f'<details class="xbd">{head}<div class="kwl">{lead}<div class="kcs">{chips}</div></div></details>')
            bars=_bar(OWN,x["own_rate"],x["own_vol"],x.get("own_kws"),me=True)
            bars+="".join(_bar(c["brand"],c["rate"],c["vol"],c.get("kws"),co=c["brand"] in (x.get("co_top") or [])) for c in x["comp"])
            bars+=f'<p class="xs na">{_t("bars.hint")}</p>'
        if not x["comp"]: bars+=f'<p class="xs na">{_t("bars.noCompetitor")}</p>'
        walk=""
        if not x["walk"] and not str(x["name"]).startswith("없음"):
            # 6-b 는 주인 없음에만 경로를 부른다 — 안 부른 것과 못 잰 것을 구분해 적는다
            walk=f'<p class="xs na">{_t("walkAxis.notQueried")}</p>'
        if x["walk"]:
            w=x["walk"]; _u=(ju(x) in ("unclaimed","emerging"))
            _note="" if _u else f' <span class="na">{_t("walkAxis.reference")}</span>'
            walk=('<p>'+_t("walkAxis.body", term=kw(x["term"]), npaths=w.get("npaths",PL),
                           own=esc(OWN), ownN=w["own"], ownStep=_st(w.get("own_step")),
                           top=kw(w["top"]), topN=w["top_n"], topStep=_st(w.get("top_step")),
                           verdict=WNAME(w["axis"]))+_note+'</p>')
        flag=f'<p class="xs warn">⚠ {esc(x["flag"])}</p>' if x.get("flag") else ""
        deepnote=(f'<p class="xs">{_t("deep.isTarget", n=len(x["ceps"]))}</p>' if x.get("deep")
                  else f'<p class="xs na">{_t("deep.notTarget")}</p>')
        ev=x["evidence"]; top=x["comp"][0] if x["comp"] else None
        over=(f' <small class=na>{_t("state.over100")}</small>' if (x["own_rate"] or 0)>100 else "")
        rate=f'{x["own_rate"]}%{over}' if x["own_rate"] is not None else f'<span class="na" title="{_t("state.noData")}">-</span>'
        if top and top["rate"] is not None:
            tcell=((f'{"·".join(kw(z) for z in x["co_top"])} <small>'+_t("comp.tiedTag")+f' {top["rate"]}%</small>') if x.get("co_top") else f'{kw(top["brand"])}{wb(top["brand"])} <small>{top["rate"]}%</small>')
        elif x["walk"] and x["walk"]["top"]!="-":
            w0=x["walk"]; tcell=f'{kw(w0["top"])} <small class="na">'+_t("walkAxis.pathKw", n=w0["top_n"])+'</small>'
        else: tcell='<span class="na">-</span>' 
        rows.append(f'<tr class="xr{" top" if (x["walk"] and x["walk"]["axis"]=="우위") else ""}" data-c="{CID[x["term"]]}" data-vol="{x["vol12"]}" data-bsum="{_bden(x)}" data-own="{x["own_vol"]}" data-rate="{x["own_rate"] or 0}" data-ev="{ev["intent"]}" data-evp="{ev["path"]}" data-j="{-JR[ju(x)]}" data-x="x{k}" tabindex="0" aria-expanded="false"><td class="xc"><span class="car">▸</span></td><td>{kw(x["group"])}</td><td class="kw">{kw(x["term"])}{wc(x)}</td><td class="num">{catvol(x)}</td>{_bsum(x)}<td class="jcol"><span class="jd {CLS[ju(x)]}">{VNAME(ju(x))}</span></td>{_top12(x)}<td class="num evc sep">{_ev0(ev["intent"])}</td><td class="num evc">{_ev0(ev["path"])}</td>{_bcells(x)}</tr>'
                    f'<tr class="xd" id="x{k}" hidden><td></td><td colspan="{9+len(BCOLS)}"><div class="xg"><div><div class="xh">{bhead}</div>{bars}</div>'
                    f'<div class="xw"><p>{why(x)}</p>{walk}{flag}</div></div>{deepnote}</td></tr>')
    cnt=Counter(ju(x) for x in J)
    allc=[(x["term"],q) for x in DEEP for q in x["ceps"]]
    def _flat(q):   # 세 축 모두 비었나
        return (not q["own"]) and not any(dq(q,a).get("own") or dq(q,a).get("top_n") for a in ("intent","path"))
    gap=sorted([t for t in allc if _flat(t[1])],key=lambda t:-(t[1]["vol"] or 0))

    # ── S1
    tot=defaultdict(int); bcnt=Counter()
    for x in J:
        for q in x["comp"]: tot[q["brand"]]+=(q["vol"] or 0); bcnt[q["brand"]]+=1
    # 지정 브랜드는 상한보다 우선한다 — 사용자가 보려고 넣은 것이라 잘리면 안 된다
    wc=[x for x in WATCH if x in tot]
    ac=[x for x,_ in sorted(tot.items(),key=lambda t:-t[1]) if bcnt[x]>=2 and x not in wc]
    cols=[OWN]+wc+ac[:max(0,11-len(wc))]
    VOL={x["term"]:dict([(OWN,x["own_vol"])]+[(q["brand"],q["vol"]) for q in x["comp"]]) for x in J}
    meas={x["term"]:set([OWN]+(C_.get(x["term"],{}).get("comp") or [])+[q["brand"] for q in x["comp"]]+WATCH) for x in J}
    def ranks(d):
        vals=sorted([v for v in d.values() if v],reverse=True)
        return {b:1+sum(1 for w in vals if w>v) for b,v in d.items() if v}
    s1what=_t("s1.what")
    s1lead=_t("s1.lead")
    so=[f'<p class="s1lead">{s1lead} <span class="lg r1">{_t("rank.1")}</span> <span class="lg r2">{_t("rank.2")}</span></p><div class="scroll"><table class="mxt s1r" data-t="s1" data-page="10" data-sort="vol"><thead><tr><th></th><th class="jc" data-k="j">{_t("col.ownPosition")}</th><th class="catv" data-k="vol">{_t("col.volume")}</th>']
    so+=[('<th class="own sep" data-k="own">'+bn(b)+'</th>') if b==OWN else ('<th>'+bn(b)+wb(b)+'</th>') for b in cols]
    so.append(f'<th class="sep">{_t("col.offTable12")}</th></tr></thead><tbody>')
    for x in J:
        c=x["term"]; rk=ranks({b:v for b,v in VOL[c].items() if b in meas[c]})
        so.append(f'<tr data-vol="{x["vol12"]}" data-own="{x["own_vol"]}" data-j="{-JR[ju(x)]}"><th scope="row" class="rh">{kw(c)}</th><td class="jc"><span class="jd {CLS[ju(x)]}">{VNAME(ju(x))}</span></td><td class="num catv" title="{n(x["vol12"])}">{short(x["vol12"])}</td>')
        for b in cols:
            ow=" own sep" if b==OWN else ""
            if b not in meas[c]: so.append(f'<td class="num empty{ow}">·</td>'); continue
            v=VOL[c].get(b)
            if not v: so.append(f'<td class="num empty{ow}">-</td>'); continue
            r=rk.get(b); rc=" r1" if r==1 else (" r2" if r==2 else "")
            so.append(f'<td class="num{rc}{ow}" title="{_t("tip.volRank", vol=n(v), rank=r)}">{short(v)}</td>')
        ext=sorted([(r,b) for b,r in rk.items() if r<=2 and b not in cols])
        so.append('<td class="sep ext">'+(" ".join(f'<span class="lg r{r}">{kw(b)} {short(VOL[c][b])}</span>' for r,b in ext) or '<span class="na">-</span>')+'</td></tr>')
    so.append('</tbody></table></div><div class="pager" data-for="s1"></div>')
    S1=""
    SH={x["term"]:{bb:(v.get("share"),v.get("vol"),v.get("n_kw")) for bb,v in ((x.get("sos") or {}).get("brands") or {}).items()} for x in J}
    bv=['<div class="bview" hidden><div class="scroll"><table id="t-bv" class="mxt s1r bv"><thead><tr><th class="xc"></th><th>{_t("col.group")}</th><th>{_t("col.category")}</th>'
        f'<th class="num">{_t("col.catVolume")}</th><th>{_t("col.ownPosition")}</th><th class="sep">{_t("col.top12")}</th>']
    bv+=[('<th class="own sep">'+bn(b)+'</th>') if b==OWN else ('<th>'+bn(b)+wb(b)+'</th>') for b in cols]
    bv.append('</tr></thead><tbody>')
    for x in J:
        c=x["term"]; d=SH.get(c,{})
        rk=ranks({b:(d.get(b) or (0,))[0] for b in d if (d.get(b) or (0,))[0]})
        bv.append(f'<tr data-c="{CID[c]}"><td></td><td class="grp">{kw((C_.get(c) or {}).get("group",""))}</td><th scope="row" class="rh">{kw(c)}</th>'
                  f'<td class="num">{short(x["vol12"])}</td><td>{badge(x)}</td>')
        top2=sorted([(r,b) for b,r in rk.items() if r<=2 and b!=OWN])
        co=x.get("co_top") or []
        bv.append('<td class="sep t12">'+(" ".join(f'<span class="lg r{r}">{kw(b)} {d[b][0]}%</span>' for r,b in top2)+(f' <small class="na">{_t("comp.tiedTag")}</small>' if co else '') if top2 else f'<span class="na">{_t("state.noBrandKw")}</span>')+'</td>')
        for b in cols:
            ow=" own sep" if b==OWN else ""
            t=d.get(b)
            if not t or not t[0]:
                bv.append(f'<td class="num empty{ow}">-</td>'); continue
            r=rk.get(b); rc=" r1" if r==1 else (" r2" if r==2 else "")
            co=" co" if b in (x.get("co_top") or []) else ""
            bv.append(f'<td class="num{rc}{ow}{co}" title="{_t("tip.brandCell", brand=esc(b), share=t[0], vol=n(t[1]), n=t[2], rank=r)}">{t[0]}%</td>')
        bv.append('</tr>')
    bv.append('</tbody></table></div>'
              f'<p class="xs na">{_t("bv.note")}</p></div>')
    BV="".join(bv)
    MTOG=('<div class="modesw vtog" role="tablist" aria-label="{_t("aria.view")}">'
          f'<button type="button" class="chip-f on" data-m="v">{_t("tog.volume")}</button>'
          f'<button type="button" class="chip-f" data-m="s">{_t("tog.share")}</button>'
          f'<button type="button" class="chip-f ball" aria-pressed="false">{_t("tog.allBrands", n=len(BCOLS)-NTOP-1)}</button>'
          f'<span class="xs na">{_t("map.note")}</span></div>')
    # 번역 문자열을 JS 로 넘긴다 — json.dumps 로 따옴표·유니코드를 안전하게 싣는다
    MJS=f'<script>var ALLOFF={json.dumps(_t("tog.topBrandsOnly"))};</script>'+"""<script>(function(){var t=document.getElementById('t-map'),w=t.closest('.dash-card');
w.querySelectorAll('.vtog button[data-m]').forEach(function(b){b.addEventListener('click',function(){
w.querySelectorAll('.vtog button[data-m]').forEach(function(z){z.classList.toggle('on',z===b);});t.dataset.mode=b.dataset.m;});});
var ba=w.querySelector('.vtog .ball'),lab=ba.textContent;function setAll(on){var g=t.querySelector('th.gcomp');if(g)g.colSpan=on?+g.dataset.c2:+g.dataset.c1;t.classList.toggle('allb',on);ba.classList.toggle('on',on);ba.setAttribute('aria-pressed',on);ba.textContent=on?ALLOFF:lab;}
ba.addEventListener('click',function(){setAll(!t.classList.contains('allb'));});
t.querySelectorAll('.bmbtn').forEach(function(x){x.addEventListener('click',function(e){e.stopPropagation();setAll(true);});});})();</script>"""
    VTOG=(f'<div class="modesw vtog" role="tablist" aria-label="{_t("aria.view")}">'
          f'<button type="button" class="chip-f on" data-view="map">{_t("tog.mapView")}</button>'
          f'<button type="button" class="chip-f" data-view="bv">{_t("tog.brandView")}</button></div>')
    VJS="""<script>(function(){var sec=document.getElementById('t-map').closest('.dash-card');
var mw=document.getElementById('t-map').closest('.scroll'),pg=sec.querySelector('.pager[data-for="map"]'),bv=sec.querySelector('.bview');
sec.querySelectorAll('.vtog button').forEach(function(b){b.addEventListener('click',function(){
 sec.querySelectorAll('.vtog button').forEach(function(z){z.classList.toggle('on',z===b);});
 var on=b.dataset.view==='bv';
 if(on){var tb=document.getElementById('t-bv').tBodies[0];
  sec.querySelectorAll('.t-map tr.xr').forEach(function(r){var m=tb.querySelector('tr[data-c="'+r.dataset.c+'"]');if(m){tb.appendChild(m);m.hidden=r.hidden;}});}
 mw.hidden=on; if(pg) pg.style.display=on?'none':''; bv.hidden=!on;});});})();</script>"""
    # ── S2
    VARX=cfg.get("brand_var",{}); OWNV=cfg.get("own",[OWN])
    def al(b): return [a.lower() for a in (OWNV if b==OWN else VARX.get(b,[b]))]
    def mentions(c,b):
        ms=[x for x in SPL[c]["mods"] if x["mod"].split()[0].lower() in al(b)]
        return len(ms),(min(x["rank"] for x in ms) if ms else None)
    def brandshare(c):
        """연관어 앞말 중 브랜드(자사 + 라벨링된 경쟁사)가 차지하는 비율."""
        M=SPL[c]["mods"]
        if not M: return 0.0
        names=[OWN]+list(C_.get(c,{}).get("comp") or [])
        b=sum(1 for x in M if any(x["mod"].split()[0].lower() in al(nm) for nm in names))
        return b/len(M)*100
    selfhead=f'<th class="num">{_t("col.brandTotal")}</th>' if SELFV else ''
    so=[f'<div class="s2tabs" role="tablist" aria-label="{_t("aria.category")}">'+"".join(f'<button type="button" role="tab" class="chip-f s2t{" on" if i==0 else ""}" data-s2="{CID[x["term"]]}" aria-selected="{"true" if i==0 else "false"}">{kw(x["term"])}<small>{short(x["vol12"])}</small></button>' for i,x in enumerate(J))+'</div>',
       f'<div class="scroll"><table id="t-uni" class="uni">',
       f'<thead><tr><th>{_t("col.brand")}</th><th class="num">{_t("col.brandKw12")}</th><th class="num">{_t("col.share")}</th>{selfhead}<th class="num">{_t("col.brandRatio")}</th><th class="num" title="{_t("tip.kwCount")}">{_t("col.kwCount")}</th><th class="num">{_t("col.pathKw")}</th></tr></thead><tbody>']
    for x in J:
        c=x["term"]; cid=CID[c]
        brows=[(OWN,x["own_vol"],x["own_rate"])]+[(q["brand"],q["vol"],q["rate"]) for q in x["comp"]]
        brows+=[(b,None,None) for b in list(C_.get(c,{}).get("comp") or [])+WATCH if b not in [r[0] for r in brows]]
        sm=sum(v for _,v,_ in brows if v) or 1
        SLF=dict([(OWN,x.get("own_self"))]+[(q["brand"],q.get("self_vol")) for q in x["comp"]])
        fst=dict(WK[c]["first"]) if c in WK else None
        topk=x["ceps"][0]["kw"] if x["ceps"] else ""
        so.append(f'<tr class="catband" data-s2="{cid}"><td colspan="6">{kw(c)} {badge(x)}<span>{_t("band.facets", n=len(x["ceps"]))}{_t("band.topFacet", kw=kw(topk)) if topk else ""}</span><i>{_t("band.headKw", vol=n(x["vol12"]))}</i></td></tr>')
        for b,v,r in brows:
            _sb=((x.get("sos") or {}).get("brands") or {}).get(b) or {}
            m=_sb.get("n_kw",0)
            try: _il=json.load(open(R+f"data/cat/{c}_intent.json"))["data"]; rkx=(_il.index(_sb["rep_kw"])+1) if _sb.get("rep_kw") in _il else None
            except Exception: rkx=None
            fr="·" if fst is None else str(fst.get(b,0))
            me=' class="me"' if b==OWN else ""
            sv=SLF.get(b)
            selfcell=(f'<td class="num">{short(sv) if sv else "-"}</td>' if SELFV else "")
            rkp=(' <small>'+_t("unit.rankParen", rank=rkx)+'</small>') if rkx else ""
            so.append(f'<tr data-s2="{cid}"{me}><td class="kw">{kw(b)}{wb(b)}</td><td class="num">{n(v) if v else "-"}</td><td class="num">{str(r)+"%" if r is not None else "<span class=na>-</span>"}</td>{selfcell}<td class="num">{round((v or 0)/sm*100,1)}%</td><td class="num">{m}{rkp}</td><td class="num">{fr}</td></tr>')
    so.append("</tbody></table></div>")
    S2="".join(so)
    # ── 세부 수요 심층 · 심층 대상 카테고리에만
    so=[]
    for k,x in enumerate(DEEP):
        cols=x.get("cep_cols") or ([OWN]+list(C_.get(x["term"],{}).get("comp") or []))
        seen_=set()
        for q in x["ceps"]:
            for a in ("intent","path"):
                for b,v in (dq(q,a).get("brands") or {}).items():
                    if v: seen_.add(b)
        queried=[q for q in x["ceps"] if q.get("deep")]
        cc=[b for b in cols if b==OWN or b in seen_] if queried else []
        drop=[b for b in cols if b not in cc]
        hd="".join(('<th class="own sep">'+bn(b)+'</th>') if b==OWN else ('<th'+(' class="sep"' if i==0 else '')+'>'+bn(b)+'</th>') for i,b in enumerate(cc))
        cvt=sum(q["vol"] or 0 for q in x["ceps"]) or 1
        rw=""
        for q in sorted(x["ceps"],key=lambda t:-(t["vol"] or 0)):
            pp=dq(q,"path")                 # 세부 수요는 경로 축만으로 판정한다
            PB=(pp.get("brands") or {})
            sh=f'{q["vol"]/cvt*100:.0f}%' if q["vol"] else '<span class="na">-</span>'
            def rk(d):
                vs=sorted([v for v in d.values() if v],reverse=True)
                return {b:1+sum(1 for z in vs if z>v) for b,v in d.items() if v}
            rp=rk(PB)
            cells=""
            for b in cc:
                ow=" own sep" if b==OWN else ""
                pv=PB.get(b) or 0
                cp=" p-r1" if rp.get(b)==1 else (" p-r2" if rp.get(b)==2 else "")
                cells+=(f'<td class="num{cp}{ow}" title="{_t("tip.pathCell", n=pv, step=_st((pp.get("steps") or {}).get(b)))}">'
                        f'{pv or "<span class=na>-</span>"}</td>')
            jd=(cbadge(pp["axis"]) if q.get("deep") else '<span class="na">{_t("state.notQueried")}</span>')
            rw+=(f'<tr data-vol="{q["vol"] or 0}" data-own="{q["own"] or 0}">'
                 f'<th scope="row" class="rh">{kw(q["cep"])}</th>'
                 f'<td class="jc">{jd}</td>'
                 f'<td class="num catv" title="{n(q["vol"] or 0)}">{short(q["vol"])}</td>'
                 f'<td class="num">{sh}</td>'
                 f'{cells}</tr>')
        tid=f"dcep{k}"
        tog=(f'<div class="modesw"><button type="button" class="chip-f on" data-mode="p" data-for="{tid}">{_t("col.pathKw")}</button>'
             f'<button type="button" class="chip-f" data-mode="v" data-for="{tid}">{_t("col.comboVolume")}</button>'
             f'</div>')
        dn=""
        if not queried:
            so.append(f'<div class="dcep"><div class="shead2"><h3>{kw(x["term"])} {badge(x)}</h3>'
                      f'<span class="na">{_t("deep.headMeta", vol=n(x["vol12"]), n=len(x["ceps"]))}</span></div>'
                      f'<p class="hl">{cepsum(x)}</p>'
                      f'<p class="note">{_t("deep.notRun", term=kw(x["term"]), n=len(x["ceps"]))}</p>'
                      f'<div class="scroll"><table class="mxt s1r" data-t="dq{k}" data-sort="vol"><thead><tr>'
                      f'<th>{_t("col.facet")}</th><th class="catv" data-k="vol">{_t("col.volume")}</th><th class="num">{_t("col.shareCol")}</th>'
                      f'<th class="own sep" data-k="own">{_t("col.ownCombo", own=esc(OWN))}</th><th class="num">{_t("col.attachRate")}</th></tr></thead><tbody>'
                      +"".join(f'<tr data-vol="{q["vol"] or 0}" data-own="{q["own"] or 0}">'
                               f'<th scope="row" class="rh">{kw(q["cep"])}</th>'
                               f'<td class="num catv">{short(q["vol"])}</td>'
                               f'<td class="num">{(str(round((q["vol"] or 0)/(sum(z["vol"] or 0 for z in x["ceps"]) or 1)*100))+chr(37)) if q["vol"] else "-"}</td>'
                               f'<td class="num own sep">{short(q["own"]) if q["own"] else "<span class=na>-</span>"}</td>'
                               f'<td class="num">{pct(q["rate"])}</td></tr>'
                               for q in sorted(x["ceps"],key=lambda t:-(t["vol"] or 0)))
                      +'</tbody></table></div></div>')
            continue
        so.append(f'<div class="dcep"><div class="shead2"><h3>{kw(x["term"])} {badge(x)}</h3>'
                  f'<span class="na">{_t("deep.headMeta", vol=n(x["vol12"]), n=len(x["ceps"]))}</span></div>'
                  f'<p class="hl">{cepsum(x)}</p>'
                  f'<p class="xs na">{_t("deep.comboNote", own=esc(OWN), kw=kw(x["ceps"][0]["kw"]), when=_t("deep.comboNone") if not any(q.get("own") for q in x["ceps"]) else _t("deep.comboSome"), npaths=PL)}</p>'
                  f'<div class="scroll"><table id="{tid}" class="mxt s1r cepm" data-mode="p" data-t="{tid}" data-sort="vol"><thead><tr>'
                  f'<th>{_t("col.facet")}</th><th class="jc" title="{_t("col.verdictTip")}">{_t("col.verdict")}</th><th class="catv" data-k="vol">{_t("col.volume")}</th><th class="num">{_t("col.shareCol")}</th>'
                  f'{hd}</tr></thead><tbody>{rw}</tbody></table></div>{dn}</div>')
    # 세부 수요 심층에서 후보 모수 미달로 빠진 자리 — 「기회 없음」으로 읽히면 안 된다
    THIN=[x for x in J if x["evidence"].get("mods",99)<30 and not x.get("deep")]
    thinli=('<li>'+_t("limits.thin", n=len(THIN))
            +" · ".join(_t("limits.thinItem", term=kw(x["term"]), n=x["evidence"].get("mods",0)) for x in sorted(THIN,key=lambda r:-(r["vol12"] or 0))[:12])
            +(_t("limits.andMore", n=len(THIN)-12) if len(THIN)>12 else '')
            +_t("limits.thinTail")+'</li>') if (THIN and DEEP) else ''
    scopeli=('<li>'+_t("limits.scope", total=len(CAND), done=len(CAND)-len(SKIP))
             +" · ".join(f'{kw(k)}({short(CAND[k].get("vol") or 0)})' for k in SKIP[:20])
             +(_t("limits.andMore", n=len(SKIP)-20) if len(SKIP)>20 else '')+'</li>') if SKIP else ''
    SCEP=("".join(so)+f'<p class="xs">{_t("deep.rankLegend")} <span class="lg r1">{_t("rank.1")}</span> <span class="lg r2">{_t("rank.2")}</span>.</p>'
          ) if DEEP else f'<p class="note">{_t("deep.noneSelected")}</p>'

    # ── S4 · 행을 가로질러야만 나오는 것만 · 값이 없는 절은 내지 않는다
    def tbl(head,rows,cls=""):
        h="".join(f'<th{" class=num" if i else ""}>{c}</th>' for i,c in enumerate(head))
        b="".join("<tr>"+"".join(f'<td{" class=num" if i else ""}>{c}</td>' for i,c in enumerate(r))+"</tr>" for r in rows)
        return f'<div class="scroll"><table class="ins {cls}"><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'
    def block(t,body,lead=""):
        return f'<div class="insb"><h3>{t}</h3>'+(f'<p class="xs">{lead}</p>' if lead else "")+body+'</div>'
    so=[]
    # ① 지킬 곳 · 뺏을 곳 (항상) — 두 덩어리를 구분해서 낸다
    keep=[x for x in J if ju(x) in ("owned","emerging")]
    med=sorted(x["vol12"] for x in J)[len(J)//2]
    take=sorted([x for x in J if ju(x)=="trailing" and x["vol12"]>=med],key=lambda x:-x["vol12"])[:5]
    def _row(x,kind):
        t=x["comp"][0] if x["comp"] else None
        rival=(kw(t["brand"])+wb(t["brand"])+" "+pct(t["rate"])) if (t and t["rate"] is not None) else f'<span class="na">{_t("state.noBrandKw")}</span>'
        rate=pct(x["own_rate"]) if x["own_rate"] is not None else f'<span class="na" title="{_t("state.noData")}">-</span>'
        return (f'<span class="kind {kind}">{_t("s4.keep") if kind=="k" else _t("s4.take")}</span> <b>{kw(x["term"])}</b> {badge(x)}',
                n(x["vol12"]),rate,rival)
    r1=[_row(x,"k") for x in keep]+[_row(x,"t") for x in take]
    lead=(_t("s4.keepTakeLead", keep=len(keep), own=esc(OWN), take=len(take), med=n(med)) if take
          else _t("s4.keepTakeLeadNone", keep=len(keep), med=n(med)))
    so.append(block(_t("s4.keepTakeTitle"),
        tbl([_t("col.category"),_t("col.catVolume"),_t("col.ownShare", own=esc(OWN)),_t("col.rival1")],r1) if r1 else f'<p class="na">{_t("state.none")}</p>',
        lead))
    # ② 카테고리와 세부 수요가 엇갈리는 곳 (항상 · 값 없으면 문장)
    WMx={"우위":"owned","경합":"contested","열세":"trailing"}
    dis=[]
    for x in DEEP:
        ax=Counter(WMx[(q.get("deep") or {}).get("path",{}).get("axis")] for q in x["ceps"]
                   if (q.get("deep") or {}).get("path",{}).get("axis") in WMx)
        if not ax: continue
        if len(ax)>1 or list(ax)[0]!=ju(x):
            dis.append((f'<b>{kw(x["term"])}</b> {badge(x)}'," · ".join(f"{k} {v}" for k,v in ax.most_common()),
                        " · ".join(kw(q["cep"]) for q in x["ceps"] if q.get("deep"))))
    so.append(block(_t("s4.mismatchTitle"),
        tbl([_t("col.category"),_t("col.facetMix"),_t("col.facetStudied")],dis) if dis
        else f'<p class="na">{_t("s4.mismatchNone")}</p>',
        _t("s4.mismatchLead")))
    # ③ 이 회차는 무엇으로 판정했나 (항상)
    byname=sum(1 for x in J if hr(x)); bywalk=sum(1 for x in J if not hr(x) and x["walk"] and x["walk"]["axis"] in WMx)
    none_=len(J)-byname-bywalk
    cepq=sum(1 for x in DEEP for q in x["ceps"] if q.get("deep"))
    so.append(block(_t("s4.axisTitle"),
        tbl([_t("col.axis"),_t("col.catCount")],[(_t("axis.naming"),byname),(_t("axis.journeyOnly"),bywalk),(_t("axis.neither"),none_),
                              (_t("axis.facetDeep"),_t("s4.facetCount", n=cepq, cats=len(DEEP)))]),
        _t("s4.axisLead")))
    # ④ 반복 상대 (조건부)
    t1=Counter(); ap=Counter(); dv=Counter()
    for x in J:
        if x["comp"] and x["comp"][0]["vol"]: t1[x["comp"][0]["brand"]]+=1
        for q in x["comp"]: ap[q["brand"]]+=1; dv[q["brand"]]+=x["vol12"]
    rep_=[(kw(b)+wb(b),_t("unit.places", n=k),_t("unit.places", n=ap[b]),n(dv[b])) for b,k in t1.most_common(6) if k>=2]
    if rep_: so.append(block(_t("s4.rivalsTitle"),
        tbl([_t("col.brand"),_t("col.rival1"),_t("col.asRival"),_t("col.demandSum")],rep_),
        _t("s4.rivalsLead")))
    # ⑤ 묶음별 그림 (조건부)
    g=defaultdict(Counter); gv=defaultdict(int)
    for x in J: g[x["group"]][ju(x)]+=1; gv[x["group"]]+=x["vol12"]
    big=[k for k in g if sum(g[k].values())>=3]
    if len(big)>=2:
        so.append(block(_t("s4.groupTitle"),
            tbl([_t("col.group"),_t("col.verdictMix"),_t("col.demandSum")],
                [(kw(k)," · ".join(f"{VNAME(a)} {b}" for a,b in g[k].most_common()),n(gv[k])) for k in sorted(g,key=lambda z:-gv[z])]),
            _t("s4.groupLead")))
    # ⑥ 이름과 여정이 엇갈리는 곳 (조건부)
    cross=[(f'<b>{kw(x["term"])}</b>',VNAME(ju(x)),VNAME(WMx[x["walk"]["axis"]]),n(x["vol12"]))
           for x in J if ju(x) in WMx.values() and x["walk"] and x["walk"]["axis"] in WMx and WMx[x["walk"]["axis"]]!=ju(x)]
    if cross: so.append(block(_t("s4.crossTitle"),
        tbl([_t("col.category"),_t("axis.namingShort"),_t("axis.journeyShort"),_t("col.catVolume")],sorted(cross,key=lambda r:-int(r[3].replace(",","")))[:8]),
        _t("s4.crossLead")))
    # ⑦ 지정 브랜드 (조건부)
    if WATCH:
        wr=[]
        for b in WATCH:
            hits=sorted([(x["term"],q) for x in J for q in x["comp"] if q["brand"]==b and q["vol"]],key=lambda t:-t[1]["vol"])
            if hits: wr.append((kw(b),_t("unit.outOfPlaces", n=len(hits), total=len(J)),kw(hits[0][0]),n(hits[0][1]["vol"])+f' <small>({hits[0][1]["rate"]}%)</small>'))
        if wr: so.append(block(_t("s4.watchTitle"),
            tbl([_t("col.brand"),_t("col.spanCats"),_t("col.biggestSpot"),_t("col.comboVolume")],wr),
            _t("s4.watchLead")))
    # ⑧ 못 잰 것 (항상)
    miss=[x["term"] for x in J if x["own_rate"] is None]
    nocep=[x["term"] for x in DEEP if not any(q.get("deep") for q in x["ceps"])]
    li=[]
    if miss: li.append(_t("s4.missOwn", own=esc(OWN), n=len(miss))+" · ".join(kw(t) for t in miss[:8]))
    if nocep: li.append(_t("s4.missFacet", n=len(nocep))+" · ".join(kw(t) for t in nocep))
    li.append(_t("method.alias"))
    li.append(_t("method.namingAxis"))
    li.append(_t("method.journeyAxis", npaths=PL))
    li.append(_t("method.facetAxis", npaths=PL))
    so.append(block(_t("s4.unmeasuredTitle"),'<ul class="open">'+"".join(f'<li>{z}</li>' for z in li)+'</ul>',
        _t("s4.unmeasuredLead")))
    S4="".join(so)

    # ── 버블맵
    JC={"owned":"var(--j-own)","emerging":"var(--j-own)","contested":"var(--j-cmp)","trailing":"var(--j-low)","unclaimed":"var(--j-emp)",
        "named":"var(--m-name)","walked":"var(--m-path)","absent":"var(--m-none)"}
    W,H=980,520; L,Rr,T,B=64,150,40,56
    vmin=max(min(x["vol12"] for x in J)/2,100); vmax=max(x["vol12"] for x in J)*1.6
    def lx(v): return L+(math.log10(max(v,vmin))-math.log10(vmin))/(math.log10(vmax)-math.log10(vmin))*(W-L-Rr)
    def ly(r):
        r=min(max(r,0.15),8.0); return T+(1-(math.log(r,2)+3)/6)*(H-T-B)
    pts=[]
    for x in J:
        if not hr(x):                      # 부착률을 못 잰 곳은 경로 비율로 놓는다
            w=x["walk"]; ratio=((w["own"]+1)/(w["top_n"]+1)) if w else 1.0
        else:
            t=(x["comp"][0]["rate"] or 0) if x["comp"] else 0
            ratio=((x["own_rate"] or 0)/t) if t else 8.0
        pts.append((x,ratio,ju(x)))
    RATED=RATED0
    szf=(lambda x:(x["own_vol"] or 0)) if RATED else (lambda x:(x["walk"]["own"] if x["walk"] else 0))
    mxo=max(szf(x) for x in J) or 1
    def rad(v): return 5+math.sqrt(max(v,0)/mxo)*26
    sv=[f'<svg viewBox="0 0 {W} {H}" class="bub" role="img" aria-label="{_t("aria.bubble")}">',
        f'<rect x="{L}" y="{T}" width="{W-L-Rr}" height="{H-T-B}" fill="var(--soft)" opacity=".5"/>']
    xm=lx(math.sqrt(vmin*vmax))
    sv.append(f'<line x1="{xm}" y1="{T}" x2="{xm}" y2="{H-B}" stroke="var(--line)" stroke-dasharray="4 4"/>')
    sv.append(f'<line x1="{L}" y1="{ly(1)}" x2="{W-Rr}" y2="{ly(1)}" stroke="var(--line)"/>')
    for r,lab in [(2,_t("bubble.ahead2x")),(0.5,_t("bubble.behind2x"))]:
        sv.append(f'<line x1="{L}" y1="{ly(r)}" x2="{W-Rr}" y2="{ly(r)}" stroke="var(--line)" stroke-dasharray="2 5"/><text x="{W-Rr+6}" y="{ly(r)+4}" class="bax">{lab}</text>')
    sv.append(f'<text x="{W-Rr+6}" y="{ly(1)+4}" class="bax">{_t("bubble.tied")}</text>')
    ticks=[t for t in [1000,5000,10000,50000,100000,500000,1000000,2000000] if vmin<=t<=vmax]
    for v in ticks:
        sv.append(f'<text x="{lx(v)}" y="{H-B+18}" class="bax" text-anchor="middle">{short(v)}</text>')
    sv.append(f'<text x="{L}" y="{H-B+38}" class="bax">{_t("bubble.xAxis")}</text>')
    yl=_t("bubble.yShare", own=esc(OWN)) if RATED else _t("bubble.yPath")
    sv.append(f'<text transform="translate(16,{T+(H-T-B)/2}) rotate(-90)" class="bax" text-anchor="middle">{yl}</text>')
    for q,(qx,qy,ta) in {_t("bubble.qDefendBig"):(W-Rr-8,T+18,"end"),_t("bubble.qTakeBig"):(W-Rr-8,H-B-10,"end"),_t("bubble.qOwnSmall"):(L+8,T+18,"start"),_t("bubble.qNeglected"):(L+8,H-B-10,"start")}.items():
        sv.append(f'<text x="{qx}" y="{qy}" class="bq" text-anchor="{ta}">{q}</text>')
    rects=[]; lbl=[]
    def free(x0,y0,x1,y1):
        if x0<L+2 or x1>W-Rr-2 or y0<T+2 or y1>H-B-2: return False
        return not any(not(x1<r[0] or x0>r[2] or y1<r[3] or y0>r[1]) for r in rects)
    for x,ratio,jj in sorted(pts,key=lambda t:-szf(t[0])):
        cx,cy,r=lx(x["vol12"]),ly(ratio),rad(szf(x))
        dash=' stroke-dasharray="3 3"' if jj=="unclaimed" else ''
        sv.append(f'<circle class="bcz" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{JC[jj]}" fill-opacity=".22" stroke="{JC[jj]}"{dash} '
                  f'data-n="{esc(x["term"])}" data-j="{jj}" data-jc="{CLS[jj]}" data-vol="{n(x["vol12"])}" data-own="{n(x["own_vol"] or 0)}" data-rate="{x["own_rate"] or 0}" '
                  f'data-top="{esc(x["comp"][0]["brand"]) if x["comp"] else "-"}" data-toprate="{(x["comp"][0]["rate"] or 0) if x["comp"] else 0}" data-ratio="{ratio:.1f}" data-cepn="{len(x["ceps"])}"></circle>')
        nm=x["term"]; wd=len(nm)*11.2+4; ht=13
        for dx,dy,anc in [(0,-r-6,"middle"),(0,r+13,"middle"),(r+6,4,"start"),(-r-6,4,"end"),(0,-r-19,"middle"),(0,r+26,"middle"),(r+6,-10,"start"),(-r-6,-10,"end")]:
            tx,ty=cx+dx,cy+dy
            x0=tx-(wd/2 if anc=="middle" else (0 if anc=="start" else wd)); y0=ty-ht+3
            if free(x0,y0,x0+wd,y0+ht):
                rects.append((x0,y0+ht,x0+wd,y0)); lbl.append((tx,ty,anc,nm)); break
        else:
            tx,ty=cx,cy-r-6; rects.append((tx-wd/2,ty+3,tx+wd/2,ty-10)); lbl.append((tx,ty,"middle",nm))
    for tx,ty,anc,nm in lbl:
        sv.append(f'<text x="{tx:.1f}" y="{ty:.1f}" class="blb" text-anchor="{anc}">{esc(nm)}</text>')
    sv.append("</svg>")
    lg=" ".join(f'<span class="blg"><i style="background:{JC[k]}"></i>{VNAME(k)}</span>' for k in ["owned","contested","trailing","unclaimed"])
    ax=(_t("bubble.axisShare", own=esc(OWN)) if RATED else _t("bubble.axisPath"))
    BUB=f'<div class="bwrap" data-brand="{esc(OWN)}">'+"".join(sv)+'<div class="btip" hidden></div></div>'+f'<p class="xs">{_t("bubble.note", axis=ax)} {lg}</p>'
    # 사분면은 세로축(1위 대비 위치)에 분포가 있을 때만 그린다 — 전부 바닥이면 다른 차트와 같은 정보뿐이다
    def _ratio(x):
        o=x["own_rate"] or 0; t=x["comp"][0]["rate"] if x["comp"] else 0
        return (o/t) if t else (9.9 if o else 0)
    _rs=[_ratio(x) for x in J]; _mx=max(_rs) if _rs else 0
    if _mx<0.5:
        BUB=f'<p class="xs na">{_t("bubble.skipped", own=esc(OWN), pct=f"{_mx*100:.0f}")}</p>'
    cat=Counter()
    for x in J: cat[ju(x)]+=x["vol12"]
    def barline(d,title,note,lm=None):
        tt=sum(d.values()) or 1; ks=lm or list(VERDICTS)
        seg="".join(f'<span style="width:{d[k]/tt*100:.2f}%;background:{JC.get(k,"var(--line)")}" title="{BN(k)} {d[k]/tt*100:.0f}%"></span>' for k in ks if d.get(k))
        lab=" · ".join(f'<b>{BN(k)}</b> {d[k]/tt*100:.0f}%' for k in ks if d.get(k))
        return f'<div class="dbar"><div class="dbt">{title} <small class="na">{note} · {_t("bar.total", vol=short(tt))}</small></div><div class="dbr">{seg}</div><div class="dbl">{lab}</div></div>'
    # 한 장 요약의 세부 수요 막대 — S3 절은 없앴지만 구성은 요약에 남긴다
    def cbucket(q):
        if q["own"]: return "named"
        d=q.get("deep") or {}
        p=d.get("path") or {}        # 세부 수요는 경로 축만으로 판정한다
        return "walked" if (p.get("own") or p.get("top_n")) else "absent"
    agg=Counter()
    for x in DEEP:
        for q in x["ceps"]: agg[cbucket(q)]+=q["vol"] or 0
    # ── 한 장 요약 차트: ① 판정별 카테고리 수요(막대) ② 자사 검색량의 카테고리 구성(파이)
    def _bar_svg():
        ks=["owned","contested","trailing","unclaimed"]; vs=[cat.get(k,0) for k in ks]
        mxv=max(vs) or 1; step=10**max(0,len(str(int(mxv)))-1)
        top=((int(mxv)//step)+1)*step
        W,H,L_,B_,T_=440,260,64,34,14; pw=W-L_-12; ph=H-B_-T_; bw=pw/len(ks)*0.56
        o=[f'<svg viewBox="0 0 {W} {H}" class="sch" role="img" aria-label="{_t("chart.demandByVerdict")}">']
        for g in range(0,5):
            v=top*g/4; y=T_+ph-ph*g/4
            o.append(f'<line x1="{L_}" x2="{W-12}" y1="{y:.1f}" y2="{y:.1f}" class="sg"/><text x="{L_-6}" y="{y+4:.1f}" class="sy" text-anchor="end">{short(v) if v else 0}</text>')
        for i,(k,v) in enumerate(zip(ks,vs)):
            cx=L_+pw/len(ks)*(i+.5); h=ph*v/top; y=T_+ph-h
            xs_=sorted([x for x in J if ju(x)==k],key=lambda x:-x["vol12"]); tt_=sum(cat.values()) or 1
            tip_=(f'<b>{VNAME(k)}</b> <span class="jd {CLS.get(k,"")}">{_t("unit.catCount", n=len(xs_))}</span><table>'
                  f'<tr><th>{_t("tip.catVolumeSum")}</th><td>{n(v)}</td></tr><tr><th>{_t("tip.ofTotal")}</th><td>{v/tt_*100:.0f}%</td></tr></table>'
                  +('<table class="tl">'+"".join(f'<tr><th>{kw(x["term"])}</th><td>{n(x["vol12"])}</td></tr>' for x in xs_)+'</table>' if xs_ else ""))
            if v: o.append(f'<rect class="ctz" data-tip="{html.escape(tip_,quote=True)}" x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" rx="3" fill="{JC.get(k,"var(--accent)")}"></rect>'
                       f'<text x="{cx:.1f}" y="{y-6:.1f}" class="sv" text-anchor="middle">{short(v)}</text>')
            o.append(f'<text x="{cx:.1f}" y="{H-B_+18}" class="sx" text-anchor="middle">{VNAME(k)} <tspan class="sc">{_t("unit.countCats", n=sum(1 for x in J if ju(x)==k))}</tspan></text>')
        o.append(f'<line x1="{L_}" x2="{W-12}" y1="{T_+ph}" y2="{T_+ph}" class="sa"/></svg>')
        return "".join(o)
    JX={x["term"]:x for x in J}
    def _ptip(t,v,tt):
        x=JX[t]; c0=x["comp"][0] if x["comp"] else None
        return (f'<b>{kw(t)}</b> <span class="jd {CLS[ju(x)]}">{VNAME(ju(x))}</span><table>'
                f'<tr><th>{_t("tip.ownVolume", own=esc(OWN))}</th><td>{n(v)}</td></tr>'
                f'<tr><th>{_t("tip.ownVolumeShare", own=esc(OWN))}</th><td>{v/tt*100:.1f}%</td></tr>'
                f'<tr><th>{_t("col.catVolume")}</th><td>{n(x["vol12"])}</td></tr>'
                f'<tr><th>{_t("col.ownShare", own=esc(OWN))}</th><td>{x["own_rate"] if x["own_rate"] is not None else "-"}%</td></tr>'
                +(f'<tr><th>{_t("col.rival1")}</th><td>{kw(c0["brand"])} <small>({c0["rate"]}%)</small></td></tr>' if c0 else '')
                +'</table>')
    def _pie_svg():
        it=sorted([(x["own_vol"] or 0,x["term"]) for x in J if x["own_vol"]],reverse=True)
        tt=sum(v for v,_ in it) or 1
        # LM 브랜드 램프 4색 × (main → darker) · 은퇴한 판정색(#F96E6E·#EBAA03·#35CA00)이
        # 파이에 남아 있으면 읽는 사람이 판정 배지와 섞어 본다. 색조를 번갈아 두어 인접 조각을 가른다.
        PAL=["#7F18FF","#CD3197","#AA18CC","#FF247A","#5A10B8","#821E60","#7A1194","#A81650"]
        cx,cy,r=130,130,112; a0=-math.pi/2; o=[f'<svg viewBox="0 0 260 260" class="sch pie" role="img" aria-label="{_t("aria.pie", own=esc(OWN))}">']
        if len(it)==1: o.append(f'<circle class="ctz" data-tip="{html.escape(_ptip(it[0][1],it[0][0],tt),quote=True)}" cx="{cx}" cy="{cy}" r="{r}" fill="{PAL[0]}"/>')
        for i,(v,t) in enumerate(it if len(it)>1 else []):
            a1=a0+2*math.pi*v/tt; lg=1 if a1-a0>math.pi else 0
            x0,y0=cx+r*math.cos(a0),cy+r*math.sin(a0); x1,y1=cx+r*math.cos(a1),cy+r*math.sin(a1)
            o.append(f'<path class="ctz" data-tip="{html.escape(_ptip(t,v,tt),quote=True)}" d="M{cx},{cy} L{x0:.2f},{y0:.2f} A{r},{r} 0 {lg} 1 {x1:.2f},{y1:.2f} Z" fill="{PAL[i%len(PAL)]}" stroke="var(--bg,#fff)" stroke-width="1.5"></path>')
            a0=a1
        o.append("</svg>")
        lg_="".join(f'<li class="ctz" data-tip="{html.escape(_ptip(t,v,tt),quote=True)}"><i style="background:{PAL[i%len(PAL)]}"></i><span class="pn">{kw(t)}</span><span class="pv">{n(v)}</span><span class="pp">{v/tt*100:.1f}%</span></li>' for i,(v,t) in enumerate(it))
        none=[x["term"] for x in J if not x["own_vol"]]
        nn=(f'<p class="xs na">'+_t("chart.noKwCats", own=esc(OWN))+" · ".join(kw(z) for z in none)+'</p>') if none else ""
        return "".join(o),f'<ul class="plg">{lg_}</ul>{nn}',tt
    _pv,_pl,_pt=_pie_svg()
    CJS="""<script>(function(){(document.querySelector('.view-dash')||document).querySelectorAll('.cwrap').forEach(function(w){var tip=w.querySelector('.btip');
function show(el,ev){tip.innerHTML=el.dataset.tip;tip.hidden=false;var r=el.getBoundingClientRect(),W=window.innerWidth,H=window.innerHeight,tw=tip.offsetWidth,th=tip.offsetHeight;
var cx=ev&&ev.clientX?ev.clientX:r.right,cy=ev&&ev.clientY?ev.clientY:r.top+r.height/2,L,T;
if(cx+18+tw<=W-8){L=cx+18;T=Math.min(Math.max(8,cy-th/2),H-th-8);}            /* 커서 오른쪽 */
else{L=Math.min(Math.max(8,cx-tw/2),W-tw-8);T=r.top-th-10;                    /* 대상 위쪽 */
 if(T<8){L=Math.max(8,cx-18-tw);T=Math.min(Math.max(8,cy-th/2),H-th-8);}}    /* 위도 막히면 커서 왼쪽 */
tip.style.left=L+'px';tip.style.top=T+'px';}
w.querySelectorAll('.ctz').forEach(function(el){el.addEventListener('mousemove',function(e){show(el,e);el.classList.add('hv');});
el.addEventListener('mouseleave',function(){tip.hidden=true;el.classList.remove('hv');});el.addEventListener('click',function(e){show(el,e);});});});})();</script>"""
    SUM=('<div class="sch2">'
         f'<div class="schc cwrap"><div class="btip" hidden></div><div class="dbt">{_t("chart.demandByVerdict")} <small class="na">{_t("chart.demandByVerdictNote", total=short(sum(cat.values())))}</small></div>{_bar_svg()}</div>'
         f'<div class="schc cwrap"><div class="btip" hidden></div><div class="dbt">{_t("chart.ownByCategory", own=esc(OWN))} <small class="na">{_t("chart.ownByCategoryNote", own=esc(OWN), total=n(_pt))}</small></div>'
         f'<div class="pwrap">{_pv}<div>{_pl}</div></div></div>'
         '</div>'+CJS)
    # ── 한 줄 요약
    _tc=sum(cat.values()) or 1; _cc=sum(agg.values()) or 1
    _win=[x for x in J if ju(x) in ("owned","emerging")]
    _med=sorted(x["vol12"] for x in J)[len(J)//2]
    _take=sorted([x for x in J if ju(x)=="trailing" and x["vol12"]>=_med],key=lambda x:-x["vol12"])[:3]
    _open=gap[:3]
    p1=((_t("summary.leadSome", n=len(J), own=esc(OWN), items=", ".join(kw(x["term"]) for x in _win), k=len(_win))) if _win else _t("summary.leadNone", n=len(J), own=esc(OWN))
        +(_t("summary.behindShare", pct=f'{cat["trailing"]/_tc*100:.0f}') if cat.get("trailing") else _t("summary.noneBehind")))
    p2=(_t("summary.absentShare", pct=f'{agg["absent"]/_cc*100:.0f}', vol=short(agg["absent"]), own=esc(OWN)) if agg.get("absent") else '')
    def _tk(x):
        if x["comp"]: return f'{kw(x["term"])}({kw(x["comp"][0]["brand"])} {x["comp"][0]["rate"]}% vs {x["own_rate"]}%)'
        w=x["walk"]; return _t("summary.takeWalkItem", term=kw(x["term"]), top=kw(w["top"]), topN=w["top_n"], own=w["own"]) if w else kw(x["term"])
    p3=(_t("summary.takeFrom", items=" · ".join(_tk(x) for x in _take)) if _take else '')
    p4=(_t("summary.claimFirst", items=" · ".join(f'{kw(q["kw"])}({short(q["vol"])})' for t,q in _open)) if _open else '')
    HL=f'<p class="hl"><b>{_t("summary.oneLine")}</b> — {p1}{p2}{p3}{p4}</p>'
    SUM=HL+SUM
    # ── 조립
    _vk4=["owned","contested","trailing","unclaimed"]
    kpi=(f'<div class="kpis"><div class="kpi"><b>{len(J)}</b><span>{_t("kpi.categories")}</span></div>'
         f'<div class="kpi"><b>{len(allc)}</b><span>{_t("kpi.facets")}</span></div>'
         f'<div class="kpi"><b>'+" · ".join(str(cnt[k]) for k in _vk4)
         +f'</b><span>{" · ".join(VNAME(k) for k in _vk4)}</span></div>'
         f'<div class="kpi"><b>{len(DEEP)}</b><span>{_t("kpi.deepCategories")}</span></div></div>')
    # 카테고리를 무엇으로 찾았는지가 0·0 이면 그 사실만 적는다 — 회차 고유 서술을 박지 않는다
    _noev=sum(1 for x in J if not (x["evidence"]["intent"] or x["evidence"]["path"]))
    cato=(" "+_t("limits.noEvidence", n=_noev) if _noev else "")

    def _bhead():
        o=[]
        for i_,b in enumerate(BCOLS):
            if b==OWN: continue
            if i_==NTOP+1:
                o.append('<th class="bmore"><button type="button" class="bmbtn" title="'+_t("tip.expandBrands")+'">+'+str(len(BCOLS)-NTOP-1)+'</button></th>')
            cls="num bc"+(" sep" if i_==1 else "")+(" bx" if i_>NTOP else "")
            o.append('<th class="'+cls+'">'+bn(b,_t("tip.inNCategories", n=_bc[b]))+wb(b)+'</th>')
        return "".join(o)
    BHEAD=_bhead()
    # ── 참전 여부로 다시 본 판정 (자사 공식몰 조사)
    def _pg(f): return [x for x in J if x.get("presence") and f(x)]
    _lab=lambda x:x["presence"]["label"]
    _rows=[(_t("priority.realWeak"),_pg(lambda x:_lab(x)=="참전" and ju(x)=="trailing")),
           (_t("priority.fightingNow"),_pg(lambda x:_lab(x)=="참전" and ju(x)=="contested")),
           (_t("priority.defend"),_pg(lambda x:_lab(x)=="참전" and ju(x) in("owned","emerging"))),
           (_t("priority.claim"),_pg(lambda x:_lab(x)=="참전" and ju(x)=="unclaimed")),
           (_t("priority.adjacentForm"),_pg(lambda x:_lab(x)=="부분 참전")),
           (_t("priority.noProduct"),_pg(lambda x:_lab(x) in("미판매","미확인")))]
    _li=[]
    for t,xs in _rows:
        if not xs: continue
        it=" · ".join(f'{kw(x["term"])}' for x in sorted(xs,key=lambda r:-(r["vol12"] or 0)))
        _li.append(f'<tr><th style="text-align:left;white-space:nowrap">{t}</th><td style="white-space:normal">{it}</td></tr>')
    PRES=(f'<p class="sub">{_t("priority.lead", own=esc(OWN))}</p>'
          f'<div class="scroll"><table>{"".join(_li)}</table></div>') if _li else ""
    # ── 지도 표 · 대시 뷰용(컨트롤 포함)과 A4 사본(정적)을 따로 만든다
    MAPT=(f'<div class="scroll"><table id="t-map" class="t-map" data-mode="v" data-t="map" data-page="10" data-sort="vol">\n'
      f'<thead><tr class="g1"><th class="xc" rowspan="2" aria-label="{_t("col.expand")}"></th><th rowspan="2">{_t("col.group")}</th><th class="cat" rowspan="2">{_t("col.category")}</th><th class="num" rowspan="2" data-k="vol" title="{_t("tip.catVolume")}">{_t("col.catVolume")}</th><th class="num" rowspan="2" data-k="bsum" title="{_t("tip.brandVolume")}">{_t("col.brandVolume")}</th><th class="jcol" rowspan="2" data-k="j" title="{_t("tip.ownPosition")}">{_t("col.ownPosition")}</th><th class="sep" rowspan="2" title="{_t("tip.top12")}">{_t("col.top12")}</th><th class="gh own sep" colspan="3">{_t("col.ownGroup", own=esc(OWN))}</th><th class="gh gcomp sep" colspan="{NTOP+1}" data-c1="{NTOP+1}" data-c2="{len(BCOLS)-1}">{_t("col.rivalGroup")} (<span class="mv">{_t("col.brandVolume")}</span><span class="ms">{_t("col.share")}</span>)</th></tr>'
      f'<tr class="g2"><th class="num sep" data-k="ev" title="{_t("tip.evIntent", own=esc(OWN), n=BIN)}">{_t("col.evIntent")}</th><th class="num" data-k="evp" title="{_t("tip.evPath", own=esc(OWN), n=BPN)}">{_t("col.evPath")}</th><th class="num own" data-k="own" title="{_t("tip.ownCell", own=esc(OWN))}"><span class="mv">{_t("col.brandVolume")}</span><span class="ms">{_t("col.share")}</span></th>{BHEAD}</tr></thead>'
      f'<tbody>{"".join(rows)}</tbody></table></div>')

    def _static(h):
        # A4 사본 — 상호작용 장치를 뗀다. id 를 남기면 중복돼 JS 가 첫 벌만 잡고,
        # 정렬·페이지·펼침 버튼은 인쇄물에서 누를 수가 없다. 표 스타일은 class 로 받는다.
        h=re.sub(r'<tr class="xd"[^>]*>.*?</tr>','',h,flags=re.S)
        h=re.sub(r'<t[dh] class="xc"[^>]*>.*?</t[dh]>','',h,flags=re.S)
        h=re.sub(r'<script.*?</script>','',h,flags=re.S)
        h=re.sub(r'<button\b.*?</button>','',h,flags=re.S)   # 종이에서는 누를 수 없다
        h=re.sub(r'<div class="pager"[^>]*></div>','',h)
        h=re.sub(r'\sid="[^"]*"','',h)
        h=re.sub(r'\sdata-(?:page|sort|x|for|more|mid)="[^"]*"','',h)
        h=re.sub(r'\stabindex="[^"]*"|\saria-expanded="[^"]*"','',h)
        return h

    def _a4matrix():
        """A4 「경쟁 매트릭스」 — 화면 지도의 경쟁사 열 블록(열 20개+)은 쪽 폭(714px)에 들어가지
           않아 접힌다. 그 대신 **행·열을 뒤집어**(행 = 브랜드 · 열 = 카테고리) 같은 숫자를 다 싣는다.
           카테고리가 많으면 8개씩 끊어 표를 여러 장 낸다 — 한 칸이 「1.2만 · 12.3%」를 넘지 않게."""
        CH=8; out=[]
        cats=[x["term"] for x in J]
        rk={}
        for c in cats:
            d=_SH.get(c,{}); vs=sorted([v.get("vol") or 0 for v in d.values() if v.get("vol")],reverse=True)
            rk[c]={b:1+sum(1 for w in vs if w>(v.get("vol") or 0)) for b,v in d.items() if v.get("vol")}
        for i in range(0,len(cats),CH):
            cs=cats[i:i+CH]
            head="".join(f'<th class="num a4m-c">{kw(c)}</th>' for c in cs)
            body=[]
            for b in BCOLS:
                if not any((_SH.get(c,{}).get(b) or {}).get("vol") for c in cs): continue
                tds=[]
                for c in cs:
                    t=_SH.get(c,{}).get(b) or {}
                    if not t.get("vol"): tds.append('<td class="num empty">-</td>'); continue
                    r=rk[c].get(b,99); rc=" r1" if r==1 else (" r2" if r==2 else "")
                    sh=(str(t["share"])+"%") if t["share"]>=0.1 else "&lt;0.1%"
                    tds.append(f'<td class="num{rc}"><span class="a4m-v">{short(t["vol"])}</span><span class="a4m-s">{sh}</span></td>')
                body.append(f'<tr class="{"own" if b==OWN else ""}"><th class="a4m-b">{bn(b)}</th>{"".join(tds)}</tr>')
            tag=f' ({i//CH+1}/{(len(cats)+CH-1)//CH})' if len(cats)>CH else ""
            out.append(f'<div class="a4m"><table class="a4m-t"><thead><tr><th class="a4m-b">{_t("col.brand")}{tag}</th>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>')
        return (f'<h3 class="a4m-h">{_t("a4.matrixTitle")}</h3>'
                f'<p class="sub">{_t("a4.matrixNote")}</p>'+"".join(out))

    def _evidence(h):
        # A4 쪽 「카테고리별 근거」 — 화면에서 행을 눌러야 보이는 내용(브랜드별 점유율 막대 ·
        # 연관어 목록 · 판정 근거)을 표 뒤에 펼쳐 싣는다. 표 행 안에 colspan 블록으로 두면
        # 쪽이 끊기는 자리에서 표 머리글과 분리돼 읽기 어려워진다.
        out=[]
        for m in re.finditer(r'<tr class="xr"[^>]*>(.*?)</tr>\s*<tr class="xd"[^>]*>(.*?)</tr>',h,re.S):
            cat=re.sub(r'<[^>]+>','',re.search(r'<td class="kw"[^>]*>(.*?)</td>',m.group(1),re.S).group(1)).strip()
            inner=re.search(r'<td colspan="\d+"[^>]*>(.*)</td>\s*$',m.group(2),re.S)
            if not inner: continue
            out.append(f'<div class="a4-ev"><h4 class="a4-ev__cat">{kw(cat)}</h4>{_static(inner.group(1))}</div>')
        return (f'<div class="a4-evs"><p class="sub">{_t("a4.evidenceNote")}</p>{"".join(out)}</div>') if out else ""

    _S1DESC=f'<p class="sub">{_t("s4.lead")}</p>'
    _L3=f'<li>{_t("limits.llmPick")}</li>'
    _L4=f'<li>{_t("limits.oneSeed")}</li>'
    _L5=(f'<li>{_t("limits.noCombo")}</li>') if not RATED0 else ""
    LIMIT=f'<div class="note"><ol>{scopeli}{thinli}{_L3}{_L4}{_L5}</ol></div>'

    # ── 섹션 = (제목, 배지, 대시 본문, A4 본문) · 두 뷰가 같은 재료를 각자 감싼다
    SECS=[(_t("sec.summary"),"MAP",kpi+SUM+BUB,kpi+_static(SUM+BUB)),
          (_t("sec.map"),"S0",MTOG+MAPT+'<div class="pager" data-for="map"></div>'+MJS,_static(MAPT)+_a4matrix()+_evidence(MAPT))]
    if PRES: SECS.append((_t("sec.priority"),"S0-p",PRES,_static(PRES)))
    SECS+=[(_t("sec.facetDeep"),"S0-d",SCEP,_static(SCEP)),
           (_t("sec.synthesis"),"S1",_S1DESC+S4,_S1DESC+_static(S4)),
           (_t("sec.limits"),"",LIMIT,LIMIT)]

    def _card(t,b,inner):
        bd=f'<span class="dash-card__badge">{b}</span>' if b else ""
        return (f'<div class="dash-card"><div class="dash-card__head">'
                f'<span class="dash-card__title">{t}</span>{bd}</div>'
                f'<div class="dash-card__body">{inner}</div></div>\n')

    LEDE=_t("report.lede", own=esc(OWN))

    DASH=(f'<div class="dash-cover-block"><div class="dash-card">'
      f'<div class="dash-cover-gradient dash-cover-gradient--brand">'
      f'<div class="dash-cover-eyebrow">{_t("cover.eyebrow")}</div>'
      f'<div class="dash-cover-title">{esc(OWN)}</div>'
      f'<div class="dash-cover-category">{_t("cover.subtitle")}</div>'
      f'<div class="dash-cover-meta">{meta}</div></div>'
      f'<div class="mr-summary-box mr-summary-box--dash"><div class="mr-summary-box__title">{_t("report.purpose.title")}</div>'
      f'<p class="mr-summary-text">{LEDE}</p></div></div></div>\n'
      +"".join(_card(t,b,d) for t,b,d,_ in SECS))

    A4=(f'<div class="rpt-page rpt-page--cover"><div class="cover-body"><div>'
      f'<div class="cover-lm">ListeningMind.AI</div>'
      f'<div class="cover-title">{_t("cover.eyebrow")}</div>'
      f'<div class="cover-category">{esc(OWN)}</div>'
      f'<div class="cover-meta"><span>{meta}</span></div></div></div></div>\n'
      f'<div class="rpt-page"><div class="page-body">'
      f'<div class="mr-summary-box"><div class="mr-summary-box__title">{_t("report.purpose.title")}</div>'
      f'<p class="mr-summary-text--sm">{LEDE}</p></div>'
      f'{_card(SECS[0][0],SECS[0][1],SECS[0][3])}</div></div>\n'
      +"".join(f'<div class="rpt-page"><div class="page-body">{_card(t,b,a)}</div></div>\n'
               for t,b,_,a in SECS[1:]))

    VIEWJS = """(function(){var b=document.querySelectorAll('.mini-toolbar__view button');
b.forEach(function(x){x.addEventListener('click',function(){var m=x.getAttribute('data-view');
document.body.classList.toggle('view-mode-dash',m==='dash');document.body.classList.toggle('view-mode-a4',m==='a4');
b.forEach(function(z){z.classList.toggle('active',z===x);});});});})();"""
    BNJS="""(function(){var tip=document.createElement('div');tip.className='bntip';tip.setAttribute('role','tooltip');document.body.appendChild(tip);
function show(e){var el=e.target.closest&&e.target.closest('.bn');if(!el)return;var f=el.dataset.full,t=el.dataset.tip;
 tip.innerHTML='';var b=document.createElement('b');b.textContent=f;tip.appendChild(b);if(t){var s=document.createElement('span');s.textContent=t;tip.appendChild(s);}
 tip.classList.add('on');var r=el.getBoundingClientRect(),w=tip.offsetWidth,h=tip.offsetHeight;
 var x=Math.min(Math.max(8,r.left+r.width/2-w/2),window.innerWidth-w-8),y=r.top-h-8;if(y<8)y=r.bottom+8;
 tip.style.left=x+'px';tip.style.top=y+'px';}
function hide(e){if(e.target.closest&&e.target.closest('.bn'))tip.classList.remove('on');}
document.addEventListener('mouseover',show);document.addEventListener('mouseout',hide);
document.addEventListener('focusin',show);document.addEventListener('focusout',hide);
window.addEventListener('scroll',function(){tip.classList.remove('on');},true);})();"""
    # JS 자산이 쓰는 화면 문구 — 리포트 언어로 먼저 심는다 (sortpage.js 의 L() 이 꺼내 쓴다)
    _JSK = ("col.catVolume", "col.rival1", "js.rows", "js.ownCombo", "js.ownFallback",
            "js.relLead", "js.times", "js.collapse", "js.showMore")
    # 템플릿이 이미 <script> 로 감싼다 — 여기서 태그를 또 넣으면 스크립트 전체가 죽는다
    jsl = "window.LMBC_L=%s;" % json.dumps({k: _t(k) for k in _JSK}, ensure_ascii=False)
    trjs = ("var trBtn=document.querySelector('.mini-toolbar__tr');"
            "if(trBtn){trBtn.addEventListener('click',function(){"
            "var on=document.body.classList.toggle('kw-translated');"
            "trBtn.setAttribute('aria-pressed',on?'true':'false');});}")
    script = jsl + "\n" + trjs + "\n" + "\n".join([_asset("expand.js"), _asset("sortpage.js"), VIEWJS, BNJS])

    inlined = inline_styles(STYLES_DIR, SLUG, SKILL_STYLES)
    if LOCALE_FONT_OVERRIDE.get(lang):
        inlined += "\n\n/* === locale font override === */\n" + LOCALE_FONT_OVERRIDE[lang]
    blocks = {
        "{{LANG}}": HTML_LANG.get(lang, "en"),
        "{{FONT_HREF}}": FONT_HREF.get(lang, FONT_HREF["us"]),
        "{{CATEGORY}}": esc(OWN),
        "{{REPORT_TITLE}}": _t("report.title"),
        "{{INLINED_CSS}}": inlined,
        "{{TOOLBAR_DASH_BTN}}": TOOLBAR_DASH_BTN.get(lang, "Dashboard"),
        "{{TOOLBAR_A4_LABEL}}": "A4",
        "{{TOOLBAR_PRINT_BTN}}": TOOLBAR_PRINT_BTN.get(lang, "Print"),
        # 번역이 없으면 버튼 자체가 없다 — 누를 게 없는 토글을 두지 않는다
        "{{TOOLBAR_TR_BTN}}": (
            '<button type="button" class="mini-toolbar__tr" aria-pressed="false">'
            + esc(_t("toolbar.translateBtn")) + '</button>') if _tr else "",
        "{{DASH_BODY}}": DASH,
        "{{A4_BODY}}": A4,
        "{{INLINE_SCRIPT}}": script,
    }
    with open(os.path.join(TEMPLATES_DIR, f"{SLUG}.html"), encoding="utf-8") as f:
        template = f.read()
    # 단일 패스 치환 — 순차 replace 를 쓰면 데이터 안의 {{...}} 가 다시 펼쳐진다
    pat = re.compile("|".join(re.escape(k) for k in blocks))
    open(out,"w",encoding="utf-8").write(pat.sub(lambda m: blocks[m.group(0)], template))
    print(out,len(J),"카테고리 ·",len(allc),"세부 수요 ·",dict(cnt),"· 주인 없음 세부 수요",len(gap))   # i18n-ok · 콘솔

def selftest():
    """이식본 전용 검사 — 정본의 selftest 를 라벨 체계에 맞춰 다시 썼다.
    옛 상수(WB · NAME · CSS · HEAD)는 이식하며 사라졌고, 대신 라벨·템플릿·CSS 파일을 검사한다."""
    global LABELS
    f=0
    def eq(got,want,what):
        nonlocal f
        if got!=want: f+=1; print(f"  ✗ {what}: {got!r} != {want!r}")

    # ── 라벨 · 세 언어의 키가 완전히 같아야 한다 (t() 가 없는 키를 조용히 키로 찍는다)
    langs={}
    for lg in REPORT_LANGS:
        pth=os.path.join(LABELS_DIR, f"{SLUG}.{lg}.json")
        eq(os.path.exists(pth),True,f"라벨 파일 {lg}")
        if os.path.exists(pth):
            with open(pth,encoding="utf-8") as fh: langs[lg]=json.load(fh)
    if len(langs)==len(REPORT_LANGS):
        base=set(langs["kr"])
        # 집합을 통째로 찍으면 200줄이 쏟아져 읽을 수 없다 — 차이만 보인다
        for lg,d in langs.items():
            miss, extra = sorted(base-set(d)), sorted(set(d)-base)
            eq(miss,[],f"{lg} 에 없는 키")
            eq(extra,[],f"{lg} 에만 있는 키")
        # 자리표시자도 같아야 한다 — 다르면 번역본에서 숫자가 빠진다
        import re as _re
        ph=lambda v:set(_re.findall(r"\{[a-zA-Z0-9]+\}",v))
        shared=set.intersection(*(set(d) for d in langs.values()))
        bad=sorted(k for k in shared if any(ph(langs[lg][k])!=ph(langs["kr"][k]) for lg in langs))
        eq(bad,[],"자리표시자가 세 언어에서 같다")
        # _core 가 언어를 알아내는 데 쓰는 값 — 철자가 바뀌면 개수 표기가 조용히 깨진다
        eq(langs["kr"].get("country.KR"),"한국","format_count 가 보는 country.KR")
        eq(langs["jp"].get("country.JP"),"日本","format_count 가 보는 country.JP")
        for lg in REPORT_LANGS:
            for k in ("country.KR","country.JP","country.US",
                      "report.marketLabel.KR","report.marketLabel.JP","report.marketLabel.US"):
                eq(k in langs[lg],True,f"{lg} 에 공통 키 {k}")

    LABELS=langs.get("kr",{})

    # ── 숫자 표기 · 자릿수 체계가 언어마다 다르다
    eq(n(None),"-","미수록은 -")
    eq(n(0),"0","실제 0 은 0")
    eq(pct(None),"-","부착률 미수록은 -")
    eq(pct(0.0),"0.0%","부착률 0 은 0.0%")
    eq(short(None),"-","short 미수록")
    eq(short(9999),"9,999","1만 미만은 원값")
    eq(short(10000),"1만","kr 은 만 단위")
    eq(short(12345),"1.2만","만 단위 반올림")
    LABELS=langs.get("us",{})
    eq(short(10000),"10k","us 는 k 단위")
    eq(short(1200000),"1.2M","us 는 100만에서 M")
    LABELS=langs.get("kr",{})

    # ── 판정 슬러그 · 표시 문자열이 아니라 슬러그로 키잡혀야 한다
    for k in VERDICTS:
        eq(k in CLS,True,f"CLS 에 {k}")
        eq(k in JR,True,f"정렬 순서에 {k}")
        eq(_t("verdict."+k)!="verdict."+k,True,f"verdict.{k} 라벨이 있다")
    for a_ in ("우위","경합","열세","없음","없음 · 자사 1위"):
        eq(a_ in VK,True,f"judge.py 내부값 {a_} 매핑")
    for a_ in ("우위","경합","열세","없음","보류"):
        eq(_t("walk."+WAK[a_])!="walk."+WAK[a_],True,f"탐색 축 라벨 {a_}")

    # ── CSS · 토큰이 있고 측정 축이 판정색을 쓰지 않는다
    css=inline_styles(STYLES_DIR, SLUG, SKILL_STYLES)
    for t in ("--j-own","--j-cmp","--j-low","--j-emp","--m-name","--m-path","--m-none"):
        eq(t in css,True,f"CSS 토큰 {t}")
    eq("var(--j-own)" not in css.split("--m-name")[-1][:80],True,"측정 축이 판정색을 쓰지 않는다")
    eq(".view-dash .a4m" in css,True,"A4 매트릭스는 대시에서 숨긴다")
    eq(".bn{" in css,True,"브랜드명 말줄임 규칙")

    # ── 템플릿 · 토큰이 모두 채워지는가
    tpl_path=os.path.join(TEMPLATES_DIR, f"{SLUG}.html")
    eq(os.path.exists(tpl_path),True,"템플릿 파일")
    if os.path.exists(tpl_path):
        import re as _re
        with open(tpl_path,encoding="utf-8") as fh: tpl=fh.read()
        toks=set(_re.findall(r"\{\{[A-Z_0-9]+\}\}",tpl))
        filled={"{{LANG}}","{{FONT_HREF}}","{{CATEGORY}}","{{REPORT_TITLE}}","{{INLINED_CSS}}",
                "{{TOOLBAR_DASH_BTN}}","{{TOOLBAR_A4_LABEL}}","{{TOOLBAR_PRINT_BTN}}","{{TOOLBAR_TR_BTN}}",
                "{{DASH_BODY}}","{{A4_BODY}}","{{INLINE_SCRIPT}}"}
        eq(toks-filled,set(),"템플릿에 채우지 않는 토큰이 없다")

    # ── 자산 · templates/ 의 JS 가 실려 있나
    for nm in ("expand.js","sortpage.js"):
        pth=os.path.join(TEMPLATES_DIR,nm)
        eq(os.path.exists(pth),True,f"자산 {nm}")
        if os.path.exists(pth):
            with open(pth,encoding="utf-8") as fh: blob=fh.read()
            eq(len(blob)>0,True,f"자산 {nm} 내용")
            eq("나이키" in blob,False,f"{nm} 에 회차 고유 브랜드명이 없다")

    # i18n - 렌더러 안에 라벨로 빠지지 않은 한국어가 남아 있지 않나.
    #   라벨 값을 바꿔 보는 식(센티널)으로는 "애초에 추출되지 않은 문자열"이 안 보이고,
    #   회차에 따라 안 타는 분기도 있으므로 렌더 결과가 아니라 소스를 본다.
    import io as _io, tokenize as _tk
    CONTRACT={"우위","경합","열세","없음","없음 · 자사 1위","보류",
              "참전","부분 참전","미판매","미확인","지정"}
    CONTRACT_W=set(w for c in CONTRACT for w in re.findall("[\uac00-\ud7a3]+", c))
    _src=open(os.path.abspath(__file__),encoding="utf-8").read()
    _lines=_src.split(chr(10)); _hang=re.compile("[\uac00-\ud7a3]")
    _selt=_src.index("def selftest(")
    _bad=[]
    for _t2 in _tk.generate_tokens(_io.StringIO(_src).readline):
        if _t2.type!=_tk.STRING or not _hang.search(_t2.string): continue
        if _t2.string.lstrip("frbu").startswith(('"""', "'''")): continue
        if sum(len(l)+1 for l in _lines[:_t2.start[0]-1])>_selt: continue
        # 큰 f-string 안에 계약값 비교만 들어 있는 경우가 있다 — 리터럴 통째가 아니라
        # 한글 낱말 단위로 본다. 모든 낱말이 계약 어휘면 통과.
        _w=re.findall("[\uac00-\ud7a3]+", _t2.string)
        if _w and all(x in CONTRACT_W for x in _w): continue
        if "i18n-ok" in _lines[_t2.start[0]-1]: continue
        _bad.append(str(_t2.start[0]) + ":" + _t2.string[:40])
    eq(_bad,[],"라벨로 빠지지 않은 한국어 문자열")

    # 템플릿이 이미 <script> 로 감싼다 - INLINE_SCRIPT 가 태그를 또 넣으면 스크립트 전체가 죽는다
    with open(os.path.join(TEMPLATES_DIR,SLUG+".html"),encoding="utf-8") as fh: _tpl=fh.read()
    eq("<script>{{INLINE_SCRIPT}}</script>" in _tpl,True,"INLINE_SCRIPT 는 템플릿이 감싼다")

    # 검색어 번역 배선
    eq(hasattr(ca,"kw_html") and hasattr(ca,"set_translations"),True,"_core 에 kw_html·set_translations")
    eq("{{TOOLBAR_TR_BTN}}" in _tpl,True,"템플릿에 번역 버튼 자리")
    eq(_src.count("kw(")>30,True,"검색어 자리가 kw() 로 간다")

    print(f"render_report.py selftest — {f} checks failed")
    return 1 if f else 0

if __name__=="__main__":
    if "--selftest" in sys.argv: sys.exit(selftest())
    ap=argparse.ArgumentParser(description="Render the brand-competition category map report.")
    ap.add_argument("--skill",required=True,choices=[SLUG])
    ap.add_argument("--run",required=True,help="run folder (config.json · data/ · work/)")
    ap.add_argument("--category",help="brand name for the cover (default: config.brand)")
    # --gl = market analysed · --lang = report language. They are independent.
    ap.add_argument("--gl",required=True,choices=["kr","jp","us"],help="target market")
    ap.add_argument("--lang",choices=list(REPORT_LANGS),help="report language (default: same as --gl)")
    ap.add_argument("--date",required=True,help="YYYY-MM-DD")
    ap.add_argument("--out",required=True,help="output HTML path")
    ap.add_argument("--translations",
                    help="keyword translation map {original: translation} as JSON. "
                         "Only when the market language differs from --lang. "
                         "Passing it adds the keyword-translation toggle to the toolbar.")
    a=ap.parse_args()
    build(a.run, a.out, gl=a.gl, lang=(a.lang or a.gl).lower(), date=a.date,
          translations=a.translations)
