#!/usr/bin/env python3
"""Cross-finder aggregator for the redesigned 통합 요약 (total-insight) tab.

Joins the three finders' EXISTING outputs (query / path / cluster) on
`keyword.strip()` exact (no case-fold) and computes the 6 cross-finder modules,
emitting `{WORKDIR}/lm_total_facts.json` — numbers + structure ONLY (facts), every
item carrying a stable id. The LLM step (lm_total.json) owns only id-keyed
qualitative notes; the renderer merges facts + notes by id, so a note whose id is
absent from facts is simply ignored (hallucination is structurally impossible).

Standard library only. Subcommand: `total`.

Inputs (only present finders are read; graceful reduction, query + ≥1 more):
  query   : q/lm_query_result.json (.keywords[]) + q/lm_groups.json (.groups[])
  path    : p/lm_path_result.json (.nodes[]/.paths[]/.hubs[]/.downstreamMap) + p/lm_paths.json
  cluster : c/lm_cluster_result.json (.keywords[]/.clusters/.clusterMembers/.hubKeywords) + c/lm_groups.json

Critic fixes applied (see docs/total-insight-redesign.spec.md §비평 반영):
  - honesty: present/absent framed as coverage difference + coveragePct, never "market gap".
  - cluster hub axis = cross-cluster connectivity (is_hub + outgoing), NOT centrality.
  - NO flowType numeric weighting in value-leak (structural signals only, reproducible).
  - downstream concentration is hub-limited (re-join kw→volume, never parse volLabel strings).
  - volume_trend promoted to a 1st-class momentum signal; cluster-only items get momentum 0.
  - brand (query relation='alternative') defense kept as its own backlog/leak track (n=0.0 guard).
"""

import argparse
import bisect
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

INTENT_KEYS = ("i", "n", "c", "t")
INTENT_WEIGHT = {"i": 0.2, "n": 0.0, "c": 0.5, "t": 1.0}  # 수익 의도 지수 M 가중
FORMAT_LABEL = {"i": "가이드", "n": "브랜드", "c": "비교", "t": "제품"}

STAGES = ("entry", "mid", "exit")

# tuning parameters (exposed as module constants per discipline)
DEADEND_MIN_PATHS = 2      # value-leak dead-end: min pathCount to count a terminal node
BRIDGE_MIN_TRANS = 2       # corridor: min fwd+rev transitions or verdict=inconclusive
BRIDGE_DIR_THR = 0.34      # |directionality| above which a direction is "dominant"
VOL_MISMATCH_TOL = 0.10    # relative volume gap above which a keyword is flagged mismatched
TREND_CLIP = 30.0          # volume_trend magnitude that maps to full momentum (±1)
BACKLOG_CAP = 5            # max items per Now/Next/Later bucket
STRUCT_W = (0.6, 0.4)      # (w1 journey, w2 cluster) for structure_strength
STRUCT_EPS = 0.2           # ε in opportunity ÷ (structure+ε)


# ─────────────────────────────────────────────────────────────────────────
# small helpers
# ─────────────────────────────────────────────────────────────────────────

def _num(v, default=0):
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


def _read_json(path):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _coalesce(*vals):
    for v in vals:
        if v:
            return v
    return 0


def M_of(intents):
    """수익 의도 지수 M ∈ [0,1] — INTENT_WEIGHT 가중 평균."""
    if not intents:
        return 0.0
    tot = sum(_num(intents.get(k, 0)) for k in INTENT_KEYS)
    if tot <= 0:
        return 0.0
    return sum(INTENT_WEIGHT[k] * _num(intents.get(k, 0)) for k in INTENT_KEYS) / tot


def _dominant_intent(intents):
    if not intents:
        return ""
    best = max(INTENT_KEYS, key=lambda k: _num(intents.get(k, 0)))
    return best if _num(intents.get(best, 0)) > 0 else ""


def _pct_rank(v, sorted_vals):
    """Percentile rank of v within sorted_vals → [0,1] (mid-rank for ties)."""
    n = len(sorted_vals)
    if n == 0:
        return 0.0
    if n == 1:
        return 1.0
    lo = bisect.bisect_left(sorted_vals, v)
    hi = bisect.bisect_right(sorted_vals, v)
    return ((lo + hi) / 2.0) / n


def _norm_fn(values):
    """Return a min-max normalizer over the given values → [0,1]."""
    vals = [x for x in values]
    if not vals:
        return lambda x: 0.0
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return (lambda x: 1.0) if hi > 0 else (lambda x: 0.0)
    return lambda x: max(0.0, min(1.0, (x - lo) / (hi - lo)))


def _vol_label(v):
    return f"{int(round(v)):,}" if v and v > 0 else ""


def _r(v, n=4):
    return round(v, n)


# ─────────────────────────────────────────────────────────────────────────
# Loading + master join table
# ─────────────────────────────────────────────────────────────────────────

