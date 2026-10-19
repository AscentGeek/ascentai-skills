#!/usr/bin/env python3
"""Aggregate ListeningMind cluster_finder (Cluster Finder) responses into the
report data JSON consumed by render_report.py --skill cluster-landscape.

Standard library only. Two data sources are merged:
  1. POST /cluster_finder (data_type=all) — the co-search graph:
     {"data": {"communities": {"0": [kw,...], "1": [...]}, "rels": [[a,b],...]}}
     communities = Louvain topic clusters (keyword strings only, NO metrics),
     rels = undirected co-search edge pairs (keyword strings, NO weights).
  2. POST /keyword_info (data_type=all) — per-keyword enrichment:
     {"data": [{"keyword", "ads_metrics": {"volume_avg", ...}, "intents": {...}}]}
     cluster_finder itself returns NO volumes, so keyword_info supplies them.

The `context` subcommand fuses the two into lm_cluster_result.json (per-cluster
membership, hub keywords via edge degree, outgoing cluster flows, + the `csv`
the LLM analysis step reads). The `groups` subcommand post-processes the LLM's
4-section output (검색목적 클러스터 그룹 + From→To 흐름) into the persona-card
`groups`, the hub-keyword summary `hubTable`, and the `flows` list — attaching
all facts (volume sums, hub keywords) in Python per the numbers policy.
"""

import argparse
import json
import sys
from pathlib import Path


INTENT_KEYS = ("i", "n", "c", "t")
# 지배 의도 (agent_cluster 는 '검색 의도 축'을 정성 해석하므로 대표 라벨만 CSV 로 전달)
#
# 표시 문자열은 라벨 JSON 에서 가져온다. 예전에는 한국어를 여기 박아 두었는데, 그러면
# us·jp 리포트의 CSV 에도 한국어가 들어가 LLM 이 그 말로 해석하게 된다. 리포트 화면에
# 직접 찍히지는 않지만 해석 품질에 섞이므로 다른 스킬과 같은 라벨 키를 쓴다.
INTENT_LABEL_KEY = {
    "i": "customerAnalysis.stage.informational",
    "n": "customerAnalysis.stage.navigational",
    "c": "customerAnalysis.stage.commercial",
    "t": "customerAnalysis.stage.transactional",
}
# 라벨 파일을 못 읽었을 때만 쓰는 폴백 — 영어로 둔다(한국어가 섞이는 것이 원래 문제였다)
INTENT_FALLBACK = {"i": "Informational", "n": "Navigational",
                   "c": "Commercial", "t": "Transactional"}

# LLM 분석 입력(CSV) 상한. cluster_finder limit=10000 이면 노드 수가 시드에 따라 크게 갈린다
# (실측 2026-10-12 · 6개 시드: 1,225 ~ 7,124 노드 · 클러스터 10 ~ 76개). 수집 상한과 분리해 둔다.
#
# 이 값은 **CSV 와 context["keywords"] 를 동시에 캡한다** — 둘을 벌리면 안 된다.
# _members_of_clusters() 가 '카드 근거를 CSV 에 있는 키워드로만 제한'하는 환각 방지 장치이고
# 그 판정을 build_keyword_map(context["keywords"]) 으로 하기 때문에, keywords 만 넓히면
# LLM 이 못 본 키워드가 카드 근거로 올라온다.
#
# 그래프·허브·흐름 계산은 이 상한과 무관하게 **받은 노드 전체**로 돈다(5단계 이전).
KEYWORD_CONTEXT_TOP_N = 2000

# 클러스터별 최소 보장 수. 검색량순으로만 자르면 꼬리 클러스터가 통째로 사라진다
# (실측 · 나이키 kr: 76개 클러스터 중 31개가 상위 2,000 밖). 그 클러스터는 검색량이 작아도
# 구조상 존재하는 탐색 묶음이고, 허브가 CSV 에 없으면 STEP 4 게이트가 카드째로 버린다.
# 그래서 상위 N 을 채우기 전에 **클러스터마다 검색량 상위 k 개를 먼저 확보**한다.
# 76 클러스터 × 6 = 456 행이면 상한 2,000 의 23% 이고, 나머지 1,544 행은 검색량순으로 채운다.
CLUSTER_MIN_KEYWORDS = 6
# 카드 evidence·허브 표에 노출할 대표 키워드 수(검색량순).
EVIDENCE_TOP_N = 8

