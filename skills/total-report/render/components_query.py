"""HTML builders for the query-opportunity report.

Each builder returns an HTML string. Chart data is embedded as
<script type="application/json" id="{canvasId}-data"> blocks that the inline
QUERY_CHART_SCRIPT (render_report.py) reads to draw Chart.js charts.
"""

import html
import json

from components import t  # shared label helper


def _esc(s):
    return html.escape(str(s if s is not None else ""))


def _fmt(n):
    try:
        return f"{int(round(n)):,}"
    except (TypeError, ValueError):
        return "0"


def _chart_data(canvas_id, config):
    # Keywords come from third-party search-query data and may contain a
    # literal "</script>" or "<!--<script>" — either can break out of the
    # JSON <script> block (the HTML tokenizer's script-data-escaped state
    # kicks in on "<!--" and can swallow the rest of the document even
    # without a bare "</"). Escape every "<" as the JSON unicode escape for
    # "less-than" so the tokenizer never sees a raw "<"; JSON.parse still
    # round-trips it back to "<" at parse time.
    payload = json.dumps(config, ensure_ascii=False).replace("<", "\\u003c")
    return (f'<script type="application/json" id="{canvas_id}-data">'
            f'{payload}</script>')


# ── 대시보드: 커버 + KPI ──
def _kpi_cells(data, labels):
    """Shared KPI grid cells for both the dashboard and A4 covers."""
    k = data["kpis"]
    primary = k.get("primaryIntent", "")
    # NOTE: components.t(labels, key) has no `default` param (falls back to the
    # key itself if missing) — so the "-" fallback is applied here instead.
    intent_lbl = t(labels, f"intent.{primary}") if primary else "-"
    kpis = [
        (t(labels, "kpi.queryCount"), _fmt(data["queryCount"])),
        (t(labels, "kpi.totalVolume"), _fmt(k["totalVolume"])),
        (t(labels, "kpi.avgCpc"), _fmt(k["avgCpc"])),
        (t(labels, "kpi.primaryIntent"), intent_lbl),
    ]
    return "".join(
        f'<div class="qo-kpi"><div class="qo-kpi__label">{_esc(lbl)}</div>'
        f'<div class="qo-kpi__value">{_esc(val)}</div></div>'
        for lbl, val in kpis
    )


def dash_cover_html(data, category, gl_label, labels):
    cells = _kpi_cells(data, labels)
    return (
        f'<section class="qo-cover">'
        f'<h1>{_esc(t(labels, "agent.queryOpportunity.name"))} · {_esc(category)}</h1>'
        f'<p class="qo-cover__meta">{_esc(gl_label)} · {_esc(data["date"])} · '
        f'{_fmt(data["queryCount"])} queries</p>'
        f'<div class="qo-kpi-grid">{cells}</div>'
        f'</section>'
    )


def dash_tabs_html(labels):
    return (
        '<div class="dash-tabs" role="tablist">'
        f'<button class="dash-tab active" role="tab" data-panel="opportunity" aria-selected="true">'
        f'{_esc(t(labels, "queryOpportunity.dashTab.opportunity"))}</button>'
        f'<button class="dash-tab" role="tab" data-panel="actions" aria-selected="false">'
        f'{_esc(t(labels, "queryOpportunity.dashTab.actions"))}</button>'
        '</div>'
    )


def _funnel_config(data, labels):
    f = data["funnel"]
    return {
        "type": "doughnut",
        "data": {
            "labels": [t(labels, f"intent.{k}") for k in ("i", "n", "c", "t")],
            "datasets": [{"data": [f["i"], f["n"], f["c"], f["t"]],
                          "backgroundColor": ["#8ecae6", "#adb5bd", "#ffb703", "#fb8500"]}],
        },
        "options": {"responsive": True, "maintainAspectRatio": False,
                    "plugins": {"legend": {"position": "right"}}},
    }


def _opportunity_map_config(data, labels):
    pts = [{"x": q["competition_index"], "y": q["volume_avg"],
            "r": max(4, min(24, (q["cpc"] or 0) / 80)), "label": q["keyword"]}
           for q in data["queries"]]
    return {
        "type": "bubble",
        "data": {"datasets": [{"label": t(labels, "section.opportunityMap"),
                               "data": pts, "backgroundColor": "rgba(170,24,204,.45)"}]},
        "options": {"responsive": True, "maintainAspectRatio": False,
                    "scales": {"x": {"title": {"display": True, "text": "경쟁도"}},
                               "y": {"title": {"display": True, "text": "월평균 검색량"}}}},
    }