def load_finders(args):
    """Return dict of the present finders' parsed docs (+ which are present)."""
    f = {}
    q_meta = _read_json(args.query_meta)
    q_groups = _read_json(args.query_groups)
    if q_meta and isinstance(q_meta.get("keywords"), list):
        f["query"] = {"meta": q_meta, "groups": q_groups or {}}

    p_meta = _read_json(args.path_meta)
    p_paths = _read_json(args.path_paths)
    if p_meta and isinstance(p_meta.get("nodes"), list):
        f["path"] = {"meta": p_meta, "paths": p_paths or {}}

    c_meta = _read_json(args.cluster_meta)
    c_groups = _read_json(args.cluster_groups)
    if c_meta and isinstance(c_meta.get("keywords"), list):
        f["cluster"] = {"meta": c_meta, "groups": c_groups or {}}
    return f


def _persona_index(groups_doc):
    """kw -> [group name,...] and ordered list of {name,relation,members[]}."""
    kw2p = defaultdict(list)
    personas = []
    for g in (groups_doc or {}).get("groups", []) or []:
        name = g.get("name", "")
        members = [m.get("kw") for m in (g.get("members") or []) if isinstance(m, dict) and m.get("kw")]
        personas.append({"name": name, "relation": g.get("relation", ""),
                          "stage": g.get("stage", ""), "members": members,
                          "clusterIds": g.get("clusterIds") or []})
        for kw in members:
            kw2p[kw].append(name)
    return kw2p, personas


def build_master(f):
    """Master join table KW[kw] = merged per-keyword facts across finders."""
    KW = {}

    def ensure(kw):
        if kw not in KW:
            KW[kw] = {
                "kw": kw,
                "q_present": False, "q_vol": 0, "q_trend": 0, "q_intents": {},
                "p_present": False, "p_vol": 0, "p_trend": 0, "p_intents": {},
                "p_primary": "", "p_outDeg": 0, "p_inDeg": 0, "p_pathCount": 0,
                "c_present": False, "c_vol": 0, "c_cluster": "", "c_is_hub": False,
                "c_outgoing": [], "c_intents": {},
                "persona_query": [], "persona_cluster": [],
            }
        return KW[kw]

    if "query" in f:
        q_kw2p, _ = _persona_index(f["query"]["groups"])
        for r in f["query"]["meta"]["keywords"]:
            kw = (r.get("keyword") or "").strip()
            if not kw:
                continue
            row = ensure(kw)
            row["q_present"] = True
            row["q_vol"] = _num(r.get("volume_avg"))
            row["q_trend"] = _num(r.get("volume_trend"))
            row["q_intents"] = {k: _num((r.get("intents") or {}).get(k, 0)) for k in INTENT_KEYS}
            row["persona_query"] = q_kw2p.get(kw, [])

    if "path" in f:
        for n in f["path"]["meta"]["nodes"]:
            kw = (n.get("keyword") or "").strip()
            if not kw:
                continue
            row = ensure(kw)
            row["p_present"] = True
            row["p_vol"] = _num(n.get("volume_avg"))
            row["p_trend"] = _num(n.get("volume_trend"))
            row["p_intents"] = {k: _num((n.get("intents") or {}).get(k, 0)) for k in INTENT_KEYS}
            row["p_primary"] = n.get("primary_intent", "")
            row["p_outDeg"] = _num(n.get("outDegree"))
            row["p_inDeg"] = _num(n.get("inDegree"))
            row["p_pathCount"] = _num(n.get("pathCount"))

    if "cluster" in f:
        c_kw2p, _ = _persona_index(f["cluster"]["groups"])
        for r in f["cluster"]["meta"]["keywords"]:
            kw = (r.get("keyword") or "").strip()
            if not kw:
                continue
            row = ensure(kw)
            row["c_present"] = True
            row["c_vol"] = _num(r.get("volume_avg"))
            row["c_cluster"] = r.get("cluster", "")
            row["c_is_hub"] = bool(r.get("is_hub"))
            row["c_outgoing"] = list(r.get("outgoing") or [])
            row["c_intents"] = {k: _num((r.get("intents") or {}).get(k, 0)) for k in INTENT_KEYS}
            row["persona_cluster"] = c_kw2p.get(kw, [])
        # cluster members beyond the top-1000 capped keywords[] still count as C-present
        for letter, members in (f["cluster"]["meta"].get("clusterMembers") or {}).items():
            for kw in members:
                kw = (kw or "").strip()
                if not kw:
                    continue
                row = ensure(kw)
                if not row["c_present"]:
                    row["c_present"] = True
                    row["c_cluster"] = row["c_cluster"] or letter

    # derived: coalesced volume + M (query intents preferred)
    for row in KW.values():
        row["volume"] = _coalesce(row["q_vol"], row["p_vol"], row["c_vol"])
        row["intents"] = row["q_intents"] or row["p_intents"] or row["c_intents"]
        row["M"] = M_of(row["intents"])
        # momentum source: query/path only (cluster has no trend) → cluster-only = 0
        row["trend"] = row["q_trend"] if row["q_present"] else (row["p_trend"] if row["p_present"] else 0)
    return KW


# ─────────────────────────────────────────────────────────────────────────
# M1 — coverage-gap
# ─────────────────────────────────────────────────────────────────────────

