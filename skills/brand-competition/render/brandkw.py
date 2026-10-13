"""5단계 입력 — keyword_info 에 넣을 키워드만 뽑는다(정의 A).
카테고리 연관어 중 브랜드명(자사·경쟁사·별칭)이 들어간 검색어 + 카테고리 대표어.
일반 검색어는 넣지 않는다. 4단계(경쟁사 라벨) 뒤에 돌린다.
사용: python3 brandkw.py <회차> [--chunk 1000] [--skip-done]
     → work/brandkw.json(전체 목록 · 커버리지 기준), work/brandkw_<i>.json(조회할 배치)
--skip-done · 이미 검색량을 받아 둔 키워드를 배치에서 뺀다. 6-b 에서 새 브랜드를 찾아
            목록을 다시 뽑을 때 쓴다 — 앞서 받은 것을 두 번 사지 않는다.

배치마다 `brandkw_<i>.params.json` 도 함께 쓴다 — `keyword_info` 에 보낼 파라미터 그대로다.
그 파일을 `mcp_cache.py` 의 `lookup`/`store --params-file` 과 `fetch_dl.py --params-file` 에
넘기면 **세 곳이 같은 파라미터를 본다** — 손으로 옮겨 적다 한 글자 달라지면 캐시 키가 갈라져
적중하지 않고 크레딧이 두 번 나간다."""
import json,sys,os,glob
R=sys.argv[1]; CH=int(sys.argv[sys.argv.index("--chunk")+1]) if "--chunk" in sys.argv else 1000
SKIP="--skip-done" in sys.argv
ns=lambda k:k.replace(" ","").lower()
cfg=json.load(open(f"{R}/config.json")); OWN=cfg["brand"]
C=json.load(open(f"{R}/work/curate.json")); C.pop("_note",None)
VAR=dict(cfg.get("alias",{})); VAR.setdefault(OWN,cfg.get("own",[OWN])); EXC=cfg.get("alias_exclude",{})
B={OWN}|{b for v in C.values() for b in v.get("comp",[])}|set(cfg.get("watch_brands",[]))
def hit(b,k):
    """judge.py · cep_deep.py 와 **같은 규칙**이다 — 낱말 첫머리에서 시작해야 한다.
    여기가 어긋나면 조회 목록(=분모)과 판정이 서로 다른 집합을 보게 된다."""
    n=ns(k)
    if any(ns(z) in n for z in EXC.get(b,())): return False
    t=k.lower().split()
    if len(b)==1: return b.lower() in t
    tails=["".join(t[i:]) for i in range(len(t))]
    return any(x.startswith(ns(a)) for a in [b]+list(VAR.get(b,[])) if ns(a) for x in tails)
out=[];seen=set();per={}
for c in C:
    f=f"{R}/data/cat/{c}_intent.json"
    if not os.path.exists(f): continue
    ks=[k for k in json.load(open(f))["data"] if any(hit(b,k) for b in B)]
    per[c]=len(ks)
    for k in [c]+ks:
        if k not in seen: seen.add(k); out.append(k)
json.dump(out,open(f"{R}/work/brandkw.json","w"),ensure_ascii=False)

# 이미 받아 둔 검색량 — judge.py 와 같은 자리를 본다
def _rows(f):
    d=json.load(open(f))
    return d if isinstance(d,list) else (d.get("data") or [])
done=set()
for f in sorted(glob.glob(f"{R}/data/cat/*vol*.json"))+sorted(glob.glob(f"{R}/data/sos/*.json")):
    for x in _rows(f):
        if isinstance(x,dict) and x.get("keyword"): done.add(ns(x["keyword"]))
ask=[k for k in out if ns(k) not in done] if SKIP else out

for f in glob.glob(f"{R}/work/brandkw_*.json"): os.remove(f)
GL=cfg.get("gl","kr")
for i in range(0,len(ask),CH):
    b=ask[i:i+CH]; j=i//CH
    json.dump(b,open(f"{R}/work/brandkw_{j}.json","w"),ensure_ascii=False)
    json.dump(dict(keywords=b,gl=GL,data_type="ads_metrics",response_format="download_url"),
              open(f"{R}/work/brandkw_{j}.params.json","w"),ensure_ascii=False)
nb=(len(ask)-1)//CH+1 if ask else 0
msg=f"브랜드 검색어+대표어 {len(out):,}개"
if SKIP: msg+=f" · 이미 받은 것 {len(out)-len(ask):,}개 제외 → 조회 {len(ask):,}개"
print(f"{msg} → {nb}배치 · 카테고리별 {per}")
for j in range(nb): print(f"  brandkw_{j}.json · {len(ask[j*CH:(j+1)*CH]):,}개 · 파라미터 work/brandkw_{j}.params.json")
if SKIP and not ask: print("  더 조회할 키워드가 없다 — 5단계를 건너뛴다")
