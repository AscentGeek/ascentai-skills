# -*- coding: utf-8 -*-
"""회차 폴더 점검 — 무엇이 있고 무엇이 빠졌는지, 다음에 뭘 해야 하는지 찍는다.

 스크립트는 파일만 읽는다. MCP 응답을 파일로 쓰지 않으면 아무것도 돌지 않는다.
 단계를 넘어가기 전에 이걸 돌려서 빠진 것을 먼저 채운다.

 사용:  python3 check_run.py <회차>
"""
import json,os,sys,glob
R=sys.argv[1].rstrip("/")
def has(p): return os.path.exists(p) and os.path.getsize(p)>0
def jl(p):
    try: return len(json.load(open(p))["data"])
    except Exception: return None
ok=True
print(f"회차 · {R}\n")
cfg=f"{R}/config.json"
if not has(cfg): print("✗ config.json 없음 — brand · own 을 적어야 한다"); sys.exit(1)
c=json.load(open(cfg)); OWN=c["brand"]
print(f"✓ config.json · 브랜드 {OWN} · 별칭 {len(c.get('own',[]))}개"
      + (f" · 지정 브랜드 {c['watch_brands']}" if c.get("watch_brands") else "")
      + (f" · 지정 카테고리 {c['watch_categories']}" if c.get("watch_categories") else ""))

# 1단계
b1,b2=f"{R}/data/cat/{OWN}_brand_intent.json",f"{R}/data/cat/{OWN}_brand_path.json"
for p,nm in ((b1,"브랜드 연관어"),(b2,"브랜드 경로")):
    if has(p):
        n=jl(p); print(f"✓ {nm} {n}건" + ("  ⚠ 100건 미만 — 카테고리 발굴이 어렵다" if (n or 0)<100 and nm.endswith("연관어") else ""))
    else: print(f"✗ {nm} 없음 → {p}"); ok=False

# 2·4단계
cu=f"{R}/work/curate.json"
if not has(cu):
    print("✗ work/curate.json 없음 — 2단계(카테고리 세우기)를 먼저 한다"); sys.exit(0 if ok else 1)
C=json.load(open(cu)); C.pop("_note",None)
# 2-b · 범위를 좁혔나
CA=f"{R}/work/candidates.json"
if has(CA):
    cand=json.load(open(CA)); sk=[k for k,v in cand.items() if not v.get("chosen")]
    print(f"✓ 조사 범위 · 후보 {len(cand)}개 중 {len(cand)-len(sk)}개 선택" + (f" · 제외 {len(sk)}개" if sk else ""))
    miss_w=[x for x in (c.get("watch_categories") or []) if x in sk]
    if miss_w: print(f"✗ 지정 카테고리가 제외됐다 → {' · '.join(miss_w)} — 지정은 범위에서 빼지 않는다"); ok=False
elif len(C)>10:
    print(f"  ⚠ 카테고리 {len(C)}개인데 candidates.json 이 없다 — 10개를 넘으면 2-b 에서 사람이 범위를 정한다")
deep=[k for k,v in C.items() if v.get("deep")]
print(f"✓ curate.json · 카테고리 {len(C)}개 · 심층 {len(deep)}개 · 경쟁사 라벨 {sum(1 for v in C.values() if v.get('comp'))}곳")

# 3단계 · 연관어는 전 카테고리 · 경로는 「빈자리」에만 (6-b)
miss=[k for k in C if not has(f"{R}/data/cat/{k}_intent.json")]
done=len(C)-len(miss)
if not miss: print(f"✓ 카테고리 연관어 {done}/{len(C)} 전부 있음")
else:
    # 턴을 나눠 도는 환경에서 그대로 할 일 목록이 된다 — 있는 것을 다시 부르지 않게
    print(f"✗ 카테고리 연관어 {done}/{len(C)} · 남은 {len(miss)}건 → "+" · ".join(miss))
ok &= not miss
# 6-b · judge.json 이 있어야 어디가 빈자리인지 알 수 있다
JP=f"{R}/work/judge.json"
if has(JP):
    J=json.load(open(JP))
    blank=[x["term"] for x in J if x["name"].startswith("없음")]
    nop=[k for k in blank if not has(f"{R}/data/cat/{k}_path.json")]
    if not blank: print("✓ 빈자리 없음 — 경로 조회가 필요한 카테고리가 없다")
    elif nop: print(f"✗ 빈자리 경로 {len(blank)-len(nop)}/{len(blank)}건 → 빠진 곳: {' · '.join(nop[:8])}"); ok=False
    else: print(f"✓ 빈자리 경로 {len(blank)}/{len(blank)}건")
    extra=[k for k in C if has(f"{R}/data/cat/{k}_path.json") and k not in blank]
    if extra: print(f"  ⚠ 빈자리가 아닌데 경로를 부른 곳 {len(extra)}건 — 6-b 는 빈자리에만 부른다 ({' · '.join(extra[:5])})")
else:
    print("· 6-b 빈자리 경로 — judge.py 를 먼저 돌려야 판정된다")
