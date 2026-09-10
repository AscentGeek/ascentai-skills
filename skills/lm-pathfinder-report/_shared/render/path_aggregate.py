#!/usr/bin/env python3
"""Aggregate ListeningMind path_finder (Path Finder) responses into the report
data JSON consumed by render_report.py --skill path-opportunity.

Path Finder returns pure journey paths — data: List[List[str]] — with NO
per-node metrics. So this pipeline mirrors how the production PathFinder agent
sees data (PathDataDTO: paths + info + intent) by reproducing the internal
`get_path_info` shape from two public tool calls:

  1) path_finder  -> the graph structure (ordered keyword journeys / edges)
  2) keyword_info -> per-node volume / intent / trend for every node in the graph

`context` merges the two into a graph (nodes + derived edges + hub metrics + a
flow tree) and emits the CSV/text the LLM grouping step (step 3) consumes.
`paths` post-processes the LLM's Top-5-paths + 3-hubs output, attaching the
Python-computed facts (volumes, out-degree, downstream) and hard-filtering any
hallucinated keyword that isn't a real node.

The analytical frame is ported from the in-repo PathFinder fallback prompt
DEFAULT_PROMPTS["path"] (ascentkorea-hubble-ai-api prompt_builder.py:56-109):
structure/flow uses id/name/volume/edges; strategy uses intent/cpc/cmp. Node,
path and hub ranking is by `volume` (월평균 검색량), the agent's primary metric.

Standard library only — no third-party deps needed in Claude Desktop.
Envelope-tolerant: accepts the public data-API flat form ({"data": [...]}) and
the internal form ({"result": {"paths": [...]}}).
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


INTENT_KEYS = ("i", "n", "c", "t")

# process_path caps nodes at MAX_KEYWORDS=1000 by descending volume
# (context_processor.py:21). We keep the full node set for facts but cap the
# per-node CSV / paths text handed to the LLM to keep the token budget sane.
NODE_CSV_TOP_N = 400        # candidate nodes exposed to the LLM (by volume)
PATHS_TEXT_TOP_N = 60       # candidate journeys exposed to the LLM (by volume)
HUBS_CSV_TOP_N = 40         # candidate hubs exposed to the LLM (by out-degree)
DOWNSTREAM_TOP_N = 6        # downstream keywords shown per hub
EVIDENCE_TOP_N = 8          # representative keywords per path card

# 여정 흐름도(flow tree) — 데이터에서 직접 뽑는 상위 여정의 분기 트리.
FLOW_MAX_PATHS = 24
FLOW_MAX_DEPTH = 4
FLOW_MAX_CHILDREN = 4
FLOW_MAX_ROOTS = 5


# ─────────────────────────────────────────────────────────────────────────
# Coercion / small helpers (mirrors query_aggregate._num semantics)
# ─────────────────────────────────────────────────────────────────────────

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

    keyword_info metric types are unverified: a numeric field may arrive as a
    JSON string (e.g. volume_avg: "74000"). Without coercion this crashes
    sorting/formatting downstream.
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


def _vol_label(vol):
    return f"{int(round(vol)):,}" if vol and vol > 0 else ""


def primary_intent(intents):
    if not intents:
        return ""
    best = max(INTENT_KEYS, key=lambda k: _num(intents.get(k, 0)))
    # An all-zero intents dict is still truthy, so `not intents` doesn't catch
    # it and max() would return "i" — mislabeling a signal-less node as
    # informational. Blank it instead (matches the guarded context primaryIntent
    # and nodes absent from keyword_info, which both yield "").
    return best if _num(intents.get(best, 0)) > 0 else ""


# ─────────────────────────────────────────────────────────────────────────
# Input normalization
# ─────────────────────────────────────────────────────────────────────────

def normalize_paths(raw):
    """Return List[List[str]] of journeys from a path_finder response.

    Accepts the public flat form ({"data": [[...], ...]}) and the internal
    form ({"result": {"paths": [[...], ...]}}); also a bare list.
    """
    data = None
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            data = raw["data"]
        elif isinstance(raw.get("result"), dict) and isinstance(raw["result"].get("paths"), list):
            data = raw["result"]["paths"]
        elif isinstance(raw.get("paths"), list):
            data = raw["paths"]

    paths = []
    for row in (data or []):
        if not isinstance(row, list):
            continue
        seq = []
        for x in row:
            if isinstance(x, str) and x.strip():
                seq.append(x.strip())
        # de-dupe immediate repeats (A -> A) which would be self-loops
        deduped = [kw for i, kw in enumerate(seq) if i == 0 or kw != seq[i - 1]]
        if deduped:
            paths.append(deduped)
    return paths


def normalize_node_records(raw):
    """Return {keyword -> {volume_avg, volume_total, volume_trend, intents,
    monthly_volume, cpc, competition_index}} from a keyword_info response.

    Envelope-tolerant like query_aggregate.normalize_records. Missing/typed-off
    fields degrade to empty/zero rather than crashing.
    """
    rows = []
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("data"), list):
            rows = raw["data"]
        elif isinstance(raw.get("data"), dict) and isinstance(raw["data"].get("results"), list):
            rows = raw["data"]["results"]
        elif isinstance(raw.get("result"), dict):
            rows = raw["result"].get("hits", {}).get("hits", [])
        elif isinstance(raw.get("hits"), dict):
            rows = raw["hits"].get("hits", [])
        elif isinstance(raw.get("results"), list):
            rows = raw["results"]

    node_info = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = row["_source"] if isinstance(row.get("_source"), dict) else row
        keyword = src.get("keyword")
        if not keyword or not isinstance(keyword, str):
            continue
        am = src.get("ads_metrics")
        am = am if isinstance(am, dict) else {}
        intents = src.get("intents")
        intents = {k: _num(v) for k, v in intents.items()} if isinstance(intents, dict) else {}
        mv = src.get("monthly_volume")
        node_info[keyword.strip()] = {
            "volume_avg": _num(am.get("volume_avg")),
            "volume_total": _num(am.get("volume_total")),
            "volume_trend": _num(am.get("volume_trend")),
            "cpc": _num(am.get("cpc")),
            "competition_index": _num(am.get("competition_index")),
            "intents": {k: _num(intents.get(k, 0)) for k in INTENT_KEYS},
            "monthly_volume": mv if isinstance(mv, list) else [],
        }
    return node_info


# ─────────────────────────────────────────────────────────────────────────
# Graph construction
# ─────────────────────────────────────────────────────────────────────────

def build_graph(paths, node_info):
    """Turn journeys + node metrics into the node/edge/hub/path graph.

    Edges are derived from `paths` adjacency exactly as the production
    ContextProcessor.process_path does (context_processor.py:717-738): each
    consecutive (prev, next) pair is an edge; a node's out-degree = number of
    distinct downstream nodes = its "분기(branch)" count.
    """
    out_edges = defaultdict(Counter)   # kw -> Counter(next_kw -> transition weight)
    in_edges = defaultdict(Counter)    # kw -> Counter(prev_kw -> weight)
    node_pathcount = Counter()         # kw -> number of paths passing through it

    all_kws = []
    seen_kw = set()
    for path in paths:
        for kw in dict.fromkeys(path):        # unique per path
            node_pathcount[kw] += 1
            if kw not in seen_kw:
                seen_kw.add(kw)
                all_kws.append(kw)
        for a, b in zip(path, path[1:]):
            out_edges[a][b] += 1
            in_edges[b][a] += 1

    nodes = {}
    for kw in all_kws:
        info = node_info.get(kw, {})
        nodes[kw] = {
            "keyword": kw,
            "volume_avg": _num(info.get("volume_avg")),
            "volume_trend": _num(info.get("volume_trend")),
            "intents": info.get("intents", {k: 0 for k in INTENT_KEYS}),
            "primary_intent": primary_intent(info.get("intents", {})),
            "pathCount": node_pathcount[kw],
            "outDegree": len(out_edges[kw]),
            "inDegree": len(in_edges[kw]),
            "outWeight": sum(out_edges[kw].values()),
        }

    edge_count = sum(len(c) for c in out_edges.values())
    return nodes, out_edges, in_edges, edge_count


def _path_volume(seq, nodes):
    return sum(_num(nodes.get(kw, {}).get("volume_avg")) for kw in seq)


def _rank_paths(paths, nodes):
    """Rank journeys by total node volume (demand along the journey), then hops.
    Volume is the PathFinder agent's primary ranking metric."""
    scored = []
    for seq in paths:
        vol = _path_volume(seq, nodes)
        scored.append({
            "seq": seq,
            "totalVolume": vol,
            "hops": len(seq),
        })
    scored.sort(key=lambda p: (p["totalVolume"], p["hops"]), reverse=True)
    return scored


