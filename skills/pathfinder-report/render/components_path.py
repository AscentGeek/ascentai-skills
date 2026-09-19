"""HTML builders for the path-opportunity (검색 여정 분석) report.

Renders the PathFinder journey graph through the same ListeningMind.AI card
shell as customer-analysis, so the dashboard and A4 views match the web app.
Three path-specific pieces live here — the 여정 흐름도(flow tree), the 경로
카드(path card), and the 허브 카드(hub card) — while covers/purpose-box/actions
panel are reused from components.py unchanged.

All user/LLM/third-party text goes through `escape_with_strong` (HTML-escape,
then re-allow <strong> pairs) or html.escape.
"""

import html
from typing import Any, Dict, List, Optional

from components import (  # shared, unchanged from the customer-analysis skill
    escape_with_strong,
    kw_html,
    t,
    format_count,
    purpose_box_html,
    dash_panel_actions_html,
    action_list_html,
)

FLOW_TYPES = ("conversion", "comparison", "risk")
INTENT_CODES = ("i", "n", "c", "t")


# ─────────────────────────────────────────
# 여정 흐름도 — prefix-merge trie of top journeys (data-derived, not LLM)
# ─────────────────────────────────────────

def _flow_tree_html(roots: List[Dict[str, Any]], depth: int = 0, seed: Optional[str] = None) -> str:
    if not roots:
        return ""
    items = []
    for n in roots:
        kw_raw = str(n.get("kw", ""))
        kw = kw_html(kw_raw)
        vol = n.get("volLabel", "")
        vol_html = f'<span class="flow-node__vol">{html.escape(str(vol))}</span>' if vol else ""
        is_seed = seed is not None and kw_raw == seed
        # 시드 강조가 의도색보다 우선 (기점 노드를 어디서든 눈에 띄게)
        node_cls = " flow-node--seed" if is_seed else ""
        intent = n.get("primary_intent", "")
        if not is_seed and intent in INTENT_CODES:
            node_cls += f" flow-node--{intent}"
        children = n.get("children") or []
        child_html = _flow_tree_html(children, depth + 1, seed) if children else ""
        items.append(
            f'<li class="flow-branch">'
            f'<div class="flow-node{node_cls}">'
            f'<span class="flow-node__kw">{kw}</span>{vol_html}'
            f'</div>'
            f'{child_html}'
            f'</li>'
        )
    return f'<ul class="flow-tree flow-tree--d{min(depth, 4)}">{"".join(items)}</ul>'


def _flow_max_depth(roots: List[Dict[str, Any]], depth: int = 0) -> int:
    best = depth
    for n in roots:
        children = n.get("children") or []
        if children:
            best = max(best, _flow_max_depth(children, depth + 1))
    return best