def _trend_config(data, labels):
    tr = data["trend"]
    palette = ["#AA18CC", "#CD3197", "#fb8500", "#219ebc", "#2a9d8f"]
    ds = [{"label": s["keyword"], "data": s["data"], "borderColor": palette[i % len(palette)],
           "fill": False, "tension": 0.3} for i, s in enumerate(tr["series"])]
    return {"type": "line", "data": {"labels": tr["labels"], "datasets": ds},
            "options": {"responsive": True, "maintainAspectRatio": False}}


# ── 빈 섹션 생략(§8): intents/monthly_volume이 없으면 전부-0 도넛이나 빈
# 라인차트가 그려지는 대신 해당 섹션 자체를 생략한다. ──
def _has_funnel_data(data):
    return sum(data["funnel"].values()) > 0


def _has_trend_data(data):
    series = data["trend"]["series"]
    return bool(series) and any(s.get("data") for s in series)


def _table_html(queries, labels):
    head = "".join(f"<th>{_esc(t(labels, k))}</th>" for k in
                   ("table.keyword", "table.volume", "table.competition", "table.cpc",
                    "table.intent", "table.trend", "table.score"))
    rows = []
    for q in queries:
        badge = q["quadrant"]
        pi = q["primary_intent"]
        # NOTE: components.t(labels, key) has no `default` param — apply the
        # fallback (raw primary_intent) here instead of passing it to t().
        intent_lbl = t(labels, f"intent.{pi}") if pi else pi
        rows.append(
            f'<tr><td>{_esc(q["keyword"])} '
            f'<span class="qo-badge qo-badge--{badge}">{_esc(t(labels, "quadrant."+badge))}</span></td>'
            f'<td>{_fmt(q["volume_avg"])}</td><td>{_esc(q["competition"] or q["competition_index"])}</td>'
            f'<td>{_fmt(q["cpc"])}</td><td>{_esc(intent_lbl)}</td>'
            f'<td>{q["volume_trend"]:.2f}</td><td>{q["opportunity_score"]:.3f}</td></tr>'
        )
    return f'<table class="qo-table"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


# ── 대시보드: 기회 분석 패널 ──
def dash_panel_opportunity_html(data, labels):
    omap = _chart_data("opportunityMapChart", _opportunity_map_config(data, labels))
    parts = ['<div class="dash-tab-panel active" data-panel="opportunity">']
    if _has_funnel_data(data):
        funnel = _chart_data("funnelChart", _funnel_config(data, labels))
        parts.append(
            f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.funnel"))}</div>'
            f'<div class="qo-chart-wrap"><canvas id="funnelChart"></canvas></div>{funnel}</div>'
        )
    parts.append(
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.opportunityMap"))}</div>'
        f'<div class="qo-chart-wrap"><canvas id="opportunityMapChart"></canvas></div>{omap}</div>'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.topQueries"))}</div>'
        f'{_table_html(data["topQueries"], labels)}</div>'
    )
    if _has_trend_data(data):
        trend = _chart_data("trendChart", _trend_config(data, labels))
        parts.append(
            f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.trend"))}</div>'
            f'<div class="qo-chart-wrap"><canvas id="trendChart"></canvas></div>{trend}</div>'
        )
    parts.append('</div>')
    return "".join(parts)


# ── 대시보드: 실행 제안 패널 ──
def _action_items(items):
    return "".join(
        f'<div class="qo-action"><strong>{_esc(it.get("title",""))}</strong>'
        f'<div>{_esc(it.get("body",""))}</div></div>' for it in (items or [])
    )


def dash_panel_actions_html(actions, labels):
    return (
        '<div class="dash-tab-panel" data-panel="actions">'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.insight"))}</div>'
        f'<p>{_esc(actions.get("summary",""))}</p></div>'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "actions.now"))}</div>'
        f'<div class="qo-actions">{_action_items(actions.get("now"))}</div></div>'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "actions.future"))}</div>'
        f'<div class="qo-actions">{_action_items(actions.get("future"))}</div></div>'
        '</div>'
    )


