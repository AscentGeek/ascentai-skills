# -*- coding: utf-8 -*-
"""카테고리 경로에서 경쟁사 후보를 뽑는다 — 판정하지 않는다.

 연관어 앞말은 <브랜드> <카테고리> 결합이 실제로 검색될 때만 브랜드를 찾는다.
 대안 관계(블랙키위 ↔ 검색량 조회)나 사전에 없는 브랜드(제스트컴퍼니)는 그 방식으로 안 잡힌다.
 사람들은 “블랙키위 검색량 조회”라고 검색하지 않는다 — 대안은 **형제 키워드**로 나온다.

 그래서 경로 1,000개에서 시드 뒤 3스텝 노드를 빈도순으로 내고, 브랜드 판정은 LLM 이 한다.

 사용:  python3 pathcand.py <회차> [TOPN]
"""
import json,sys,os,collections
R=sys.argv[1]; TOPN=int(sys.argv[2]) if len(sys.argv)>2 else 22
cfg=json.load(open(f"{R}/config.json")); OWN=cfg["brand"]
OWNV=[a.lower() for a in cfg.get("own",[OWN])]
C=json.load(open(f"{R}/work/curate.json")); C.pop("_note",None)
def ns(s): return s.replace(" ","")
for c in C:
    f=f"{R}/data/cat/{c}_path.json"
    if not os.path.exists(f): print(f"## {c} — 경로 없음"); continue
    P=json.load(open(f))["data"]
    cnt=collections.Counter(); seed=0
    for p in P:
        if not p or p[0]!=c: continue
        seed+=1
        for k in p[1:4]:
            if ns(c) in ns(k): continue                    # 시드 변형은 후보가 아니다
            if any(a in k.lower() for a in OWNV): continue # 자사는 따로 센다
            cnt[k]+=1
    known=set(C[c].get("comp") or [])
    rows=[("●" if any(b in k for b in known) else " ")+f"{k}({v})" for k,v in cnt.most_common(TOPN)]
    print(f"## {c} · 시드 경로 {seed} · 이미 잡은 경쟁사 {sorted(known)}")
    print("   "+" · ".join(rows))