# keyword_info 로 상세 조회할 키워드 수 상한.
#
# 왜 두는가 · 노드 전량을 조회해도 CSV 에 들어가는 건 KEYWORD_CONTEXT_TOP_N 개뿐이다.
# 검색량·의도는 CSV 행에만 쓰이고(허브·흐름은 cluster_finder 그래프로 계산된다) 나머지는
# 받아서 버린다 — 실측 2026-10-13 '마그네슘영양제': 3,285 조회 → 1,285개(39%) 폐기.
#
# 그리고 이 폐기가 **리포트 생성 시간의 최대 병목**이다. 느린 쪽은 받는 응답이 아니라
# **보내는 키워드 배열**이다(1개 호출 9초 / 50개 35초 · 응답 다운로드는 1초 미만).
# 1,000개 배열이 약 9,500 토큰이라 청크 하나가 곧 수 분이다. 조회를 CSV 상한에 맞추면
# 청크 수가 줄어 그만큼 직접 단축된다(실측 시드 4청크 → 2청크 · 약 17분 → 13분).
#
# 왜 degree 로 고르는가 · 조회 전에는 검색량을 모른다(그게 이 호출로 받는 값이다). 그래서
# 그래프만으로 골라야 하고, degree 는 downstream 허브 선정 기준과 같은 축이다.
# 실측 2026-10-13 '마그네슘영양제': 제외된 1,285개가 **전부 degree<=1 말단 노드**였고
# 실제 검색량 중앙값 41 · 73%가 100 미만이었다(조회군 평균 3,811 — 약 60배 차이).
# 즉 빠지는 쪽은 그래프 주변부의 저검색량 키워드다.
#
# 품질 영향(실측) · 클러스터 33/33 유지 · 허브 33/33 유지 · 멤버 부족 클러스터 0개 ·
# totalVolume -2.3% · CSV 검색량 커버리지 98.4% → 97.7%.
# 주의 · 검색량이 큰데 말단인 키워드는 빠질 수 있다(실측 '고혈압에 좋은 음식' 9,313 · degree 1).
# 시드 시장의 주변 토픽이라 카드 근거로서의 가치는 낮지만, 숫자만 보면 손실로 읽힌다.
KEYWORD_ENRICH_TOP_N = KEYWORD_CONTEXT_TOP_N


def _unwrap_content_blocks(raw):
    """Strip the MCP content-block wrapper if present.

    Some hosts persist a large tool result as [{"type":"text","text":"<JSON>"}]
    rather than the bare envelope. Left alone, every block looks like one record
    and extraction yields nothing. Observed on the claude.ai web container.
    """
    if isinstance(raw, list) and raw:
        blocks = [b for b in raw
                  if isinstance(b, dict) and b.get("type") == "text" and "text" in b]
        if blocks and len(blocks) == len(raw):
            try:
                return json.loads("".join(str(b.get("text") or "") for b in blocks))
            except (json.JSONDecodeError, TypeError):
                return raw
    return raw


def _load_json(path):
    """Read a tool-response file, unwrapping the MCP content-block wrapper."""
    return _unwrap_content_blocks(json.loads(Path(path).read_text(encoding="utf-8")))


def _num(v, default=0):
    """Coerce int/float/numeric-string to a number; anything else -> default.

    The upstream metric types are unverified: volume_avg may arrive as a
    JSON string (e.g. "74000"). Without coercion the sums/formatters break.
    """
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            f = float(v)
        except ValueError:
            return default
        return int(f) if f.is_integer() else f
    return default


def _cluster_letter(index):
    """Map a community index (0,1,2,...) to a letter id (A,B,...,Z,AA,AB,...),
    mirroring the agent_cluster '0→A, 1→B, 2→C...' mapping rule."""
    n = int(index)
    letters = ""
    while True:
        letters = chr(65 + (n % 26)) + letters
        n = n // 26 - 1
        if n < 0:
            break
    return letters


# ─────────────────────────────────────────
# Parsing the two API responses
# ─────────────────────────────────────────