def module_coverage(KW, f):
    present = {"Q": "query" in f, "P": "path" in f, "C": "cluster" in f}
    combos = Counter()
    combo_vol = Counter()
    for row in KW.values():
        bits = ""
        if row["q_present"]:
            bits += "Q"
        if row["p_present"]:
            bits += "P"
        if row["c_present"]:
            bits += "C"
        if not bits:
            continue
        combos[bits] += 1
        combo_vol[bits] += row["volume"]

    combo_list = []
    for bits in sorted(combos, key=lambda b: combo_vol[b], reverse=True):
        combo_list.append({
            "id": f"combo#{bits}",
            "sets": list(bits),
            "count": combos[bits],
            "volume": int(round(combo_vol[bits])),
        })

    def bucket(pred, tag):
        items = [r for r in KW.values() if pred(r)]
        items.sort(key=lambda r: r["volume"], reverse=True)
        out = []
        for i, r in enumerate(items, 1):
            out.append({
                "id": f"gap#{tag}-{i:02d}",
                "kw": r["kw"],
                "volume": int(round(r["volume"])),
                "M": _r(r["M"]),
                "trend": r["trend"],
                "cluster": r["c_cluster"],
            })
        return out

    gap_buckets = {}
    if present["Q"] and present["P"]:
        gap_buckets["q_not_p"] = bucket(lambda r: r["q_present"] and not r["p_present"], "qnp")
    if present["Q"] and present["C"]:
        gap_buckets["q_not_c"] = bucket(lambda r: r["q_present"] and not r["c_present"], "qnc")
    if present["Q"] and (present["P"] or present["C"]):
        gap_buckets["struct_not_q"] = bucket(
            lambda r: (r["p_present"] or r["c_present"]) and not r["q_present"], "snq")

    # volume mismatch: keyword present in ≥2 finders with a relative volume gap
    mismatches = []
    for row in KW.values():
        vols = {}
        if row["q_present"]:
            vols["q"] = row["q_vol"]
        if row["p_present"]:
            vols["p"] = row["p_vol"]
        if row["c_present"]:
            vols["c"] = row["c_vol"]
        nz = [v for v in vols.values() if v > 0]
        if len(nz) >= 2 and min(nz) > 0 and (max(nz) - min(nz)) / max(nz) > VOL_MISMATCH_TOL:
            mismatches.append({
                "id": f"vm#{len(mismatches)+1:04d}",
                "kw": row["kw"],
                "q": int(round(vols.get("q", 0))) if "q" in vols else None,
                "p": int(round(vols.get("p", 0))) if "p" in vols else None,
                "c": int(round(vols.get("c", 0))) if "c" in vols else None,
                "spread": _r((max(nz) - min(nz)) / max(nz), 3),
            })
    mismatches.sort(key=lambda m: m["spread"], reverse=True)

    # coveragePct — 3-finder simultaneous coverage share of volume (honesty metric)
    total_vol = sum(r["volume"] for r in KW.values()) or 1
    # covered-by-all = keywords present in every finder that ran
    covered_vol = sum(r["volume"] for r in KW.values()
                      if (not present["Q"] or r["q_present"])
                      and (not present["P"] or r["p_present"])
                      and (not present["C"] or r["c_present"]))
    coverage_pct = _r(100.0 * covered_vol / total_vol, 1)

    # per-persona coverage% (scope-diff vs market-gap discriminator)
    by_persona = []
    if "cluster" in f:
        _, personas = _persona_index(f["cluster"]["groups"])
        for p in personas:
            mvol = sum(KW[kw]["volume"] for kw in p["members"] if kw in KW) or 0
            cov = sum(KW[kw]["volume"] for kw in p["members"] if kw in KW
                      and (not present["Q"] or KW[kw]["q_present"])
                      and (not present["P"] or KW[kw]["p_present"])
                      and (not present["C"] or KW[kw]["c_present"]))
            by_persona.append({"persona": p["name"],
                                "coveragePct": _r(100.0 * cov / mvol, 1) if mvol else 0.0})

    return {
        "combos": combo_list,
        "gapBuckets": gap_buckets,
        "volumeMismatch": mismatches,
        "coveragePct": coverage_pct,
        "coveragePctByPersona": by_persona,
        "totalVolume": int(round(total_vol)),
        "coveredVolume": int(round(covered_vol)),
        "findersPresent": [k for k in ("query", "path", "cluster") if k in f],
    }


# ─────────────────────────────────────────────────────────────────────────
# M2 — hub-divergence  (cluster axis = cross-cluster connectivity, not centrality)
# ─────────────────────────────────────────────────────────────────────────

