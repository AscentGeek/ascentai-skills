# -*- coding: utf-8 -*-
"""CEP 심층 — '<CEP> <카테고리>' 를 시드로 따로 조회한 경로에서 판정한다.

 **경로 축만으로 판정한다.** `<자사> CEP <카테고리>`(예: '원소주 소주 하이볼') 같은 결합
 검색은 거의 존재하지 않는다 — 실측으로 한 회차에서 9개 중 9개가 검색량 데이터에 없었다.
 그래서 이름 축은 CEP 에서 쓰지 않는다.

 세는 법 · 경로 **전체 노드**에 등장한 그 브랜드 검색어의 고유 개수. 카테고리 탐색 축과
 같은 지표이고, 패스뷰에서 브랜드명으로 키워드 목록을 거른 수와 같다.
 판정 · 2배 규칙 · 양쪽 모두 3개 미만이면 '없음' · 보류 게이트 없음.

 왜 따로 조회하나 · 카테고리 응답 안에서 CEP 를 슬라이스하면 모수가 너무 작다.
 실측 · '양말' 연관어 1,000개 중 '러닝'을 포함한 것은 24건뿐이었다. 시드로 따로 넣으면
 경로가 300개 나온다. intent_finder 는 부르지 않는다 — CEP 시드는 3~4단어라 몇 개
 안 나온다(실측 · '수영 골전도 이어폰' → 8개).

 CEP 검색량 데이터가 없으면 시드로 쓸 수 없다 — 빈 응답이 온다. 조회 목록에서 뺀다.

 입력 · <회차>/data/cep/<CEP> <카테고리>_path.json
 사용 · python3 cep_deep.py <회차>
"""
import json,os,sys,collections
RATIO,KWFLOOR=2,3
def ns(s): return s.replace(" ","").lower()
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
def run(R):
    cfg=json.load(open(f"{R}/config.json")); OWN=cfg["brand"]
    VAR=dict(cfg.get("alias",{})); VAR.setdefault(OWN,cfg.get("own",[OWN]))
    EXC=cfg.get("alias_exclude",{})
    C=json.load(open(f"{R}/work/curate.json")); C.pop("_note",None)
    VOL={}
    import glob
    for f in glob.glob(f"{R}/data/cat/*vol*.json"):
        for xx in json.load(open(f))["data"]:
            VOL.setdefault(ns(xx["keyword"]),xx["ads_metrics"]["volume_total"])
    J=json.load(open(f"{R}/work/judge.json")); TRUNC=[]
    ALLB=[]
    for v in C.values():
        for b in (v.get("comp") or []):
            if b not in ALLB and b!=OWN: ALLB.append(b)
    for b in cfg.get("extra_brands",[]):
        if b not in ALLB and b!=OWN: ALLB.append(b)
    def axis(own,top,floor=KWFLOOR):
        if own<floor and top<floor: return "없음"
        if top>=RATIO*own: return "열세"
        if own>=RATIO*top: return "우위"
        return "경합"
    n=0
    for x in J:
        c=x["term"]
        if not C.get(c,{}).get("deep"): x["deep"]=False; continue
        x["deep"]=True
        # CEP 안의 경쟁 지형은 카테고리 경계를 넘는다 — 회차 전체 브랜드로 센다
        BR=[OWN]+ALLB
        x["cep_cols"]=BR
        for q in x["ceps"]:
            seed=f'{q["cep"]} {c}'
            fp=f"{R}/data/cep/{seed}_path.json"
            legacy=f"{R}/data/kwidx/{seed}.json"
            B=None; npath=None
            if os.path.exists(fp):
                d=json.load(open(fp)); P=d.get("data") or []; npath=len(P)
                if d.get("nodes_kept") and os.path.exists(legacy):
                    TRUNC.append(seed); B=json.load(open(legacy))["brands"]
                else:
                    if d.get("nodes_kept"): TRUNC.append(seed)
                    acc={}
                    for path in P:
                        si=next((k for k,nd in enumerate(path) if ns(nd)==ns(seed)),None)
                        for k,nd in enumerate(path):
                            for b in BR:
                                if not hit(b,nd,VAR,EXC): continue
                                e=acc.setdefault(b,{"kw":set(),"min_step":None})
                                e["kw"].add(nd)
                                st=(k-si) if si is not None else k
                                if st and (e["min_step"] is None or st<e["min_step"]): e["min_step"]=st
                    B={b:{"n":len(e["kw"]),"min_step":e["min_step"]} for b,e in acc.items()}
            elif os.path.exists(legacy):
                B=json.load(open(legacy))["brands"]
            if B is None: q["deep"]=None; continue
            o=B.get(OWN,{"n":0,"min_step":None})
            comp=sorted([(b,v) for b,v in B.items() if b!=OWN],
                        key=lambda z:(-z[1]["n"],z[1]["min_step"] if (z[1]["min_step"] or 0)>0 else 99))
            tb,tv=(comp[0] if comp else ("-",{"n":0,"min_step":None}))
            q["deep"]=dict(seed=seed,
                           path=dict(axis=axis(o["n"],tv["n"]),own=o["n"],own_step=o.get("min_step"),
                                     top=tb,top_n=tv["n"],top_step=tv.get("min_step"),metric="kw",
                                     branded=sum(v["n"] for v in B.values()),npaths=npath,
                                     steps={b:v.get("min_step") for b,v in B.items()},
                                     brands={b:B.get(b,{}).get("n",0) for b in BR}))
            n+=1
    json.dump(J,open(f"{R}/work/judge.json","w"),ensure_ascii=False,indent=1)
    if TRUNC: print(f"  ⚠ 경로가 앞 4노드로 잘린 CEP 시드 {len(TRUNC)}건 — 전체 노드로 다시 저장할 것")
    return J,OWN,n,TRUNC

if __name__=="__main__":
    for R in sys.argv[1:]:
        J,OWN,n,TR=run(R)
        deep=[x for x in J if x.get("deep")]
        print(f"\n### {R} · 심층 카테고리 {len(deep)} · 조회된 CEP {n}")
        for x in deep:
            print(f"  ## {x['term']}")
            for q in x["ceps"]:
                d=q.get("deep")
                if not d: print(f"     {q['cep']:10} <조회 안 함>"); continue
                p=d["path"]
                def _st(v): return f"({v}단계)" if (v or 0)>0 else ("(시드 이전)" if v else "")
                print(f"     {q['cep']:10} {p['axis']:4} · 등장 검색어 {OWN} {p['own']:3}개{_st(p['own_step'])}"
                      f" vs {p['top']} {p['top_n']:3}개{_st(p['top_step'])}")