def normalize_keyword_info(raw):
    """Return {keyword: {volume_avg, volume_total, volume_trend, intents}} from
    a /keyword_info response. Envelope-tolerant ({"data":[...]} or bare list)."""
    rows = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            rows = raw["data"]
        elif isinstance(raw.get("data"), dict) and isinstance(raw["data"].get("results"), list):
            rows = raw["data"]["results"]
        elif isinstance(raw.get("results"), list):
            rows = raw["results"]

    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = row["_source"] if isinstance(row.get("_source"), dict) else row
        keyword = src.get("keyword")
        if not keyword:
            continue
        am = src.get("ads_metrics")
        am = am if isinstance(am, dict) else {}
        intents = src.get("intents")
        intents = intents if isinstance(intents, dict) else {}
        out[keyword] = {
            "volume_avg": _num(am.get("volume_avg")),
            "volume_total": _num(am.get("volume_total")),
            "volume_trend": _num(am.get("volume_trend")),
            "intents": {k: _num(intents.get(k)) for k in INTENT_KEYS},
        }
    return out


def parse_cluster_response(raw):
    """Return (communities: {clusterId(str): [keyword,...]}, rels: [[a,b],...])
    from a /cluster_finder response. Envelope-tolerant."""
    data = raw.get("data") if isinstance(raw, dict) else None
    if not isinstance(data, dict):
        data = raw if isinstance(raw, dict) else {}
    communities = data.get("communities")
    rels = data.get("rels")
    communities = communities if isinstance(communities, dict) else {}
    rels = rels if isinstance(rels, list) else []
    # keep only well-formed 2-element string edges
    clean_rels = [
        [str(e[0]), str(e[1])]
        for e in rels
        if isinstance(e, (list, tuple)) and len(e) == 2 and e[0] and e[1]
    ]
    clean_comm = {
        str(cid): [kw for kw in kws if isinstance(kw, str)]
        for cid, kws in communities.items()
        if isinstance(kws, list)
    }
    return clean_comm, clean_rels


def load_intent_labels(lang):
    """Return {i/n/c/t: display string} for `lang`, read from the label JSON.

    Falls back to English when the file is missing or a key is absent — the bug
    this replaces was Korean leaking into every market's csv, so the fallback
    must not reintroduce it.
    """
    out = dict(INTENT_FALLBACK)
    # 소스 트리는 skills/<스킬>/{render,labels}/, zip 은 _shared/{render,labels}/ —
    # 둘 다 render 의 형제 폴더라 한 경로로 닿는다.
    path = Path(__file__).resolve().parent.parent / "labels" / f"cluster-landscape.{lang}.json"
    try:
        labels = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return out
    for k, key in INTENT_LABEL_KEY.items():
        v = labels.get(key)
        if isinstance(v, str) and v.strip():
            out[k] = v
    return out


def _dominant_intent(intents, intent_labels=None):
    if not intents:
        return ""
    total = sum((intents.get(k, 0) or 0) for k in INTENT_KEYS)
    if total <= 0:
        return ""
    table = intent_labels or INTENT_FALLBACK
    return table[max(INTENT_KEYS, key=lambda k: intents.get(k, 0) or 0)]


# ─────────────────────────────────────────
# context — fuse graph + enrichment into lm_cluster_result.json
# ─────────────────────────────────────────

def select_enrich_keywords(communities, rels, top_n=KEYWORD_ENRICH_TOP_N,
                           cluster_min=CLUSTER_MIN_KEYWORDS):
    """Pick which keywords to send to `keyword_info`, before any volume is known.

    Volumes are exactly what this call fetches, so the pick can only use the graph.
    It mirrors build_cluster_context's own ranking so nothing it needs goes missing:

      1. every cluster's hub (highest edge degree) — postprocess_groups() discards a
         cluster whose hub is absent from the csv, so these are non-negotiable,
      2. then each cluster's next `cluster_min - 1` members by degree, so no cluster
         arrives with too few rows to characterize,
      3. then the rest by degree desc until `top_n`.

    Degree is the right proxy here: it is what picks hubs downstream, and a keyword
    co-searched with many others is the one worth enriching. Returns keywords in a
    stable order (degree desc, then first-seen) so the chunking is reproducible.
    """
    kw_cluster = {}
    for cid in sorted(communities.keys(), key=lambda c: (0, int(c)) if str(c).isdigit() else (1, c)):
        for kw in communities[cid]:
            kw_cluster.setdefault(kw, cid)

    degree = {}
    for a, b in rels:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1

    order = {kw: i for i, kw in enumerate(kw_cluster)}
    rank = sorted(kw_cluster, key=lambda k: (-degree.get(k, 0), order[k]))
    if top_n is None or len(rank) <= top_n:
        return rank

    by_cluster = {}
    for kw in rank:
        by_cluster.setdefault(kw_cluster[kw], []).append(kw)

    picked = []
    seen = set()

    def take(kw):
        if kw not in seen:
            seen.add(kw)
            picked.append(kw)

    floor = max(1, cluster_min or 1)
    for depth in range(floor):
        for members in by_cluster.values():
            if depth < len(members) and len(seen) < top_n:
                take(members[depth])
    for kw in rank:
        if len(seen) >= top_n:
            break
        take(kw)

    return sorted(picked, key=lambda k: (-degree.get(k, 0), order[k]))


