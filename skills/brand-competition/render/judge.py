# -*- coding: utf-8 -*-
"""카테고리 판정 — 이름 축(검색 점유율)과 탐색 축(경로 등장 검색어).

 이름 축 · 검색 점유율 = 카테고리 연관어 중 그 브랜드 검색어의 검색량 합 ÷ 연관어 전체
           검색량 합. 2배 규칙 · 바닥 3%(일반 검색어로 희석되므로 부착률의 10%보다 낮다).
           대표 검색어(브랜드 검색어 중 최대)는 참고로만 — 브랜드 전체 수요라 카테고리 몫이 아니다.
 탐색 축 · path_finder 경로 **전체 노드**에 등장한 그 브랜드 검색어의 고유 개수.
           패스뷰에서 브랜드명으로 키워드 목록을 거른 수와 같다. 2배 규칙 · 바닥 3개 · 보류 없음.
           보조로 첫 등장 단계(시드 뒤 몇 번째 · 0 이하는 시드 이전).
 빈자리(양쪽 모두 바닥 미만) + 탐색 우위 = 잠재 선점 (배지는 렌더 단계에서 붙인다)

 **경로는 전체 노드가 있어야 한다.** 앞 4노드만 저장하면 뒤쪽에서 처음 나오는 브랜드가
 통째로 빠진다(실측 — 안동소주가 4단계에서 처음 나와 41개가 0개가 됐다).

 **브랜드 속성으로 분기하지 않는다.** 점유율이 전부 바닥 미만이면 일반 규칙이 그대로
 '없음'(빈자리) 을 낸다 — B2B 라고 따로 빼지 않는다.

 사용:  python3 judge.py <회차>
 출력:  <회차>/work/judge.json · <회차>/work/walk.json
"""
import json,glob,os,sys
# ── 순수 판정 로직 (입출력 없음 · --selftest 가 여기를 검사한다)
RATE,RATIO=3,2      # (구) 연관어 전체 분모 시절 바닥 3% · 2배 규칙
NAMEMIN=10          # 브랜드 지명 비율 하한 % — 미만이면 「빈자리」(브랜드 없이 검색되는 카테고리)
BVOLMIN=1000        # 브랜드 검색어 합 하한(12개월) — 미만이면 점유율이 흔들려 「빈자리」
KWFLOOR=3           # 탐색 축 바닥 — 등장 검색어 3개
def axis(own,top,floor):
    if own<floor and top<floor: return "없음"
    if top>=RATIO*own: return "열세"
    if own>=RATIO*top: return "우위"
    return "경합"
CEPMIN=30      # 심층 후보 최소 앞말 수 — 8-b 가 세부 수요 3개를 필요로 한다
PRIO={"경합":0,"열세":1,"없음":2,"없음 · 자사 1위":2,"우위":3}   # 약한 곳·빈 곳 먼저
def ns(k): return k.replace(" ","").lower()
def hit(b,k,alias,exclude):
    """브랜드 b 가 검색어 k 에 들어 있나. 별칭은 브랜드명을 **대체하지 않고 더한다**.

    브랜드(별칭)는 **낱말 첫머리에서 시작해야** 한다. 띄어쓰기를 지운 부분문자열로 보면
    「웨이더 단백질」·「파우더 단백질」이 `더단백` 으로 잡힌다(실측 2026-10-02 · 단백질 보충제
    회차의 더단백 1,336 이 전부 이 오탐이었다). 원소주 회차에서도 「일품진로 하이볼」 12,390 이
    진로로, 「홋카이도 하이볼」이 이도로, 「청와대 선정 전통주」가 대선으로 잡혔다.
    끝은 낱말 안이어도 된다(신타 → 신타6 · 샥즈골전도이어폰). 1글자 브랜드는 토큰 일치.
    제외어가 먼저다."""
    n=ns(k)
    for z in exclude.get(b,()):
        if ns(z) in n: return False
    t=k.lower().split()
    if len(b)==1: return b.lower() in t
    tails=["".join(t[i:]) for i in range(len(t))]
    return any(x.startswith(ns(a)) for a in ([b]+list(alias.get(b,[]))) if ns(a) for x in tails)