def _downstream_list(kw, out_edges, nodes):
    """Downstream neighbors of a node, sorted by volume desc. Uses .get to
    avoid mutating the out_edges defaultdict for nodes with no out-edges."""
    counter = out_edges.get(kw)
    if not counter:
        return []
    ds = [{"kw": nb, "volLabel": _vol_label(_num(nodes.get(nb, {}).get("volume_avg")))}
          for nb in counter]
    ds.sort(key=lambda d: _num(nodes.get(d["kw"], {}).get("volume_avg")), reverse=True)
    return ds


def _rank_hubs(nodes, out_edges, top_n=HUBS_CSV_TOP_N):
    """Hubs = high fan-out branch points. Rank by out-degree (분기 수), then
    volume — the two signals the agent uses to pick '가장 중요한 분기점'."""
    candidates = [n for n in nodes.values() if n["outDegree"] >= 2]
    candidates.sort(key=lambda n: (n["outDegree"], n["volume_avg"], n["pathCount"]), reverse=True)
    hubs = []
    for n in candidates[:top_n]:
        kw = n["keyword"]
        hubs.append({
            "keyword": kw,
            "volume_avg": n["volume_avg"],
            "outDegree": n["outDegree"],
            "pathCount": n["pathCount"],
            "downstream": _downstream_list(kw, out_edges, nodes),
        })
    return hubs