def _select_context_keywords(keywords, top_n, cluster_min):
    """Pick the CSV rows: guarantee each cluster its top `cluster_min` keywords,
    then fill the remaining budget by volume desc.

    Ranking by volume alone drops whole clusters off the tail — measured on seed
    나이키 (kr), 31 of 76 clusters fell outside the top 2,000. Those clusters are
    small in volume but real in structure, and a cluster whose hub is missing from
    the csv is discarded outright by postprocess_groups(). The floor keeps every
    cluster representable; the rest of the budget still goes to the biggest
    keywords, so the head is unaffected.

    `keywords` must already be sorted by volume desc. Order of the returned list
    stays volume desc so the csv reads head-first.
    """
    if top_n is None or len(keywords) <= top_n:
        return keywords

    picked = set()

    # Hubs first, unconditionally. A hub is chosen by edge degree, not volume, so a
    # low-volume hub can sit far down this volume-sorted list — and postprocess_groups()
    # discards any cluster whose hub is absent from the csv. Reserving hubs is what
    # actually keeps a cluster usable; the per-cluster floor below only adds context.
    for i, k in enumerate(keywords):
        if k.get("is_hub"):
            picked.add(i)
    if len(picked) > top_n:
        picked = set(sorted(picked)[:top_n])

    if cluster_min and cluster_min > 0 and len(picked) < top_n:
        per = {}
        for i in sorted(picked):
            letter = keywords[i].get("cluster") or ""
            per[letter] = per.get(letter, 0) + 1
        for i, k in enumerate(keywords):
            if len(picked) >= top_n:
                break
            if i in picked:
                continue
            letter = k.get("cluster") or ""
            n = per.get(letter, 0)
            if n < cluster_min:
                per[letter] = n + 1
                picked.add(i)

    for i in range(len(keywords)):
        if len(picked) >= top_n:
            break
        picked.add(i)

    return [keywords[i] for i in sorted(picked)]


