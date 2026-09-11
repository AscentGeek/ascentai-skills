"""HTML builders for the total-report UMBRELLA shell (탭 1 통합 요약 + 외곽 4탭).

This is the ONLY net-new renderer in total-report. Tabs 2~4 reuse the vendored
finder builders verbatim (components.py / components_path.py / components_cluster.py);
this module supplies:

  1. total_cover_html      — the umbrella cover (통합 요약문 = LLM overview).
  2. tabnav_html           — the top-level 4-tab nav (통합요약/쿼리/여정/클러스터).
  3. finder_panel_html     — the .tot-panel wrapper for an OUTER finder tab (q/p/c).
  4. tab1_intro_html       — 탭 1 머리글(리드 + 읽는 법 + recap + 통합 요약 박스).
  5. module_* (M1~M6)      — the six CROSS-INSIGHT modules that only exist when the
                             three finders are joined; each renders facts(numbers) and
                             merges the matching id-keyed LLM note (lm_total.json).
  6. nodata_html           — placeholder when a finder's inputs are absent.
  7. total_a4_pages_html   — the 통합 A4 cover + body (flat, always-open modules).

숫자·구조·좌표는 total_aggregate.py 가 계산해 lm_total_facts.json 에 담고, LLM 은 그
안정 id 에 대응하는 **정성 노트만**(lm_total.json) 씁니다. 렌더러는 둘을 **id 로 머지**
합니다 — facts 에 없는 id 의 노트는 무시(별도 환각필터 불필요), 노트 없는 facts 는 숫자만.

카피 규율: 모든 사용자 노출 문구는 평이한 한국어(라벨 JSON). 전문용어는 UI 에 노출하지
않고 각 모듈에 "쉽게 말하면 …" 마이크로카피를 답니다. 텍스트는 escape_with_strong 로
HTML-escape 하고 <strong> 만 허용(형제 규율 계승).
"""

import html
from typing import Any, Dict, List, Optional

from components import t, escape_with_strong


# key → color/label family used across the umbrella chrome
_FINDER_KEYS = ("t", "q", "p", "c")


# ─────────────────────────────────────────
# small formatting / primitive helpers
# ─────────────────────────────────────────

def _fmt(n: Any) -> str:
    """Integer with thousands separators; '' for None/blank."""
    if n is None or n == "":
        return ""
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return html.escape(str(n))


def _dec(x: Any, d: int = 2) -> str:
    try:
        return f"{float(x):.{d}f}"
    except (TypeError, ValueError):
        return "—"


def _signed(x: Any, d: int = 2) -> str:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    return f"+{v:.{d}f}" if v >= 0 else f"{v:.{d}f}"


def _pctw(x: Any) -> str:
    """0..1 → clamped percent-width string."""
    try:
        v = max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        v = 0.0
    return f"{v * 100:.1f}"


def _badge(text: str, kind: str) -> str:
    return f'<span class="ti-badge ti-badge--{kind}">{html.escape(text)}</span>'


def bar_badge(label_html: str, pct: Any, *, sub_html: str = "",
              tone: str = "what", badge: Optional[tuple] = None,
              val: str = "") -> str:
    """THE shared bar+badge row primitive.

    label_html : already-escaped/safe label markup for the left column.
    pct        : 0..1 fill fraction of the bar.
    sub_html   : optional muted sub-line under the label (safe markup).
    tone       : bar fill color family (what/how/who/good/bad/warn/hub/na).
    badge      : (text, kind) → right-aligned pill; else `val` text is shown.
    """
    if badge is not None:
        right = _badge(badge[0], badge[1])
    elif val:
        right = f'<span class="ti-row__val">{html.escape(val)}</span>'
    else:
        right = ""
    sub = f'<small>{sub_html}</small>' if sub_html else ""
    return (
        '<div class="ti-row">'
        f'<div class="ti-row__lbl">{label_html}{sub}</div>'
        f'<div class="ti-bar"><i class="ti-bar__fill ti-bar__fill--{tone}" style="width:{_pctw(pct)}%"></i></div>'
        f'<div class="ti-row__right">{right}</div>'
        '</div>'
    )


def _mod_shell(mn: str, title: str, desc: str, plain: str, body: str, *,
               collapsible: bool = True, open_: bool = False) -> str:
    """Module card. Dashboard → <details> (progressive disclosure); A4 → flat
    always-open <section>. `plain` = the '쉽게 말하면 …' microcopy — trusted label
    markup (its lead word carries its own <strong>)."""
    plain_box = f'<div class="ti-plain">{plain}</div>' if plain else ""
    head_inner = (
        f'<span class="ti-mod__mn">{html.escape(mn)}</span>'
        '<div class="ti-mod__ttl">'
        f'<h3>{html.escape(title)}</h3>'
        f'<div class="ti-mod__der">{html.escape(desc)}</div>'
        '</div>'
    )
    if collapsible:
        open_attr = " open" if open_ else ""
        return (
            f'<details class="ti-mod"{open_attr}>'
            f'<summary class="ti-mod__sum">{head_inner}<span class="ti-mod__chev">▸</span></summary>'
            f'<div class="ti-mod__body">{plain_box}{body}</div>'
            '</details>'
        )
    return (
        '<section class="ti-mod ti-mod--flat">'
        f'<div class="ti-mod__hd">{head_inner}</div>'
        f'<div class="ti-mod__body">{plain_box}{body}</div>'
        '</section>'
    )