def build_flow_tree(ranked_paths, nodes,
                    max_paths=FLOW_MAX_PATHS, max_depth=FLOW_MAX_DEPTH,
                    max_children=FLOW_MAX_CHILDREN, max_roots=FLOW_MAX_ROOTS):
    """A prefix-merge trie of the top journeys — the 여정 흐름도. Shared prefixes
    across the highest-volume paths merge into branches, so the diagram shows
    where journeys converge and where they fork. Depth/breadth capped for
    readability; branches ordered by node volume."""
    forest = {}
    for p in ranked_paths[:max_paths]:
        level = forest
        for kw in p["seq"][:max_depth]:
            node = level.setdefault(kw, {"kw": kw, "count": 0, "children": {}})
            node["count"] += 1
            level = node["children"]

    def conv(level, depth):
        items = list(level.values())
        items.sort(
            key=lambda n: (_num(nodes.get(n["kw"], {}).get("volume_avg")), n["count"]),
            reverse=True,
        )
        cap = max_roots if depth == 0 else max_children
        out = []
        for n in items[:cap]:
            vol = _num(nodes.get(n["kw"], {}).get("volume_avg"))
            out.append({
                "kw": n["kw"],
                "volLabel": _vol_label(vol),
                "pathCount": n["count"],
                "primary_intent": nodes.get(n["kw"], {}).get("primary_intent", ""),
                "children": conv(n["children"], depth + 1),
            })
        return out

    return conv(forest, 0)


def _build_paths_text(ranked_paths, top_n=PATHS_TEXT_TOP_N):
    lines = []
    for i, p in enumerate(ranked_paths[:top_n], 1):
        chain = " → ".join(p["seq"])
        vol = int(round(p["totalVolume"]))
        lines.append(f"{i}. {chain}  (합산 검색량 {vol:,})")
    return "\n".join(lines)


def _build_hubs_csv(hubs):
    lines = ["name,volume,out_degree,path_count,downstream"]
    for h in hubs:
        ds = " | ".join(d["kw"] for d in h["downstream"][:DOWNSTREAM_TOP_N])
        name = h["keyword"].replace('"', '""')
        ds = ds.replace('"', '""')
        lines.append(f'"{name}",{int(round(h["volume_avg"]))},{h["outDegree"]},{h["pathCount"]},"{ds}"')
    return "\n".join(lines)


def _intent_label_codes(intents):
    """Return the sorted list of intent codes present (>0), e.g. ["i","c"]."""
    return [k for k in INTENT_KEYS if _num(intents.get(k, 0)) > 0]


def _build_nodes_csv(nodes, out_edges, top_n=NODE_CSV_TOP_N):
    """Node table for the LLM: id,name,volume,volume_trend,intent,out_degree,
    path_count,outgoing — mirrors process_path columns. Only nodes kept in the
    cap get ids; `outgoing` references those ids."""
    top = sorted(nodes.values(), key=lambda n: n["volume_avg"], reverse=True)[:top_n]
    id_of = {n["keyword"]: i for i, n in enumerate(top)}
    lines = ["id,name,volume,volume_trend,intent,out_degree,path_count,outgoing"]
    for n in top:
        kw = n["keyword"]
        outgoing = [id_of[nb] for nb in out_edges.get(kw, {}) if nb in id_of]
        # intent codes joined with '|' (NOT json.dumps, whose ["i", "c"] output
        # embeds a comma that would shift every subsequent CSV column). Wrapped
        # in quotes for good measure; the codes themselves are comma-free.
        intents = "|".join(_intent_label_codes(n["intents"]))
        name = kw.replace('"', '""')
        lines.append(
            f'{id_of[kw]},"{name}",{int(round(n["volume_avg"]))},'
            f'{n["volume_trend"]},"{intents}",{n["outDegree"]},{n["pathCount"]},'
            f'"{json.dumps(outgoing)}"'
        )
    return "\n".join(lines)