def build_cluster_context(communities, rels, kw_info, seed, gl, date,
                          top_n=KEYWORD_CONTEXT_TOP_N,
                          cluster_min=CLUSTER_MIN_KEYWORDS,
                          intent_labels=None):
    """Fuse communities + rels + keyword_info into the report context dict."""
    # 1) keyword -> cluster letter (a keyword belongs to a single community).
    #    Community ids are numeric strings ('0','1',...); sort numerically so
    #    letter assignment is stable ('0'→A regardless of dict order).
    def _cid_key(cid):
        try:
            return (0, int(cid))
        except (TypeError, ValueError):
            return (1, cid)

    ordered_cids = sorted(communities.keys(), key=_cid_key)
    cid_to_letter = {cid: _cluster_letter(i) for i, cid in enumerate(ordered_cids)}
    kw_cluster = {}
    cluster_members = {}  # letter -> [keyword,...]
    for cid in ordered_cids:
        letter = cid_to_letter[cid]
        members = []
        for kw in communities[cid]:
            if kw in kw_cluster:
                continue  # first cluster wins if duplicated
            kw_cluster[kw] = letter
            members.append(kw)
        cluster_members[letter] = members

    # 2) edge degree per keyword + which clusters each keyword links out to.
    degree = {}
    kw_out_clusters = {}  # keyword -> set(cluster letters it connects to, excl. own)
    for a, b in rels:
        degree[a] = degree.get(a, 0) + 1
        degree[b] = degree.get(b, 0) + 1
        ca, cb = kw_cluster.get(a), kw_cluster.get(b)
        if ca and cb and ca != cb:
            kw_out_clusters.setdefault(a, set()).add(cb)
            kw_out_clusters.setdefault(b, set()).add(ca)

    # 3) hub keyword per cluster: highest edge-degree member, tie/void-broken by
    #    volume_avg (agent_cluster rule: h=TRUE, else highest v).
    def _vol(kw):
        return _num((kw_info.get(kw) or {}).get("volume_avg"))

    hub_keywords = {}  # letter -> [hub keyword,...] (usually 1)
    is_hub = set()
    for letter, members in cluster_members.items():
        if not members:
            hub_keywords[letter] = []
            continue
        ranked = sorted(members, key=lambda k: (degree.get(k, 0), _vol(k)), reverse=True)
        hub = ranked[0]
        hub_keywords[letter] = [hub]
        is_hub.add(hub)

    # 4) per-cluster outgoing flow (union of member out-clusters) for context.
    cluster_out = {}  # letter -> set(other cluster letters)
    for letter, members in cluster_members.items():
        outs = set()
        for kw in members:
            outs |= kw_out_clusters.get(kw, set())
        outs.discard(letter)
        cluster_out[letter] = outs

    # 5) per-keyword rows (sorted by volume desc), capped for the CSV.
    keywords = []
    total_volume = 0
    for kw, letter in kw_cluster.items():
        info = kw_info.get(kw) or {}
        vavg = _num(info.get("volume_avg"))
        total_volume += vavg
        keywords.append({
            "keyword": kw,
            "cluster": letter,
            "volume_avg": vavg,
            "is_hub": kw in is_hub,
            "outgoing": sorted(kw_out_clusters.get(kw, set())),
            "intents": info.get("intents", {}),
        })
    keywords.sort(key=lambda k: k["volume_avg"], reverse=True)
    top_keywords = _select_context_keywords(keywords, top_n, cluster_min)

    # 6) per-cluster rollup (volume sum, keyword count, hub, out) for hub table.
    clusters = {}
    for letter, members in cluster_members.items():
        vol = sum(_vol(k) for k in members)
        clusters[letter] = {
            "cluster": letter,
            "keywordCount": len(members),
            "volume": int(round(vol)),
            "hub": hub_keywords.get(letter, []),
            "outgoing": sorted(cluster_out.get(letter, set())),
        }

    return {
        "seed": seed,
        "gl": gl,
        "date": date,
        "keywordCount": len(kw_cluster),
        "clusterCount": len(cluster_members),
        "edgeCount": len(rels),
        "totalVolume": int(round(total_volume)),
        "clusters": clusters,
        "clusterMembers": cluster_members,
        "hubKeywords": hub_keywords,
        "keywords": top_keywords,
        "csv": _build_csv(top_keywords, intent_labels),
    }


def _csv_field(value):
    s = str(value)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def _build_csv(keywords, intent_labels=None):
    """LLM analysis input. Columns mirror the internal agent_cluster context:
    n=keyword, v=volume_avg(월평균), c=cluster letter, h=is_hub(TRUE/FALSE),
    o=outgoing cluster letters(pipe-joined), i=대표 검색의도."""
    lines = ["n,v,c,h,o,i"]
    for kw in keywords:
        lines.append(",".join([
            _csv_field(kw["keyword"]),
            str(int(round(kw["volume_avg"]))),
            kw["cluster"],
            "TRUE" if kw["is_hub"] else "FALSE",
            "|".join(kw["outgoing"]),
            _dominant_intent(kw.get("intents") or {}, intent_labels),
        ]))
    return "\n".join(lines)


# ─────────────────────────────────────────
# groups — postprocess LLM 4-section output into cards + hub table + flows
# ─────────────────────────────────────────

def _vol_label(vol):
    return f"{int(round(vol)):,}" if vol > 0 else ""


def build_keyword_map(context):
    """{keyword: {volume_avg, cluster, is_hub}} lookup from the context's
    (capped) keywords list — the same set the LLM saw in the CSV."""
    return {
        k["keyword"]: {
            "volume_avg": k.get("volume_avg", 0),
            "cluster": k.get("cluster", ""),
            "is_hub": k.get("is_hub", False),
        }
        for k in context.get("keywords", [])
    }


def _members_of_clusters(cluster_letters, cluster_members, keyword_map):
    """Union of keywords in the given cluster letters, restricted to CSV-known
    keywords (anti-hallucination), sorted by volume desc."""
    seen = []
    for letter in cluster_letters:
        for kw in cluster_members.get(letter, []):
            if kw in keyword_map and kw not in seen:
                seen.append(kw)
    seen.sort(key=lambda kw: _num(keyword_map[kw]["volume_avg"]), reverse=True)
    return seen


