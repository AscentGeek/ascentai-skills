"""Cluster-specific HTML builders that extend the shared customer-analysis
card renderer (components.py) with the two ClusterFinder-native sections:

  1. hub_table_html  — the 허브 키워드 요약 표
     [검색목적 클러스터명 | 클러스터 | 대표(허브) 키워드] — mirrors the
     ClusterHubService "## ClusterHub 대표 키워드" table the production
     cluster_finder agent emits after its analysis.
  2. flows_html      — the From→To 흐름 분석 section (agent_cluster §3):
     representative hub keyword → cluster A → cluster B transition paths.

Both return dash-card blocks so they slot into the existing dashboard/A4 shell
(components.py owns the cover, cards, and actions panel unchanged).
"""

import html

import components as ca  # shared card/cover/actions builders
from components import t, escape_with_strong, kw_html  # shared helpers


def _esc(s):
    return html.escape(str(s if s is not None else ""))


# ─────────────────────────────────────────
# 허브 키워드 요약 표
# ─────────────────────────────────────────

def hub_table_html(hub_table, labels, *, variant="dash"):
    """Render the hub-keyword summary table. `hub_table` rows:
    {groupName, clusterIds: [A,B], hubKeywords: [kw,...]}."""
    if not hub_table:
        return ""
    head = (
        '<tr>'
        f'<th>{_esc(t(labels, "clusterLandscape.hubTable.colGroup"))}</th>'
        f'<th>{_esc(t(labels, "clusterLandscape.hubTable.colClusters"))}</th>'
        f'<th>{_esc(t(labels, "clusterLandscape.hubTable.colHub"))}</th>'
        '</tr>'
    )
    rows = []
    for r in hub_table:
        clusters = ", ".join(r.get("clusterIds") or [])
        hubs = "".join(
            f'<span class="cl-hub-chip">{kw_html(kw)}</span>'
            for kw in (r.get("hubKeywords") or [])
        )
        rows.append(
            '<tr>'
            f'<td class="cl-hubtable__group">{_esc(r.get("groupName", ""))}</td>'
            f'<td class="cl-hubtable__clusters">{_esc(clusters)}</td>'
            f'<td class="cl-hubtable__hub">{hubs}</td>'
            '</tr>'
        )
    table = (
        '<div class="cl-hubtable-wrap">'
        f'<table class="cl-hubtable"><thead>{head}</thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
        '</div>'
    )
    title = t(labels, "clusterLandscape.hubTable.title")
    note = t(labels, "clusterLandscape.hubTable.note")
    return (
        '<div class="dash-card cl-section">'
        '<div class="dash-card__head">'
        f'<span class="dash-card__title">{_esc(title)}</span>'
        '</div>'
        f'<p class="persona-section-desc">{_esc(note)}</p>'
        f'<div class="dash-card__body">{table}</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# From → To 흐름 분석
# ─────────────────────────────────────────

def _flow_path_html(path_detail):
    steps = []
    for step in path_detail:
        letter = _esc(step.get("cluster", ""))
        hub = step.get("hub")
        label = f'{letter} · {kw_html(hub)}' if hub else letter
        steps.append(f'<span class="cl-flow__node">{label}</span>')
    return '<span class="cl-flow__arrow">→</span>'.join(steps)


def _flow_card_html(flow, labels):
    hub = flow.get("hubKeyword", "")
    vol = flow.get("hubVolLabel", "")
    conn = flow.get("connectivity")
    character = flow.get("character", "")
    meta_parts = []
    if vol:
        meta_parts.append(
            t(labels, "clusterLandscape.flow.volLabel").replace("{vol}", str(vol))
        )
    if conn:
        meta_parts.append(
            t(labels, "clusterLandscape.flow.connLabel").replace("{n}", str(conn))
        )
    if character:
        meta_parts.append(character)
    meta = (
        f'<span class="cl-flow__meta">{_esc(" · ".join(meta_parts))}</span>'
        if meta_parts else ""
    )
    path_html = _flow_path_html(flow.get("pathDetail") or [])
    insight = flow.get("insight")
    insight_html = (
        f'<div class="cl-flow__insight">{escape_with_strong(insight)}</div>'
        if insight else ""
    )
    return (
        '<div class="cl-flow">'
        '<div class="cl-flow__head">'
        f'<span class="cl-flow__hub">{kw_html(hub)}</span>'
        f'{meta}'
        '</div>'
        f'<div class="cl-flow__path">{path_html}</div>'
        f'{insight_html}'
        '</div>'
    )


def flows_html(flows, labels):
    """Render the From→To flow section as a dash-card. `flows` rows:
    {hubKeyword, hubVolLabel, character, path:[A,B], pathDetail:[{cluster,hub}], insight}."""
    if not flows:
        return ""
    cards = "".join(_flow_card_html(f, labels) for f in flows)
    title = t(labels, "clusterLandscape.flow.title")
    note = t(labels, "clusterLandscape.flow.note")
    return (
        '<div class="dash-card cl-section">'
        '<div class="dash-card__head">'
        f'<span class="dash-card__title">{_esc(title)}</span>'
        '</div>'
        f'<p class="persona-section-desc">{_esc(note)}</p>'
        f'<div class="dash-card__body cl-flows">{cards}</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# Dashboard panel wrappers (share data-panel with the components.py panels so
# the tab-toggle JS shows/hides them together with the cards / actions panels)
# ─────────────────────────────────────────

def dash_hub_panel_html(hub_table, labels):
    """Hub table lives under tab 0 (검색 클러스터), after the cluster cards."""
    inner = hub_table_html(hub_table, labels)
    if not inner:
        return ""
    return (
        '<div class="dash-tab-panel active" role="tabpanel" aria-labelledby="dash-tab-0" data-panel="0">'
        + inner + '</div>'
    )


def dash_flows_panel_html(flows, labels):
    """Flows live under tab 1 (흐름·인사이트), before the insight cards."""
    inner = flows_html(flows, labels)
    if not inner:
        return ""
    return (
        '<div class="dash-tab-panel" role="tabpanel" aria-labelledby="dash-tab-1" data-panel="1">'
        + inner + '</div>'
    )


# ─────────────────────────────────────────
# A4 body — cover reuses components.a4_cover_page_html; the body inserts the
# hub table + flows between the cluster cards and the insight blocks.
# ─────────────────────────────────────────

def a4_body_page_html(groups, hub_table, flows, actions, category, market_label, labels, overview=None):
    if isinstance(actions, str) or actions is None:
        actions = {"synthesis": actions}
    cards = "".join(ca.persona_card_html(g, i, labels) for i, g in enumerate(groups))
    hub_html = hub_table_html(hub_table, labels, variant="a4")
    flow_html = flows_html(flows, labels)
    synthesis = actions.get("synthesis")
    parts = [
        f'<div class="a4-prose">{escape_with_strong(synthesis)}</div>' if synthesis else ""
    ]
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
            f'<div class="rpt-act-list">{ca.action_list_html(items, kind, labels)}</div>'
        )
    return (
        '<div class="rpt-page" id="page-1">'
        '<div class="page-body">'
        + ca.purpose_box_html(category, market_label, labels, "a4", overview=overview)
        + cards
        + hub_html
        + flow_html
        + "".join(parts)
        + '</div>'
        '</div>'
    )