def module_hub_divergence(KW, f):
    # per-finder rank distributions
    p_outdeg = sorted(r["p_outDeg"] for r in KW.values() if r["p_present"]) if "path" in f else []
    c_conn = sorted(((1 if r["c_is_hub"] else 0) + len(r["c_outgoing"]))
                    for r in KW.values() if r["c_present"]) if "cluster" in f else []
    q_demand = sorted((r["q_vol"] * r["M"]) for r in KW.values() if r["q_present"]) if "query" in f else []

    items = []
    for row in KW.values():
        n_present = sum([row["q_present"], row["p_present"], row["c_present"]])
        if n_present < 2:
            continue
        ranks = {}
        if row["p_present"]:
            ranks["journey"] = _r(_pct_rank(row["p_outDeg"], p_outdeg))
        if row["c_present"]:
            ranks["connectivity"] = _r(_pct_rank((1 if row["c_is_hub"] else 0) + len(row["c_outgoing"]), c_conn))
        if row["q_present"]:
            ranks["demand"] = _r(_pct_rank(row["q_vol"] * row["M"], q_demand))
        vals = list(ranks.values())
        dispersion = _r(max(vals) - min(vals)) if len(vals) >= 2 else 0.0
        hi = [ax for ax, v in ranks.items() if v >= 0.66]
        lo = [ax for ax, v in ranks.items() if v < 0.4]
        if len(ranks) == 3 and len(hi) == 3:
            typ = "TRIPLE_ANCHOR"
        elif len(hi) == 1 and len(ranks) >= 2:
            typ = "BIASED"
        elif len(hi) >= 1 and lo:
            typ = "HALF"
        else:
            typ = "MIXED"
        missing = [ax for ax in ("journey", "connectivity", "demand") if ax not in ranks]
        # weakest axis: an absent finder first, else the lowest-percentile present axis
        missing_axis = missing[0] if missing else (lo[0] if lo else "")
        items.append({
            "kw": row["kw"],
            "journey_rank": ranks.get("journey"),
            "connectivity_rank": ranks.get("connectivity"),
            "demand_rank": ranks.get("demand"),
            "dispersion": dispersion,
            "type": typ,
            "missingAxis": missing_axis,
            "volume": int(round(row["volume"])),
            "isClusterHub": row["c_is_hub"],
            "outDegree": row["p_outDeg"],
        })
    items.sort(key=lambda x: (x["dispersion"], x["volume"]), reverse=True)
    for i, it in enumerate(items, 1):
        it["id"] = f"hub#{i:04d}"
    return items


# ─────────────────────────────────────────────────────────────────────────
# M3 — persona × journey matrix (format folded into cell chips)
# ─────────────────────────────────────────────────────────────────────────

def _stage_of(KW, f):
    """kw -> entry|mid|exit from path seq avg normalized position; intent fallback."""
    pos = defaultdict(list)
    if "path" in f:
        for p in f["path"]["meta"].get("paths", []):
            seq = p.get("seq") or []
            L = len(seq)
            if L < 2:
                continue
            for i, kw in enumerate(seq):
                pos[kw.strip()].append(i / (L - 1))
    stage = {}
    for kw, ps in pos.items():
        avg = sum(ps) / len(ps)
        stage[kw] = "entry" if avg < 0.34 else ("mid" if avg < 0.67 else "exit")
    # intent-based fallback for non-path kws
    for kw, row in KW.items():
        if kw in stage:
            continue
        di = _dominant_intent(row["intents"])
        stage[kw] = {"i": "entry", "n": "entry", "c": "mid", "t": "exit"}.get(di, "mid")
    return stage


def module_matrix(KW, f):
    # personas: cluster groups preferred, else query groups
    if "cluster" in f and (f["cluster"]["groups"].get("groups")):
        _, personas = _persona_index(f["cluster"]["groups"])
        persona_src = "cluster"
    elif "query" in f:
        _, personas = _persona_index(f["query"]["groups"])
        persona_src = "query"
    else:
        return {"personas": [], "stages": list(STAGES), "cells": [], "personaLeak": [], "slope": [], "personaSource": ""}

    stage_of = _stage_of(KW, f)
    cells = []
    persona_leak = []
    slope = []
    persona_names = []
    for pi, p in enumerate(personas):
        persona_names.append(p["name"])
        members = [kw for kw in p["members"] if kw in KW]
        # bucket members by stage
        by_stage = {s: [] for s in STAGES}
        for kw in members:
            by_stage[stage_of.get(kw, "mid")].append(kw)
        stage_vol = {}
        stage_M = {}
        for si, s in enumerate(STAGES):
            mk = by_stage[s]
            vol = sum(KW[kw]["volume"] for kw in mk)
            stage_vol[s] = vol
            wsum = sum(KW[kw]["volume"] for kw in mk) or 0
            avgM = (sum(KW[kw]["M"] * KW[kw]["volume"] for kw in mk) / wsum) if wsum else 0.0
            stage_M[s] = avgM
            top = sorted(mk, key=lambda kw: KW[kw]["volume"], reverse=True)[:5]
            fmt = Counter(FORMAT_LABEL.get(_dominant_intent(KW[kw]["intents"]), "") for kw in mk)
            cells.append({
                "id": f"cell#p{pi}-s{si}",
                "persona": p["name"],
                "stage": s,
                "volume": int(round(vol)),
                "avgM": _r(avgM),
                "topKw": [{"kw": kw, "volLabel": _vol_label(KW[kw]["volume"]),
                           "format": FORMAT_LABEL.get(_dominant_intent(KW[kw]["intents"]), "")}
                          for kw in top],
                "formatMix": [{"format": fl, "count": ct} for fl, ct in fmt.most_common() if fl],
                "gap": False,
                "gapSeverity": 0,
            })
        # gap cells: empty stage flanked by demand
        cell_by_stage = {c["stage"]: c for c in cells if c["persona"] == p["name"]}
        for si, s in enumerate(STAGES):
            c = cell_by_stage[s]
            if c["volume"] == 0:
                adj = 0
                if si > 0:
                    adj = max(adj, stage_vol[STAGES[si - 1]])
                if si < len(STAGES) - 1:
                    adj = max(adj, stage_vol[STAGES[si + 1]])
                if adj > 0:
                    c["gap"] = True
                    c["gapSeverity"] = int(round(adj))
        # personaLeak: max drop-off between consecutive stages (share of persona volume)
        tot = sum(stage_vol.values()) or 1
        shares = {s: stage_vol[s] / tot for s in STAGES}
        drops = []
        for a, b in zip(STAGES, STAGES[1:]):
            drops.append((a, shares[a] - shares[b]))
        leakiest, dropoff = max(drops, key=lambda x: x[1]) if drops else ("", 0.0)
        persona_leak.append({
            "persona": p["name"],
            "leakiestStage": leakiest,
            "dropoff": _r(max(0.0, dropoff)),
            "stageShare": {s: _r(shares[s]) for s in STAGES},
        })
        slope.append({
            "persona": p["name"],
            "entryM": _r(stage_M["entry"]),
            "midM": _r(stage_M["mid"]),
            "exitM": _r(stage_M["exit"]),
            "slope": _r(stage_M["exit"] - stage_M["entry"]),
        })

    return {
        "personas": persona_names,
        "stages": list(STAGES),
        "cells": cells,
        "personaLeak": persona_leak,
        "slope": slope,
        "personaSource": persona_src,
    }