def _evidence_for(keywords, keyword_map, top_n=EVIDENCE_TOP_N):
    scored = [(kw, _num((keyword_map.get(kw) or {}).get("volume_avg"))) for kw in keywords]
    sliced = scored if top_n is None else scored[:top_n]
    return [{"kw": kw, "volLabel": _vol_label(vol)} for kw, vol in sliced]


def _known_clusters(letters, cluster_members):
    return [l for l in (letters or []) if l in cluster_members]


def postprocess_groups(groups_raw, context):
    """Shape the LLM's {overview, clusterGroups, flows} into the render inputs:
    {overview, groups: [persona-card...], hubTable: [...], flows: [...]}.
    Python attaches every number (volume sums) and every hub keyword; the LLM
    supplies only grouping, names, and qualitative text. Cluster ids and member
    keywords are hard-filtered to what actually exists (anti-hallucination)."""
    cluster_members = context.get("clusterMembers", {})
    hub_keywords = context.get("hubKeywords", {})
    keyword_map = build_keyword_map(context)
    # 허브 키워드의 연결성(agent_cluster §3 '연결성: N개') = 그 키워드가 잇는
    # 다른 클러스터 수(= csv 의 o 컬럼 길이). context.keywords 에서 복원.
    kw_outgoing = {k["keyword"]: (k.get("outgoing") or []) for k in context.get("keywords", [])}

    groups = []
    hub_table = []
    for cg in (groups_raw.get("clusterGroups") or []):
        letters = _known_clusters(cg.get("memberClusters"), cluster_members)
        if not letters:
            continue
        members = _members_of_clusters(letters, cluster_members, keyword_map)
        if not members:
            continue
        vol = sum(_num(keyword_map[kw]["volume_avg"]) for kw in members)
        # hub keywords of the member clusters (dedup, keep CSV-known)
        hubs = []
        for letter in letters:
            for hk in hub_keywords.get(letter, []):
                if hk in keyword_map and hk not in hubs:
                    hubs.append(hk)
        kbf = [{"factor": "허브(대표) 키워드", "evidence_keywords": hubs}] if hubs else []
        groups.append({
            "name": cg.get("title", ""),
            "relation": "core",
            "stage": cg.get("character", ""),
            "who": cg.get("who") or "",
            "kbf": kbf,
            "insight": cg.get("insight") or "",
            "evidence": _evidence_for(members, keyword_map),
            "members": _evidence_for(members, keyword_map, top_n=None),
            "volumeLabel": _vol_label(vol),
            "memberCount": len(members),
            "clusterCount": len(letters),
            "clusterIds": letters,
            "_vol": vol,
        })
        hub_table.append({
            "groupName": cg.get("title", ""),
            "clusterIds": letters,
            "hubKeywords": hubs or [
                hk for letter in letters for hk in hub_keywords.get(letter, [])
            ],
        })

    groups.sort(key=lambda g: g["_vol"], reverse=True)
    hub_order = {g["name"]: i for i, g in enumerate(groups)}
    hub_table.sort(key=lambda h: hub_order.get(h["groupName"], 999))
    for g in groups:
        del g["_vol"]

    # From→To flows (Section 3): validate hub keyword + path clusters exist.
    flows = []
    for fl in (groups_raw.get("flows") or []):
        path = _known_clusters(fl.get("path"), cluster_members)
        if len(path) < 2:
            continue
        hub = fl.get("hubKeyword") or ""
        hub_vol = _vol_label(_num((keyword_map.get(hub) or {}).get("volume_avg"))) if hub in keyword_map else ""
        path_detail = [
            {"cluster": l, "hub": (hub_keywords.get(l) or [""])[0]} for l in path
        ]
        connectivity = len(kw_outgoing.get(hub, []))
        flows.append({
            "hubKeyword": hub,
            "hubVolLabel": hub_vol,
            "connectivity": connectivity,
            "character": fl.get("character") or "",
            "path": path,
            "pathDetail": path_detail,
            "insight": fl.get("insight") or "",
        })

    result = {"groups": groups, "hubTable": hub_table, "flows": flows}
    overview = groups_raw.get("overview")
    if overview:
        result["overview"] = overview
    return result


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def _cmd_enrich_plan(args):
    cluster_raw = _load_json(args.cluster)
    communities, rels = parse_cluster_response(cluster_raw)
    if not communities:
        print("ERROR: cluster_finder 응답에서 communities 를 찾지 못했습니다.", file=sys.stderr)
        return 1

    total = len({kw for members in communities.values() for kw in members})
    picked = select_enrich_keywords(communities, rels, top_n=args.top_n)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    # 이전 회차의 청크가 남아 있으면 병합 단계가 섞어 읽는다.
    for stale in outdir.glob("kw_params_*.json"):
        stale.unlink()

    chunk = max(1, args.chunk)
    n_chunks = (len(picked) + chunk - 1) // chunk
    for i in range(n_chunks):
        (outdir / f"kw_params_{i}.json").write_text(
            json.dumps({"keywords": picked[i * chunk:(i + 1) * chunk],
                        "gl": args.gl, "data_type": "all"}, ensure_ascii=False),
            encoding="utf-8")

    print(f"{len(picked):,} keywords to enrich → {n_chunks} chunk(s) in {outdir}")
    if len(picked) < total:
        print(f"  graph has {total:,} nodes; enriching the top {len(picked):,} by connection count "
              f"(cap {args.top_n:,}) — every cluster hub and >= {CLUSTER_MIN_KEYWORDS} keywords "
              f"per cluster are included")
        print(f"  the remaining {total - len(picked):,} would not have reached the csv "
              f"(cap {KEYWORD_CONTEXT_TOP_N:,}); cluster volume totals read ~2% lower as a result")
    else:
        print(f"  all {total:,} nodes fit under the {args.top_n:,} cap")
    return 0