# 사람이 지목한 카테고리가 조용히 빠지지 않았나
wc=[x for x in (c.get("watch_categories") or []) if x not in C]
if wc: print(f"✗ 지정 카테고리가 curate.json 에 없다 → {' · '.join(wc)} — 근거가 없어도 넣는다"); ok=False
# limit 이 섞였나 — 도구마다 기본값이 다르므로 따로 본다 (연관어 1,000 · 경로 300)
def _lims(suf):
    out=set()
    for k in C:
        p=f"{R}/data/cat/{k}_{suf}.json"
        if has(p):
            try: out.add(json.load(open(p))["request_detail"].get("limit"))
            except Exception: pass
    return {x for x in out if x}
nk=set()
for g in (f"{R}/data/cat/*_path.json",f"{R}/data/cep/*_path.json"):
    for pth in glob.glob(g):
        try: nk.add(json.load(open(pth)).get("nodes_kept"))
        except Exception: pass
if any(x for x in nk):
    print(f"  ✗ 경로가 앞 {sorted(x for x in nk if x)[0]}노드로 잘려 있다 — 탐색 축은 **전체 노드**를 세므로 뒤에서 처음 나오는 브랜드가 통째로 빠진다"); ok=False
for suf,nm,dflt in (("intent","연관어",1000),("path","경로",300)):
    lm=_lims(suf)
    if len(lm)>1: print(f"  ⚠ {nm} limit 이 섞여 있다 {sorted(lm)} — 회차 안에서 하나로 통일한다 (기본 {dflt:,})")
    elif lm and dflt not in lm: print(f"  ⚠ {nm} limit 이 {sorted(lm)[0]:,} 다 — 기본값은 {dflt:,} 다")
    if suf=="path":
        for pth in glob.glob(f"{R}/data/cep/*_path.json"):      # 세부 수요 경로도 같은 하한이 걸린다
            try: lm.add(json.load(open(pth))["request_detail"].get("limit"))
            except Exception: pass
        lm={x for x in lm if x}
        if lm and min(lm)<300:
            print(f"  ✗ 경로 limit {min(lm)} — 300 미만은 게이트 하한(6회·15건)이 물려 「보류」가 과하게 늘어난다. 분량이 문제면 세부 수요 개수를 줄이거나 턴을 나눈다"); ok=False

# 5단계 · 검색 점유율은 카테고리 연관어 전체의 검색량이 있어야 한다
sv=glob.glob(f"{R}/data/sos/*.json")+glob.glob(f"{R}/data/cat/*vol*.json")
if sv:
    _kv=set()
    for _f in sv:
        try:
            _d=json.load(open(_f)); _rows=_d if isinstance(_d,list) else (_d.get("data") or [])
            for _r in _rows:
                if isinstance(_r,dict) and _r.get("keyword"): _kv.add(_r["keyword"])
        except Exception: pass
    _bk=f"{R}/work/brandkw.json"
    if has(_bk): _need=set(json.load(open(_bk)))          # 정의 A — 브랜드 검색어 + 대표어만
    else:
        _need=set()
        for k in C:
            _f=f"{R}/data/cat/{k}_intent.json"
            if has(_f): _need|=set(json.load(open(_f))["data"])
    _miss=_need-_kv
    if _need:
        cov=(len(_need)-len(_miss))/len(_need)*100
        print(f"{'✓' if cov>=95 else '✗'} 연관어 검색량 커버리지 {cov:.0f}% ({len(_need)-len(_miss):,}/{len(_need):,}) — 브랜드 검색어(+대표어) 기준 · 검색 점유율의 분모다")
        ok &= cov>=95
v=glob.glob(f"{R}/data/cat/*vol*.json")+glob.glob(f"{R}/data/sos/*.json")
print(f"{'✓' if v else '✗'} 검색량 응답 {len(v)}건" + ("" if v else " — *vol*.json 이름으로 저장한다")); ok &= bool(v)

# 8단계
if deep:
    need=[(k,p) for k in deep for p in (C[k].get("cep") or [])]
    got=[(k,p) for k,p in need if has(f"{R}/data/cep/{p} {k}_path.json")]
    print(f"{'✓' if len(got)==len(need) else '✗'} 세부 수요 심층 경로 {len(got)}/{len(need)}건"
          + ("" if len(got)==len(need) else " → "+" · ".join(f"{p} {k}" for k,p in need if (k,p) not in got)[:120]))
    ok &= (len(got)==len(need))     # 이게 빠져 있어서 세부 수요가 비어도 「렌더」로 안내했다
else:
    print("✗ 심층 대상이 아직 없다 — 7단계에서 사람이 3~5개를 고른 뒤 8단계로 간다"); ok=False

print("\n다음 단계 · " + ("판정(judge.py → cep_deep.py) 후 렌더" if ok else "위의 ✗ 를 먼저 채운다 — 응답을 파일로 쓰지 않으면 스크립트가 돌지 않는다"))
if not ok: print("           턴을 나눠 돌고 있으면 이 목록이 그대로 할 일이다 — 이미 ✓ 인 것은 다시 부르지 않는다")