if "--selftest" in sys.argv:
    f=0
    def eq(got,want,what):
        global f
        if got!=want: f+=1; print(f"  ✗ {what}: {got!r} != {want!r}")
    # 2배 규칙
    eq(axis(40,10,3),"우위","자사 4배")
    eq(axis(10,40,3),"열세","경쟁사 4배")
    eq(axis(30,20,3),"경합","1.5배는 경합")
    eq(axis(20,10,3),"우위","정확히 2배는 우위")
    eq(axis(10,20,3),"열세","정확히 2배 뒤짐은 열세")
    eq(axis(2.9,2.9,3),"없음","둘 다 바닥 미만")
    eq(axis(3,0,3),"우위","바닥 걸치면 판정한다")
    eq(RATE,3,"이름 축 바닥은 3% (점유율은 일반 검색어로 희석된다)")
    eq(axis(2,2,KWFLOOR),"없음","탐색 축 바닥 3개")
    # 브랜드 매칭 — 별칭 · 제외어 · 1글자
    AL={"산토리":["산토리","가쿠"],"짐빔":["짐빔","짐볼"]}; EX={"진로":["일품진로","진로일품","하이트진로"],"산토리":["산토리니"]}
    eq(hit("산토리","가쿠빈 하이볼",AL,EX),True,"제품명을 모회사로 묶는다")
    eq(hit("산토리","산토리니 여행",AL,EX),False,"산토리니는 산토리가 아니다")
    eq(hit("진로","일품진로 가격",AL,EX),False,"일품진로는 진로가 아니다")
    eq(hit("진로","진로 소주",AL,EX),True,"진로 자체는 잡는다")
    eq(hit("짐빔","짐볼 하이볼",AL,EX),True,"흔한 오타도 묶는다")
    eq(hit("려","려 샴푸",{},{}),True,"1글자는 토큰 일치")
    eq(hit("려","배려 깊은",{},{}),False,"1글자가 다른 말에 묻히면 아니다")
    eq(hit("진로","진로 토닉워터",{"진로":["진로 소주"]},EX),True,"별칭 목록이 브랜드명 자체를 가리지 않는다")
    eq(hit("더단백","웨이더 단백질 보충제",{},{}),False,"낱말 중간에서 시작하면 아니다(웨이|더단백)")
    eq(hit("더단백","나우푸드 웨이 프로틴 파우더 단백질 보충제",{},{}),False,"파우|더단백도 아니다")
    eq(hit("더단백","더단백 프로틴 단백질 보충제",{},{}),True,"낱말 첫머리면 잡는다")
    eq(hit("신타","단백질 보충제 신타6",{},{}),True,"끝은 낱말 안이어도 된다")
    eq(hit("셀렉스","단백질보충제 셀렉스",{},{}),True,"띄어쓰기 없는 앞말 뒤 낱말도 잡는다")
    eq(hit("골드 스탠다드","골드스탠다드 웨이",{},{}),True,"여러 낱말 브랜드는 붙여 써도 잡는다")
    eq(hit("진로","하이트진로 소주",{},{}),False,"제외어 없이도 낱말 중간은 안 잡는다")
    eq(hit("이도","홋카이도 하이볼",{},{}),False,"홋카|이도 — 원소주 회차 실측 오탐")
    eq(hit("대선","청와대 선정 전통주",{},{}),False,"청와|대 선정 — 원소주 회차 실측 오탐")
    # 데이터 3상태 — None(미수록) 과 0(실제 0) 은 다르다
    eq((None or 0)==0,True,"None 은 0 으로 떨어진다(비율 계산 전에 분리해야 한다)")
    eq(axis(0,0,10),"없음","둘 다 0 이면 빈자리")
    # 심층 추천 우선순위 — 선점(우위)이 맨 뒤여야 한다
    eq(sorted(["우위","없음","경합","열세"],key=lambda k:PRIO[k]),["경합","열세","없음","우위"],"추천 우선순위")
    eq(PRIO["우위"]>PRIO["없음"],True,"선점은 빈자리보다 뒤")
    print(f"judge.py selftest — {f} checks failed"); sys.exit(1 if f else 0)

R=sys.argv[1]
cfg=json.load(open(f"{R}/config.json")); OWN=cfg["brand"]
OWNV=[a.lower() for a in cfg.get("own",[OWN])]
C=json.load(open(f"{R}/work/curate.json")); C.pop("_note",None)
V={}
def _rows(f):
    d=json.load(open(f))
    return d if isinstance(d,list) else (d.get("data") or [])