def _honest(text: str, *, lb: str) -> str:
    """Honest caveat box (trusted label text — may carry <strong>)."""
    if not text:
        return ""
    return (
        '<div class="ti-honest">'
        f'<span class="ti-honest__lb">{html.escape(lb)}</span> {text}'
        '</div>'
    )


def _notes_by_id(items: List[Dict[str, Any]], field: str = "note") -> Dict[str, str]:
    out: Dict[str, str] = {}
    for it in items or []:
        _id = it.get("id")
        if _id and it.get(field):
            out[str(_id)] = str(it[field])
    return out


# ─────────────────────────────────────────
# Umbrella cover (통합 요약문)  — unchanged contract
# ─────────────────────────────────────────

def total_cover_html(counts: Dict[str, Any], category: str, gl_label: str,
                     market_label: Optional[str], labels: Dict[str, str],
                     overview: Optional[str] = None) -> str:
    eyebrow_base = t(labels, "totalInsight.cover.eyebrow")
    eyebrow = f"{eyebrow_base} · {html.escape(gl_label)}" if gl_label else eyebrow_base

    meta_bits: List[str] = []
    date = counts.get("date")
    if date:
        meta_bits.append(t(labels, "totalInsight.cover.metaDate").replace("{date}", str(date)))
    if market_label:
        meta_bits.append(t(labels, "totalInsight.cover.metaMarket").replace("{market}", str(market_label)))
    if counts.get("clusterCount"):
        meta_bits.append(t(labels, "totalInsight.cover.metaCluster").replace("{clusterCount}", str(counts["clusterCount"])))
    if counts.get("personaCount"):
        meta_bits.append(t(labels, "totalInsight.cover.metaPersona").replace("{personaCount}", str(counts["personaCount"])))
    if counts.get("pathCount"):
        meta_bits.append(t(labels, "totalInsight.cover.metaPath").replace("{pathCount}", str(counts["pathCount"])))
    meta_html = "".join(f"<span>{html.escape(b)}</span>" for b in meta_bits)

    summary_html = ""
    if overview:
        summary_html = (
            '<div class="tot-cover__summary">'
            f'<div class="tot-cover__summary-t">{t(labels, "totalInsight.cover.summaryTitle")}</div>'
            f'<p>{escape_with_strong(overview)}</p>'
            '</div>'
        )

    return (
        '<div class="tot-cover">'
        f'<div class="tot-cover__eyebrow">{html.escape(eyebrow)}</div>'
        f'<h1 class="tot-cover__title">{t(labels, "totalInsight.reportTitle")}</h1>'
        f'<div class="tot-cover__cat">{html.escape(category)}</div>'
        f'<div class="tot-cover__meta">{meta_html}</div>'
        f'{summary_html}'
        '</div>'
    )


# ─────────────────────────────────────────
# Outer 4-tab nav / finder panel / no-data  — unchanged contract
# ─────────────────────────────────────────

def tabnav_html(labels: Dict[str, str]) -> str:
    btns = []
    for i, key in enumerate(_FINDER_KEYS):
        selected = "true" if i == 0 else "false"
        active = " is-active" if i == 0 else ""
        short = t(labels, f"totalInsight.tab.{key}.short")
        slug = t(labels, f"totalInsight.tab.{key}.slug")
        btns.append(
            f'<button type="button" class="tot-tab tot-tab--{key}{active}" '
            f'role="tab" aria-selected="{selected}" data-tab="{key}">'
            f'<span class="tot-tab__name">{html.escape(short)}</span>'
            f'<span class="tot-tab__slug">{html.escape(slug)}</span>'
            '</button>'
        )
    return (
        '<nav class="tot-tabnav" role="tablist" aria-label="reports">'
        + "".join(btns)
        + '</nav>'
    )


def finder_panel_html(key: str, body_html: str, labels: Dict[str, str], *, active: bool = False) -> str:
    active_cls = " is-active" if active else ""
    k_label = t(labels, f"totalInsight.tab.{key}.k")
    title = t(labels, f"totalInsight.tab.{key}.title")
    sub = t(labels, f"totalInsight.tab.{key}.sub")
    return (
        f'<section class="tot-panel tot-panel--{key}{active_cls}" data-tab="{key}" role="tabpanel">'
        '<div class="tot-panel__head">'
        f'<span class="tot-panel__k tot-k--{key}">{html.escape(k_label)}</span>'
        f'<h2 class="tot-panel__title">{html.escape(title)}</h2>'
        f'<span class="tot-panel__sub">{html.escape(sub)}</span>'
        '</div>'
        f'{body_html}'
        '</section>'
    )