def _cmd_context(args):
    cluster_raw = _load_json(args.cluster)
    kwinfo_raw = _load_json(args.keyword_info)
    communities, rels = parse_cluster_response(cluster_raw)
    if not communities:
        print("ERROR: cluster_finder 응답에서 communities 를 찾지 못했습니다.", file=sys.stderr)
        return 1
    kw_info = normalize_keyword_info(kwinfo_raw)
    intent_labels = load_intent_labels(getattr(args, "lang", None) or args.gl)

    # Never let the csv run past what was actually enriched. A row whose keyword has no
    # volume is dead weight: it carries v=0, sorts to the bottom and still occupies a slot
    # the LLM has to read. Callers that enrich fewer keywords than the cap (total-report
    # unions three finders and cuts at 1,000) would otherwise fill half the csv with zeros.
    enriched = sum(1 for kw in kw_info if _num((kw_info[kw] or {}).get("volume_avg")) > 0)
    top_n = args.top_n
    if enriched and enriched < top_n:
        print(f"  note: only {enriched:,} keywords came back with a volume — "
              f"capping the csv at that instead of {top_n:,}")
        top_n = enriched

    result = build_cluster_context(
        communities, rels, kw_info, seed=args.seed, gl=args.gl, date=args.date,
        top_n=top_n, intent_labels=intent_labels,
    )
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_rows = len(result["keywords"])
    print(f"wrote {args.out} ({result['clusterCount']} clusters, "
          f"{result['keywordCount']} keywords, {result['edgeCount']} edges)")
    # Say plainly how much of the graph reached the LLM. A silent cap reads as
    # "everything was analyzed" when a dense seed may have dropped thousands of rows.
    if csv_rows < result["keywordCount"]:
        dropped = result["keywordCount"] - csv_rows
        print(f"  csv for the LLM: {csv_rows:,} rows "
              f"(cap {top_n:,}; {dropped:,} of the graph's {result['keywordCount']:,} "
              f"nodes are not in it — peripheral, low-volume keywords; every cluster hub and "
              f">= {CLUSTER_MIN_KEYWORDS} keywords per cluster are kept)")
    else:
        print(f"  csv for the LLM: {csv_rows:,} rows (all keywords, under the "
              f"{top_n:,} cap)")
    return 0


