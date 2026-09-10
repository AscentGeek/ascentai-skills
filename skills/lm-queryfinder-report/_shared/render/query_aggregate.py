#!/usr/bin/env python3
"""Aggregate ListeningMind intent_finder (Query Finder) responses into the
report data JSON consumed by render_report.py --skill query-opportunity.

Standard library only. Envelope-tolerant: accepts both the public data-API
flat form ({"data": [...]}) and the internal ES form
({"result": {"hits": {"hits": [{"_source": {...}}]}}}).
"""

import argparse
import json
import math
import statistics
import sys
from pathlib import Path


def _num(v, default=0):
    """Coerce int/float/numeric-string to a number; anything else -> default.

    The public /intent_finder data types are unverified (spec §4.2): a
    metric that should be numeric may arrive as a JSON string (e.g.
    volume_avg: "74000"). Without coercion this crashes _max_log (TypeError
    comparing str > int) or produces strings that blow up ":.2f"/",:"
    formatting downstream.
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


def _max_log(volumes):
    top = max((v for v in volumes if v and v > 0), default=0)
    return math.log10(top + 1) if top > 0 else 1.0


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


def normalize_records(raw):
    """Return a flat list of {keyword, ads_metrics, monthly_volume, intents}."""
    raw = _unwrap_content_blocks(raw)
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

    records = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        src = row["_source"] if isinstance(row.get("_source"), dict) else row
        keyword = src.get("keyword")
        if not keyword:
            continue
        # The public /intent_finder data types are unverified (spec §4.2):
        # ads_metrics/intents may arrive as a non-dict placeholder (e.g.
        # "n/a") and monthly_volume as a non-list placeholder (e.g. "none").
        # `src.get(...) or {}` doesn't catch this since a truthy string
        # stays truthy — check the type explicitly instead.
        ads_metrics = src.get("ads_metrics")
        intents = src.get("intents")
        monthly_volume = src.get("monthly_volume")
        records.append({
            "keyword": keyword,
            "ads_metrics": ads_metrics if isinstance(ads_metrics, dict) else {},
            "monthly_volume": monthly_volume if isinstance(monthly_volume, list) else [],
            "intents": intents if isinstance(intents, dict) else {},
        })
    return records


# ── 기회 스코어링 (규칙기반, 튜닝 파라미터는 상단 상수로 노출) ──
INTENT_KEYS = ("i", "n", "c", "t")
# 거래(t)·상업(c) 의도에 가중, 길찾기(n)는 기회가치 낮음 (라벨은 labels JSON에서 옴)
INTENT_WEIGHT = {"i": 0.2, "n": 0.0, "c": 0.5, "t": 1.0}


def primary_intent(intents):
    if not intents:
        return ""
    return max(INTENT_KEYS, key=lambda k: intents.get(k, 0) or 0)


def intent_weight(intents):
    total = sum((intents.get(k, 0) or 0) for k in INTENT_KEYS)
    if total <= 0:
        return 0.0
    return sum(INTENT_WEIGHT[k] * (intents.get(k, 0) or 0) for k in INTENT_KEYS) / total


def _volume_norm(volume_avg, max_log):
    if not volume_avg or volume_avg <= 0 or max_log <= 0:
        return 0.0
    return min(math.log10(volume_avg + 1) / max_log, 1.0)


def opportunity_score(volume_avg, competition_index, intents, max_log):
    """0~1. 높을수록 '고볼륨·저경쟁·고거래의도' = 공략 우선."""
    vol_n = _volume_norm(volume_avg, max_log)
    comp_n = min(max((competition_index or 0) / 100.0, 0.0), 1.0)
    iw = intent_weight(intents)
    return round(vol_n * (1.0 - comp_n) * (0.5 + 0.5 * iw), 4)


def _quadrant(volume_avg, competition_index, med_vol, med_comp):
    hi_vol = (volume_avg or 0) >= med_vol
    hi_comp = (competition_index or 0) >= med_comp
    if hi_vol and not hi_comp:
        return "priority"      # 고볼륨·저경쟁 = 공략 우선
    if hi_vol and hi_comp:
        return "competitive"   # 고볼륨·고경쟁
    if not hi_vol and not hi_comp:
        return "niche"         # 저볼륨·저경쟁 = 틈새
    return "low"               # 저볼륨·고경쟁 = 후순위


def aggregate(records, seed, gl, date, top_n=20):
    vols = [_num(r["ads_metrics"].get("volume_avg")) for r in records]
    comps = [_num(r["ads_metrics"].get("competition_index")) for r in records]
    max_log = _max_log(vols)
    med_vol = statistics.median(vols) if vols else 0
    med_comp = statistics.median(comps) if comps else 0

    queries = []
    funnel = {k: 0 for k in INTENT_KEYS}
    total_volume = 0
    cpcs = []
    for r in records:
        am = r["ads_metrics"]
        intents = {k: _num(v) for k, v in (r["intents"] or {}).items()}
        vavg = _num(am.get("volume_avg"))
        cidx = _num(am.get("competition_index"))
        cpc = _num(am.get("cpc"))
        total_volume += vavg
        if cpc:
            cpcs.append(cpc)
        for k in INTENT_KEYS:
            funnel[k] += intents.get(k, 0)
        queries.append({
            "keyword": r["keyword"],
            "volume_avg": vavg,
            "volume_total": _num(am.get("volume_total")),
            "volume_trend": _num(am.get("volume_trend")),
            "cpc": cpc,
            "competition": am.get("competition", ""),
            "competition_index": cidx,
            "intents": {k: intents.get(k, 0) for k in INTENT_KEYS},
            "primary_intent": primary_intent(intents),
            "opportunity_score": opportunity_score(vavg, cidx, intents, max_log),
            "quadrant": _quadrant(vavg, cidx, med_vol, med_comp),
        })

    queries.sort(key=lambda q: q["opportunity_score"], reverse=True)

    # 검색의도 퍼널: 전체 합산을 비율로 정규화
    raw_funnel_total = sum(funnel.values())
    funnel_total = raw_funnel_total or 1
    funnel_pct = {k: round(100 * funnel[k] / funnel_total, 1) for k in INTENT_KEYS}

    # 트렌드: 상위 5개 쿼리의 월별 total 시리즈 (공통 월 라벨은 첫 레코드 기준)
    # monthly_volume entries are unverified third-party data (spec §4.2):
    # gg/nv/total may arrive as numeric strings (must not string-concat) and
    # individual entries may not be dicts at all (must not crash) — coerce
    # via _num and skip non-dict entries.
    trend_labels = []
    for r in records:
        month_dicts = [m for m in r["monthly_volume"] if isinstance(m, dict)]
        if month_dicts:
            trend_labels = [m.get("month", "") for m in month_dicts]
            break
    top_kw = [q["keyword"] for q in queries[:5]]
    mv_by_kw = {r["keyword"]: r["monthly_volume"] for r in records}
    trend_series = []
    for kw in top_kw:
        mv = mv_by_kw.get(kw) or []
        data = []
        for m in mv:
            if not isinstance(m, dict):
                continue
            total = m.get("total")
            data.append(_num(total) if total is not None else _num(m.get("gg")) + _num(m.get("nv")))
        if data:
            trend_series.append({"keyword": kw, "data": data})

    kpis = {
        "totalVolume": total_volume,
        "avgVolume": round(total_volume / len(records)) if records else 0,
        "avgCpc": round(sum(cpcs) / len(cpcs), 2) if cpcs else 0,
        "primaryIntent": max(INTENT_KEYS, key=lambda k: funnel[k]) if raw_funnel_total > 0 else "",
    }

    return {
        "seed": seed,
        "gl": gl,
        "date": date,
        "queryCount": len(records),
        "kpis": kpis,
        "funnel": funnel_pct,
        "quadrant": {"medVolume": med_vol, "medComp": med_comp},
        "queries": queries,
        "topQueries": queries[:top_n],
        "trend": {"labels": trend_labels, "series": trend_series},
    }


# ─────────────────────────────────────────────────────────────────────────
# New data pipeline (zip customer-analysis flow mirror): keyword context +
# persona-group postprocessing. Consumed by render_report.py --skill
# query-opportunity via lm_query_result.json / lm_groups.json. See
# docs/superpowers/specs/2026-07-16-queryfinder-zip-redesign-blend.md
# ("데이터 파이프라인", "산출물 JSON 스키마"). The older `aggregate`/scoring
# functions above stay as-is for reference — they are no longer wired into
# the report but keep their own tests green.
# ─────────────────────────────────────────────────────────────────────────

# QueryFinder prompt rule (#1958): the LLM only ever sees the top ~1,000
# keywords by volume_avg (token budget) — both the `keywords` list and the
# `csv` text handed to the LLM step are capped here. `keywordCount` /
# `totalVolume` / `primaryIntent` are computed over the FULL record set
# first, so those stay accurate even when the keyword list is capped.
KEYWORD_CONTEXT_TOP_N = 1000

# zip persona-card `evidence[]` shows a handful of representative keywords,
# not the whole member list — top 8 by volume_avg, mirroring the ported
# customer-analysis postprocess_personas behavior.
EVIDENCE_TOP_N = 8


def _csv_field(value):
    """Minimal CSV quoting: wrap in double quotes (escaping embedded quotes)
    only when the raw value could break column parsing. Keywords are
    third-party search-query text and may contain a literal comma."""
    s = str(value)
    if "," in s or '"' in s or "\n" in s:
        return '"' + s.replace('"', '""') + '"'
    return s


def _build_csv(keywords):
    # trend = ads_metrics.volume_trend (양수=상승세, 음수=하락세) — 급상승
    # 신호가 LLM 그룹핑·기회 판단에 전달되도록 CSV 마지막 컬럼으로 포함.
    lines = ["keyword,volume_avg,i,n,c,t,trend"]
    for kw in keywords:
        intents = kw.get("intents") or {}
        lines.append(",".join([
            _csv_field(kw["keyword"]),
            str(kw["volume_avg"]),
            str(intents.get("i", 0)),
            str(intents.get("n", 0)),
            str(intents.get("c", 0)),
            str(intents.get("t", 0)),
            str(kw.get("volume_trend", 0)),
        ]))
    return "\n".join(lines)


def build_keyword_context(records, seed, gl, date, top_n=KEYWORD_CONTEXT_TOP_N):
    """Aggregate normalize_records() output into the lm_query_result.json
    shape: per-keyword volume/intent breakdown + a CSV text blob that's the
    `{{query_csv}}` the LLM grouping step (step 3) consumes.
    """
    keywords = []
    intent_totals = {k: 0 for k in INTENT_KEYS}
    total_volume = 0
    for r in records:
        am = r["ads_metrics"]
        intents = {k: _num((r["intents"] or {}).get(k)) for k in INTENT_KEYS}
        vavg = _num(am.get("volume_avg"))
        total_volume += vavg
        for k in INTENT_KEYS:
            intent_totals[k] += intents[k]
        keywords.append({
            "keyword": r["keyword"],
            "volume_avg": vavg,
            "volume_total": _num(am.get("volume_total")),
            "volume_trend": _num(am.get("volume_trend")),
            "intents": intents,
        })

    keywords.sort(key=lambda k: k["volume_avg"], reverse=True)
    raw_intent_total = sum(intent_totals.values())
    primary_intent = (
        max(INTENT_KEYS, key=lambda k: intent_totals[k]) if raw_intent_total > 0 else ""
    )

    top_keywords = keywords[:top_n]
    return {
        "seed": seed,
        "gl": gl,
        "date": date,
        "keywordCount": len(records),
        "totalVolume": int(total_volume),
        "primaryIntent": primary_intent,
        "keywords": top_keywords,
        "csv": _build_csv(top_keywords),
    }


def build_keyword_map(context_or_keywords):
    """Build the {keyword: {volume_avg, volume_total, intents}} lookup used
    by postprocess_groups(). Accepts either the full build_keyword_context()
    dict (reads its "keywords" list) or a bare keywords list directly.

    NOTE: this only covers the (possibly top-1000-capped) `keywords` list of
    the context, not the full un-capped record set — that's fine because the
    LLM grouping step only ever sees that same capped CSV, so its
    memberKeywords can't reference anything outside this map anyway.
    """
    kw_list = context_or_keywords.get("keywords", []) if isinstance(context_or_keywords, dict) else context_or_keywords
    return {
        k["keyword"]: {
            "volume_avg": k.get("volume_avg", 0),
            "volume_total": k.get("volume_total", 0),
            "intents": k.get("intents", {}),
        }
        for k in kw_list
    }


def _known_keywords(keywords, keyword_map):
    """환각 차단: LLM 출력 키워드 중 CSV(keyword_map)에 실제로 존재하는
    것만 남긴다. 프롬프트가 'csv 원문만' 을 지시하지만 LLM 이 어기면 근거
    키워드처럼 리포트에 노출되므로 코드에서 강제한다."""
    return [kw for kw in (keywords or []) if kw in keyword_map]


def _filter_kbf(kbf_rows, keyword_map):
    """kbf 의 evidence_keywords 를 실키워드로만 필터. 근거가 하나도 남지
    않는 행(및 dict 가 아닌 행)은 근거 없는 주장이 되므로 통째로 버린다."""
    out = []
    for row in (kbf_rows or []):
        if not isinstance(row, dict):
            continue
        evidence = _known_keywords(row.get("evidence_keywords"), keyword_map)
        if not evidence:
            continue
        out.append({**row, "evidence_keywords": evidence})
    return out


def _evidence_for(member_keywords, keyword_map, top_n=EVIDENCE_TOP_N):
    """Top-N member keywords by volume_avg, persona-card evidence shape.
    Members are pre-filtered to CSV-known keywords by postprocess_groups.
    top_n=None 이면 캡 없이 전체 반환(뱃지 툴팁용 members)."""
    scored = [(kw, _num((keyword_map.get(kw) or {}).get("volume_avg"))) for kw in (member_keywords or [])]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    sliced = scored if top_n is None else scored[:top_n]
    return [
        {"kw": kw, "volLabel": f"{int(round(vol)):,}" if vol > 0 else ""}
        for kw, vol in sliced
    ]


def _sum_member_volume(member_keywords, keyword_map):
    return sum(_num((keyword_map.get(kw) or {}).get("volume_avg")) for kw in (member_keywords or []))


def _vol_label(vol):
    return f"{int(round(vol)):,}" if vol > 0 else ""


def postprocess_groups(groups_raw, keyword_map):
    """Shape the LLM's {"overview", "intentGroups", "brandGroups"} output
    into the persona-card {"groups": [...]} lm_groups.json consumed by
    render_report.py --skill query-opportunity. Python attaches the facts
    (volume sums + evidence) per decision 1 (수치 정책) — the LLM only
    supplies grouping/labels/qualitative text. memberKeywords and kbf
    evidence_keywords are hard-filtered to CSV-known keywords here, so a
    hallucinated keyword can never surface as report evidence.
    """
    groups = []
    for ig in (groups_raw.get("intentGroups") or []):
        members = _known_keywords(ig.get("memberKeywords"), keyword_map)
        if not members:
            continue
        vol = _sum_member_volume(members, keyword_map)
        groups.append({
            "name": ig.get("title", ""),
            "relation": "core",
            "stage": ig.get("intentType", ""),
            "who": ig.get("who") or "",
            "kbf": _filter_kbf(ig.get("kbf"), keyword_map),
            "insight": ig.get("insight") or "",
            "evidence": _evidence_for(members, keyword_map),
            "members": _evidence_for(members, keyword_map, top_n=None),
            "volumeLabel": _vol_label(vol),
            "memberCount": len(members),
            "_vol": vol,
        })
    for bg in (groups_raw.get("brandGroups") or []):
        members = _known_keywords(bg.get("memberKeywords"), keyword_map)
        if not members:
            continue
        vol = _sum_member_volume(members, keyword_map)
        groups.append({
            "name": bg.get("name", ""),
            "relation": "alternative",
            "stage": "브랜드" if bg.get("kind") == "brand" else "논브랜드",
            "who": bg.get("label") or "",
            "kbf": [],
            "insight": bg.get("analysis") or "",
            "evidence": _evidence_for(members, keyword_map),
            "members": _evidence_for(members, keyword_map, top_n=None),
            "volumeLabel": _vol_label(vol),
            "memberCount": len(members),
            "_vol": vol,
        })

    groups.sort(key=lambda g: g["_vol"], reverse=True)
    for g in groups:
        del g["_vol"]
    result = {"groups": groups}
    overview = groups_raw.get("overview")
    if overview:
        result["overview"] = overview
    return result


# ─────────────────────────────────────────
# CLI — subcommands
# ─────────────────────────────────────────

def _cmd_context(args):
    raw = json.loads(Path(args.raw).read_text(encoding="utf-8"))
    records = normalize_records(raw)
    if not records:
        print("ERROR: intent_finder 응답에서 레코드를 찾지 못했습니다.", file=sys.stderr)
        return 1
    result = build_keyword_context(records, seed=args.seed, gl=args.gl, date=args.date)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({result['keywordCount']} keywords)")
    return 0


def _cmd_groups(args):
    groups_raw = json.loads(Path(args.raw_groups).read_text(encoding="utf-8"))
    context = json.loads(Path(args.context).read_text(encoding="utf-8"))
    keyword_map = build_keyword_map(context)
    result = postprocess_groups(groups_raw, keyword_map)
    if not result["groups"]:
        print("ERROR: LLM 그룹 출력에서 유효한 그룹을 만들지 못했습니다.", file=sys.stderr)
        return 1
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} ({len(result['groups'])} groups)")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Query Finder data pipeline: keyword context builder + persona group postprocessing."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_context = sub.add_parser("context", help="Aggregate an intent_finder response into lm_query_result.json")
    p_context.add_argument("--raw", required=True, help="intent_finder 응답 JSON 경로")
    p_context.add_argument("--seed", required=True)
    # kr-only for now: label JSON (_shared/labels/query-opportunity.<gl>.json)
    # only exists for "kr" — add "jp"/"us" back once their label files land.
    p_context.add_argument("--gl", required=True, choices=["kr"])
    p_context.add_argument("--date", required=True, help="YYYY-MM-DD")
    p_context.add_argument("--out", required=True)
    p_context.set_defaults(func=_cmd_context)

    p_groups = sub.add_parser("groups", help="Postprocess LLM group output + context into lm_groups.json")
    p_groups.add_argument("--raw-groups", required=True, help="LLM lm_groups_raw.json 경로")
    p_groups.add_argument("--context", required=True, help="lm_query_result.json 경로")
    p_groups.add_argument("--out", required=True)
    p_groups.set_defaults(func=_cmd_groups)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