for f in sorted(glob.glob(f"{R}/data/cat/*vol*.json"))+sorted(glob.glob(f"{R}/data/sos/*.json")):
    for x in _rows(f):
        if isinstance(x,dict) and x.get("keyword"):
            V.setdefault(x["keyword"],(x.get("ads_metrics") or {}).get("volume_total") or 0)
VN={}
for k,v in V.items(): VN.setdefault(ns(k),[]).append((k,v))
def vol(k):
    if k in V: return V[k]
    c=VN.get(ns(k))
    return max(v for _,v in c) if c else None      # 띄어쓰기만 다른 행 — DB 정규화
BI=json.load(open(f"{R}/data/cat/{OWN}_brand_intent.json"))["data"]
BP=json.load(open(f"{R}/data/cat/{OWN}_brand_path.json"))["data"]
paths=[" > ".join(p if isinstance(p,str) else p.get("keyword","") for p in (r.get("path") or r.get("nodes") or [])) if isinstance(r,dict) else str(r) for r in BP]
# ── 브랜드 집합 · 고정 사전을 게이트로 쓰지 않는다(4단계에서 LLM 이 라벨링한 것만)
VAR=dict(cfg.get("alias",{})); VAR.setdefault(OWN,cfg.get("own",[OWN]))
EXC=cfg.get("alias_exclude",{})     # 같은 글자를 쓰지만 다른 브랜드 (진로 ← 일품진로 · 산토리 ← 산토리니)
WATCH=[b for b in cfg.get("watch_brands",[]) if b!=OWN]
# 사람이 지목한 카테고리는 근거가 없어도 남는다 — 조용히 사라지면 안 된다
for _c in cfg.get("watch_categories",[]):
    C.setdefault(_c,{"group":"지정","comp":[],"cep":[]})["src"]="지정"
# 점유율·탐색 축은 회차 전체 브랜드를 같은 집합으로 쓴다 — 카테고리마다 다르면 열이 안 맞는다
BRANDS={OWN}|set(WATCH)|set(cfg.get("extra_brands",[]))   # extra_brands = 회차에서 찾았으나 comp 에 없는 브랜드
for _v in C.values(): BRANDS|=set(_v.get("comp") or [])
TRUNC=[]
def kwindex(seed,pathfile):
    """경로 전체 노드에서 브랜드별 고유 검색어와 첫 등장 단계를 센다.

    경로가 앞 4노드로 잘려 있으면 뒤쪽 브랜드가 통째로 빠지므로, 수집 당시 만들어 둔
    data/kwidx/<시드>.json 이 있으면 그걸 쓴다(옛 회차 호환)."""
    legacy=f"{R}/data/kwidx/{seed}.json"
    if not os.path.exists(pathfile):
        return json.load(open(legacy))["brands"] if os.path.exists(legacy) else None
    d=json.load(open(pathfile)); P=d.get("data") or []
    if d.get("nodes_kept") and os.path.exists(legacy):
        TRUNC.append(seed); return json.load(open(legacy))["brands"]
    if d.get("nodes_kept"): TRUNC.append(seed)
    B={}
    for p in P:
        si=next((i for i,nd in enumerate(p) if ns(nd)==ns(seed)),None)
        for i,nd in enumerate(p):
            for b in BRANDS:
                if not hit(b,nd,VAR,EXC): continue
                e=B.setdefault(b,{"kw":set(),"min_step":None})
                e["kw"].add(nd)
                st=(i-si) if si is not None else i
                if st and (e["min_step"] is None or st<e["min_step"]): e["min_step"]=st
    return {b:{"kw":sorted(e["kw"]),"n":len(e["kw"]),"min_step":e["min_step"]} for b,e in B.items()}