def nodata_html(labels: Dict[str, str]) -> str:
    return (
        '<div class="dash-card tot-nodata">'
        '<div class="dash-card__body">'
        f'<p class="mr-summary-text">{t(labels, "totalInsight.nodata")}</p>'
        '</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# 탭 1 머리글 — 리드 + 읽는 법 + recap + 통합 요약
# ─────────────────────────────────────────

def tab1_head_html(labels: Dict[str, str]) -> str:
    return (
        '<div class="tot-panel__head">'
        f'<span class="tot-panel__k tot-k--t">{html.escape(t(labels, "totalInsight.tab.t.k"))}</span>'
        f'<h2 class="tot-panel__title">{html.escape(t(labels, "totalInsight.tab.t.title"))}</h2>'
        f'<span class="tot-panel__sub">{html.escape(t(labels, "totalInsight.tab.t.sub"))}</span>'
        '</div>'
    )


def _readguide_html(labels: Dict[str, str]) -> str:
    rows = "".join(
        f'<div>{t(labels, f"ti.readguide.m{i}")}</div>' for i in range(1, 7)
    )
    return (
        '<div class="ti-readguide">'
        f'<div class="ti-readguide__t">{html.escape(t(labels, "ti.readguide.title"))}</div>'
        f'<div class="ti-readguide__list">{rows}</div>'
        '</div>'
    )


def _recap_html(recap: Dict[str, Any], labels: Dict[str, str]) -> str:
    if not recap:
        return ""
    cards = []
    order = (
        ("q", "query", "topGroup"),
        ("p", "path", "topHub"),
        ("c", "cluster", "topCluster"),
    )
    for key, fkey, topfield in order:
        d = recap.get(fkey)
        if not d:
            continue
        count = d.get("count", "")
        top = d.get(topfield, "")
        tpl = t(labels, f"ti.recap.{key}.tpl")
        v = tpl.replace("{count}", str(count)).replace("{top}", html.escape(str(top)))
        cards.append(
            f'<div class="ti-rc ti-rc--{key}">'
            f'<div class="ti-rc__h">{html.escape(t(labels, f"ti.recap.{key}.h"))}</div>'
            f'<div class="ti-rc__v">{v}</div>'
            '</div>'
        )
    if not cards:
        return ""
    return f'<div class="ti-recap">{"".join(cards)}</div>'


def _overview_html(overview: Optional[str], labels: Dict[str, str]) -> str:
    if not overview:
        return ""
    return (
        '<div class="ti-overview">'
        f'<div class="ti-overview__t">{html.escape(t(labels, "totalInsight.cover.summaryTitle"))}</div>'
        f'<p>{escape_with_strong(overview)}</p>'
        '</div>'
    )


def tab1_intro_html(facts: Dict[str, Any], notes: Dict[str, Any], labels: Dict[str, str]) -> str:
    return (
        tab1_head_html(labels)
        + f'<p class="ti-lede">{escape_with_strong(t(labels, "ti.lede"))}</p>'
        + _readguide_html(labels)
        + _recap_html(facts.get("recap") or {}, labels)
        + _overview_html(notes.get("overview"), labels)
    )


# ─────────────────────────────────────────
# M1 — 커버리지 갭 (UpSet 막대 + 갭 칩 + 커버리지 미터)
# ─────────────────────────────────────────

def _upset_row(sets: List[str], count: int, vol: int, maxvol: int,
               labels: Dict[str, str]) -> str:
    on = set(sets)
    dots = "".join(
        f'<span class="ti-dot ti-dot--{k.lower()}{" is-on" if k in on else ""}"></span>'
        for k in ("Q", "P", "C")
    )
    if len(sets) >= 3:
        tone = "good"
    elif len(sets) == 1:
        tone = {"Q": "what", "P": "how", "C": "who"}.get(sets[0], "na")
    else:
        tone = "na"
    w = _pctw((vol / maxvol) if maxvol else 0)
    return (
        '<div class="ti-up">'
        f'<div class="ti-up__set">{dots}</div>'
        f'<div class="ti-bar"><i class="ti-bar__fill ti-bar__fill--{tone}" style="width:{w}%"></i></div>'
        f'<span class="ti-up__val">'
        f'{t(labels, "ti.unit.count").replace("{n}", str(int(count)))} · {_fmt(vol)}</span>'
        '</div>'
    )


def _gap_chip(item: Dict[str, Any], bucket_lb: str) -> str:
    kw = html.escape(str(item.get("kw", "")))
    vol = _fmt(item.get("volume"))
    trend = item.get("trend")
    trend_html = (
        f'<span class="ti-chip__trend">↑{int(trend)}</span>'
        if isinstance(trend, (int, float)) and trend >= 8 else ""
    )
    return (
        '<span class="ti-gapchip">'
        f'<span class="ti-gapchip__lb">{html.escape(bucket_lb)}</span> '
        f'<b>{kw}</b> {vol}{trend_html}'
        '</span>'
    )


def module_coverage(facts: Dict[str, Any], labels: Dict[str, str], *,
                    collapsible: bool = True) -> str:
    cov = facts.get("coverage") or {}
    combos = cov.get("combos") or []
    body_parts: List[str] = []

    if combos:
        maxvol = max((c.get("volume", 0) or 0) for c in combos) or 1
        rows = "".join(
            _upset_row(c.get("sets", []), c.get("count", 0), c.get("volume", 0), maxvol, labels)
            for c in combos
        )
        body_parts.append(f'<div class="ti-upset">{rows}</div>')

    pct = cov.get("coveragePct")
    if pct is not None:
        body_parts.append(
            '<div class="ti-covmeter">'
            f'<span>{html.escape(t(labels, "ti.m1.coverMeter"))}</span>'
            f'<div class="ti-covmeter__track"><i style="width:{_pctw((float(pct) / 100) if pct else 0)}%"></i></div>'
            f'<b class="ti-covmeter__n">{_dec(pct, 1)}%</b>'
            '</div>'
        )

    gap_buckets = cov.get("gapBuckets") or {}
    chips: List[str] = []
    for bkey, lbkey in (("q_not_p", "ti.m1.gap.qnp"), ("q_not_c", "ti.m1.gap.qnc"),
                        ("struct_not_q", "ti.m1.gap.snq")):
        bucket_lb = t(labels, lbkey)
        for item in (gap_buckets.get(bkey) or [])[:4]:
            chips.append(_gap_chip(item, bucket_lb))
    if chips:
        body_parts.append(f'<div class="ti-gaps">{"".join(chips)}</div>')

    body_parts.append(_honest(t(labels, "ti.m1.honest"), lb=t(labels, "ti.honest.lb")))

    return _mod_shell(
        "M1", t(labels, "ti.m1.title"), t(labels, "ti.m1.desc"), t(labels, "ti.m1.plain"),
        "".join(body_parts), collapsible=collapsible, open_=True,
    )


# ─────────────────────────────────────────
# M2 — 허브 역할 불일치 (3축 수평바 + 역할 배지)
# ─────────────────────────────────────────

_HUB_TYPE = {
    "TRIPLE_ANCHOR": ("anchor", "ti.hubType.TRIPLE_ANCHOR"),
    "MIXED": ("half", "ti.hubType.MIXED"),
    "BIASED": ("biased", "ti.hubType.BIASED"),
}
_AXIS_LB = {
    "journey": "ti.axis.journey",
    "connectivity": "ti.axis.connectivity",
    "demand": "ti.axis.demand",
}


def _mini_axis(axis_key: str, rank: Any, labels: Dict[str, str]) -> str:
    tone = {"journey": "how", "connectivity": "who", "demand": "what"}[axis_key]
    if rank is None:
        bar = f'<div class="ti-bar ti-bar--na"><i class="ti-bar__fill ti-bar__fill--na" style="width:0%"></i></div>'
        na = f'<span class="ti-axis__na">{t(labels, "ti.axis.na")}</span>'
    else:
        bar = f'<div class="ti-bar"><i class="ti-bar__fill ti-bar__fill--{tone}" style="width:{_pctw(rank)}%"></i></div>'
        na = ""
    return (
        '<div class="ti-axis">'
        f'<span class="ti-axis__lb">{html.escape(t(labels, _AXIS_LB[axis_key]))}</span>'
        f'{bar}{na}'
        '</div>'
    )


def module_hub(facts: Dict[str, Any], notes: Dict[str, Any], labels: Dict[str, str], *,
               collapsible: bool = True) -> str:
    hubs = facts.get("hubDivergence") or []
    rx_by_id = _notes_by_id(notes.get("hubNotes") or [], field="rx")

    # 앵커(진짜 핵심) 먼저, 그 다음 편차 큰(반쪽) 순 — 상위 8.
    ordered = sorted(
        hubs,
        key=lambda h: (0 if h.get("type") == "TRIPLE_ANCHOR" else 1, -(h.get("dispersion") or 0)),
    )[:8]

    rows: List[str] = []
    for h in ordered:
        kw = html.escape(str(h.get("kw", "")))
        kind, lbkey = _HUB_TYPE.get(h.get("type"), ("muted", "ti.hubType.MIXED"))
        badge = _badge(t(labels, lbkey), kind)
        missing = h.get("missingAxis")
        weak_html = ""
        if missing and h.get("type") != "TRIPLE_ANCHOR" and missing in _AXIS_LB:
            weak_html = (
                '<small class="ti-hubrow__weak">'
                + t(labels, "ti.m2.weak").replace("{axis}", t(labels, _AXIS_LB[missing]))
                + '</small>'
            )
        gauges = (
            _mini_axis("journey", h.get("journey_rank"), labels)
            + _mini_axis("connectivity", h.get("connectivity_rank"), labels)
            + _mini_axis("demand", h.get("demand_rank"), labels)
        )
        disp = t(labels, "ti.m2.disp").replace("{v}", _dec(h.get("dispersion"), 2))
        rx = rx_by_id.get(str(h.get("id")))
        rx_html = (
            f'<div class="ti-hubrow__rx">{escape_with_strong(rx)}</div>' if rx else ""
        )
        rows.append(
            '<div class="ti-hubrow">'
            '<div class="ti-hubrow__head">'
            f'<div class="ti-hubrow__kw">{kw}{weak_html}</div>{badge}'
            '</div>'
            f'<div class="ti-gauges">{gauges}</div>'
            f'<div class="ti-hubrow__val">{html.escape(disp)}</div>'
            f'{rx_html}'
            '</div>'
        )

    body = f'<div class="ti-hub">{"".join(rows)}</div>' + _honest(
        t(labels, "ti.m2.honest"), lb=t(labels, "ti.honest.lb"))

    return _mod_shell(
        "M2", t(labels, "ti.m2.title"), t(labels, "ti.m2.desc"), t(labels, "ti.m2.plain"),
        body, collapsible=collapsible, open_=True,
    )


# ─────────────────────────────────────────
# M3 — 페르소나 × 여정 매트릭스 (접힌 히트맵 + 기울기 스파크라인)
# ─────────────────────────────────────────

def _slope_svg(vals: List[Any], tone: str) -> str:
    xs = (3, 23, 43)
    pts = []
    for x, v in zip(xs, vals):
        try:
            vv = max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            vv = 0.0
        y = 15 - vv * 12
        pts.append(f"{x},{y:.1f}")
    return (
        '<svg width="46" height="18" viewBox="0 0 46 18" class="ti-spark" aria-hidden="true">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="var(--ti-{tone})" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def module_matrix(facts: Dict[str, Any], notes: Dict[str, Any], labels: Dict[str, str], *,
                  collapsible: bool = True) -> str:
    mx = facts.get("matrix") or {}
    personas = mx.get("personas") or []
    stages = mx.get("stages") or []
    cells = mx.get("cells") or []
    slopes = {s.get("persona"): s for s in (mx.get("slope") or [])}
    leaks = {p.get("persona"): p for p in (mx.get("personaLeak") or [])}
    cell_notes = _notes_by_id(notes.get("cellNotes") or [], field="note")

    cell_by = {(c.get("persona"), c.get("stage")): c for c in cells}

    stage_lb = {
        "entry": t(labels, "ti.stage.entry"),
        "mid": t(labels, "ti.stage.mid"),
        "exit": t(labels, "ti.stage.exit"),
    }

    header = (
        f'<div class="ti-mxh ti-mxh--p">{html.escape(t(labels, "ti.m3.colPersona"))}</div>'
        + "".join(f'<div class="ti-mxh">{html.escape(stage_lb.get(s, s))}</div>' for s in stages)
        + f'<div class="ti-mxh">{html.escape(t(labels, "ti.m3.colSlope"))}</div>'
    )

    rows_html: List[str] = []
    for p in personas:
        leak = leaks.get(p) or {}
        leak_badge = ""
        if (leak.get("dropoff") or 0) > 0 and leak.get("leakiestStage"):
            lst = stage_lb.get(leak["leakiestStage"], leak["leakiestStage"])
            leak_badge = _badge(t(labels, "ti.m3.leakiest").replace("{stage}", lst), "warn")
        row = [f'<div class="ti-mxr">{html.escape(str(p))}{leak_badge}</div>']
        for s in stages:
            c = cell_by.get((p, s)) or {}
            if c.get("gap"):
                row.append(
                    '<div class="ti-cell ti-cell--gap" title="'
                    + html.escape(t(labels, "ti.m3.gapTitle"))
                    + f'">{html.escape(t(labels, "ti.m3.gapCell"))}</div>'
                )
                continue
            vol = c.get("volume", 0) or 0
            if vol <= 0:
                row.append('<div class="ti-cell ti-cell--empty">—</div>')
                continue
            avgm = c.get("avgM", 0) or 0
            try:
                mix = max(8.0, min(60.0, float(avgm) * 60.0))
            except (TypeError, ValueError):
                mix = 8.0
            top = (c.get("topKw") or [])
            top_kw = html.escape(str(top[0].get("kw"))) if top else ""
            title_kw = " · ".join(html.escape(str(k.get("kw"))) for k in top[:3])
            top_line = f'<div class="ti-cell__kw">{top_kw}</div>' if top_kw else ""
            row.append(
                f'<div class="ti-cell" title="{title_kw}" '
                f'style="background:color-mix(in srgb,var(--ti-what) {mix:.0f}%,var(--white))">'
                f'<div class="ti-cell__vol">{_fmt(vol)}</div>{top_line}'
                '</div>'
            )
        sl = slopes.get(p) or {}
        slope_v = sl.get("slope", 0) or 0
        tone = "good" if slope_v > 0.02 else ("bad" if slope_v < -0.02 else "warn")
        row.append(
            f'<div class="ti-cell ti-cell--slope">'
            f'{_slope_svg([sl.get("entryM"), sl.get("midM"), sl.get("exitM")], tone)}</div>'
        )
        rows_html.append("".join(row))

    grid = (
        '<div class="ti-mx"><div class="ti-mxgrid" '
        f'style="grid-template-columns:150px repeat({max(len(stages),1)},1fr) 96px">'
        + header + "".join(rows_html) + '</div></div>'
    )

    legend = (
        '<div class="ti-heat-legend">'
        f'<span><i class="ti-heat-sw"></i>{html.escape(t(labels, "ti.m3.legendHeat"))}</span>'
        f'<span><i class="ti-heat-sw ti-heat-sw--gap"></i>{html.escape(t(labels, "ti.m3.legendGap"))}</span>'
        f'<span>{html.escape(t(labels, "ti.m3.legendSlope"))}</span>'
        '</div>'
    )

    # cell notes (LLM) — id 로 머지, 셀 라벨 접두
    note_lines = []
    for c in cells:
        n = cell_notes.get(str(c.get("id")))
        if not n:
            continue
        lb = f'{c.get("persona","")} · {stage_lb.get(c.get("stage"), c.get("stage",""))}'
        note_lines.append(
            f'<div class="ti-cellnote"><span class="ti-cellnote__lb">{html.escape(lb)}</span> {escape_with_strong(n)}</div>'
        )
    notes_html = f'<div class="ti-cellnotes">{"".join(note_lines)}</div>' if note_lines else ""

    body = grid + legend + notes_html
    return _mod_shell(
        "M3", t(labels, "ti.m3.title"), t(labels, "ti.m3.desc"), t(labels, "ti.m3.plain"),
        body, collapsible=collapsible, open_=True,
    )


# ─────────────────────────────────────────
# M4 — 수익 의도 × 여정 누수 (수평바 + 배지 리스트)
# ─────────────────────────────────────────

def _leak_shape_key(out_deg: Any) -> str:
    try:
        o = int(out_deg)
    except (TypeError, ValueError):
        o = 0
    if o == 0:
        return "ti.leak.deadend"
    if o >= 4:
        return "ti.leak.spread"
    return "ti.leak.branch"


def module_leak(facts: Dict[str, Any], labels: Dict[str, str], *,
                collapsible: bool = True) -> str:
    vl = facts.get("valueLeak") or {}
    leaks = vl.get("leaks") or []
    safe = vl.get("safePoints") or []

    def _sub(item: Dict[str, Any]) -> str:
        persona = item.get("persona") or ""
        shape = t(labels, _leak_shape_key(item.get("outDegree")))
        return f'{html.escape(persona)} · {html.escape(shape)}' if persona else html.escape(shape)

    rows: List[str] = []
    seen: set = set()

    # ① 실제로 새는 지점(누수 강도>0) — 상위 4, 강도순
    flowing = [lk for lk in leaks if (lk.get("leak_score") or 0) > 0.01 and lk.get("outDegree") not in (0, None)]
    for lk in sorted(flowing, key=lambda x: -(x.get("leak_score") or 0))[:4]:
        kw = str(lk.get("kw", ""))
        score = lk.get("leak_score") or 0
        if score >= 0.5:
            rows.append(bar_badge(html.escape(kw), score, sub_html=_sub(lk), tone="bad",
                                  badge=(t(labels, "ti.badge.urgent"), "bad")))
        elif score >= 0.12:
            rows.append(bar_badge(html.escape(kw), score, sub_html=_sub(lk), tone="how",
                                  val=t(labels, "ti.badge.mid")))
        else:
            rows.append(bar_badge(html.escape(kw), score, sub_html=_sub(lk), tone="how",
                                  val=t(labels, "ti.badge.low")))
        seen.add(kw)

    # ② 막다른 길(여정이 끊김, outDeg=0) — 값진 순(opp)으로 상위 2. 바 = 걸린 가치(opp).
    deadends = [lk for lk in leaks if lk.get("outDegree") == 0]
    for lk in sorted(deadends, key=lambda x: -(x.get("volume") or 0))[:2]:
        kw = str(lk.get("kw", ""))
        if kw in seen:
            continue
        rows.append(bar_badge(html.escape(kw), lk.get("opp"), sub_html=_sub(lk), tone="warn",
                              badge=(t(labels, "ti.badge.deadend"), "warn")))
        seen.add(kw)

    # ③ 대조군: 적게 새는 전환점 — 값진 순(opp)으로 상위 3.
    for sp in sorted(safe, key=lambda x: -(x.get("opp") or 0))[:3]:
        kw = str(sp.get("kw", ""))
        if kw in seen:
            continue
        persona = sp.get("persona") or ""
        sub = html.escape(persona) if persona else ""
        rows.append(bar_badge(html.escape(kw), sp.get("opp"), sub_html=sub, tone="good",
                              badge=(t(labels, "ti.badge.safe"), "good")))
        seen.add(kw)

    body = f'<div class="ti-rows">{"".join(rows)}</div>' + _honest(
        t(labels, "ti.m4.honest"), lb=t(labels, "ti.honest.lb"))
    return _mod_shell(
        "M4", t(labels, "ti.m4.title"), t(labels, "ti.m4.desc"), t(labels, "ti.m4.plain"),
        body, collapsible=collapsible, open_=True,
    )


# ─────────────────────────────────────────
# M5 — 전환 회랑 (방향성 표 + 인라인)
# ─────────────────────────────────────────

_VERDICT = {
    "corridor": ("good", "ti.verdict.corridor"),
    "substitute_leak": ("bad", "ti.verdict.substitute_leak"),
    "false_adjacency": ("biased", "ti.verdict.false_adjacency"),
    "inconclusive": ("muted", "ti.verdict.inconclusive"),
}


def module_corridor(facts: Dict[str, Any], notes: Dict[str, Any], labels: Dict[str, str], *,
                    collapsible: bool = True) -> str:
    bridges = facts.get("bridges") or []
    bnotes = _notes_by_id(notes.get("bridgeNotes") or [], field="note")

    head = (
        '<thead><tr>'
        f'<th>{html.escape(t(labels, "ti.m5.colLink"))}</th>'
        f'<th>{html.escape(t(labels, "ti.m5.colSeq"))}</th>'
        f'<th>{html.escape(t(labels, "ti.m5.colDir"))}</th>'
        f'<th>{html.escape(t(labels, "ti.m5.colIntent"))}</th>'
        f'<th>{html.escape(t(labels, "ti.m5.colVerdict"))}</th>'
        '</tr></thead>'
    )
    body_rows: List[str] = []
    for b in bridges:
        frm = html.escape(str(b.get("fromHub", b.get("from", ""))))
        to = html.escape(str(b.get("toHub", b.get("to", ""))))
        fwd = b.get("fwd", 0) or 0
        rev = b.get("rev", 0) or 0
        if fwd > rev:
            dir_cls, dir_txt = "fwd", t(labels, "ti.m5.dirFwd")
        elif rev > fwd:
            dir_cls, dir_txt = "rev", t(labels, "ti.m5.dirRev")
        else:
            dir_cls, dir_txt = "none", t(labels, "ti.m5.dirNone")
        idelta = b.get("intent_delta")
        idelta_txt = _signed(idelta, 2) if idelta is not None else "—"
        kind, vkey = _VERDICT.get(b.get("verdict"), ("muted", "ti.verdict.inconclusive"))
        body_rows.append(
            '<tr>'
            f'<td><span class="ti-linkkw">{frm} → {to}</span></td>'
            f'<td class="ti-num">{int(fwd)} / {int(rev)}</td>'
            f'<td class="ti-dir ti-dir--{dir_cls}">{html.escape(dir_txt)}</td>'
            f'<td class="ti-num">{html.escape(idelta_txt)}</td>'
            f'<td>{_badge(t(labels, vkey), kind)}</td>'
            '</tr>'
        )
    table = f'<div class="ti-tw"><table class="ti-table">{head}<tbody>{"".join(body_rows)}</tbody></table></div>'

    note_lines = []
    for b in bridges:
        n = bnotes.get(str(b.get("id")))
        if not n:
            continue
        lb = f'{b.get("fromHub","")} → {b.get("toHub","")}'
        note_lines.append(
            f'<div class="ti-cellnote"><span class="ti-cellnote__lb">{html.escape(lb)}</span> {escape_with_strong(n)}</div>'
        )
    notes_html = f'<div class="ti-cellnotes">{"".join(note_lines)}</div>' if note_lines else ""

    body = table + notes_html + _honest(t(labels, "ti.m5.honest"), lb=t(labels, "ti.honest.lb"))
    return _mod_shell(
        "M5", t(labels, "ti.m5.title"), t(labels, "ti.m5.desc"), t(labels, "ti.m5.plain"),
        body, collapsible=collapsible, open_=True,
    )


# ─────────────────────────────────────────
# M6 — 우선순위 백로그 (Now/Next/Later 칸반 + 점수바 + 기여스택 + KPI)
# ─────────────────────────────────────────

_STACK_SEG = (
    ("volume", "vol"),
    ("intent", "int"),
    ("momentum", "mom"),
    ("structure", "str"),
    ("leak", "leak"),
)
_SRCMOD_LB = {
    "hub-divergence": "ti.srcmod.hub",
    "value-leak": "ti.srcmod.leak",
    "coverage-gap": "ti.srcmod.coverage",
    "corridor-bridge": "ti.srcmod.corridor",
    "momentum": "ti.srcmod.momentum",
    "brand-defense": "ti.srcmod.brand",
    "pijourney-matrix": "ti.srcmod.matrix",
}


def _task_card(item: Dict[str, Any], note: Optional[Dict[str, Any]], labels: Dict[str, str]) -> str:
    title = (note or {}).get("title") or item.get("target") or ""
    body = (note or {}).get("body")
    score = item.get("score") or 0
    breakdown = item.get("breakdown") or {}
    total = sum(max(0.0, float(breakdown.get(k, 0) or 0)) for k, _ in _STACK_SEG) or 1.0
    segs = "".join(
        f'<i class="ti-stack__seg ti-stack__seg--{cls}" style="width:{(max(0.0, float(breakdown.get(k,0) or 0)) / total) * 100:.1f}%"></i>'
        for k, cls in _STACK_SEG
    )
    chips = "".join(
        f'<span class="ti-kc">{html.escape(str(kw))}</span>' for kw in (item.get("evidenceKw") or [])
    )
    srcs = " · ".join(
        t(labels, _SRCMOD_LB[m]) for m in (item.get("sourceModules") or []) if m in _SRCMOD_LB
    )
    body_html = f'<div class="ti-task__body">{escape_with_strong(body)}</div>' if body else ""
    src_html = f'<div class="ti-task__src">← {html.escape(srcs)}</div>' if srcs else ""
    return (
        '<div class="ti-task">'
        f'<div class="ti-task__tt">{escape_with_strong(title)}</div>'
        f'{body_html}'
        '<div class="ti-task__sc">'
        f'<span class="ti-task__num">{score * 10:.1f}</span>'
        f'<div class="ti-stack">{segs}</div>'
        '</div>'
        f'<div class="ti-task__chips">{chips}</div>'
        f'{src_html}'
        '</div>'
    )


def module_backlog(facts: Dict[str, Any], notes: Dict[str, Any], labels: Dict[str, str], *,
                   collapsible: bool = True) -> str:
    bl = facts.get("backlog") or {}
    items = bl.get("items") or []
    kpi = bl.get("kpi") or {}
    bnotes = {str(n.get("id")): n for n in (notes.get("backlogNotes") or []) if n.get("id")}

    # KPI tiles
    kpi_tiles = (
        '<div class="ti-kpis">'
        f'<div class="ti-kpi"><div class="ti-kpi__n ti-kpi__n--bad">{_fmt(kpi.get("recoverableLeakVolume"))}</div>'
        f'<div class="ti-kpi__l">{html.escape(t(labels, "ti.m6.kpiLeak"))}</div></div>'
        f'<div class="ti-kpi"><div class="ti-kpi__n ti-kpi__n--hub">{_fmt(kpi.get("orphanCount"))}</div>'
        f'<div class="ti-kpi__l">{html.escape(t(labels, "ti.m6.kpiOrphan"))}</div></div>'
        f'<div class="ti-kpi"><div class="ti-kpi__n ti-kpi__n--good">{_dec(kpi.get("coveragePct"), 1)}%</div>'
        f'<div class="ti-kpi__l">{html.escape(t(labels, "ti.m6.kpiCoverage"))}</div></div>'
        '</div>'
    )

    cols_def = (("now", "ti.m6.now"), ("next", "ti.m6.next"), ("later", "ti.m6.later"))
    cols_html: List[str] = []
    for bucket, lbkey in cols_def:
        tasks = [it for it in items if it.get("bucket") == bucket]
        tasks.sort(key=lambda x: x.get("rank", 99))
        cards = "".join(_task_card(it, bnotes.get(str(it.get("id"))), labels) for it in tasks)
        cols_html.append(
            f'<div class="ti-col ti-col--{bucket}">'
            f'<span class="ti-col__ch">{html.escape(t(labels, lbkey))}</span>'
            f'{cards}'
            '</div>'
        )
    kanban = f'<div class="ti-kan">{"".join(cols_html)}</div>'

    stack_legend = (
        '<div class="ti-stack-legend">'
        + "".join(
            f'<span><i class="ti-stack__seg--{cls}"></i>{html.escape(t(labels, f"ti.stack.{cls}"))}</span>'
            for _, cls in _STACK_SEG
        )
        + '</div>'
    )
    leak_legend = (
        '<div class="ti-leak-legend">'
        f'<strong>{html.escape(t(labels, "ti.m6.leakLegendTitle"))}</strong> '
        f'{t(labels, "ti.m6.leakLegendBody")}'
        '</div>'
    )

    body = kpi_tiles + kanban + stack_legend + leak_legend
    return _mod_shell(
        "M6", t(labels, "ti.m6.title"), t(labels, "ti.m6.desc"), t(labels, "ti.m6.plain"),
        body, collapsible=collapsible, open_=True,
    )


# ─────────────────────────────────────────
# module registry — dashboard (collapsible) + A4 (flat)
# ─────────────────────────────────────────

def total_modules(facts: Dict[str, Any], notes: Dict[str, Any], labels: Dict[str, str], *,
                  collapsible: bool = True) -> Dict[str, str]:
    return {
        "m1": module_coverage(facts, labels, collapsible=collapsible),
        "m2": module_hub(facts, notes, labels, collapsible=collapsible),
        "m3": module_matrix(facts, notes, labels, collapsible=collapsible),
        "m4": module_leak(facts, labels, collapsible=collapsible),
        "m5": module_corridor(facts, notes, labels, collapsible=collapsible),
        "m6": module_backlog(facts, notes, labels, collapsible=collapsible),
    }


# ─────────────────────────────────────────
# 통합 A4 (unified print — first pages, flat always-open modules)
# ─────────────────────────────────────────

def total_a4_pages_html(counts: Dict[str, Any], facts: Dict[str, Any], notes: Dict[str, Any],
                        category: str, market_label: Optional[str], labels: Dict[str, str],
                        overview: Optional[str] = None) -> str:
    a4_meta = (
        t(labels, "totalInsight.a4.coverMeta")
        .replace("{clusterCount}", str(counts.get("clusterCount", "")))
        .replace("{personaCount}", str(counts.get("personaCount", "")))
        .replace("{pathCount}", str(counts.get("pathCount", "")))
    )
    cover = (
        '<div class="rpt-page rpt-page--cover" id="page-total-cover">'
        '<div class="cover-body">'
        '<div>'
        '<div class="cover-lm">ListeningMind.AI</div>'
        f'<div class="cover-title">{t(labels, "totalInsight.reportTitle")}</div>'
        f'<div class="cover-category">{html.escape(category)}</div>'
        '<div class="cover-meta">'
        f'<span>{html.escape(str(counts.get("date", "")))}</span>'
        '<span class="cover-meta-sep">|</span>'
        f'<span>{html.escape(a4_meta)}</span>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
    )

    overview_html = _overview_html(overview, labels)
    recap_html = _recap_html(facts.get("recap") or {}, labels)
    mods = total_modules(facts, notes, labels, collapsible=False)
    body = (
        '<div class="rpt-page ti-scope" id="page-total-body">'
        '<div class="page-body">'
        f'<div class="persona-subhead">{t(labels, "totalInsight.cover.summaryTitle")}</div>'
        f'{overview_html}{recap_html}'
        + "".join(mods[k] for k in ("m1", "m2", "m3", "m4", "m5", "m6"))
        + '</div>'
        '</div>'
    )
    return cover + body