def _cmd_groups(args):
    groups_raw = json.loads(Path(args.raw_groups).read_text(encoding="utf-8"))
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    result = postprocess_groups(groups_raw, context)
    if not result["groups"]:
        print("ERROR: LLM 클러스터 그룹 출력에서 유효한 그룹을 만들지 못했습니다.", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({len(result['groups'])} groups, "
          f"{len(result['flows'])} flows)")
    return 0


def _cmd_keywords(args):
    """리포트 화면에 실제로 박히는 키워드만 모아 준다 — 검색어 번역 단계의 입력.
    그룹 대표 검색어·허브 키워드·흐름도 노드까지 전부 포함한다. 여기 없는
    키워드를 번역해봐야 화면에 나오지 않는다."""
    doc = json.loads(Path(args.groups).read_text(encoding="utf-8"))
    ordered, seen = [], set()

    def add(kw):
        if kw and kw not in seen:
            seen.add(kw)
            ordered.append(kw)

    # 표지·목적 문구에 박히는 씨드 검색어도 화면에 보이므로 번역 대상이다.
    add(args.category)

    for group in doc.get("groups", []):
        for row in (group.get("members") or []) + (group.get("evidence") or []):
            add(row.get("kw"))
        for kbf in (group.get("kbf") or []):
            for kw in (kbf.get("evidence_keywords") or []):
                add(kw)
    for row in doc.get("hubTable", []):
        for kw in (row.get("hubKeywords") or []):
            add(kw)
    for flow in doc.get("flows", []):
        add(flow.get("hub"))
        for step in (flow.get("pathDetail") or []):
            add(step.get("hub"))

    Path(args.out).write_text(
        json.dumps({"keywords": ordered}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"wrote {args.out} · {len(ordered)} keywords")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Cluster Finder data pipeline: graph+enrichment context builder + LLM group postprocessing."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser(
        "enrich-plan",
        help="Pick the keywords to send to keyword_info and write one params file per chunk")
    p_plan.add_argument("--cluster", required=True, help="/cluster_finder 응답 JSON 경로 (data_type=all)")
    p_plan.add_argument("--gl", required=True, choices=["kr", "jp", "us"])
    p_plan.add_argument("--outdir", required=True, help="kw_params_<N>.json 을 쓸 폴더 (= WORKDIR)")
    p_plan.add_argument("--top-n", type=int, default=KEYWORD_ENRICH_TOP_N,
                        help=f"조회 상한 (기본 {KEYWORD_ENRICH_TOP_N})")
    p_plan.add_argument("--chunk", type=int, default=1000, help="청크 크기 (keyword_info maxItems=1000)")
    p_plan.set_defaults(func=_cmd_enrich_plan)

    p_context = sub.add_parser("context", help="Fuse cluster_finder + keyword_info into lm_cluster_result.json")
    p_context.add_argument("--cluster", required=True, help="/cluster_finder 응답 JSON 경로 (data_type=all)")
    p_context.add_argument("--keyword-info", required=True, help="/keyword_info 응답 JSON 경로")
    p_context.add_argument("--seed", required=True)
    p_context.add_argument("--gl", required=True, choices=["kr", "jp", "us"])
    p_context.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_context.add_argument("--lang", choices=["kr", "jp", "us"],
                           help="CSV 의 의도 라벨 언어 (리포트 언어). 생략하면 --gl 을 따른다 — "
                                "CSV 는 LLM 입력이고 그 출력이 리포트 언어로 나가므로 맞춰 주는 편이 낫다")
    p_context.add_argument("--out", required=True)
    p_context.add_argument("--top-n", type=int, default=KEYWORD_CONTEXT_TOP_N,
                           help=f"CSV 행 상한 (기본 {KEYWORD_CONTEXT_TOP_N}). "
                                "조회한 키워드가 이보다 적으면 그 수에 맞춰 낮춰 준다 — "
                                "그러지 않으면 검색량 0 인 행이 CSV 절반을 채운다 "
                                "(total-report 는 3개 파인더 합집합을 1,000개로 끊어 "
                                "조회하므로 --top-n 1000 으로 부른다)")
    p_context.set_defaults(func=_cmd_context)

    p_groups = sub.add_parser("groups", help="Postprocess LLM group output + context into lm_groups.json")
    p_groups.add_argument("--raw-groups", required=True, help="LLM lm_groups_raw.json 경로")
    p_groups.add_argument("--context", required=True, help="lm_cluster_result.json 경로")
    p_groups.add_argument("--out", required=True)
    p_groups.set_defaults(func=_cmd_groups)

    p_kw = sub.add_parser(
        "keywords",
        help="List the keywords that actually appear in the report (for translation)")
    p_kw.add_argument("--groups", required=True, help="lm_groups.json 경로")
    p_kw.add_argument("--category", required=True, help="씨드 검색어 — 표지에 박히므로 함께 번역한다")
    p_kw.add_argument("--out", required=True)
    p_kw.set_defaults(func=_cmd_keywords)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