def summarize(B,cols=None):
    o=B.get(OWN,{"n":0,"min_step":None})
    comp=sorted([(b,v) for b,v in B.items() if b!=OWN],
                key=lambda z:(-z[1]["n"],z[1]["min_step"] if (z[1]["min_step"] or 0)>0 else 99))
    tb,tv=(comp[0] if comp else ("-",{"n":0,"min_step":None}))
    d=dict(axis=axis(o["n"],tv["n"],KWFLOOR),own=o["n"],own_step=o.get("min_step"),
           top=tb,top_n=tv["n"],top_step=tv.get("min_step"),
           branded=sum(v["n"] for v in B.values()),metric="kw",
           first=[[b,v["n"]] for b,v in sorted(B.items(),key=lambda z:-z[1]["n"])],
           steps={b:v["min_step"] for b,v in B.items()})
    if cols: d["brands"]={b:B.get(b,{}).get("n",0) for b in cols}
    return d

def walk_of(c,comp):
    f=f"{R}/data/cat/{c}_path.json"
    B=kwindex(c,f)
    if B is None: return None
    w=summarize(B); w.update(src="catpath",npaths=(json.load(open(f))["data"].__len__() if os.path.exists(f) else None))
    return w

def share_of(c):
    """검색 점유율(정의 A · 브랜드 간) — 분모 = 자사+경쟁사 브랜드 검색어 검색량 합.
    카테고리 연관어 중 브랜드명이 들어간 검색어만 검색량이 있으면 된다(일반 검색어는 조회하지 않는다).
    지명 비율 = 브랜드 검색어(중복 제거) 합 ÷ (그 합 + 대표어 검색량) — 빈자리 판정에 쓴다."""
    f=f"{R}/data/cat/{c}_intent.json"
    if not os.path.exists(f): return None
    kws=json.load(open(f))["data"]
    S={}; U={}
    for b in BRANDS:
        ks=[k for k in kws if hit(b,k,VAR,EXC)]
        if not ks: continue
        vs=sorted(((vol(k) or 0,k) for k in ks),reverse=True)
        tot=sum(x for x,_ in vs)
        if not tot: continue
        for x,k in vs: U[k]=x
        S[b]=dict(vol=tot,n_kw=len(ks),rep_kw=vs[0][1],rep_vol=vs[0][0],kws=[[k,x] for x,k in vs])
    den=sum(t["vol"] for t in S.values())
    for t in S.values(): t["share"]=round(t["vol"]/den*100,1) if den else 0
    branded=sum(U.values()); seed=vol(c) or 0
    nr=round(branded/(branded+seed)*100,1) if (branded+seed) else 0
    return dict(denom=den,n_kw=len(kws),n_branded=len(U),branded=branded,seed=seed,name_ratio=nr,brands=S,defn="A")

out=[]; WK={}
for c,v in C.items():
    cat=vol(c) or 0
    sos=share_of(c)
    S=(sos or {}).get("brands",{})
    o=S.get(OWN,{})
    comp=[dict(brand=b,vol=t["vol"],rate=t["share"],self_vol=None,watch=(b in WATCH),
               rep_kw=t["rep_kw"],rep_vol=t["rep_vol"],n_kw=t["n_kw"],kws=t["kws"])
          for b,t in sorted(((b,t) for b,t in S.items() if b!=OWN),key=lambda z:-z[1]["vol"])][:8]
    ov=o.get("vol") or None
    own=o.get("share") or 0
    top=comp[0]["rate"] if comp else 0
    nr=(sos or {}).get("name_ratio",0); bt=(sos or {}).get("branded",0)
    name="없음" if (bt<BVOLMIN or nr<NAMEMIN) else axis(own,top,0)
    ceps=[]
    for p in v["cep"]:
        cv=vol(f"{p} {c}"); nv=vol(f"{OWN} {p} {c}")
        ceps.append(dict(cep=p,kw=f"{p} {c}",vol=cv,own=nv,rate=(round(nv/cv*100,1) if cv and nv is not None else None)))
    ceps.sort(key=lambda x:-(x["vol"] or 0))
    mf=f"{R}/work/mods_{c}.json"; M=json.load(open(mf)) if os.path.exists(mf) else {"n":0,"mods":[]}
    w=walk_of(c,v["comp"])
    if w: WK[c]=w
    ev=dict(intent=(o.get("n_kw") or 0),path=sum(1 for p in paths if c in p),
            brand_intent=sum(1 for k in BI if c in k),
            cat_intent_n=M["n"],mods=len(M.get("mods",[])))
    # 조회 자체를 안 한 자리와 조회했는데 검색량 데이터가 없는 자리를 구분해 둔다
    queried=os.path.exists(f"{R}/data/cat/{c}_intent.json") or os.path.exists(f"{R}/data/cat/{c}_path.json")
    out.append(dict(term=c,group=v["group"],src=v.get("src"),queried=queried,vol12=cat,
                    own_vol=ov,own_rate=(o.get("share") if o else None),own_self=None,
                    own_rep=([o.get("rep_kw"),o.get("rep_vol")] if o else None),own_kws=o.get("kws") or [],
                    sos=sos,comp=comp,name=name,walk=w,
                    ceps=ceps,flag=v.get("flag"),evidence=ev,presence=v.get("presence")))
