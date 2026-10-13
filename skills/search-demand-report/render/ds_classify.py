#!/usr/bin/env python3
"""ds_classify.py · references/keyword-method.md (method-v4) 를 코드로 적용한다.

  check   : seed.json + intent_finder(시드) → 시드 적합성(주제형 · 넓은 시드) + 모드 판정(연관 검색어 구성) · 질문·좁히기 필요 시 exit 10
            kind = topic · broad · brandwide · mode (broad·brandwide → references/scope.md)
            통과하면 seed.json 의 modeReason · composition 을 코드가 채운다
  propose : seed.json + finder 원자료 → classify.json + classify.md
            1 시장 흐름 비교군 · 분석 대상 유사의도 · 2 내부 동향 후보를 규칙대로 낸다. LLM 은 classify.md 를 읽고 picks.json 을 쓴다.
  plan    : picks.json → plan.json (분석 대상 대표 표기 · 커버 검사용 상세 묶음 · 비교군 · 내부 라인 또는 의도 묶음)

seed.json:
  {"seed": "나이키 러닝화", "gl": "kr", "mode": "entity", "brand": ["나이키", "nike"], "item": ["러닝화"],
   "upper": "러닝화", "heads": ["화", "운동화"]}
  gl = 시장 (kr · jp · us) · 분류 사전이 시장마다 다르다 (ds_market.py · method-v5.12) · 없으면 kr
  upper = 01 비교군 · 분석 대상 유사의도 finder 입력 (entity: 대상 카테고리 · category: 상위 대분류)
picks.json:
  {"synonyms": {"pick": ["런닝화", "러닝 슈즈"], "analyst": ["달리기 신발"], "skip": {"테니스화": "M3a 다른 품목"}},
   "external": {"pick": ["아디다스", {"name": "온러닝", "variants": ["온러닝", "on"]}], "skip": {"여성": "M5-1"}},
   "internal": {"pick": ["페가수스", {"name": "줌플라이", "variants": ["줌플라이", "줌 플라이"]}], "skip": {}}}
  category 의 internal: {"pick": [브랜드…], "topics": [{"name": "쿠션", "variants": ["쿠션"]}], "skip": {}}

표준 라이브러리만 사용한다.
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ds_common as C  # noqa: E402

METHOD = "method-v5.12"
CAP = None        # method-v2: 묶음을 자르지 않는다
MOD_MAX = 2       # M3·M6: 품목 일반어(운동화·신발·런 등) 최대 개수
ALLOWED = {"generic"}  # method-v3: 묶음은 같은 대상을 부르는 말만 — 탐색·속성 수식어는 넣지 않는다

# M2 수식어 사전 · 시장(gl)마다 한 벌 (ds_market.py) · 바꾸면 METHOD 버전을 올린다
#   set_market(gl) 이 아래 전역(DICT · RX · WORD · INTENT_BUNDLES · FIT 의 단어 목록 · CMP_WORDS)을 그 시장 것으로 바꾼다.
import ds_market as MK  # noqa: E402

MARKET = MK.get("kr")
DICT, RX, WORD = {}, [], {}
BAD = {"use", "howto", "channel", "community", "info", "year"}
SHOE_GENERIC = []
CMP_WORDS = []  # M5-0 비교 언급 단어 · set_market 이 채운다


def configure(seed, picks=None):
    """method-v5 · 품목 일반어와 '같은 의도 표현'을 시드마다 정한다.
    - seed.generic 이 있으면 그 목록이 품목 일반어다 (없으면 기존 신발 일반어 · 러닝화 등 신발 시드 호환).
      필라테스처럼 신발이 아닌 시드에 '신발·슈즈·러닝'이 일반어로 붙어 타겟에 섞이는 것을 막는다.
    - picks.synonyms.intent = 시드와 함께 쓰여 '같은 의도'(시드를 찾는 사람)의 검색이 되는 표현 (필라테스 학원 · 수업 · 스튜디오).
      이 표현은 1·2 묶음에서 품목 일반어처럼 허용된다 (1 비교군에도 같은 규칙 · M6)."""
    gen = seed.get("generic")
    if gen is not None:
        for w in SHOE_GENERIC:
            if WORD.get(w) == "generic":
                del WORD[w]
        DICT["generic"] = list(gen)
        for w in gen:
            WORD[w] = "generic"
    sy = (picks or {}).get("synonyms") or {}
    for w in sy.get("intent") or []:
        for piece in norm(w).split(" "):
            WORD[piece] = "generic"
            if piece not in DICT["generic"]:
                DICT["generic"].append(piece)

# method-v4 · 02 내부 동향 카테고리 모드 = 의도 묶음. 한 검색어는 한 묶음에만 들어간다 (순서 = 우선순위):
#   브랜드·모델 탐색(02 에서 고른 브랜드) → 토픽(02 에서 고른 성분·맛·특징) → 아래 고정 의도 → 어디에도 없으면 넣지 않는다
INTENT_BUNDLES = []  # set_market 이 채운다 · (묶음 이름, 단어 목록) 순서 = 우선순위
BRAND_BUNDLE = "브랜드·모델 검색"  # picks.internal.pick 을 쓸 때만 (v5 기본은 catchall 의 브랜드명 검색)
# 02 브랜드/제품 모드: 브랜드명이 없는 표기('페가수스 41')는 시드 쪽 intent 결과에서 나온 것만 같은 SKU 로 합산한다
OWN_SRC = {"intent:seed", "intent:internal", "intent:sku", "intent:brand"}


KNOWN = set()  # 원자료에서 띄어 쓴 조각으로 등장한 말 (붙여 쓴 앞말 판정용) · load_sources 가 채운다


class BoundRe:
    """브랜드·제품명용 검색: 다른 단어 안에 든 경우는 맞추지 않는다 (러닝화 실측: '슬립온'의 '온', 'saucony'의 'on').
    붙여 쓴 경우는 앞말이 원자료에서 따로 쓰이는 말일 때만 인정한다 ('쿠쿠에그밥솥'의 '쿠쿠', '줌보메로'의 '줌')."""

    def __init__(self, rx):
        self.rx = rx

    def search(self, t):
        for m in self.rx.finditer(t):
            st = m.start()
            if st == 0 or t[st - 1] == " ":
                return m
            ws = t.rfind(" ", 0, st) + 1
            if t[ws:st] in KNOWN:
                return m
        return None


def kw_re(variants, bound=False):
    """띄어쓰기를 무시하고 변형 중 하나에 맞는 정규식 (긴 것 먼저). bound=True 는 브랜드·제품명 (BoundRe)."""
    alts = []
    for v in sorted(set(variants), key=len, reverse=True):
        core = re.sub(r"\s+", "", v.lower())
        if core:
            a = r"\s*".join(re.escape(ch) for ch in core)
            if bound and re.fullmatch(r"[a-z0-9]+", core):
                a = r"(?<![a-z0-9])" + a + r"(?![a-z0-9])"
            alts.append(a)
    if not alts:
        return None
    rx = re.compile("|".join(alts))
    return BoundRe(rx) if bound else rx


def norm(s):
    return re.sub(r"\s+", " ", str(s).lower()).strip()


def strip_parts(s, regexes):
    """regexes 를 차례로 한 번씩 지운다. 하나라도 없으면 None. 남은 말을 조각 목록으로."""
    t = norm(s)
    for rx in regexes:
        m = rx.search(t) if rx else None
        if not m:
            return None
        t = (t[:m.start()] + " " + t[m.end():]).strip()
    return [p for p in re.split(r"\s+", t) if p]


def kind(piece):
    if piece in WORD:
        return WORD[piece]
    for k, rx in RX:
        if rx.match(piece):
            return k
    if re.search(MARKET["foreign"], piece):
        return "info"  # 다른 시장 문자가 섞인 오입력 검색어 (kr: 가나 · jp: 한글 · us: 한글·가나·한자)
    sub = MARKET["substr"]
    for k in ("community", "use", "explore"):  # 붙여 쓴 경우 ('4디시', '3사이즈'는 attr 로 아래에서) · us 는 단어 단위(복수형 포함)
        if MK.word_in(piece, DICT[k], sub):
            return k
    if sub and any(w in piece for w in MARKET["attrSub"]):
        return "attr"
    if not sub and MK.word_in(piece, DICT["attr"], False):
        return "attr"
    return "residual"


def classes(pieces):
    return [kind(p) for p in pieces]


def is_bundle_member(s, regexes):
    """M3/M6 (method-v3): 필수 성분(regexes) + 품목 일반어 0~2 개만으로 이루어졌는가 (같은 대상을 부르는 말만)."""
    ps = strip_parts(s, regexes)
    if ps is None:
        return False
    ks = classes(ps)
    return all(k in ALLOWED for k in ks) and len(ks) <= MOD_MAX


# ───────────────────────── 원자료 ─────────────────────────

# method-v5.11 · 1 시장 동향 비교군 '가까움' 판정 (category) — 하나라도 넘으면 가까운 시장
NEAR = {"seedMin": 2,   # 시드 cluster 등장 N (시드와 함께 검색된 노드 수)
        "coMin": 2,     # 함께 언급 N (시드 품목과 후보가 한 검색어에)
        "cmpMin": 1,    # 비교 언급 N (차이·비교·vs·대신)
        "want": 4}      # 가까움 후보가 이 수 미만이면 M5-0 (LLM 대체·인접 후보 → lm_intent_near.json)

SEED_NODES = []  # method-v5.10 · 시드 cluster(lm_cluster_seed.json) 노드 — 1 시장 동향 비교군 후보의 1순위 근거 (category)


def cluster_nodes_of(path):
    comm, rels = C.cluster_parts(C.load_json(path))
    nodes = []
    for a, b in rels:
        nodes += [a, b]
    for v in comm.values():
        nodes += list(v)
    return list(dict.fromkeys(nodes))


def load_sources(intent_files, cluster_file, seed_cluster_file=None):
    """문자열 → {src, rank}. rank = 각 intent 파일 안의 순서(검색량 순). cluster 는 rank 없음.
    method-v5.10 · seed_cluster_file = 시드 자체의 cluster (함께 검색된 다른 품목 = 비교군 1순위 근거)."""
    info = {}
    if seed_cluster_file and Path(seed_cluster_file).exists():
        SEED_NODES[:] = cluster_nodes_of(seed_cluster_file)
        for s in SEED_NODES:
            KNOWN.update(norm(s).split(" "))
            info.setdefault(s, {"src": set(), "rank": 10 ** 6})["src"].add("cluster")
    for f in sorted(intent_files):  # 입력 순서와 관계없이 같은 결과가 나오도록
        name = Path(f).stem.replace("lm_intent_", "")
        for i, s in enumerate(C.intent_strings(C.load_json(f))):
            KNOWN.update(norm(s).split(" "))
            r = info.setdefault(s, {"src": set(), "rank": 10 ** 6})
            r["src"].add("intent:" + name)
            r["rank"] = min(r["rank"], i)
    if cluster_file and Path(cluster_file).exists():
        comm, rels = C.cluster_parts(C.load_json(cluster_file))
        for a, b in rels:
            KNOWN.update(norm(a).split(" "))
            KNOWN.update(norm(b).split(" "))
        for a, b in rels:
            for s in (a, b):
                info.setdefault(s, {"src": set(), "rank": 10 ** 6})["src"].add("cluster")
        for v in comm.values():
            for s in v:
                info.setdefault(s, {"src": set(), "rank": 10 ** 6})["src"].add("cluster")
    return info


def src_tag(srcs):
    """cluster > intent > analyst. lm_intent_analyst*.json 은 LLM 이 finder 후보 밖에서 떠올린 이름으로 조회한 결과다 (M5-4)."""
    if "cluster" in srcs:
        return "cluster"
    if any(x.startswith("intent:") and not x.startswith("intent:analyst") for x in srcs):
        return "intent"
    return "analyst"


# ───────────────────────── propose ─────────────────────────

def propose(seed, info):
    mode = seed["mode"]
    B = kw_re(seed.get("brand") or [], bound=True) if mode == "entity" else None
    I = kw_re(seed["item"])
    req = [B, I] if mode == "entity" else [I]
    strings = sorted(info, key=lambda s: info[s]["rank"])
    opt = bool(seed.get("itemOptional")) and mode == "entity"  # 시드가 브랜드 단독(bhc)이면 '브랜드 + (품목)' 모두 유사어
    target = [s for s in strings if is_bundle_member(s, req) or (opt and is_bundle_member(s, [B]))]

    # 브랜드 후보 (entity 01 비교군 · category 02 내부): I* 와 잔여어 1개, 나머지는 사전어
    brand_c = defaultdict(lambda: {"n": 0, "rank": 10 ** 6, "cluster": False, "srcs": set(), "ex": []})
    for s in strings:
        if B and B.search(norm(s)):
            continue
        ps = strip_parts(s, [I])
        if ps is None:
            continue
        res = [p for p in ps if kind(p) == "residual"]
        if len(res) != 1 or any(k in BAD for k in classes(ps)):
            continue
        # 브랜드는 품목 앞에 온다 ('아디다스 러닝화'). 품목 뒤에만 붙는 말('전기압력밥솥 삼계탕')은 브랜드 근거가 아니다
        m = I.search(norm(s))
        before = norm(s)[:m.start()].replace(" ", "")
        if res[0] not in before:
            continue
        c = brand_c[res[0]]
        c["n"] += 1
        c["rank"] = min(c["rank"], info[s]["rank"])
        c["cluster"] |= "cluster" in info[s]["src"]
        c["srcs"] |= info[s]["src"]
        if len(c["ex"]) < 3:
            c["ex"].append(s)
    for c in brand_c.values():
        c["src"] = src_tag(c.pop("srcs"))

    def order(kv):  # 순위가 있는 후보(검색량 확인) 먼저 · 그 안에서 cluster 먼저 · 등장 순위 · 등장 횟수
        v = kv[1]
        return (v["rank"] >= 10 ** 6, v["src"] != "cluster", v["rank"], -v["n"])

    out = {"method": METHOD, "seed": seed, "target": target}
    # M3a · 01 유사의도(품목 동의어) 후보: 상위어 cluster·intent 에서 브랜드·사전어 없이 품목 이름만으로 된 검색어 (1~2 조각)
    #   LLM 이 이 목록에서 시드 품목과 같은 물건의 다른 이름만 고른다 (picks.synonyms) · cluster 가 없으면 LLM 후보(analyst)를 keyword_info 로 검증
    syn = defaultdict(lambda: {"rank": 10 ** 6, "srcs": set(), "n": 0})
    sibs = {norm(x).replace(" ", "") for x in (seed.get("scope") or {}).get("siblings") or []}
    for s in strings:
        t = norm(s)
        if I.search(t) or (B and B.search(t)):
            continue
        if any(x and x in t.replace(" ", "") for x in sibs):
            continue  # scope 의 다른 후보가 든 검색어는 동의어 후보가 아니다 (조말론 향수 · 마스크 팩)
        ps = t.split(" ")
        if len(ps) > 2 or any(kind(p) not in ("residual", "generic") for p in ps) or (len(ps) == 1 and kind(ps[0]) == "generic"):
            continue
        c = syn[t]
        c["brandish"] = any(p in brand_c for p in ps)  # 품목 앞에 붙은 적 있음 — 브랜드일 수도, '썬크림 선크림'처럼 동의어일 수도 (LLM 판단)
        c["rank"] = min(c["rank"], info[s]["rank"])
        c["srcs"] |= info[s]["src"]
        c["n"] += 1
    # method-v5 · 같은 의도 표현 후보: 시드 품목 + 잔여어 한 조각 ('필라테스 학원' · '근처 필라테스') — LLM 이 시드를 찾는 사람의 표현만 고른다
    sint = defaultdict(lambda: {"rank": 10 ** 6, "n": 0, "ex": []})
    for s in strings:
        ps = strip_parts(s, [I])
        if ps is None or not ps or len(ps) > 2:
            continue
        if any(kind(p) in ("generic",) for p in ps) and all(kind(p) == "generic" for p in ps):
            continue
        key = " ".join(ps)
        c = sint[key]
        c["rank"] = min(c["rank"], info[s]["rank"])
        c["n"] += 1
        if len(c["ex"]) < 2:
            c["ex"].append(s)
    out["intentExpr"] = sorted(({"name": k, **v} for k, v in sint.items()), key=lambda c: c["rank"])
    out["synonyms"] = sorted(({"name": k, "src": src_tag(v["srcs"]), "rank": v["rank"], "brandish": v.get("brandish", False)} for k, v in syn.items()),
                             key=lambda c: (c["src"] != "cluster", c["rank"]))
    if mode == "entity":
        ext_c = sorted(brand_c.items(), key=order)
        # 제품 명칭 후보: B* 와 함께 나온 잔여어 (2회 이상)
        prod = defaultdict(lambda: {"n": 0, "rank": 10 ** 6, "ex": [], "withItem": 0})
        for s in strings:
            t = norm(s)
            if not B.search(t):
                continue
            ps = strip_parts(s, [B])
            ps2 = strip_parts(" ".join(ps), [I]) if ps is not None else None
            ps = ps2 if ps2 is not None else ps
            if not ps or any(k in BAD for k in classes(ps)):
                continue
            has_item = bool(I.search(t)) or bool(seed.get("itemOptional"))
            for p in ps:
                if kind(p) == "residual" and len(p) >= 2:
                    c = prod[p]
                    c["n"] += 1
                    c["withItem"] += has_item
                    c["rank"] = min(c["rank"], info[s]["rank"])
                    if len(c["ex"]) < 3:
                        c["ex"].append(s)
        # 시드 품목과 한 번 이상 함께 검색된 이름만 (쿠쿠 정수기처럼 다른 품목 라인은 뺀다 · M7)
        out["internal"] = [{"name": k, **v} for k, v in sorted(prod.items(), key=lambda kv: (-kv[1]["n"], kv[1]["rank"]))
                           if v["n"] >= 2 and v["withItem"] >= 1]
        # 같은 이름이 양쪽에 잡히면 더 많이 나온 쪽으로 보낸다:
        # '러닝화 페가수스'(브랜드 자리) 3회 < '나이키 페가수스'(시드 브랜드와 함께) 370회 → 내부
        # '아디다스 러닝화' 14회 > '나이키 아디다스 러닝화' 5회 → 외부
        own_n = {c["name"]: c["n"] for c in out["internal"]}
        bn = {k: v["n"] for k, v in brand_c.items()}
        out["external"] = [{"name": k, **v} for k, v in ext_c if own_n.get(k, 0) <= v["n"]]
        out["internal"] = [c for c in out["internal"] if bn.get(c["name"], 0) < c["n"]]
    else:
        # 형제 품목 후보: H 로 끝나고, I* 가 없고, explore 를 뺀 나머지가 사전어 없는 1~2 조각
        H = [h.lower() for h in seed.get("heads") or []]
        sib = defaultdict(lambda: {"rank": 10 ** 6, "cluster": False, "srcs": set(), "ex": [], "n": 0})
        for s in strings:
            t = norm(s)
            if I.search(t):
                continue
            ps = [p for p in t.split(" ") if kind(p) != "explore"]
            if not ps or len(ps) > 2 or any(kind(p) != "residual" for p in ps):
                continue
            name = " ".join(ps)
            core = name.replace(" ", "")
            if not any(core.endswith(h) and core != h for h in H):
                continue
            c = sib[core]
            c["name"] = c.get("name") or name
            c["rank"] = min(c["rank"], info[s]["rank"])
            c["cluster"] |= "cluster" in info[s]["src"]
            c["srcs"] |= info[s]["src"]
            c["n"] += 1
            if len(c["ex"]) < 3:
                c["ex"].append(s)
        # scope-v1 · 넓은 시드에서 좁혀 왔으면 같은 영역의 나머지 후보(부적합 제외)가 1 시장 동향 비교군 후보다
        #   scope 단계에서 intent_finder·keyword_info 로 검증됐다 (lm_intent_scope.json) · 출처 intent
        for i, name in enumerate((seed.get("scope") or {}).get("siblings") or []):
            core = norm(name).replace(" ", "")
            if core in sib:
                continue
            ex = [x for x in strings if norm(x).replace(" ", "") == core]
            sib[core] = {"name": name, "rank": info[ex[0]]["rank"] if ex else 10 ** 6, "srcs": {"intent:scope"},
                         "ex": ex[:1] or [name], "n": 1, "cluster": False}
        # method-v5.10 · 시드 cluster 후보 (1순위): 시드와 함께 검색된 노드 중 시드 품목이 없는 것에서, 사전어·브랜드를 뺀 이름 조각.
        #   '시드 cluster 등장 N' = 그 이름이 찾는 대상 자리(마지막 조각)에 온 노드 수 (시드와 함께 검색된 정도). 2회 이상만.
        #   상위어 cluster 는 상위어가 다른 뜻과 섞이면(상의 → 상의하다) 비어 버린다 — 시드 cluster 는 그 문제가 없다.
        sc = defaultdict(lambda: {"n": 0, "ex": []})
        for s in SEED_NODES:
            t = norm(s)
            if I.search(t):
                continue
            # 찾는 대상 자리(사전어를 뺀 마지막 조각)만 센다 — '나이키 맨투맨 회색' → 맨투맨 (브랜드·수식어는 앞에 온다)
            res = [p for p in t.split(" ") if kind(p) == "residual"]
            if not res:
                continue
            p = res[-1]
            if len(p) < 2 or re.fullmatch(r"[\d.a-z]{1,3}", p):
                continue
            c = sc[p]
            c["n"] += 1
            if len(c["ex"]) < 3:
                c["ex"].append(s)
        for p, v in sc.items():
            if v["n"] < 2:
                continue
            core = p.replace(" ", "")
            if core in sib:
                sib[core]["srcs"].add("cluster")
                sib[core]["cluster"] = True
                sib[core]["seedN"] = v["n"]
                continue
            ex = [x for x in strings if norm(x).replace(" ", "") == core]
            sib[core] = {"name": p, "rank": info[ex[0]]["rank"] if ex else 10 ** 6, "srcs": {"cluster"},
                         "ex": v["ex"], "n": v["n"], "cluster": True, "seedN": v["n"]}
        # method-v5.11 · 가까운 시장 후보 (M5-0) — LLM 이 seed.json near 에 적은 대체·인접 품목 (향수 → 바디미스트 · 고체향수)
        #   intent_finder(lm_intent_near.json)로 조회한 결과에 이름이 있으면 출처 intent, 없으면 analyst.
        for nc in seed.get("near") or []:
            nc = nc if isinstance(nc, dict) else {"name": nc}
            core = norm(nc["name"]).replace(" ", "")
            vs = [norm(v).replace(" ", "") for v in (nc.get("variants") or [nc["name"]])]
            def _rest(x):  # 후보 이름을 지운 나머지 (섬유향수처럼 시드 품목 글자를 품은 이름도 다룬다)
                r = norm(x).replace(" ", "")
                for v in sorted(vs, key=len, reverse=True):
                    r = r.replace(v, "#")
                return r
            ex = [x for x in strings if "#" in _rest(x) and not I.search(_rest(x))]
            c = sib.get(core) or {"name": nc["name"], "rank": 10 ** 6, "srcs": set(), "ex": [], "n": 0, "cluster": False}
            c["srcs"] |= ({"intent:near"} if ex else {"analyst"})
            if ex:
                c["rank"] = min(c["rank"], min(info[x]["rank"] for x in ex))
                c["ex"] = c["ex"] or ex[:3]
            c["nearWhy"] = nc.get("why") or ""
            c["nearVariants"] = vs
            sib[core] = c
        # method-v5.11 · 근접 근거 — '같은 영역'(뷰티 안의 샴푸)이 아니라 '같은 수요를 두고 함께 찾는 시장'인지 데이터로 본다.
        #   함께 언급 N = 시드 품목과 후보 이름이 한 검색어에 같이 든 수 (바디미스트 향수 차이 · 향수 대신 바디미스트)
        #   비교 언급 N = 그중 차이·비교·vs·대신 같은 말이 붙은 수 (대체재의 가장 강한 근거)
        CMP = CMP_WORDS  # 시장별 (ds_market · kr: 차이 · 비교 · vs · 대신 …)
        item_cores = {norm(v).replace(" ", "") for v in seed["item"]}
        for core, c in sib.items():
            vs = c.get("nearVariants") or [core]
            co = cmp_ = 0
            for s in strings:
                t = norm(s)
                rest = t.replace(" ", "")
                for v in sorted(vs, key=len, reverse=True):
                    rest = rest.replace(v, "#")
                if "#" not in rest or not any(ic in rest for ic in item_cores):
                    continue  # 후보 이름과 시드 품목이 한 검색어에 따로 들어 있어야 한다
                co += 1
                cmp_ += MK.text_has(t, CMP, MARKET["substr"])
            c["coN"], c["cmpN"] = co, cmp_
            sp = "intent:scope" in c["srcs"]
            if c.get("seedN", 0) >= NEAR["seedMin"] or co >= NEAR["coMin"] or cmp_ >= NEAR["cmpMin"]:
                c["near"] = "가까움"
            elif sp:
                c["near"] = "영역만"  # 넓은 시드 좁히기에서 넘어온 같은 영역 후보 · 함께 찾은 근거 없음 (뷰티 → 샴푸)
            else:
                c["near"] = "근거 약함"
        for c in sib.values():
            c["src"] = src_tag(c.pop("srcs"))
            c.setdefault("seedN", 0)
            c.pop("nearVariants", None)
        # 브랜드가 앞에 붙은 것(쿠쿠 압력밥솥)은 형제 품목이 아니다: 02 브랜드 후보이거나, 앞말이 2개 이상의 다른 품목 앞에 붙는 경우
        firsts = defaultdict(set)
        for core, v in sib.items():
            ps = v["name"].split(" ")
            if len(ps) == 2:
                firsts[ps[0]].add(ps[1])
        brandish = {k for k in brand_c} | {f for f, items in firsts.items() if len(items) >= 2}
        # method-v5.11 · 정렬 = 가까움 먼저 (근거 수 많은 순) → 근거 약함 → 영역만 (같은 영역이라는 것만으로는 비교 시장이 아니다)
        NR = {"가까움": 0, "근거 약함": 1, "영역만": 2}
        out["external"] = [{**v} for _, v in sorted(sib.items(), key=lambda kv: (NR[kv[1]["near"]], -(kv[1]["seedN"] + kv[1]["coN"]),) + order(kv))
                           if not (len(v["name"].split(" ")) == 2 and v["name"].split(" ")[0] in brandish)]
        out["internal"] = [{"name": k, **v} for k, v in sorted(brand_c.items(), key=order)]
        # 02 토픽 후보 (method-v4): 품목과 함께 나온 속성·잔여어 (성분·맛·특징) · 2회 이상 · 브랜드 후보 제외
        topic = defaultdict(lambda: {"n": 0, "rank": 10 ** 6, "ex": []})
        for s in strings:
            ps = strip_parts(s, [I])
            if not ps or any(k in BAD for k in classes(ps)):
                continue
            for p in ps:
                if (kind(p) in ("attr", "residual") and p not in brand_c and len(p) >= 2 and not re.fullmatch(r"[\d.]+", p)
                        and not any(p in ws for _, ws in INTENT_BUNDLES)):
                    c = topic[p]
                    c["n"] += 1
                    c["rank"] = min(c["rank"], info[s]["rank"])
                    if len(c["ex"]) < 3:
                        c["ex"].append(s)
        out["topics"] = [{"name": k, **v} for k, v in sorted(topic.items(), key=lambda kv: (-kv[1]["n"], kv[1]["rank"])) if v["n"] >= 2]
    out["extSynonyms"] = ext_synonym_candidates(out, brand_c, strings, info, mode, seed, B)
    return out


ASCII = re.compile(r"^[a-z][a-z0-9 .&'-]*$")


def ext_synonym_candidates(out, brand_c, strings, info, mode, seed, B):
    """method-v5.2 · M5a 비교 대상별 유사의도(같은 이름의 다른 표기) 후보 — 타겟의 M3a 와 같은 판단을 비교 대상마다 한다.
    후보 풀 = finder 결과에서 '이름 자리'에 오는 말 (entity: 품목 앞 브랜드 자리 · category: 품목 이름만으로 된 검색어).
    - 이름이 서로 포함되는 것(호카 ⊂ 호카오네오네 · 뉴발 ⊂ 뉴발란스 · 홈트 ⊂ 홈트레이닝) → 그 비교 대상의 후보로 붙인다
    - 영문 표기(hoka · adidas · yoga) → 어느 대상인지 코드가 알 수 없어 공통 풀로 보이고 LLM 이 대상마다 고른다
    LLM 은 이 후보 안에서 고르고(picks.external.pick[].synonyms.pick), 후보에 없는 표기는 analyst 로 적어 keyword_info 로 검증한다."""
    names = [c["name"] for c in out.get("external") or []][:40]
    if mode == "entity":
        # 브랜드 자리 후보를 시드 품목뿐 아니라 품목 동의어 후보(러닝화 · 조깅화 — 대분류 머리말로 끝나는 이름) 앞에서도 찾는다.
        #   propose 는 M3a 전에 돌아 I* 가 시드 품목뿐이라, 'hoka 러닝화' 처럼 동의어 표기로만 나온 영문 표기를 놓쳤다 (실측).
        H = [h.lower() for h in seed.get("heads") or []]
        items2 = list(seed["item"]) + [c["name"] for c in out.get("synonyms") or []
                                         if " " not in c["name"] and any(c["name"].endswith(h) for h in H)]
        I2 = kw_re(items2)
        pool = {k: {"rank": v["rank"], "src": v["src"], "ex": v["ex"][:2]} for k, v in brand_c.items()}
        for x in strings:
            t = norm(x)
            if B and B.search(t):
                continue
            m = I2.search(t)
            if not m:
                continue
            head = [w for w in norm(t[:m.start()]).split(" ") if w]
            tail = norm(t[m.end():]).strip()
            if not head or tail or len(head) > 2 or any(kind(w) != "residual" for w in head):
                continue
            k = " ".join(head)
            c = pool.setdefault(k, {"rank": 10 ** 6, "src": src_tag(info[x]["src"]), "ex": []})
            c["rank"] = min(c["rank"], info[x]["rank"])
            if len(c["ex"]) < 2:
                c["ex"].append(x)
    else:
        pool = {c["name"]: {"rank": c["rank"], "src": c["src"], "ex": []} for c in out.get("synonyms") or []}
        for c in out.get("external") or []:
            pool.setdefault(c["name"], {"rank": c["rank"], "src": c["src"], "ex": c.get("ex", [])[:2]})
    per = {}
    for n in names:
        k = norm(n).replace(" ", "")
        joined = {norm(x).replace(" ", "") for x in pool if " " not in norm(x)}
        m = []
        for x in pool:
            xk = norm(x).replace(" ", "")
            if x == n or len(xk) < 2 or len(k) < 2 or not (k in xk or xk in k):
                continue
            # 한 단어 표기(호카오네오네 · 뉴발)이거나, 띄어 쓴 표기가 붙여 쓴 한 단어로도 나온 것(호카 오네오네)만 —
            #   '아디다스 제로'처럼 이름 + 제품명은 다른 표기가 아니다
            if " " in norm(x) and xk not in joined:
                continue
            m.append(x)
        per[n] = sorted(m, key=lambda x: pool[x]["rank"])[:10]
    # 영문 표기 풀 · us 는 모든 표기가 영문이라 따로 보이지 않는다 (method-v5.12)
    latin = sorted((x for x in pool if ASCII.match(norm(x)) and len(x) >= 2), key=lambda x: pool[x]["rank"]) if MARKET["latin"] else []
    return {"per": per, "latin": latin, "pool": {x: pool[x] for x in set(sum(per.values(), [])) | set(latin)}}


def write_md(P):
    s = P["seed"]
    o = [f"# classify · {s['seed']} · mode={s['mode']} · {METHOD}",
         "규칙은 references/keyword-method.md. [선택] 은 M3a(유사의도) · M5(시장 동향 비교군) · M8(내부) 세 곳뿐이다. 고른 결과와 뺀 이유(규칙 번호)를 picks.json 에 쓴다.", "",
         f"## [1 분석 대상] (M3 · 시드 품목 기준 · 유사의도 선택 전 {len(P['target'])}개 · plan 에서 동의어까지 넓힌다 · 커버 검사용 상세 묶음)", " · ".join(P["target"][:60]) + (" …" if len(P["target"]) > 60 else ""), "",
         "## [1 시장 흐름] 비교군 후보 (M4 → M5 로 고른다 · 시드 cluster 등장 많은 순 → 출처 cluster → intent → analyst · rank = finder 등장 순위, 작을수록 검색량 큼)"]
    if s["mode"] == "category":
        nseed = sum(1 for c in P["external"] if c.get("seedN"))
        o.append(f"(method-v5.10 · 시드 cluster 후보 {nseed}개 — " + ("lm_cluster_seed.json 이 없다: 시드로 cluster_finder 를 먼저 부른다 (workflow Step 2)" if not SEED_NODES
                 else "M5-1 같은 위치·같은 수준만 고른다 · 브랜드·속성·다른 뜻(시드의 한 종류·상위어)은 skip") + ")")
    if s["mode"] == "category":
        nn = sum(1 for c in P["external"] if c.get("near") == "가까움")
        o.append(f"(method-v5.11 · 근접 판정: 가까움 {nn}개 = 시드 cluster 등장 ≥ {NEAR['seedMin']} · 함께 언급 ≥ {NEAR['coMin']} · 비교 언급 ≥ {NEAR['cmpMin']} 중 하나. "
                 "'영역만' = 넓은 시드 좁히기에서 넘어온 같은 영역 후보일 뿐 함께 찾은 근거가 없다 — 가까움이 모자랄 때만, 고르면 사용자에게 확인)")
        if nn < NEAR["want"]:
            o.append(f"⚠ 가까움 후보 {nn}개 < {NEAR['want']} — M5-0: 시드의 대체재(같은 목적 · 다른 형태)·인접재(같은 상황에서 함께 고르는 것)를 seed.json near 에 적고, "
                     "intent_finder 로 한 번에 조회해 lm_intent_near.json 으로 받은 뒤 propose 를 다시 돌린다")
    for c in P["external"][:40]:
        rk = "검색량 미확인" if c["rank"] >= 10 ** 6 else f"rank {c['rank']}"
        sn = f" · 시드 cluster 등장 {c['seedN']}" if c.get("seedN") else ""
        nr = ""
        if c.get("near"):
            nr = f" · [{c['near']}] 함께 언급 {c.get('coN', 0)} · 비교 언급 {c.get('cmpN', 0)}" + (f" · LLM 근거: {c['nearWhy']}" if c.get("nearWhy") else "")
        o.append(f"- {c['name']}{sn}{nr} · {c['src']} · {rk} · 예: {' / '.join(c['ex'])}")
    es = P.get("extSynonyms") or {}
    if es:
        o += ["", "## [1 시장 동향] 비교 대상별 유사의도 후보 (M5a · 고른 비교 대상마다 picks.external.pick[].synonyms 에 pick/analyst/skip — 비워 둘 수 없다)",
              "타겟의 M3a 와 같다: 같은 대상의 다른 이름(영문·줄임·풀네임·띄어쓰기)만 고른다. 제품명·속성·다른 대상은 skip 에 규칙 번호와 함께."]
        for n, xs in (es.get("per") or {}).items():
            rows = [f"{x} ({es['pool'][x]['src']} · {'검색량 미확인' if es['pool'][x]['rank'] >= 10 ** 6 else 'rank ' + str(es['pool'][x]['rank'])})" for x in xs]
            o.append(f"- {n} · 이름이 겹치는 후보: {' / '.join(rows) if rows else '없음'}")
        if es.get("latin"):
            o.append("- 영문 표기 후보 (어느 비교 대상인지 직접 판단): " + " / ".join(
                f"{x} ({es['pool'][x]['src']})" for x in es["latin"][:40]))
        o.append("- 후보에 없지만 알려진 표기(영문 브랜드명 등)는 synonyms.analyst 에 — plan 이 검증 문자열로 만들어 keyword_info 측정값이 있는 것만 남긴다")
    o += ["", f"## [2 내부 동향] 후보 (M7 → M8 로 고른다 · {'제품 라인' if s['mode'] == 'entity' else '브랜드 → 브랜드·모델 탐색 묶음'})"]
    for c in P["internal"][:40]:
        rk = "검색량 미확인" if c["rank"] >= 10 ** 6 else f"rank {c['rank']}"
        o.append(f"- {c['name']} · 등장 {c.get('n', '')}회 · {rk} · 예: {' / '.join(c['ex'])}")
    if P.get("topics") is not None:
        o += ["", "## [2 내부 동향] 토픽 후보 (M8 → 성분·맛·특징 묶음으로 쓸 것만 picks.internal.topics 에)"]
        for c in P["topics"][:30]:
            o.append(f"- {c['name']} · 등장 {c['n']}회 · 예: {' / '.join(c['ex'])}")
    o += ["", "## [1 분석 대상] 같은 의도 표현 후보 (method-v5 · 시드를 찾는 사람이 함께 쓰는 말만 picks.synonyms.intent 에 · 예: 학원·수업·스튜디오·근처)",
          "탐색(추천·가격)·속성·형태(기구·매트)·관련 품목(양말·신발)·직업(강사·자격증)은 고르지 않는다 — 형태·탐색은 2 내부 동향이 나눈다"]
    for c in P.get("intentExpr", [])[:80]:
        rk = "검색량 미확인" if c["rank"] >= 10 ** 6 else f"rank {c['rank']}"
        o.append(f"- {c['name']} · {kind(c['name'].split(' ')[0])} · {rk} · 예: {' / '.join(c['ex'])}")
    o += ["", "## [1 분석 대상] 유사의도 후보 (M3a → 시드 품목과 같은 물건의 다른 이름만 picks.synonyms 에 · cluster 먼저)"]
    for c in P.get("synonyms", [])[:40]:
        rk = "검색량 미확인" if c["rank"] >= 10 ** 6 else f"rank {c['rank']}"
        o.append(f"- {c['name']} · {c['src']} · {rk}" + (" · 품목 앞에 붙은 적 있음(브랜드면 제외)" if c.get("brandish") else ""))
    if not P.get("synonyms"):
        o.append("- (후보 없음 · cluster 를 못 불렀으면 LLM 후보를 picks.synonyms.analyst 에 적고 keyword_info 로 검증한다)")
    return "\n".join(o) + "\n"




# ───────────────────────── check (시드 적합성 점검 · references/ask.md) ─────────────────────────
FIT = {
    "buyWords": [],         # 시장별 (ds_market · set_market 이 채운다)
    "howWords": [],
    "buyMin": 0.10,         # 구매 탐색 결합 비율이 이 미만이고
    "entityBrandMin": 0.5,  # 모드 판정(method-v4): 연관 검색어 중 시드 브랜드 포함 비율이 이 이상이면 브랜드/제품
    "categoryBrandsMin": 2,  # 모드 판정: 품목 바로 앞에 붙은 브랜드(사전에 없는 말)가 이 수 이상이고, 한 브랜드가 절반을 넘지 않으면 카테고리
}


def set_market(gl):
    """시장(gl)의 사전 · 패턴 · 의도 묶음 · 신호 단어로 전역을 바꾼다 (method-v5.12). gl 이 없으면 kr."""
    global MARKET, RX, SHOE_GENERIC, INTENT_BUNDLES, CMP_WORDS
    MARKET = MK.get(gl)
    DICT.clear()
    DICT.update({k: list(v) for k, v in MARKET["dict"].items()})
    WORD.clear()
    WORD.update({w: k for k, ws in DICT.items() for w in ws})
    RX = MK.compile_rx(MARKET)
    SHOE_GENERIC = list(DICT["generic"])
    INTENT_BUNDLES = [(n, list(ws)) for n, ws in MARKET["intentBundles"]]
    CMP_WORDS = list(MARKET["cmpWords"])
    FIT["buyWords"] = list(MARKET["buyWords"])
    FIT["howWords"] = list(MARKET["howWords"])


set_market("kr")


def composition(seed, S):
    """method-v4 모드 판정 · 시드의 연관 검색어(intent_finder) 구성으로 정한다 (시드에 브랜드 토큰이 있는지가 아니다).
    브랜드/제품 = 한 브랜드의 제품명·라인·사용 검색이 대부분 · 카테고리 = 일반 수식어가 대부분이고 브랜드명이 2개 이상."""
    I = kw_re(seed.get("item") or [seed["seed"]])
    B = kw_re(seed.get("brand") or [], bound=True) if seed.get("brand") else None
    n = max(len(S), 1)
    brands, seedb, mod = defaultdict(int), 0, 0
    for x in S:
        t = norm(x)
        hb = bool(B and B.search(t))
        seedb += hb
        m = I.search(t) if I else None
        if m:
            before = t[:m.start()].strip().split(" ")
            w = before[-1] if before and before[-1] else ""
            if w and kind(w) == "residual" and not (B and B.search(w)):
                brands[w] += 1
        if not hb and any(kind(p) in ("explore", "attr") for p in t.split(" ")):
            mod += 1
    other = sorted(brands, key=lambda b: -brands[b])
    top = max((brands[b] for b in other), default=0) / n
    sig = {"intentCount": len(S), "seedBrandShare": round(seedb / n, 3) if B else None,
           "brandsSeen": len(other), "brandsTop": other[:5], "topBrandShare": round(top, 3), "modifierShare": round(mod / n, 3)}
    if B and seedb / n >= FIT["entityBrandMin"]:
        mode = "entity"
        why = (f"연관 검색어 {len(S)}개 중 '{seed['brand'][0]}' 포함 {seedb / n:.1%} — 한 브랜드의 제품·라인·사용 검색이 대부분이다")
    elif len(other) >= FIT["categoryBrandsMin"] and top < FIT["entityBrandMin"]:
        mode = "category"
        why = (f"연관 검색어 {len(S)}개에 브랜드 {len(other)}개({' · '.join(other[:3])} 등)가 품목 앞에 붙고, "
               f"브랜드 없는 수식어 결합이 {mod / n:.1%} — 여러 브랜드를 아우르는 일반어다")
    else:
        mode, why = None, (f"연관 검색어 {len(S)}개 · 시드 브랜드 포함 {sig['seedBrandShare'] if B else '—'} · "
                           f"품목 앞 브랜드 {len(other)}개 — 어느 모드 조건도 충족하지 않는다")
    return mode, why, sig


def check(seed, seed_intent):
    """모드 판정(연관 검색어 구성) + 시드가 '사는 대상'(브랜드·제품·품목)인지 점검. 결정적 규칙만 쓴다."""
    S = [norm(x) for x in seed_intent]
    n = max(len(S), 1)
    sub = MARKET["substr"]
    buy = sum(1 for x in S if MK.text_has(x, FIT["buyWords"], sub)) / n
    how = sum(1 for x in S if MK.text_has(x, FIT["howWords"], sub)) / n
    cmode, why, csig = composition(seed, S)
    sig = {"intentCount": len(S), "buyShare": round(buy, 3), "howShare": round(how, 3), **csig}
    reasons, kind_ = [], None
    # method-v5 · 넓은 시드 검사를 '가장 먼저' 한다. 예전에는 주제형(topic) 판정이 먼저 걸리면 좁히기 검사가 돌지 않아
    #   '운동'(주제형이면서 넓은 영역어)이 좁혀지지 않고 그대로 리포트가 나왔다. 이미 좁혀 온 시드(seed.scope)는 다시 검사하지 않는다.
    if not seed.get("scope"):
        import ds_scope
        broad, bsig, bwhy = ds_scope.gate(seed, seed_intent)
        sig.update(bsig)
        if broad:
            kind_ = broad
            reasons.append(bwhy)
    if kind_ is None and seed["mode"] == "category" and buy < FIT["buyMin"] and how >= buy:
        kind_ = "topic"
        reasons.append(f"구매 탐색 결합(가격·추천·비교·후기 등) {buy:.1%} < {FIT['buyMin']:.0%} 이고 방법·식단·효과 결합 {how:.1%} 가 더 많다 — 사는 물건이 아니라 목표·주제일 수 있다")
    if kind_ is None and cmode != seed["mode"]:
        kind_ = "mode"
        reasons.append(f"seed.json 은 {seed['mode']} 인데 연관 검색어 구성은 {cmode or '판정 불가'} — {why}")
    fit = seed.get("fit") or {}
    # ask.md 로 이미 물었다면 그 kind 에 한해서만 다시 묻지 않는다 (topic 답이 넓은 시드 좁히기를 건너뛰게 하지 않는다)
    if fit.get("asked") and kind_ in ("topic", "mode") and fit.get("kind", kind_) == kind_:
        why = f"{why} (적합성 점검: {fit.get('kind', kind_)} → {fit.get('answer', '')} · {seed['mode']} 로 진행)"
        reasons, kind_ = [], None
    return {"needAsk": bool(reasons), "kind": kind_, "signals": sig, "reasons": reasons,
            "modeByComposition": cmode, "modeReason": why}


# ───────────────────────── plan ─────────────────────────

def pick_list(x):
    out = []
    for p in x or []:
        if isinstance(p, str):
            out.append({"name": p, "variants": [p]})
        else:
            out.append({"name": p["name"], "variants": p.get("variants") or [p["name"]]})
    return out


class PicksError(Exception):
    pass


def ext_pick_list(x):
    """method-v5.6 · 비교 대상 고르기. M5a(다른 표기 추리기)는 선택 — 1 은 비교용이라 대표 표기면 충분하다 (실측: 대표 표기가 검색량 96~99%).
    "아디다스" · {"name": "아디다스"} · {"name": "호카", "synonyms": {"pick": ["hoka"]}} 모두 받는다.
    → variants = 이름 + synonyms.pick + synonyms.analyst (+ 옛 variants)."""
    out = []
    for p in x or []:
        if isinstance(p, str):
            p = {"name": p}
        sy = p.get("synonyms") if isinstance(p.get("synonyms"), dict) else {}
        v = [p["name"]] + [w for w in (sy.get("pick") or []) + (sy.get("analyst") or []) + (p.get("variants") or []) if w != p["name"]]
        out.append({"name": p["name"], "variants": list(dict.fromkeys(v)), "synonyms": sy or None})
    return out


def rank_sort(kws, info):
    return sorted(dict.fromkeys(kws), key=lambda s: info.get(s, {"rank": 10 ** 6})["rank"])


def cap(kws):
    return kws if CAP is None else kws[:CAP]


def item_set(seed, picks):
    """M3a · I* = seed.item + picks.synonyms(pick · analyst). 고른 동의어는 01 · 02 의 품목 자리에 모두 쓰인다."""
    sy = picks.get("synonyms") or {}
    out = list(seed["item"])
    for p in pick_list(sy.get("pick")) + pick_list(sy.get("analyst")):
        for v in p["variants"]:
            if v not in out:
                out.append(v)
    return out


def target_keywords(seed, picks, items, info):
    """M3 · 타겟 = 시드 이름 + 유사의도(동의어) · finder 문자열에서 규칙으로 고르고, 고른 동의어로 만든 문자열은 keyword_info 로 검증한다."""
    mode = seed["mode"]
    I = kw_re(items)
    B = kw_re(seed.get("brand") or [], bound=True) if mode == "entity" else None
    req = [B, I] if mode == "entity" else [I]
    opt = bool(seed.get("itemOptional")) and mode == "entity"
    found = [s for s in info if is_bundle_member(s, req) or (opt and is_bundle_member(s, [B]))]
    sy = picks.get("synonyms") or {}
    gen = []
    if mode == "entity":  # method-v5.1 · 브랜드 표기(나이키·nike) × 품목 이름(시드 품목 + 고른 동의어) — 1 비교군과 같은 규칙
        gen = [f"{b} {v}" for b in (seed.get("brand") or [])[:4] for v in items]
    else:
        for p in pick_list(sy.get("pick")) + pick_list(sy.get("analyst")):
            gen += p["variants"]
    have = {norm(x).replace(" ", "") for x in found}
    verify = [g for g in dict.fromkeys(gen) if norm(g).replace(" ", "") not in have]
    return found, verify


def flow_parts_entity(seed, picks, info, B, I, strings):
    """M9 (method-v5.1) · 제품 라인별 묶음 = 카테고리 모드의 검색 목적과 같은 자리 (화면·표·그래프 동일).
    - 라인 = 브랜드가 붙인 고유 제품명 P. 브랜드명이 붙은 표기와 안 붙은 표기('나이키 페가수스 41' · '페가수스 41')를 한 라인에 넣는다.
      안 붙은 표기는 시드 쪽 intent 결과(OWN_SRC)에서 나온 것만 쓴다 (다른 브랜드 결과에 섞인 동명 제품 방지).
    - 세대·하위 모델명('페가수스 41')은 따로 묶지 않는다 — 라인을 펼치면 검색어 행으로 보이고, 새로 생긴 것은 신규 뱃지가 붙는다.
    - 탐색·속성 수식어(추천·여성)와 사용·구매처·커뮤니티가 붙은 검색어는 넣지 않는다. 두 라인이 함께 든 검색어도 넣지 않는다."""
    parts_p = pick_list((picks.get("internal") or {}).get("pick"))
    rxs = {p["name"]: kw_re(p["variants"], bound=True) for p in parts_p}
    with_i, without_i, alone = defaultdict(int), defaultdict(int), set()
    for s in strings:
        ps = strip_parts(s, [B])
        if ps is None:
            continue
        res = [x for x in ps if kind(x) == "residual"]
        for x in res:
            (with_i if I.search(norm(s)) else without_i)[x] += 1
        if not I.search(norm(s)) and len(res) == 1 and len(ps) == 1:
            alone.add(res[0])
    other = {x for x in alone if with_i[x] < 0.2 * (with_i[x] + without_i[x])} - set(rxs)
    parts = []
    for p in parts_p:
        rx = rxs[p["name"]]
        kws, subs = [], defaultdict(list)
        for s in strings:
            t = norm(s)
            if not rx.search(t):
                continue
            if not B.search(t) and not (info[s]["src"] & OWN_SRC):
                continue
            if any(o != p["name"] and orx.search(t) for o, orx in rxs.items()):
                continue  # 두 라인이 함께 든 검색어는 어느 쪽에도 넣지 않는다
            pieces = strip_parts(s, [rx]) or []
            for extra in (B, I):
                rest = strip_parts(" ".join(pieces), [extra]) if pieces else None
                pieces = rest if rest is not None else pieces
            ks = ["gen" if re.fullmatch(r"\d+(\.\d+)?", x) else kind(x) for x in pieces]
            if any(k in BAD or k in ("explore", "attr") for k in ks):
                continue  # 탐색·속성 수식어가 붙은 검색어는 넣지 않는다
            if other and not I.search(t) and any(x in other for x in pieces):
                continue  # 같은 이름의 다른 품목 (쿠쿠 에코웨일 큐브 = 음식물처리기)
            model = [x for x, k in zip(pieces, ks) if k in ("gen", "residual")]
            kws.append(s)
            subs[" ".join(model)].append(s)
        if not kws:
            continue
        # method-v5.1 · 라인 = 카테고리 모드의 검색 목적과 같은 자리. 하위 SKU 단계 없이 라인 안 검색어가 바로 펼쳐진다
        #   (세대·모델명 '페가수스 41' 은 검색어 행의 신규 뱃지로 보인다).
        parts.append({"name": p["name"], "keywords": rank_sort(kws, info)})
    return parts, other


def intent_parts_category(seed, picks, info, I, strings):
    """M9 (method-v4) · 카테고리 모드 2 내부 동향 = 의도 묶음. 품목(I*)이 든 검색어 중 사용·구매처·커뮤니티·정보·연도가 없는 것을
    브랜드·모델 탐색 → 토픽 → 고정 의도(INTENT_BUNDLES) 순서로 한 묶음에만 넣는다. 품목 이름만 있는 검색어는 분석 대상(이름 자체)이라 넣지 않는다."""
    it = picks.get("internal") or {}
    brands = pick_list(it.get("pick"))
    topics = pick_list(it.get("topics"))
    brx = kw_re([v for p in brands for v in p["variants"]], bound=True) if brands else None
    trx = [(p["name"], kw_re(p["variants"])) for p in topics]
    ca = it.get("catchall")
    cax = kw_re(ca.get("variants") or []) if ca and ca.get("variants") else None
    caex = set(ca.get("exclude") or []) if ca else set()
    buckets = defaultdict(list)
    unassigned = 0
    for s in strings:
        t = norm(s)
        if not I.search(t):
            continue
        ps = strip_parts(s, [I])
        if not ps:
            continue
        ks = classes(ps)
        if any(k in BAD for k in ks) or all(k == "generic" for k in ks):
            continue
        name = None
        if brx and brx.search(t):
            name = BRAND_BUNDLE
        if not name:
            name = next((n for n, rx in trx if rx and rx.search(t)), None)
        if not name:
            if MARKET["substr"]:
                name = next((n for n, ws in INTENT_BUNDLES if any(w in p for p in ps for w in ws if len(w) >= 2 or p == w)), None)
            else:  # us · 단어 단위 ('new balance' 의 'new' · 'laptop' 의 'top' 오탐 방지)
                name = next((n for n, ws in INTENT_BUNDLES if any(MK.word_in(p, ws, False) for p in ps)), None)
        if not name and ca:
            # method-v5 · 찾기 묶음(catchall): 품목 '앞'에 붙은 고유 이름(스튜디오·지역) 1~2개 또는 근처·학원 같은 찾기 표현
            if cax and cax.search(t):
                name = ca["name"]
            else:
                pos = t.find(I.search(t).group(0)) if I.search(t) else -1
                head = [x for x in norm(t[:pos]).split(" ") if x] if pos > 0 else []
                tail = [x for x in ps if x not in head]
                if (head and len(head) <= 2 and not tail and all(kind(x) == "residual" for x in head)
                        and not any(x in caex for x in head)):
                    name = ca["name"]
        if name:
            buckets[name].append(s)
        else:
            unassigned += 1
    order = [BRAND_BUNDLE] + [n for n, _ in trx] + [n for n, _ in INTENT_BUNDLES] + ([ca["name"]] if ca else [])
    parts = [{"name": n, "keywords": rank_sort(buckets[n], info)} for n in order if buckets.get(n)]
    # method-v5 · 찾기 묶음 안을 하위 묶음으로: 찾기 표현(근처·학원) / 지역명(지명·역·동) / 스튜디오·브랜드명
    if ca and buckets.get(ca["name"]):
        regions = set(ca.get("regions") or [])
        rsuf = re.compile(MARKET["regionSuffix"])  # 지역명 접미사 · 시장별 (kr: 역·동·구 … · jp: 駅·市·区 … · us: 없음)
        subs = defaultdict(list)
        for kw in buckets[ca["name"]]:
            t = norm(kw)
            if cax and cax.search(t):
                subs[ca.get("subNames", {}).get("words", "근처·학원 등 찾기 표현")].append(kw)
                continue
            pos = t.find(I.search(t).group(0)) if I.search(t) else -1
            head = [x for x in norm(t[:pos]).split(" ") if x] if pos > 0 else []
            if head and (head[0] in regions or rsuf.search(head[0]) and len(head[0]) >= 2 and head[0] not in (ca.get("notRegion") or [])):
                subs[ca.get("subNames", {}).get("region", "지역명으로 찾기")].append(kw)
            else:
                subs[ca.get("subNames", {}).get("brand", "스튜디오 이름으로 찾기")].append(kw)
        if ca.get("split"):  # method-v5 · 하위 묶음을 각각 독립된 검색 목적으로 (지역명 / 브랜드명 / 근처·학원)
            i = next(j for j, prt in enumerate(parts) if prt["name"] == ca["name"])
            parts[i:i + 1] = [{"name": k, "keywords": rank_sort(v, info)} for k, v in subs.items() if v]
        else:
            for prt in parts:
                if prt["name"] == ca["name"]:
                    prt["skus"] = [{"name": k, "keywords": rank_sort(v, info)} for k, v in subs.items()]
    
    return parts, unassigned


def build_plan(P, picks, info):
    seed = P["seed"]
    mode = seed["mode"]
    items = item_set(seed, picks)
    I = kw_re(items)
    B = kw_re(seed.get("brand") or [], bound=True) if mode == "entity" else None
    strings = list(info)
    found, verify = target_keywords(seed, picks, items, info)
    plan = {"seed": seed["seed"], "mode": mode, "modeReason": seed.get("modeReason", ""), "method": METHOD,
            # 모드 판정 숫자 근거 · 리포트가 jp · us 문장을 이 숫자로 다시 쓴다 (modeReason 은 한국어 문장)
            "modeSignals": {**(seed.get("composition") or {}), "brand": (seed.get("brand") or [None])[0]} if seed.get("composition") else None,
            "upper": seed.get("upper"), "itemVariants": items, "scope": seed.get("scope"),
            "target": {"name": seed["seed"], "keywords": rank_sort(found, info) + verify, "verify": verify}}
    # 섹션 1 시장 동향 · M6 (타겟과 같은 규칙)
    ext = []
    csrc = {c["name"]: c.get("src") for c in P["external"]}
    cnear = {c["name"]: {k: c.get(k) for k in ("near", "seedN", "coN", "cmpN", "nearWhy") if c.get(k) is not None}
             for c in P["external"] if c.get("near")}  # method-v5.11 · 근접 근거 (build 가 '가까움' 아닌 비교 대상을 경고)
    ext_picks = ext_pick_list((picks.get("external") or {}).get("pick"))
    for p in ext_picks:
        rx = kw_re(p["variants"], bound=(mode == "entity"))
        req = [rx, I] if mode == "entity" else [rx]
        kws = [s for s in strings if is_bundle_member(s, req)
               or (mode == "entity" and seed.get("itemOptional") and is_bundle_member(s, [rx]))]
        if mode == "category":
            kws = [s for s in kws if not I.search(norm(s))]
        name = f"{p['name']} {seed['item'][0]}" if mode == "entity" else p["name"]
        if kws or mode == "entity":  # method-v5.1 · finder 에 없어도 표기 × 품목 이름 문자열을 측정값으로 검증한다
            srcs = [csrc.get(v) for v in p["variants"] if csrc.get(v)]
            src = "cluster" if "cluster" in srcs else ("intent" if "intent" in srcs else "analyst")
            ext.append({"name": name, "keywords": cap(rank_sort(kws, info)), "src": src})
    # method-v5 · 비교군도 타겟과 같은 규칙: 이름 자체의 다른 표기(yoga · 홈트레이닝)만 더한다.
    #   finder 결과에 없는 표기는 keyword_info 측정값으로 검증한다 (측정값 없으면 build 가 뺀다 · 타겟의 analyst 동의어와 같다).
    # method-v5.1 · 브랜드/제품 모드도 같은 규칙: 비교 브랜드 표기(아디다스·adidas) × 타겟과 같은 품목 이름(런닝화·러닝화·조깅화 …)
    #   타겟에 섞은 같은 뜻의 검색어가 비교군에도 똑같이 섞여야 비교가 기울지 않는다 (M6).
    picked = {}
    for p in ext_picks:
        picked[f"{p['name']} {seed['item'][0]}" if mode == "entity" else p["name"]] = p
    for g in ext:
        p = picked.get(g["name"])
        if not p:
            continue
        have = {norm(x).replace(" ", "") for x in g["keywords"]}
        cand = [f"{v} {i}" for v in p["variants"] for i in items] if mode == "entity" else p["variants"]
        gen = []
        for v in dict.fromkeys(cand):  # 띄어쓰기만 다른 표기는 하나만 (같은 측정 레코드)
            kk = norm(v).replace(" ", "")
            if kk not in have:
                have.add(kk)
                gen.append(v)
        g["keywords"] = g["keywords"] + gen
        g["verify"] = gen
        g["synonyms"] = p["synonyms"]  # M5a 기록 · 리포트 하단 '키워드셋 분류 근거'에 실린다
    if mode == "entity":
        # method-v5.6 · 1 은 비교용 대표 표기만 (M6-lite): 브랜드 표기 × 대표 품목 이름(시드 품목 + 고른 동의어 첫 번째).
        #   분석 대상(나이키)도 같은 규칙 → 1 의 분석 대상 행은 2 의 상세 묶음과 다를 수 있다 (2 = 모든 이름).
        #   역순(러닝화 아디다스)·수식어(아디다스 운동화 런닝화)·조깅화·러닝 슈즈 같은 작은 표기는 넣지 않는다 (합쳐도 2~4%).
        syp = pick_list((picks.get("synonyms") or {}).get("pick"))
        lite = list(dict.fromkeys([seed["item"][0]] + ([syp[0]["variants"][0]] if syp else [])))

        def combos(variants):
            out, seen = [], set()
            for v in variants:
                for i in lite:
                    # v5.6.3 · 앞뒤 순서 둘 다 (나이키 러닝화 · 러닝화 나이키) — 온러닝은 역순이 검색량의 11% 였다
                    for c in (f"{v} {i}", f"{i} {v}"):
                        k = norm(c).replace(" ", "")
                        if k not in seen:
                            seen.add(k)
                            out.append(c)
            return out
        def broad(variants, rx):
            # method-v5.6.2 · 커버 검사용 상세 묶음 = 예전 규칙 (파인더 문자열: 표기 + 품목 이름 + 일반어만 · 순서 무관) + 표기 × 품목 이름 전부 조합
            fs = [x for x in strings if is_bundle_member(x, [rx, I])]
            return list(dict.fromkeys(fs + [f"{v} {i}" for v in variants for i in items]))
        ext = []
        for p in ext_picks:
            kws = combos(p["variants"])
            srcs = [csrc.get(v) for v in p["variants"] if csrc.get(v)]
            src = "cluster" if "cluster" in srcs else ("intent" if "intent" in srcs else "analyst")
            ext.append({"name": f"{p['name']} {seed['item'][0]}", "keywords": kws, "src": src,
                        "verify": list(kws), "synonyms": p["synonyms"],  # 조합 문자열은 모두 keyword_info 측정값으로 (없으면 build 가 뺀다)
                        "broad": broad(p["variants"], kw_re(p["variants"], bound=True))})
        mk = combos(seed.get("brand") or [seed["seed"]])
        plan["marketTarget"] = {"name": seed["seed"], "keywords": mk, "verify": list(mk), "items": lite,
                                "broad": list(dict.fromkeys(plan["target"]["keywords"] + mk))}  # 커버 검사 = 분석 대상 상세 묶음(plan.target) 대비
    else:
        # method-v5.9 · 카테고리 모드도 1 = 비교용 대표 이름 (M6-lite category) · 상세 묶음(plan.target)은 커버 검사용.
        #   분석 대상 = 시드 품목 + 고른 같은 뜻의 이름 첫 번째(synonyms.pick → analyst 순) · 비교 대상 = 이름 + M5a 다른 표기 첫 번째.
        #   모든 묶음이 '대표 이름 2개까지'로 같은 기준.
        #   상세 묶음(broad · 예전 규칙)은 커버 검사(대표 이름 ÷ 상세 < 90% 경고)에만 쓴다.
        sy = picks.get("synonyms") or {}
        syl = pick_list(sy.get("pick")) + pick_list(sy.get("analyst"))
        lite = list(dict.fromkeys([seed["item"][0]] + ([syl[0]["variants"][0]] if syl else [])))

        def uniq(names):
            out, seen = [], set()
            for v in names:
                k = norm(v).replace(" ", "")
                if k not in seen:  # 띄어쓰기만 다른 표기는 같은 측정 레코드 — 한 번만
                    seen.add(k)
                    out.append(v)
            return out
        full = {g["name"]: g for g in ext}
        ext = []
        for p in ext_picks:
            kws = uniq(p["variants"][:2])
            srcs = [csrc.get(v) for v in p["variants"] if csrc.get(v)]
            src = "cluster" if "cluster" in srcs else ("intent" if "intent" in srcs else "analyst")
            nr = next((cnear[v] for v in p["variants"] if v in cnear), {"near": "근거 약함", "seedN": 0, "coN": 0, "cmpN": 0})
            ext.append({"name": p["name"], "keywords": kws, "src": src, "verify": list(kws), "synonyms": p["synonyms"], "closeness": nr,
                        "broad": list(dict.fromkeys((full.get(p["name"]) or {}).get("keywords", []) + p["variants"]))})
        mk = uniq(lite)
        plan["marketTarget"] = {"name": seed["seed"], "keywords": mk, "verify": list(mk), "items": lite,
                                "broad": list(dict.fromkeys(plan["target"]["keywords"] + mk))}  # 커버 검사 = 분석 대상 상세 묶음(plan.target) 대비
    plan["external"] = ext
    # 섹션 2 내부 동향 · M9
    unit = (picks.get("internal") or {}).get("unit") or ("제품 라인" if mode == "entity" else "의도")
    other, unassigned = set(), None
    if mode == "entity":
        parts, other = flow_parts_entity(seed, picks, info, B, I, strings)
    elif unit == "의도":
        parts, unassigned = intent_parts_category(seed, picks, info, I, strings)
    else:  # 주제형(unit = 방법) · ask.md topic A — 고른 이름 + 품목명(+일반어)만
        parts = []
        parts_p = pick_list((picks.get("internal") or {}).get("pick"))
        rxs = {p["name"]: kw_re(p["variants"], bound=True) for p in parts_p}
        for p in parts_p:
            rx = rxs[p["name"]]
            kws = []
            for s in strings:
                t = norm(s)
                if not rx.search(t) or not I.search(t) or any(o != p["name"] and orx.search(t) for o, orx in rxs.items()):
                    continue
                pieces = strip_parts(s, [rx]) or []
                rest = strip_parts(" ".join(pieces), [I]) if pieces else None
                pieces = rest if rest is not None else pieces
                if all(kind(x) == "generic" for x in pieces):
                    kws.append(s)
            if kws:
                parts.append({"name": p["name"], "keywords": rank_sort(kws, info)})
    plan["internal"] = {"unit": unit, "parts": parts}
    if unassigned is not None:
        plan["internal"]["unassigned"] = unassigned
    plan["picks"] = picks
    plan["otherLines"] = sorted(other)
    return plan


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check")
    c.add_argument("--seed", required=True)
    c.add_argument("--intent", required=True, help="lm_intent_seed.json")
    c.add_argument("--out", required=True)
    for name in ("propose", "plan"):
        x = sp.add_parser(name)
        x.add_argument("--seed", required=True)
        x.add_argument("--intent", nargs="+", required=True)
        x.add_argument("--cluster")
        x.add_argument("--cluster-seed", help="method-v5.10 · 시드 cluster (category 필수 · lm_cluster_seed.json)")
        x.add_argument("--out", required=True)
        if name == "propose":
            x.add_argument("--brief", required=True)
        else:
            x.add_argument("--picks", required=True)
    a = ap.parse_args()
    seed = C.load_json(a.seed)
    set_market(seed.get("gl"))  # method-v5.12 · 시장별 사전 · seed.json 에 gl 이 없으면 kr
    if a.cmd == "check":
        r = check(seed, C.intent_strings(C.load_json(a.intent)))
        Path(a.out).write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        if not r["needAsk"]:  # 통과하면 모드 판정 근거를 코드 문장으로 seed.json 에 남긴다 (리포트 상단에 실린다)
            seed["modeReason"] = r["modeReason"] + (f" ({seed['modeNote']})" if seed.get("modeNote") else "")
            seed["composition"] = r["signals"]
            Path(a.seed).write_text(json.dumps(seed, ensure_ascii=False, indent=1), encoding="utf-8")
        print(("질문 필요 · " + " / ".join(r["reasons"])) if r["needAsk"] else f"적합 · {r['signals']}")
        sys.exit(10 if r["needAsk"] else 0)
    configure(seed, C.load_json(a.picks) if a.cmd == "plan" else None)
    info = load_sources(a.intent, a.cluster, a.cluster_seed)
    P = propose(seed, info)
    if a.cmd == "propose":
        Path(a.out).write_text(json.dumps({**P}, ensure_ascii=False, indent=1), encoding="utf-8")
        Path(a.brief).write_text(write_md(P), encoding="utf-8")
        print(f"wrote {a.out} · 타겟 {len(P['target'])} · 외부 후보 {len(P['external'])} · 내부 후보 {len(P['internal'])}")
    else:
        try:
            plan = build_plan(P, C.load_json(a.picks), info)
        except PicksError as ex:
            print("ERROR  " + str(ex))
            sys.exit(11)
        Path(a.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {a.out} · 타겟 {len(plan['target']['keywords'])} · 외부 {len(plan['external'])} · 내부 {len(plan['internal']['parts'])} "
              f"· 키워드 {len({k for g in [plan['target']] + plan['external'] + plan['internal']['parts'] for k in g['keywords']})} "
              f"· 검증 대상(유사의도 생성) 타겟 {len(plan['target']['verify'])} · 비교군 {sum(len(g.get('verify') or []) for g in plan['external'])} "
              f"· 커버 검사 {len({k for g in plan['external'] + [plan.get('marketTarget') or {}] for k in g.get('broad') or []})}")


if __name__ == "__main__":
    main()