def build_path_context(paths, node_info, seed, gl, date, time_point):
    nodes, out_edges, in_edges, edge_count = build_graph(paths, node_info)
    ranked_paths = _rank_paths(paths, nodes)
    hubs = _rank_hubs(nodes, out_edges)
    flow_tree = build_flow_tree(ranked_paths, nodes)

    total_volume = sum(n["volume_avg"] for n in nodes.values())
    intent_totals = {k: 0 for k in INTENT_KEYS}
    for n in nodes.values():
        for k in INTENT_KEYS:
            intent_totals[k] += _num(n["intents"].get(k, 0))
    prim = max(INTENT_KEYS, key=lambda k: intent_totals[k]) if sum(intent_totals.values()) > 0 else ""

    # node list for facts (postprocess keyword_map + meta), capped generously
    node_list = sorted(nodes.values(), key=lambda n: n["volume_avg"], reverse=True)

    # downstream for EVERY branch node (not just the top-40 hub candidates), so a
    # hub the LLM picks below the hubsCsv cap still gets its downstream chips.
    downstream_map = {
        kw: _downstream_list(kw, out_edges, nodes)[:DOWNSTREAM_TOP_N]
        for kw in nodes if out_edges.get(kw)
    }

    return {
        "seed": seed,
        "gl": gl,
        "date": date,
        "timePoint": time_point,
        "nodeCount": len(nodes),
        "pathCount": len(paths),
        "edgeCount": edge_count,
        "hubCount": len([n for n in nodes.values() if n["outDegree"] >= 2]),
        "totalVolume": int(total_volume),
        "primaryIntent": prim,
        "nodes": node_list,
        "paths": ranked_paths,
        "hubs": hubs,
        "flowTree": flow_tree,
        "downstreamMap": downstream_map,
        # LLM step-3 inputs
        "pathsText": _build_paths_text(ranked_paths),
        "hubsCsv": _build_hubs_csv(hubs),
        "nodesCsv": _build_nodes_csv(nodes, out_edges),
    }


# ─────────────────────────────────────────────────────────────────────────
# Post-processing the LLM output (step 4) — attach facts, filter hallucinations
# ─────────────────────────────────────────────────────────────────────────

FLOW_KIND = {
    "conversion": "conversion",
    "comparison": "comparison",
    "risk": "risk",
}


def build_keyword_map(context):
    return {
        n["keyword"]: {
            "volume_avg": _num(n.get("volume_avg")),
            "volume_trend": _num(n.get("volume_trend")),
            "outDegree": n.get("outDegree", 0),
            "pathCount": n.get("pathCount", 0),
            "primary_intent": n.get("primary_intent", ""),
        }
        for n in context.get("nodes", [])
    }


def _hub_downstream_map(context):
    # Prefer the full per-node downstream map (covers hubs the LLM picks below
    # the hubsCsv top-40 cap); fall back to the capped hubs list for older
    # context files that predate downstreamMap.
    dmap = context.get("downstreamMap")
    if isinstance(dmap, dict):
        return dmap
    return {h["keyword"]: h.get("downstream", []) for h in context.get("hubs", [])}


def _known(keywords, keyword_map):
    return [kw for kw in (keywords or []) if kw in keyword_map]


def _chips_for(keywords, keyword_map, top_n=None):
    scored = [(kw, _num((keyword_map.get(kw) or {}).get("volume_avg"))) for kw in (keywords or [])]
    if top_n is not None:
        scored = sorted(scored, key=lambda p: p[1], reverse=True)[:top_n]
    return [{"kw": kw, "volLabel": _vol_label(vol)} for kw, vol in scored]