os.makedirs(f"{R}/work",exist_ok=True)
json.dump(out,open(f"{R}/work/judge.json","w"),ensure_ascii=False,indent=1)
json.dump(WK,open(f"{R}/work/walk.json","w"),ensure_ascii=False)
from collections import Counter
print(R,Counter(x["name"] for x in out),Counter(x["walk"]["axis"] for x in out if x["walk"]))
for x in sorted(out,key=lambda r:-r["vol12"]):
    t=x["comp"][0] if x["comp"] else {"brand":"-","rate":None}
    w=f" · 탐색 {x['walk']['axis']}({x['walk']['own']}개 vs {x['walk']['top']} {x['walk']['top_n']}개)" if x["walk"] else ""
    cs=" ".join(f"{c['cep']}({(c['vol'] or 0)}·{c['rate'] if c['rate'] is not None else '-'}%)" for c in x["ceps"][:7])
    den=(x.get("sos") or {}).get("denom") or 0
    print(f"{x['term']:16} 브랜드합 {den:>9,} · {OWN} {(str(x['own_rate'])+'%') if x['own_rate'] is not None else '   -':>6} vs {t['brand']} {(str(t['rate'])+'%') if t.get('rate') is not None else '-':>6} → {x['name']}{w}")
    if cs: print(f"    세부 수요: {cs}")
if TRUNC: print(f"\n  ⚠ 경로가 앞 4노드로 잘린 시드 {len(TRUNC)}건 — 탐색 축이 불완전하다. 전체 노드로 다시 저장할 것")

# ── 7단계 · 심층 후보 (경합·열세·빈자리 우선 · 후보 모수 미달은 제외)
def _sup(c,terms):
    """상위어 — 다른 카테고리 이름을 품고 있으면 그쪽이 모수가 크다(밥알찹쌀떡 → 찹쌀떡)."""
    cands=[t for t in terms if t!=c and ns(t) in ns(c)]
    return max(cands,key=lambda t:MODS.get(t,0)) if cands else None
MODS={x["term"]:x["evidence"]["mods"] for x in out}
terms=[x["term"] for x in out]
ok=[x for x in out if x["evidence"]["mods"]>=CEPMIN]
thin=[x for x in out if x["evidence"]["mods"]<CEPMIN]
ok.sort(key=lambda x:(PRIO.get(x["name"],9),-x["vol12"]))
print(f"\n── 심층 후보 · 가능 {len(ok)} / 모수 미달 {len(thin)} (앞말 {CEPMIN} 미만)")
for x in ok[:10]:
    t=x["comp"][0]["brand"] if x["comp"] else "-"
    print(f"   {x['name']:<12} {x['term']:16} 앞말 {x['evidence']['mods']:>4} · 검색량 {x['vol12']:>9,} · 1위 {t}")
if thin:
    print("   ── 제외 (심층해도 표가 빈다)")
    for x in sorted(thin,key=lambda r:-r["vol12"])[:10]:
        sup=_sup(x["term"],terms)
        print(f"   {x['name']:<12} {x['term']:16} 앞말 {x['evidence']['mods']:>4}"
              + (f"  → 상위어 「{sup}」(앞말 {MODS[sup]}) 로 대신 권한다" if sup and MODS.get(sup,0)>=CEPMIN else ""))
_pick=[x for x in ok if PRIO.get(x["name"],9)<3]
if len(_pick)<3:
    print(f"   ⚠ 경합·열세·빈자리 중 가능한 것이 {len(_pick)}개뿐이다 — 막지 말고 사람에게 선택지를 준다")