# ─────────────────────────────────────────────────────────────────────────
# M4 — value-leak (commercial intent × journey leak)
# ─────────────────────────────────────────────────────────────────────────

def _downstream_conc(kw, f, KW):
    """Herfindahl of a hub's downstream neighbor VOLUMES (re-joined kw→volume,
    never volLabel string). Hub-limited: non-hub kws (no downstream) → None."""
    dmap = f["path"]["meta"].get("downstreamMap") if "path" in f else None
    ds = (dmap or {}).get(kw) if isinstance(dmap, dict) else None
    if not ds:
        return None
    vols = []
    for d in ds:
        nb = (d.get("kw") or "").strip()
        v = KW[nb]["volume"] if nb in KW else 0
        if v > 0:
            vols.append(v)
    tot = sum(vols)
    if tot <= 0:
        return None
    return _r(sum((v / tot) ** 2 for v in vols), 3)


def module_value_leak(KW, f):
    if "path" not in f:
        return {"leaks": [], "safePoints": [], "brandDefense": []}
    cands = [r for r in KW.values() if r["p_present"] and r["q_present"] and r["intents"]]
    lf_raw = {r["kw"]: r["p_outDeg"] / (r["p_inDeg"] + 1) for r in cands}
    lf_norm = _norm_fn(lf_raw.values())
    raw_scores = {}
    for r in cands:
        raw_scores[r["kw"]] = M_of(r["intents"]) * r["volume"] * lf_norm(lf_raw[r["kw"]])
    score_norm = _norm_fn(raw_scores.values())

    # brand-defense guard: alternative-relation kws must not vanish (n=0.0 sink)
    brand_kw = set()
    if "query" in f:
        for g in f["query"]["groups"].get("groups", []) or []:
            if g.get("relation") == "alternative":
                for m in g.get("members") or []:
                    if isinstance(m, dict) and m.get("kw"):
                        brand_kw.add(m["kw"])

    leaks = []
    for r in cands:
        di = _dominant_intent(r["intents"])
        deadend = (di in ("t", "c")) and r["p_outDeg"] == 0 and r["p_pathCount"] >= DEADEND_MIN_PATHS
        conc = _downstream_conc(r["kw"], f, KW)
        leaks.append({
            "kw": r["kw"],
            "opp": _r(M_of(r["intents"])),
            "volume": int(round(r["volume"])),
            "leak_factor": _r(lf_norm(lf_raw[r["kw"]])),
            "leak_score": _r(score_norm(raw_scores[r["kw"]])),
            "type": "deadend" if deadend else "leak",
            "outDegree": r["p_outDeg"],
            "inDegree": r["p_inDeg"],
            "pathCount": r["p_pathCount"],
            "downstreamConcentration": conc,
            "persona": (r["persona_cluster"] or r["persona_query"] or [""])[0],
            "isBrand": r["kw"] in brand_kw,
            "trend": r["trend"],
        })
    leaks.sort(key=lambda x: x["leak_score"], reverse=True)
    for i, lk in enumerate(leaks, 1):
        lk["id"] = f"leak#{i:04d}"

    # safe points: high opp, low leak factor (converge), inDegree ≥1
    opp_vals = [lk["opp"] for lk in leaks]
    med_opp = statistics.median(opp_vals) if opp_vals else 0
    safe = [lk for lk in leaks if lk["opp"] >= med_opp and lk["leak_factor"] <= 0.34 and lk["inDegree"] >= 1]
    safe.sort(key=lambda x: (x["opp"], x["volume"]), reverse=True)
    safe_points = []
    for i, lk in enumerate(safe[:8], 1):
        safe_points.append({"id": f"safe#{i:04d}", "kw": lk["kw"], "opp": lk["opp"],
                            "volume": lk["volume"], "leak_factor": lk["leak_factor"],
                            "inDegree": lk["inDegree"], "persona": lk["persona"]})

    brand_defense = [{"id": lk["id"], "kw": lk["kw"], "opp": lk["opp"], "volume": lk["volume"],
                      "leak_score": lk["leak_score"]}
                     for lk in leaks if lk["isBrand"]]
    return {"leaks": leaks, "safePoints": safe_points, "brandDefense": brand_defense}


