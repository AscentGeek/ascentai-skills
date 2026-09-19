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
# 지배 의도 라벨 (agent_cluster 는 '검색 의도 축'을 정성 해석하므로 대표 라벨만 CSV 로 전달)
INTENT_LABEL = {"i": "정보탐색", "n": "길찾기", "c": "상업조사", "t": "거래"}

# keyword_info 상세 조회 상한(공개 API maxItems) 과 동일. LLM CSV 도 이 상한으로 캡.
KEYWORD_CONTEXT_TOP_N = 1000
# 카드 evidence·허브 표에 노출할 대표 키워드 수(검색량순).
EVIDENCE_TOP_N = 8


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


def _dominant_intent(intents):
    if not intents:
        return ""
    total = sum((intents.get(k, 0) or 0) for k in INTENT_KEYS)
    if total <= 0:
        return ""
    return INTENT_LABEL[max(INTENT_KEYS, key=lambda k: intents.get(k, 0) or 0)]


# ─────────────────────────────────────────
# context — fuse graph + enrichment into lm_cluster_result.json
# ─────────────────────────────────────────

def build_cluster_context(communities, rels, kw_info, seed, gl, date, top_n=KEYWORD_CONTEXT_TOP_N):
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
    top_keywords = keywords[:top_n]

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
        "csv": _build_csv(top_keywords),
    }


def _csv_field(value):
    s = str(value)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def _build_csv(keywords):
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
            _dominant_intent(kw.get("intents") or {}),
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

def _cmd_context(args):
    cluster_raw = _load_json(args.cluster)
    kwinfo_raw = _load_json(args.keyword_info)
    communities, rels = parse_cluster_response(cluster_raw)
    if not communities:
        print("ERROR: cluster_finder 응답에서 communities 를 찾지 못했습니다.", file=sys.stderr)
        return 1
    kw_info = normalize_keyword_info(kwinfo_raw)
    result = build_cluster_context(
        communities, rels, kw_info, seed=args.seed, gl=args.gl, date=args.date
    )
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({result['clusterCount']} clusters, "
          f"{result['keywordCount']} keywords, {result['edgeCount']} edges)")
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

    p_context = sub.add_parser("context", help="Fuse cluster_finder + keyword_info into lm_cluster_result.json")
    p_context.add_argument("--cluster", required=True, help="/cluster_finder 응답 JSON 경로 (data_type=all)")
    p_context.add_argument("--keyword-info", required=True, help="/keyword_info 응답 JSON 경로")
    p_context.add_argument("--seed", required=True)
    p_context.add_argument("--gl", required=True, choices=["kr", "jp", "us"])
    p_context.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_context.add_argument("--out", required=True)
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