def flow_diagram_html(flow_tree: List[Dict[str, Any]], category: str, labels: Dict[str, str]) -> str:
    if not flow_tree:
        return ""
    desc = t(labels, "pathAnalysis.dash.flowDesc").replace("{category}", kw_html(category))
    legend = "".join(
        f'<span class="flow-legend__item flow-legend__item--{code}">'
        f'{t(labels, f"pathAnalysis.intent.{code}")}</span>'
        for code in INTENT_CODES
    )
    # 단계(depth) 헤더 — 노드 컬럼과 정렬. tier0=진입, 그 뒤 1·2·3차 분기.
    tier_keys = ["pathAnalysis.flow.tierEntry", "pathAnalysis.flow.tier1",
                 "pathAnalysis.flow.tier2", "pathAnalysis.flow.tier3", "pathAnalysis.flow.tier4"]
    max_depth = _flow_max_depth(flow_tree)
    tiers = "".join(
        f'<div class="flow-tier"><span>{t(labels, tier_keys[min(d, len(tier_keys) - 1)])}</span></div>'
        for d in range(max_depth + 1)
    )
    return (
        '<div class="dash-card">'
        '<div class="dash-card__head">'
        f'<span class="dash-card__title">{t(labels, "pathAnalysis.dash.flowTitle")}</span>'
        '</div>'
        f'<p class="persona-section-desc">{desc}</p>'
        f'<div class="flow-legend">{t(labels, "pathAnalysis.dash.flowLegendLabel")}{legend}</div>'
        '<div class="flow-diagram">'
        '<div class="flow-inner">'
        f'<div class="flow-tiers">{tiers}</div>'
        f'<div class="flow-tree-wrap">{_flow_tree_html(flow_tree, seed=category)}</div>'
        '</div>'
        '</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# 경로 카드 — one journey (A → B → C) with flow classification
# ─────────────────────────────────────────

def _path_chain_html(nodes: List[Dict[str, Any]]) -> str:
    chips = []
    for i, n in enumerate(nodes):
        kw = kw_html(str(n.get("kw", "")))
        vol = n.get("volLabel", "")
        vol_html = f'<span class="path-chip__vol">{html.escape(str(vol))}</span>' if vol else ""
        chips.append(
            f'<span class="path-chip"><span class="path-chip__kw">{kw}</span>{vol_html}</span>'
        )
        if i < len(nodes) - 1:
            chips.append('<span class="path-arrow" aria-hidden="true">→</span>')
    return f'<div class="path-chain">{"".join(chips)}</div>'


def _field_html(label: str, value: Optional[str]) -> str:
    if not value:
        return ""
    return (
        '<div class="persona-field">'
        f'<div class="persona-field__label">{label}</div>'
        f'<div class="persona-field__val">{escape_with_strong(value)}</div>'
        '</div>'
    )


def path_card_html(path: Dict[str, Any], index: int, labels: Dict[str, str]) -> str:
    num = f"{index + 1:02d}"
    flow = path.get("flowType", "comparison")
    if flow not in FLOW_TYPES:
        flow = "comparison"
    flow_label = html.escape(t(labels, f"pathAnalysis.flow.{flow}"))

    badges = []
    vol = path.get("volumeLabel")
    if vol:
        badges.append(
            '<span class="persona-subhead__badge path-card__volbadge">'
            + html.escape(t(labels, "pathAnalysis.dash.pathVolumeBadge").replace("{vol}", str(vol)))
            + '</span>'
        )
    hops = path.get("hops")
    if hops:
        badges.append(
            '<span class="persona-subhead__badge path-card__hopbadge">'
            + html.escape(t(labels, "pathAnalysis.dash.pathHopBadge").replace("{hops}", str(hops)))
            + '</span>'
        )
    badges_html = "".join(badges)

    fields = "".join([
        _field_html(t(labels, "pathAnalysis.dash.pathIntentLabel"), path.get("intent")),
        _field_html(t(labels, "pathAnalysis.dash.pathLeakLabel"), path.get("leakOrMerge")),
        _field_html(t(labels, "pathAnalysis.dash.pathActionLabel"), path.get("action")),
    ])
    fields_html = f'<div class="persona-fields">{fields}</div>' if fields else ""

    evidence = path.get("evidence") or []
    evidence_html = ""
    if evidence:
        chips = "".join(
            '<span class="persona-ev__item">'
            f'{kw_html(str(e.get("kw", "")))}'
            + (f'<span class="persona-ev__vol">{html.escape(str(e["volLabel"]))}</span>'
               if e.get("volLabel") else "")
            + '</span>'
            for e in evidence
        )
        evidence_html = (
            '<div class="persona-subhead">'
            f'{t(labels, "pathAnalysis.dash.pathEvidenceTitle")}'
            f'<span class="persona-ev-note">{t(labels, "pathAnalysis.dash.pathEvidenceNote")}</span>'
            '</div>'
            f'<div class="persona-ev">{chips}</div>'
        )

    return (
        f'<div class="dash-card persona-card path-card path-card--{flow}">'
        '<div class="persona-card__head">'
        '<div class="persona-card__top">'
        f'<span class="persona-card__num">{num}</span>'
        '<div class="persona-card__topmain">'
        '<div class="persona-card__titlerow">'
        f'<span class="path-card__flow path-card__flow--{flow}">{flow_label}</span>'
        f'{badges_html}'
        '</div>'
        '</div>'
        '</div>'
        '</div>'

        '<div class="persona-card__body">'
        f'{_path_chain_html(path.get("nodes") or [])}'
        '</div>'

        '<div class="persona-card__body">'
        f'{fields_html}'
        f'{evidence_html}'
        '</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# 허브 카드 — a branch point (high fan-out node)
# ─────────────────────────────────────────

def hub_card_html(hub: Dict[str, Any], index: int, labels: Dict[str, str]) -> str:
    num = f"{index + 1:02d}"
    name = kw_html(str(hub.get("keyword", "")))

    badges = []
    vol = hub.get("volumeLabel")
    if vol:
        badges.append(
            '<span class="persona-subhead__badge path-card__volbadge">'
            + html.escape(t(labels, "pathAnalysis.dash.hubVolumeBadge").replace("{vol}", str(vol)))
            + '</span>'
        )
    deg = hub.get("outDegree")
    if deg:
        badges.append(
            '<span class="persona-subhead__badge hub-card__degbadge">'
            + html.escape(t(labels, "pathAnalysis.dash.hubDegreeBadge").replace("{n}", str(deg)))
            + '</span>'
        )
    badges_html = "".join(badges)

    meaning_html = _field_html(t(labels, "pathAnalysis.dash.hubMeaningLabel"), hub.get("meaning"))

    dilemmas = [d for d in (hub.get("dilemmas") or []) if str(d).strip()]
    dilemmas_html = ""
    if dilemmas:
        rows = "".join(f'<li>{escape_with_strong(d)}</li>' for d in dilemmas)
        dilemmas_html = (
            '<div class="persona-field">'
            f'<div class="persona-field__label">{t(labels, "pathAnalysis.dash.hubDilemmaLabel")}</div>'
            f'<ul class="hub-dilemmas">{rows}</ul>'
            '</div>'
        )

    actions = [a for a in (hub.get("actions") or []) if str(a).strip()]
    actions_html = ""
    if actions:
        rows = "".join(
            '<div class="rpt-act-card rpt-act-card--now">'
            f'<div class="rpt-act-card__body">{escape_with_strong(a)}</div>'
            '</div>'
            for a in actions
        )
        actions_html = (
            '<div class="persona-field">'
            f'<div class="persona-field__label">{t(labels, "pathAnalysis.dash.hubActionLabel")}</div>'
            f'<div class="rpt-act-list hub-actions">{rows}</div>'
            '</div>'
        )

    downstream = hub.get("downstream") or []
    downstream_html = ""
    if downstream:
        chips = "".join(
            '<span class="persona-ev__item">'
            f'{kw_html(str(d.get("kw", "")))}'
            + (f'<span class="persona-ev__vol">{html.escape(str(d["volLabel"]))}</span>'
               if d.get("volLabel") else "")
            + '</span>'
            for d in downstream
        )
        downstream_html = (
            '<div class="persona-subhead">'
            f'{t(labels, "pathAnalysis.dash.hubDownstreamTitle")}'
            '</div>'
            f'<div class="persona-ev">{chips}</div>'
        )

    return (
        '<div class="dash-card persona-card hub-card">'
        '<div class="persona-card__head">'
        '<div class="persona-card__top">'
        f'<span class="persona-card__num hub-card__num">{num}</span>'
        '<div class="persona-card__topmain">'
        '<div class="persona-card__titlerow">'
        f'<span class="persona-card__name">{name}</span>'
        f'{badges_html}'
        '</div>'
        '</div>'
        '</div>'
        '</div>'

        '<div class="persona-card__body">'
        f'<div class="persona-fields">{meaning_html}{dilemmas_html}{actions_html}</div>'
        f'{downstream_html}'
        '</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# Covers / tabs / panels
# ─────────────────────────────────────────

def dash_cover_html(meta: Dict[str, Any], category: str, gl_label: str,
                    market_label: Optional[str], labels: Dict[str, str],
                    overview: Optional[str] = None) -> str:
    eyebrow_base = t(labels, "pathAnalysis.dash.coverEyebrow")
    eyebrow = f"{eyebrow_base} · {html.escape(gl_label)}" if gl_label else eyebrow_base
    cover_meta = (
        t(labels, "pathAnalysis.dash.coverMeta")
        .replace("{date}", str(meta.get("date", "")))
        .replace("{pathCount}", str(meta.get("pathCount", "")))
        .replace("{hubCount}", str(meta.get("hubCount", "")))
        .replace("{nodeCount}", str(meta.get("nodeCount", "")))
    )
    return (
        '<div class="dash-cover-block">'
        '<div class="dash-card">'
        '<div class="dash-cover-gradient dash-cover-gradient--path">'
        f'<div class="dash-cover-eyebrow">{html.escape(eyebrow)}</div>'
        f'<div class="dash-cover-title">{t(labels, "agent.pathAnalysis.name")}</div>'
        f'<div class="dash-cover-category">{kw_html(category)}</div>'
        f'<div class="dash-cover-meta">{html.escape(cover_meta)}</div>'
        '</div>'
        + purpose_box_html(category, market_label, labels, "dash", overview=overview)
        + '</div>'
        '</div>'
    )


def dash_tabs_html(labels: Dict[str, str]) -> str:
    return (
        '<nav class="dash-tabs" aria-label="tabs">'
        '<div class="dash-tabs__inner" role="tablist">'
        '<button type="button" class="dash-tab active" role="tab" id="dash-tab-0" aria-selected="true" data-panel="0">'
        f'{t(labels, "pathAnalysis.dash.journeyTab")}'
        '</button>'
        '<button type="button" class="dash-tab" role="tab" id="dash-tab-1" aria-selected="false" data-panel="1">'
        f'{t(labels, "pathAnalysis.dash.actionTab")}'
        '</button>'
        '</div>'
        '</nav>'
    )


def dash_panel_journey_html(paths: List[Dict[str, Any]], hubs: List[Dict[str, Any]],
                            flow_tree: List[Dict[str, Any]], category: str,
                            labels: Dict[str, str]) -> str:
    sections: List[str] = [flow_diagram_html(flow_tree, category, labels)]

    if paths:
        cards = "".join(path_card_html(p, i, labels) for i, p in enumerate(paths))
        sections.append(
            '<div class="dash-card">'
            '<div class="dash-card__head">'
            '<span class="dash-card__title">'
            + t(labels, "pathAnalysis.dash.pathSectionTitle").replace("{category}", kw_html(category))
            + '</span>'
            f'<span class="dash-card__badge">{format_count(labels, len(paths))}</span>'
            '</div>'
            f'<p class="persona-section-desc">{t(labels, "pathAnalysis.dash.pathSectionDesc")}</p>'
            f'<div class="dash-card__body">{cards}</div>'
            '</div>'
        )

    if hubs:
        cards = "".join(hub_card_html(h, i, labels) for i, h in enumerate(hubs))
        sections.append(
            '<div class="dash-card">'
            '<div class="dash-card__head">'
            f'<span class="dash-card__title">{t(labels, "pathAnalysis.dash.hubSectionTitle")}</span>'
            f'<span class="dash-card__badge">{format_count(labels, len(hubs))}</span>'
            '</div>'
            f'<p class="persona-section-desc">{t(labels, "pathAnalysis.dash.hubSectionDesc")}</p>'
            f'<div class="dash-card__body">{cards}</div>'
            '</div>'
        )

    return (
        '<div class="dash-tab-panel active" role="tabpanel" aria-labelledby="dash-tab-0" data-panel="0">'
        + "".join(sections)
        + '</div>'
    )


# ─────────────────────────────────────────
# A4 cover & body
# ─────────────────────────────────────────

def a4_cover_page_html(meta: Dict[str, Any], category: str, labels: Dict[str, str]) -> str:
    a4_meta = (
        t(labels, "pathAnalysis.a4.coverMeta")
        .replace("{pathCount}", str(meta.get("pathCount", "")))
        .replace("{hubCount}", str(meta.get("hubCount", "")))
        .replace("{nodeCount}", str(meta.get("nodeCount", "")))
    )
    return (
        '<div class="rpt-page rpt-page--cover" id="page-0">'
        '<div class="cover-body">'
        '<div>'
        '<div class="cover-lm">ListeningMind.AI</div>'
        f'<div class="cover-title">{t(labels, "agent.pathAnalysis.name")}</div>'
        f'<div class="cover-category">{kw_html(category)}</div>'
        '<div class="cover-meta">'
        f'<span>{html.escape(str(meta.get("date", "")))}</span>'
        '<span class="cover-meta-sep">|</span>'
        f'<span>{html.escape(a4_meta)}</span>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
    )


def a4_body_page_html(paths: List[Dict[str, Any]], hubs: List[Dict[str, Any]],
                      flow_tree: List[Dict[str, Any]], actions: Dict[str, Any],
                      category: str, market_label: Optional[str],
                      labels: Dict[str, str], overview: Optional[str] = None) -> str:
    if actions is None:
        actions = {}
    parts = [
        purpose_box_html(category, market_label, labels, "a4", overview=overview),
        flow_diagram_html(flow_tree, category, labels),
    ]
    if paths:
        parts.append(f'<div class="persona-subhead">{t(labels, "pathAnalysis.a4.pathSection").replace("{category}", kw_html(category))}</div>')
        parts.append("".join(path_card_html(p, i, labels) for i, p in enumerate(paths)))
    if hubs:
        parts.append(f'<div class="persona-subhead">{t(labels, "pathAnalysis.dash.hubSectionTitle")}</div>')
        parts.append("".join(hub_card_html(h, i, labels) for i, h in enumerate(hubs)))

    synthesis = actions.get("synthesis")
    if synthesis:
        parts.append(f'<div class="a4-prose">{escape_with_strong(synthesis)}</div>')
    for key, title_key, kind in (
        ("insights", "customerAnalysis.dash.actionsInsightsTitle", "insight"),
        ("now", "customerAnalysis.dash.actionsNowTitle", "now"),
        ("future", "customerAnalysis.dash.actionsFutureTitle", "future"),
    ):
        items = actions.get(key) or []
        if not items:
            continue
        parts.append(
            f'<div class="persona-subhead">{t(labels, title_key)}</div>'
            f'<div class="rpt-act-list">{action_list_html(items, kind, labels)}</div>'
        )
    return (
        '<div class="rpt-page" id="page-1">'
        '<div class="page-body">'
        + "".join(parts)
        + '</div>'
        '</div>'
    )