# ─────────────────────────────────────────────────────────────────────────
# M5 — corridor / substitute-leak bridges
# ─────────────────────────────────────────────────────────────────────────

def module_bridges(KW, f):
    if "cluster" not in f or "path" not in f:
        return []  # needs cluster links + path direction
    kw_cluster = {r["kw"]: r["c_cluster"] for r in KW.values() if r["c_present"] and r["c_cluster"]}

    # 1) enumerate cross-cluster co-search links (unordered letter pairs)
    link_pairs = set()
    for r in KW.values():
        if not r["c_present"]:
            continue
        a = r["c_cluster"]
        for b in r["c_outgoing"]:
            if a and b and a != b:
                link_pairs.add(tuple(sorted((a, b))))
    for fl in (f["cluster"]["groups"].get("flows") or []):
        pth = [l for l in (fl.get("path") or [])]
        for a, b in zip(pth, pth[1:]):
            if a != b:
                link_pairs.add(tuple(sorted((a, b))))

    # 2) path adjacency transitions between clusters
    fwd_cnt = defaultdict(int)  # (X,Y) directed
    for p in f["path"]["meta"].get("paths", []):
        seq = p.get("seq") or []
        for a, b in zip(seq, seq[1:]):
            ca, cb = kw_cluster.get(a.strip()), kw_cluster.get(b.strip())
            if ca and cb and ca != cb:
                fwd_cnt[(ca, cb)] += 1

    # cluster mean M (volume-weighted) for intent_delta
    cl_members = defaultdict(list)
    for r in KW.values():
        if r["c_present"] and r["c_cluster"]:
            cl_members[r["c_cluster"]].append(r)

    def cluster_M(letter):
        rows = [r for r in cl_members.get(letter, []) if r["intents"]]
        wsum = sum(r["volume"] for r in rows) or 0
        return (sum(r["M"] * r["volume"] for r in rows) / wsum) if wsum else 0.0

    hub_of = {}
    if "cluster" in f:
        for letter, hks in (f["cluster"]["meta"].get("hubKeywords") or {}).items():
            hub_of[letter] = hks[0] if hks else ""

    totals = {}
    for (x, y) in link_pairs:
        totals[(x, y)] = fwd_cnt.get((x, y), 0) + fwd_cnt.get((y, x), 0)
    strength_norm = _norm_fn(totals.values())

    bridges = []
    for (x, y) in link_pairs:
        f_xy = fwd_cnt.get((x, y), 0)
        f_yx = fwd_cnt.get((y, x), 0)
        total = f_xy + f_yx
        # orient so `from`→`to` is the dominant direction
        if f_yx > f_xy:
            frm, to, fwd, rev = y, x, f_yx, f_xy
        else:
            frm, to, fwd, rev = x, y, f_xy, f_yx
        directionality = _r((fwd - rev) / total) if total else 0.0
        idelta = _r(cluster_M(to) - cluster_M(frm))
        if total == 0:
            verdict = "false_adjacency"
        elif total < BRIDGE_MIN_TRANS:
            verdict = "inconclusive"
        elif idelta < 0:
            verdict = "substitute_leak"
        elif abs(directionality) >= BRIDGE_DIR_THR and idelta >= 0:
            verdict = "corridor"
        else:
            verdict = "inconclusive"
        # bridging kw: a keyword whose OWN cluster is one endpoint and whose
        # cross-cluster outgoing reaches the OTHER endpoint. Prefer a cluster hub;
        # else the highest-volume bridging member on either side.
        def _links(cand, other):
            r = KW.get(cand)
            return bool(r) and other in (r.get("c_outgoing") or [])

        bridge_kw = ""
        for cand, other in ((hub_of.get(frm, ""), to), (hub_of.get(to, ""), frm)):
            if cand and _links(cand, other):
                bridge_kw = cand
                break
        if not bridge_kw:
            xkw = [r for r in cl_members.get(frm, []) if to in r["c_outgoing"]] \
                or [r for r in cl_members.get(to, []) if frm in r["c_outgoing"]]
            bridge_kw = max(xkw, key=lambda r: r["volume"])["kw"] if xkw else (hub_of.get(frm, "") or hub_of.get(to, ""))
        bridges.append({
            "id": f"bridge#{frm}-{to}",
            "from": frm, "to": to,
            "fromHub": hub_of.get(frm, ""), "toHub": hub_of.get(to, ""),
            "bridgeKw": bridge_kw,
            "fwd": fwd, "rev": rev,
            "directionality": directionality,
            "strength": _r(strength_norm(total)),
            "intent_delta": idelta,
            "verdict": verdict,
        })
    bridges.sort(key=lambda b: (b["fwd"] + b["rev"], b["strength"]), reverse=True)
    return bridges