# ── A4 뷰 ──
# report-shell.css already provides a full A4/print system — `.rpt-page` is
# one A4 page, `.rpt-page--cover` is the cover variant, and @media print
# handles @page sizing + break-after pagination for us. A4 charts reuse the
# same *_config() builders as the dashboard but draw into distinctly-id'd
# canvases (funnelChartA4 / opportunityMapChartA4 / trendChartA4) so the
# dashboard and A4 Chart.js instances never collide.
def a4_cover_page_html(data, category, labels):
    cells = _kpi_cells(data, labels)
    return (
        '<div class="rpt-page rpt-page--cover" id="page-0">'
        '<div class="cover-body">'
        '<div>'
        '<div class="cover-lm">ListeningMind.AI</div>'
        f'<div class="cover-title">{_esc(t(labels, "agent.queryOpportunity.name"))}</div>'
        f'<div class="cover-category">{_esc(category)}</div>'
        '<div class="cover-meta">'
        f'<span>{_esc(data["date"])}</span>'
        '<span class="cover-meta-sep">|</span>'
        f'<span>{_fmt(data["queryCount"])} queries</span>'
        '</div>'
        '</div>'
        f'<div class="qo-kpi-grid">{cells}</div>'
        '</div>'
        '</div>'
    )


# The A4 sheet is a fixed 794×1123px .rpt-page — a table of all queries
# (step-1 default limit is 300) would overflow a single sheet, so the table
# is paginated into ~ROWS_PER_PAGE-row chunks, each its own .rpt-page, so
# @media print's per-page-body pagination applies correctly.
ROWS_PER_PAGE = 24


def a4_body_pages_html(data, actions, category, labels):
    omap = _chart_data("opportunityMapChartA4", _opportunity_map_config(data, labels))

    charts_sections = []
    if _has_funnel_data(data):
        funnel = _chart_data("funnelChartA4", _funnel_config(data, labels))
        charts_sections.append(
            f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.funnel"))}</div>'
            f'<div class="qo-chart-wrap"><canvas id="funnelChartA4"></canvas></div>{funnel}</div>'
        )
    charts_sections.append(
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.opportunityMap"))}</div>'
        f'<div class="qo-chart-wrap"><canvas id="opportunityMapChartA4"></canvas></div>{omap}</div>'
    )

    page_num = 1
    pages = [
        f'<div class="rpt-page" id="page-{page_num}"><div class="page-body">'
        f'{"".join(charts_sections)}'
        '</div></div>'
    ]
    page_num += 1

    trend_section = ""
    if _has_trend_data(data):
        trend = _chart_data("trendChartA4", _trend_config(data, labels))
        trend_section = (
            f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.trend"))}</div>'
            f'<div class="qo-chart-wrap"><canvas id="trendChartA4"></canvas></div>{trend}</div>'
        )

    queries = data["queries"] or []
    chunks = [queries[i:i + ROWS_PER_PAGE] for i in range(0, len(queries), ROWS_PER_PAGE)] or [[]]
    for i, chunk in enumerate(chunks):
        table_sections = []
        if i == 0:
            table_sections.append(trend_section)
        title = f'<div class="qo-section__title">{_esc(t(labels, "section.topQueries"))}</div>' if i == 0 else ""
        table_sections.append(f'<div class="qo-section">{title}{_table_html(chunk, labels)}</div>')
        pages.append(
            f'<div class="rpt-page" id="page-{page_num}"><div class="page-body">'
            f'{"".join(table_sections)}'
            '</div></div>'
        )
        page_num += 1

    pages.append(
        f'<div class="rpt-page" id="page-{page_num}"><div class="page-body">'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "section.insight"))}</div>'
        f'<p class="a4-prose">{_esc(actions.get("summary",""))}</p></div>'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "actions.now"))}</div>'
        f'<div class="qo-actions">{_action_items(actions.get("now"))}</div></div>'
        f'<div class="qo-section"><div class="qo-section__title">{_esc(t(labels, "actions.future"))}</div>'
        f'<div class="qo-actions">{_action_items(actions.get("future"))}</div></div>'
        '</div></div>'
    )
    return "".join(pages)