def postprocess_paths(raw, keyword_map, downstream_map):
    """Shape the LLM {"overview","topPaths","hubs"} into lm_paths.json.

    Facts (volumes, out-degree, downstream) are attached by Python; the LLM only
    supplies path selection, flow classification and qualitative text. Every
    keyword referenced (path nodes, evidence, hub) is hard-filtered to real
    graph nodes so a hallucinated keyword can never surface as report evidence.
    """
    out_paths = []
    for tp in (raw.get("topPaths") or []):
        seq = _known(tp.get("path"), keyword_map)
        if len(seq) < 2:
            continue  # a "journey" needs at least one real transition
        flow = FLOW_KIND.get(str(tp.get("flowType", "")).lower().strip(), "comparison")
        total_vol = sum(_num((keyword_map.get(kw) or {}).get("volume_avg")) for kw in seq)
        evidence = _chips_for(_known(tp.get("evidenceKeywords"), keyword_map), keyword_map, EVIDENCE_TOP_N)
        out_paths.append({
            "flowType": flow,
            "nodes": _chips_for(seq, keyword_map),   # keep journey order
            "intent": (tp.get("intent") or "").strip(),
            "leakOrMerge": (tp.get("leakOrMerge") or "").strip(),
            "action": (tp.get("action") or "").strip(),
            "evidence": evidence,
            "volumeLabel": _vol_label(total_vol),
            "hops": len(seq),
            "_vol": total_vol,
        })

    # order: conversion first (strongest), comparison, risk last; by volume within
    flow_rank = {"conversion": 0, "comparison": 1, "risk": 2}
    out_paths.sort(key=lambda p: (flow_rank.get(p["flowType"], 1), -p["_vol"]))
    for p in out_paths:
        del p["_vol"]

    out_hubs = []
    for h in (raw.get("hubs") or []):
        kw = h.get("keyword")
        if kw not in keyword_map:
            continue
        km = keyword_map[kw]
        dilemmas = [d for d in (h.get("dilemmas") or []) if isinstance(d, str) and d.strip()]
        actions = [a for a in (h.get("actions") or []) if isinstance(a, str) and a.strip()]
        out_hubs.append({
            "keyword": kw,
            "volumeLabel": _vol_label(km.get("volume_avg")),
            "outDegree": km.get("outDegree", 0),
            "meaning": (h.get("meaning") or "").strip(),
            "dilemmas": dilemmas,
            "actions": actions,
            "downstream": downstream_map.get(kw, [])[:DOWNSTREAM_TOP_N],
        })
    out_hubs.sort(key=lambda h: (h["outDegree"], _num(keyword_map.get(h["keyword"], {}).get("volume_avg"))), reverse=True)

    result = {"paths": out_paths, "hubs": out_hubs}
    overview = raw.get("overview")
    if overview:
        result["overview"] = overview
    return result


# ─────────────────────────────────────────
# CLI — subcommands
# ─────────────────────────────────────────

def _cmd_context(args):
    raw_paths = _load_json(args.paths)
    paths = normalize_paths(raw_paths)
    if not paths:
        print("ERROR: path_finder 응답에서 경로(paths)를 찾지 못했습니다.", file=sys.stderr)
        return 1
    node_info = {}
    if args.nodes:
        raw_nodes = _load_json(args.nodes)
        node_info = normalize_node_records(raw_nodes)
    result = build_path_context(paths, node_info, args.seed, args.gl, args.date, args.time_point)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({result['nodeCount']} nodes, {result['pathCount']} paths, "
          f"{result['edgeCount']} edges, {result['hubCount']} hubs)")
    return 0


def _cmd_paths(args):
    raw = json.loads(Path(args.raw_paths).read_text(encoding="utf-8"))
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    keyword_map = build_keyword_map(context)
    downstream_map = _hub_downstream_map(context)
    result = postprocess_paths(raw, keyword_map, downstream_map)
    if not result["paths"] and not result["hubs"]:
        print("ERROR: LLM 경로/허브 출력에서 유효한 항목을 만들지 못했습니다(전부 환각 필터).", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({len(result['paths'])} paths, {len(result['hubs'])} hubs)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Path Finder data pipeline: journey-graph context builder + path/hub postprocessing."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_ctx = sub.add_parser("context", help="Merge path_finder + keyword_info into lm_path_result.json")
    p_ctx.add_argument("--paths", required=True, help="path_finder 응답 JSON 경로")
    p_ctx.add_argument("--nodes", required=False, help="keyword_info 응답 JSON 경로 (검색량 보강)")
    p_ctx.add_argument("--seed", required=True)
    p_ctx.add_argument("--gl", required=True, choices=["kr"])
    p_ctx.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_ctx.add_argument("--time-point", default="curr", dest="time_point")
    p_ctx.add_argument("--out", required=True)
    p_ctx.set_defaults(func=_cmd_context)

    p_paths = sub.add_parser("paths", help="Postprocess LLM path/hub output into lm_paths.json")
    p_paths.add_argument("--raw-paths", required=True, help="LLM lm_paths_raw.json 경로")
    p_paths.add_argument("--context", required=True, help="lm_path_result.json 경로")
    p_paths.add_argument("--out", required=True)
    p_paths.set_defaults(func=_cmd_paths)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