# ─────────────────────────────────────────────────────────────────────────
# M6 — priority backlog
# ─────────────────────────────────────────────────────────────────────────

def module_backlog(KW, f, cov, hub_div, leaks_mod, bridges):
    leak_by_kw = {lk["kw"]: lk for lk in leaks_mod.get("leaks", [])}
    gap_kw = set()
    for b in cov["gapBuckets"].values():
        for it in b:
            gap_kw.add(it["kw"])
    hubdiv_kw = {h["kw"]: h for h in hub_div}
    bridge_kw = {b["bridgeKw"] for b in bridges if b.get("bridgeKw")}
    brand_kw = {d["kw"] for d in leaks_mod.get("brandDefense", [])}

    # structure components normalized across the corpus
    J_raw = {kw: r["p_pathCount"] * (1 + r["p_outDeg"]) for kw, r in KW.items()}
    C_raw = {kw: (1 if r["c_is_hub"] else 0) + len(r["c_outgoing"]) for kw, r in KW.items()}
    Jn = _norm_fn(J_raw.values())
    Cn = _norm_fn(C_raw.values())
    w1, w2 = STRUCT_W

    items = []
    for kw, r in KW.items():
        if r["volume"] <= 0:
            continue
        structure = w1 * Jn(J_raw[kw]) + w2 * Cn(C_raw[kw])
        mom = max(-1.0, min(1.0, r["trend"] / TREND_CLIP)) if (r["q_present"] or r["p_present"]) else 0.0
        leak_norm = leak_by_kw.get(kw, {}).get("leak_score", 0.0)
        severity = 1.0 + 1.0 * leak_norm + (0.5 if kw in gap_kw else 0.0)
        opp_num = r["volume"] * r["M"] * (1.0 + max(0.0, mom)) * severity
        items.append({
            "kw": kw, "row": r, "structure": structure, "mom": mom,
            "leak_norm": leak_norm, "opp_num": opp_num,
            "is_orphan": structure < 0.05 and (r["M"] > 0),
            "is_preempt": mom > 0.2 and not r["c_is_hub"],
        })

    numn = _norm_fn(x["opp_num"] for x in items)
    for it in items:
        it["num_norm"] = numn(it["opp_num"])
        it["score"] = it["num_norm"] / (it["structure"] + STRUCT_EPS)
    sn = _norm_fn(x["score"] for x in items)
    for it in items:
        it["score_disp"] = _r(sn(it["score"]))

    struct_vals = sorted(x["structure"] for x in items)

    def struct_tier(s):
        rk = _pct_rank(s, struct_vals)
        return "high" if rk >= 0.66 else ("mid" if rk >= 0.33 else "low")

    # hi_value = raw impact (opportunity numerator); hi_score = structure-divided
    # leverage (favours orphans). Now defends structured high-impact keywords;
    # Later surfaces high-leverage orphans/preemption.
    num_med = statistics.median(x["num_norm"] for x in items) if items else 0
    now, nxt, later = [], [], []
    for it in items:
        tier = struct_tier(it["structure"])
        hi_value = it["num_norm"] >= num_med
        hi_score = it["score_disp"] >= 0.5
        if it["is_orphan"] and it["row"]["M"] * it["row"]["volume"] > 0:
            later.append((it, "orphan"))
        elif it["is_preempt"] and it["row"]["trend"] > 0:
            later.append((it, "preempt"))
        elif tier == "high" and it["mom"] >= 0 and hi_value:
            now.append((it, "quickwin"))
        elif tier in ("high", "mid") and (hi_value or hi_score):
            nxt.append((it, "build"))
        elif tier == "low":
            later.append((it, "orphan"))
        else:
            nxt.append((it, "build"))

    def finalize(bucket, tag):
        bucket.sort(key=lambda pr: pr[0]["score_disp"], reverse=True)
        out = []
        for i, (it, strand) in enumerate(bucket[:BACKLOG_CAP], 1):
            r = it["row"]
            src = []
            if it["kw"] in gap_kw:
                src.append("coverage-gap")
            if it["kw"] in hubdiv_kw:
                src.append("hub-divergence")
            if it["kw"] in leak_by_kw:
                src.append("value-leak")
            if it["kw"] in bridge_kw:
                src.append("corridor-bridge")
            if it["kw"] in brand_kw:
                src.append("brand-defense")
            if r["trend"] > 0:
                src.append("momentum")
            # breakdown contributions (normalized 0..1 stack)
            bd = {
                "volume": _r(_norm_fn(x["row"]["volume"] for x in items)(r["volume"])),
                "intent": _r(r["M"]),
                "momentum": _r(max(0.0, it["mom"])),
                "structure": _r(it["structure"] / (w1 + w2)),
                "leak": _r(it["leak_norm"]),
            }
            target = (r["persona_cluster"] or r["persona_query"] or [""])[0]
            out.append({
                "id": f"bl#{tag}-{i}",
                "bucket": tag,
                "rank": i,
                "strand": strand,
                "target": target or r["kw"],
                "score": it["score_disp"],
                "breakdown": bd,
                "sourceModules": sorted(set(src)),
                "evidenceKw": [r["kw"]],
                "volume": int(round(r["volume"])),
                "M": _r(r["M"]),
                "trend": r["trend"],
            })
        return out

    now_i, next_i, later_i = finalize(now, "now"), finalize(nxt, "next"), finalize(later, "later")

    # KPI
    recoverable = sum(lk["volume"] for lk in leaks_mod.get("leaks", [])
                      if lk["leak_score"] >= 0.5)
    orphan_ct = sum(1 for (it, strand) in later if strand == "orphan")
    kpi = {
        "recoverableLeakVolume": int(round(recoverable)),
        "orphanCount": orphan_ct,
        "coveragePct": cov["coveragePct"],
    }
    return {"items": now_i + next_i + later_i, "kpi": kpi}


