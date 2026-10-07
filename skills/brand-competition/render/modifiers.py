# -*- coding: utf-8 -*-
"""카테고리 연관어의 앞말을 빈도순 후보표로 낸다 — 판정하지 않는다.

 “○○ <카테고리>” 형태에서 앞말(○○)을 뽑아 등장 순서(검색량 순위)대로 줄 세운다.
 브랜드인지 세부 수요인지 잡음인지는 **LLM 이 이 표를 보고 라벨링한다**(SKILL.md 4단계).

 고정 브랜드 사전으로 가르지 않는다. 사전에 없는 브랜드가 조용히 세부 수요 후보로 흘러가고,
 새 업종마다 사전을 손으로 고쳐야 하기 때문이다. 실측에서 britz·blaupunkt(영문 표기) ·
 다이슨 · 닥터드레 · 제스트컴퍼니가 그렇게 세부 수요 후보에 섞였다.

 사용:  python3 modifiers.py <회차> <카테고리> [<카테고리> ...]
 출력:  <회차>/work/mods_<카테고리>.json  ·  화면에 후보표
"""
import json,sys,os
R=sys.argv[1]; CATS=sys.argv[2:]
cfg=json.load(open(f"{R}/config.json"))
OWNV=[a.lower() for a in cfg.get("own",[cfg["brand"]])]
def ns(s): return s.replace(" ","")
os.makedirs(f"{R}/work",exist_ok=True)
for c in CATS:
    f=f"{R}/data/cat/{c}_intent.json"
    if not os.path.exists(f): print("연관어 없음:",c); continue
    kws=json.load(open(f))["data"]
    mods=[]
    for i,k in enumerate(kws):
        if not ns(k).endswith(ns(c)): continue
        m=k[:len(k)-len(c)].strip() if k.endswith(c) else k[:ns(k).rfind(ns(c))].strip()
        if not m or ns(m)==ns(c): continue
        mods.append(dict(rank=i+1,mod=m,kw=k,own=any(a in m.lower() for a in OWNV)))
    json.dump(dict(n=len(kws),cat=c,mods=mods),
              open(f"{R}/work/mods_{c}.json","w"),ensure_ascii=False,indent=1)
    uniq=list(dict.fromkeys(x["mod"] for x in mods))
    print(f"\n## {c} · 연관어 {len(kws)} · 앞말 {len(mods)}개(고유 {len(uniq)})")
    print("   자사 표기:", " · ".join(x["mod"] for x in mods if x["own"])[:200] or "-")
    print("   후보(검색량 순):", " · ".join(uniq[:40]))