# ─────────────────────────────────────────────────────────────────────────
# recap + meta
# ─────────────────────────────────────────────────────────────────────────

def build_recap(f):
    recap = {}
    if "query" in f:
        groups = f["query"]["groups"].get("groups", []) or []
        core = [g for g in groups if g.get("relation") == "core"]
        top = max(groups, key=lambda g: len(g.get("members") or []), default=None)
        recap["query"] = {"count": len(core), "topGroup": (top or {}).get("name", "")}
    if "path" in f:
        hubs = f["path"]["paths"].get("hubs", []) or []
        recap["path"] = {"count": _num(f["path"]["meta"].get("hubCount")),
                          "topHub": (hubs[0]["keyword"] if hubs else "")}
    if "cluster" in f:
        groups = f["cluster"]["groups"].get("groups", []) or []
        top = max(groups, key=lambda g: len(g.get("members") or []), default=None)
        recap["cluster"] = {"count": _num(f["cluster"]["meta"].get("clusterCount")),
                            "topCluster": (top or {}).get("name", "")}
    return recap


def build_meta(f, seed, gl, date):
    finders = [k for k in ("query", "path", "cluster") if k in f]
    kw_counts = []
    for k in ("query", "cluster"):
        if k in f:
            kw_counts.append(_num(f[k]["meta"].get("keywordCount")))
    if "path" in f:
        kw_counts.append(_num(f["path"]["meta"].get("nodeCount")))
    keyword_count = max(kw_counts) if kw_counts else 0
    coverage_complete = keyword_count < 1000  # top-1000 cap: nothing lost beyond
    return {
        "seed": seed, "gl": gl, "date": date,
        "finders": finders,
        "keywordCount": keyword_count,
        "coverageComplete": coverage_complete,
    }


# ─────────────────────────────────────────────────────────────────────────
# assemble
# ─────────────────────────────────────────────────────────────────────────

def build_total_facts(f, seed, gl, date):
    KW = build_master(f)
    cov = module_coverage(KW, f)
    hub_div = module_hub_divergence(KW, f)
    matrix = module_matrix(KW, f)
    value_leak = module_value_leak(KW, f)
    bridges = module_bridges(KW, f)
    backlog = module_backlog(KW, f, cov, hub_div, value_leak, bridges)
    return {
        "meta": build_meta(f, seed, gl, date),
        "recap": build_recap(f),
        "coverage": cov,
        "hubDivergence": hub_div,
        "matrix": matrix,
        "valueLeak": value_leak,
        "bridges": bridges,
        "backlog": backlog,
    }


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def _cmd_total(args):
    f = load_finders(args)
    if "query" not in f:
        print("ERROR: 통합 집계에는 최소 query 파인더(--query-meta) 가 필요합니다.", file=sys.stderr)
        return 1
    if len(f) < 2:
        print("ERROR: 통합 집계에는 최소 2개 파인더가 필요합니다(우아한 축소 한계).", file=sys.stderr)
        return 1
    facts = build_total_facts(f, args.seed, args.gl, args.date)
    Path(args.out).write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    m = facts["meta"]
    print(f"wrote {args.out} (finders={','.join(m['finders'])}, "
          f"kw={m['keywordCount']}, hubDiv={len(facts['hubDivergence'])}, "
          f"cells={len(facts['matrix']['cells'])}, leaks={len(facts['valueLeak']['leaks'])}, "
          f"bridges={len(facts['bridges'])}, backlog={len(facts['backlog']['items'])})")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Total-insight cross-finder aggregator (the sole number source for 통합 요약 탭).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("total", help="Join query/path/cluster outputs → lm_total_facts.json")
    p.add_argument("--seed", required=True)
    p.add_argument("--gl", required=True, choices=["kr", "jp", "us"])
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--query-meta", help="q/lm_query_result.json")
    p.add_argument("--query-groups", help="q/lm_groups.json")
    p.add_argument("--path-meta", help="p/lm_path_result.json")
    p.add_argument("--path-paths", help="p/lm_paths.json")
    p.add_argument("--cluster-meta", help="c/lm_cluster_result.json")
    p.add_argument("--cluster-groups", help="c/lm_groups.json")
    p.add_argument("--out", required=True, help="output lm_total_facts.json path")
    p.set_defaults(func=_cmd_total)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
