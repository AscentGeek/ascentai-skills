"""HTML builders that mirror ListeningMind.AI's React components.

Each function corresponds to a JSX component in
`frontend/features/agents/components/customer-analysis/RunPage.tsx`
and produces an identical class-name structure so the ListeningMind.AI stylesheets
render the same visual output.

All user-supplied text (persona fields, action bodies, category, ...) goes
through `escape_with_strong` which HTML-escapes everything and then re-allows
the `<strong>...</strong>` tag pairs that ListeningMind.AI emits via the LLM prompt.
"""

import html
import re
from typing import Any, Dict, List, Optional


# Stage enum → label key
#   informational/…  : query_aggregate 가 데이터(i/n/c/t)로 계산한 의도 배지
#   한국어 값        : DaaS 백엔드가 한국어 enum 으로 저장하던 값 (호환 유지)
STAGE_LABEL_KEY = {
    "informational": "customerAnalysis.stage.informational",
    "navigational": "customerAnalysis.stage.navigational",
    "commercial": "customerAnalysis.stage.commercial",
    "transactional": "customerAnalysis.stage.transactional",
    "정보 탐색": "customerAnalysis.stage.explore",
    "비교 검토": "customerAnalysis.stage.compare",
    "구매 직전": "customerAnalysis.stage.purchase",
    # brandGroups 의 stage · query_aggregate 가 kind 로 채운다 (한국어 enum).
    # 라벨을 거치지 않으면 jp/us 리포트에 한국어가 그대로 노출된다 (실측).
    "브랜드": "customerAnalysis.stage.brand",
    "논브랜드": "customerAnalysis.stage.nonbrand",
}

# cluster_aggregate 가 코드로 채우는 kbf.factor → label key
KBF_FACTOR_LABEL_KEY = {
    "허브(대표) 키워드": "clusterLandscape.hubTable.colHub",
}


_STRONG_RE = re.compile(r"&lt;strong&gt;(.*?)&lt;/strong&gt;", flags=re.DOTALL)


def escape_with_strong(text: Optional[str]) -> str:
    """Escape HTML but allow <strong>...</strong>.

    Mirrors `parseSimpleHtml.tsx`: the LLM emits literal <strong> tags in
    text fields to emphasize key noun phrases. Everything else must be
    escaped to avoid injection.
    """
    if text is None:
        return ""
    escaped = html.escape(str(text))
    # Restore <strong> pairs that survived escaping as &lt;strong&gt;
    return _STRONG_RE.sub(r"<strong>\1</strong>", escaped)


# 검색어 번역 · 시장 언어와 리포트 언어가 다를 때 렌더가 채워 넣는다.
# 칩에 원문과 번역을 함께 심고, 툴바 버튼이 body 클래스로 무엇을 보일지 정한다
# (JS 로 글자를 바꾸지 않으므로 인쇄·A4 에서도 상태가 그대로 유지된다).
TRANSLATIONS: Dict[str, str] = {}


def set_translations(mapping: Optional[Dict[str, str]]) -> None:
    global TRANSLATIONS
    TRANSLATIONS = {str(k): str(v) for k, v in (mapping or {}).items() if v}


def kw_html(kw: str) -> str:
    """키워드 한 개의 표시 HTML. 번역이 있으면 원문·번역을 둘 다 심는다."""
    orig = html.escape(str(kw))
    tr = TRANSLATIONS.get(str(kw))
    if not tr:
        return orig
    return (f'<span class="kw-o">{orig}</span>'
            f'<span class="kw-t">{html.escape(tr)}</span>')


def t(labels: Dict[str, str], key: str) -> str:
    """i18n lookup; falls back to the key itself if missing."""
    return labels.get(key, key)


def format_count(labels: Dict[str, str], n: int) -> str:
    """Mirror `common.formatItemCount`. We don't have that key in the
    extracted label file, so use a locale-agnostic short form."""
    return f"{n}개" if labels.get("country.KR") == "한국" else (
        f"{n}件" if labels.get("country.JP") == "日本" else f"{n}"
    )


def _stage_label(stage: str, labels: Dict[str, str]) -> str:
    key = STAGE_LABEL_KEY.get(stage)
    return t(labels, key) if key else stage


# ─────────────────────────────────────────
# PersonaCard — RunPage.tsx:283
# ─────────────────────────────────────────

def persona_card_html(persona: Dict[str, Any], index: int, labels: Dict[str, str]) -> str:
    num = f"{index + 1:02d}"
    name = html.escape(str(persona.get("name", "")))
    stage = persona.get("stage")
    chips = []
    if stage:
        chips.append(
            f'<span>{t(labels, "customerAnalysis.dash.personaMetaStage")} '
            f'<b>{html.escape(_stage_label(stage, labels))}</b>'
            # 비중은 코드가 센 사실값 · 쏠린 시장에서 배지끼리 구분이 된다
            + (f' <b>{html.escape(str(persona.get("stageShare")))}</b>'
               if persona.get("stageShare") else "")
            + '</span>'
        )
    # 브랜드/논브랜드는 의도가 아니라 검색어의 종류다 — 제 라벨을 달고 따로 선다.
    kind = persona.get("kind")
    if kind in ("brand", "nonbrand"):
        chips.append(
            f'<span>{t(labels, "customerAnalysis.dash.personaMetaKind")} '
            f'<b>{t(labels, "customerAnalysis.stage." + kind)}</b></span>'
        )
    stage_html = f'<div class="persona-card__meta">{"".join(chips)}</div>' if chips else ""

    # 그룹 검색량 뱃지 — Python 이 합산한 사실값(volumeLabel)·키워드 수.
    # 필드가 없는 구버전 lm_groups.json 은 뱃지 없이 그대로 렌더된다.
    vol_badge_html = ""
    volume_label = persona.get("volumeLabel")
    if volume_label:
        parts = [
            t(labels, "customerAnalysis.dash.personaVolumeBadge")
            .replace("{vol}", str(volume_label))
        ]
        member_count = persona.get("memberCount")
        if member_count:
            parts.append(
                t(labels, "customerAnalysis.dash.personaKeywordCount")
                .replace("{count}", str(member_count))
            )
        # 클러스터 수 뱃지 — cluster-landscape 전용(agent_cluster §2 헤더 '클러스터 수: N개').
        # clusterCount 필드가 없는 다른 스킬(query 등)에서는 이 블록이 건너뛰어져 동작 동일.
        cluster_count = persona.get("clusterCount")
        if cluster_count:
            parts.append(
                t(labels, "customerAnalysis.dash.personaClusterCount")
                .replace("{count}", str(cluster_count))
            )
        # 마우스오버 툴팁 — 그룹의 전체 member 키워드+검색량 (members 있을 때만).
        # 본문은 10행 높이로 고정, 초과분은 스크롤. 우상단 X 로 닫기(JS).
        members = persona.get("members") or []
        tip_html = ""
        if members:
            rows = "".join(
                f'<span class="volbadge-tip__row">'
                f'<span class="volbadge-tip__kw">{kw_html(m.get("kw", ""))}</span>'
                f'<span class="volbadge-tip__vol">{html.escape(str(m.get("volLabel", "")))}</span>'
                f'</span>'
                for m in members
            )
            tip_html = (
                f'<span class="volbadge-tip" role="tooltip">'
                f'<span class="volbadge-tip__head">'
                f'<span class="volbadge-tip__title">{t(labels, "customerAnalysis.dash.volTooltipTitle")}</span>'
                f'<button type="button" class="volbadge-tip__close" aria-label="{t(labels, "customerAnalysis.dash.volTooltipClose")}">&times;</button>'
                f'</span>'
                f'<span class="volbadge-tip__body">{rows}</span>'
                f'</span>'
            )
        # 힌트: 마우스오버 시 "클릭시 키워드 목록 확인" (native title). 목록은 클릭으로 연다.
        hint = html.escape(t(labels, "customerAnalysis.dash.volTooltipHint"), quote=True)
        vol_badge_html = (
            f'<span class="persona-subhead__badge persona-card__volbadge" '
            f'tabindex="0" role="button" title="{hint}">'
            f'{html.escape(" · ".join(parts))}{tip_html}</span>'
        )

    # ── ① WHO block
    who_text = persona.get("who")
    who_text_html = (
        f'<div class="persona-who__text">{escape_with_strong(who_text)}</div>'
        if who_text else ""
    )

    fields_parts = []
    for key, label_key in (
        ("situation", "customerAnalysis.dash.personaSituation"),
        ("needs", "customerAnalysis.dash.personaNeeds"),
        ("painpoint", "customerAnalysis.dash.personaPainpoint"),
    ):
        val = persona.get(key)
        if not val:
            continue
        fields_parts.append(
            f'<div class="persona-field">'
            f'<div class="persona-field__label">{t(labels, label_key)}</div>'
            f'<div class="persona-field__val">{escape_with_strong(val)}</div>'
            f'</div>'
        )
    fields_html = (
        f'<div class="persona-fields">{"".join(fields_parts)}</div>'
        if fields_parts else ""
    )

    # ── ② KBF block
    kbf_rows = []
    for kbf in (persona.get("kbf") or []):
        # factor 는 보통 LLM 이 분석 언어로 쓴 자유 문구지만,
        # cluster_aggregate 가 허브 행만 한국어 상수로 채운다. 라벨 키로 등록된 값이면
        # 그 언어의 라벨로 바꿔 준다 (안 하면 jp/us 리포트에 한국어가 노출된다 · 실측).
        raw_factor = str(kbf.get("factor", ""))
        factor = html.escape(t(labels, KBF_FACTOR_LABEL_KEY[raw_factor])
                             if raw_factor in KBF_FACTOR_LABEL_KEY else raw_factor)
        ev_kws = kbf.get("evidence_keywords") or []
        kws_html = ""
        if ev_kws:
            chips = "".join(
                f'<span class="persona-kbf__kw">{kw_html(kw)}</span>'
                for kw in ev_kws
            )
            kws_html = f'<div class="persona-kbf__kws">{chips}</div>'
        kbf_rows.append(
            f'<div class="persona-kbf__row">'
            f'<div class="persona-kbf__factor">{factor}</div>'
            f'{kws_html}'
            f'</div>'
        )
    kbf_block_html = "".join(kbf_rows)

    # ── ③ Insight + evidence block
    insight = persona.get("insight")
    insight_html = ""
    if insight:
        insight_html = (
            f'<div class="persona-insight">'
            f'<div class="persona-insight__label">{t(labels, "customerAnalysis.dash.personaInsightLabel")}</div>'
            f'<div class="persona-insight__text">{escape_with_strong(insight)}</div>'
            f'</div>'
        )

    evidence = persona.get("evidence") or []
    evidence_block = ""
    if evidence:
        chips = "".join(
            (
                f'<span class="persona-ev__item">'
                f'{kw_html(e.get("kw", ""))}'
                + (f'<span class="persona-ev__vol">{html.escape(str(e["volLabel"]))}</span>'
                   if e.get("volLabel") else "")
                + f'</span>'
            )
            for e in evidence
        )
        # evidence 캡(EVIDENCE_TOP_N) 밖 키워드 안내 — #1958 의 '외 N건' 표기
        member_count = persona.get("memberCount")
        if member_count and member_count > len(evidence):
            chips += (
                f'<span class="persona-ev__item persona-ev__more">'
                + html.escape(
                    t(labels, "customerAnalysis.dash.personaEvidenceMore")
                    .replace("{n}", str(member_count - len(evidence)))
                )
                + '</span>'
            )
        evidence_block = (
            f'<div class="persona-subhead">'
            f'{t(labels, "customerAnalysis.dash.personaEvidenceTitle")}'
            f'<span class="persona-ev-note">{t(labels, "customerAnalysis.dash.personaEvidenceNote")}</span>'
            f'</div>'
            f'<div class="persona-ev">{chips}</div>'
        )

    return (
        '<div class="dash-card persona-card">'
        '<div class="persona-card__head">'
        '<div class="persona-card__top">'
        f'<span class="persona-card__num">{num}</span>'
        '<div class="persona-card__topmain">'
        '<div class="persona-card__titlerow">'
        f'<span class="persona-card__name">{name}</span>'
        f'{vol_badge_html}'
        '</div>'
        f'{stage_html}'
        '</div>'
        '</div>'
        '</div>'

        # ① WHO
        '<div class="persona-card__body">'
        '<div class="persona-subhead">'
        f'{t(labels, "customerAnalysis.dash.personaWhoLabel")}'
        f'<span class="persona-subhead__badge">{t(labels, "customerAnalysis.dash.personaWhoBadge")}</span>'
        '</div>'
        '<div class="persona-who">'
        f'{who_text_html}'
        f'{fields_html}'
        '</div>'
        '</div>'

        # ② KBF — 내용이 없으면 통째로 생략한다.
        #    브랜드/논브랜드 그룹은 kbf 가 아예 없어 제목만 남던 자리다 (카드마다 빈 제목).
        + (
            '<div class="persona-card__body">'
            f'<div class="persona-subhead">{t(labels, "customerAnalysis.dash.personaKbfTitle")}</div>'
            f'<div class="persona-kbf">{kbf_block_html}</div>'
            '</div>'
            if kbf_block_html.strip() else ""
        )

        # ③ Insight + Evidence
        + '<div class="persona-card__body">'
        + f'<div class="persona-subhead">{t(labels, "customerAnalysis.dash.personaInsightTitle")}</div>'
        + f'{insight_html}'
        + f'{evidence_block}'
        + '</div>'
        + '</div>'
    )


# ─────────────────────────────────────────
# ActCard — RunPage.tsx:259
# ─────────────────────────────────────────

def action_card_html(item: Dict[str, Any], kind: str) -> str:
    title = escape_with_strong(item.get("title"))
    body = escape_with_strong(item.get("body"))
    return (
        f'<div class="rpt-act-card rpt-act-card--{kind}">'
        f'<div class="rpt-act-card__title">'
        f'<span class="action-dot action-dot--{kind}"></span>'
        f'{title}'
        f'</div>'
        f'<div class="rpt-act-card__body">{body}</div>'
        f'</div>'
    )


def action_list_html(items: List[Dict[str, Any]], kind: str, labels: Dict[str, str]) -> str:
    if not items:
        return f'<div class="rpt-act-empty">{t(labels, "customerAnalysis.dash.actionsEmpty")}</div>'
    return "".join(action_card_html(item, kind) for item in items)


# ─────────────────────────────────────────
# ReportPurposeBox — _shared/report/ReportPurposeBox.tsx
# ─────────────────────────────────────────

def purpose_box_html(
    category: str,
    market_label: Optional[str],
    labels: Dict[str, str],
    variant: str,  # "dash" | "a4"
    overview: Optional[str] = None,
) -> str:
    # 문구를 먼저 이스케이프한 뒤 자리표시자를 채운다. 검색어는 번역 토글용
    # 이중 span 이라 이미 안전한 HTML 이고, 뒤늦게 넣어야 두 번 이스케이프되지 않는다.
    key = "customerAnalysis.purpose.body" if market_label else "customerAnalysis.purpose.bodyNoMarket"
    body_html = escape_with_strong(t(labels, key)).replace("{category}", kw_html(category))
    if market_label:
        body_html = body_html.replace("{market}", html.escape(market_label))
    box_class = "mr-summary-box mr-summary-box--dash" if variant == "dash" else "mr-summary-box"
    text_class = "mr-summary-text" if variant == "dash" else "mr-summary-text--sm"
    # LLM 분석 개요(#1958 ①)를 커버 요약문으로 — 고정 목적 문구 아래 데이터
    # 기반 통찰 문단을 잇는다. overview 미존재(구버전 산출물) 시 생략.
    overview_html = (
        f'<p class="{text_class} mr-overview">{escape_with_strong(overview)}</p>'
        if overview else ""
    )
    return (
        f'<div class="{box_class}">'
        f'<div class="mr-summary-box__title">{t(labels, "report.purpose.title")}</div>'
        f'<p class="{text_class}">{body_html}</p>'
        f'{overview_html}'
        f'</div>'
    )


# ─────────────────────────────────────────
# Dashboard Cover — RunPage.tsx:95
# ─────────────────────────────────────────

def dash_cover_html(
    meta: Dict[str, Any],
    category: str,
    gl_label: str,
    market_label: Optional[str],
    labels: Dict[str, str],
    overview: Optional[str] = None,
) -> str:
    eyebrow_base = t(labels, "customerAnalysis.dash.coverEyebrow")
    eyebrow = f"{eyebrow_base} · {html.escape(gl_label)}" if gl_label else eyebrow_base
    # 브랜드/논브랜드(alt) 그룹이 있으면 검색목적(core)과 구분해 센다 —
    # 커버의 '검색목적 N'이 브랜드 그룹까지 합친 수가 되지 않도록.
    meta_key = (
        "customerAnalysis.dash.coverMetaWithAlt"
        if meta.get("altCount") else "customerAnalysis.dash.coverMeta"
    )
    cover_meta = (
        t(labels, meta_key)
        .replace("{date}", str(meta.get("date", "")))
        .replace("{clusterCount}", str(meta.get("clusterCount", "")))
        .replace("{keywordCount}", str(meta.get("keywordCount", "")))
        .replace("{personaCount}", str(meta.get("personaCount", "")))
        .replace("{altCount}", str(meta.get("altCount", "")))
    )
    return (
        '<div class="dash-cover-block">'
        '<div class="dash-card">'
        '<div class="dash-cover-gradient">'
        f'<div class="dash-cover-eyebrow">{html.escape(eyebrow)}</div>'
        f'<div class="dash-cover-title">{t(labels, "agent.customerAnalysis.name")}</div>'
        f'<div class="dash-cover-category">{kw_html(category)}</div>'
        f'<div class="dash-cover-meta">{html.escape(cover_meta)}</div>'
        '</div>'
        + purpose_box_html(category, market_label, labels, "dash", overview=overview)
        + '</div>'
        '</div>'
    )


# ─────────────────────────────────────────
# Dashboard Tabs + Panels — RunPage.tsx:122~250
# ─────────────────────────────────────────

def dash_tabs_html(labels: Dict[str, str]) -> str:
    return (
        '<nav class="dash-tabs" aria-label="tabs">'
        '<div class="dash-tabs__inner" role="tablist">'
        '<button type="button" class="dash-tab active" role="tab" id="dash-tab-0" aria-selected="true" data-panel="0">'
        f'{t(labels, "customerAnalysis.dash.personaTab")}'
        '</button>'
        '<button type="button" class="dash-tab" role="tab" id="dash-tab-1" aria-selected="false" data-panel="1">'
        f'{t(labels, "customerAnalysis.dash.actionTab")}'
        '</button>'
        '</div>'
        '</nav>'
    )


def dash_panel_personas_html(
    core: List[Dict[str, Any]],
    alt: List[Dict[str, Any]],
    category: str,
    labels: Dict[str, str],
) -> str:
    sections: List[str] = []
    if core:
        cards = "".join(persona_card_html(p, i, labels) for i, p in enumerate(core))
        sections.append(
            '<div class="dash-card">'
            '<div class="dash-card__head">'
            f'<span class="dash-card__title">'
            + t(labels, "customerAnalysis.dash.coreSectionTitle").replace("{category}", kw_html(category))
            + '</span>'
            f'<span class="dash-card__badge">{format_count(labels, len(core))}</span>'
            '</div>'
            f'<div class="dash-card__body">{cards}</div>'
            '</div>'
        )
    if alt:
        cards = "".join(persona_card_html(p, i, labels) for i, p in enumerate(alt))
        desc = t(labels, "customerAnalysis.dash.altSectionDesc").replace("{category}", kw_html(category))
        sections.append(
            '<div class="dash-card">'
            '<div class="dash-card__head">'
            f'<span class="dash-card__title">{t(labels, "customerAnalysis.dash.altSectionTitle")}</span>'
            f'<span class="dash-card__badge">{format_count(labels, len(alt))}</span>'
            '</div>'
            f'<p class="persona-section-desc">{desc}</p>'
            f'<div class="dash-card__body">{cards}</div>'
            '</div>'
        )
    return (
        '<div class="dash-tab-panel active" role="tabpanel" aria-labelledby="dash-tab-0" data-panel="0">'
        + "".join(sections)
        + '</div>'
    )


def dash_panel_actions_html(actions: Dict[str, Any], labels: Dict[str, str]) -> str:
    parts: List[str] = []
    synthesis = actions.get("synthesis")
    if synthesis:
        parts.append(
            '<div class="dash-card">'
            '<div class="dash-card__head">'
            f'<span class="dash-card__title">{t(labels, "customerAnalysis.dash.actionsSynthesisTitle")}</span>'
            '</div>'
            '<div class="dash-card__body">'
            f'<p class="mr-summary-text">{escape_with_strong(synthesis)}</p>'
            '</div>'
            '</div>'
        )

    # #1958 ④ 세부 인사이트 — 총평(synthesis) 다음, 실행 제안 앞
    insights = actions.get("insights") or []
    if insights:
        parts.append(
            '<div class="dash-card">'
            '<div class="dash-card__head">'
            f'<span class="dash-card__title">{t(labels, "customerAnalysis.dash.actionsInsightsTitle")}</span>'
            f'<span class="dash-card__badge">{format_count(labels, len(insights))}</span>'
            '</div>'
            '<div class="dash-card__body">'
            f'<div class="rpt-act-list">{action_list_html(insights, "insight", labels)}</div>'
            '</div>'
            '</div>'
        )

    now = actions.get("now") or []
    parts.append(
        '<div class="dash-card">'
        '<div class="dash-card__head">'
        f'<span class="dash-card__title">{t(labels, "customerAnalysis.dash.actionsNowTitle")}</span>'
        f'<span class="dash-card__badge">{format_count(labels, len(now))}</span>'
        '</div>'
        '<div class="dash-card__body">'
        f'<div class="rpt-act-list">{action_list_html(now, "now", labels)}</div>'
        '</div>'
        '</div>'
    )

    future = actions.get("future") or []
    parts.append(
        '<div class="dash-card">'
        '<div class="dash-card__head">'
        f'<span class="dash-card__title">{t(labels, "customerAnalysis.dash.actionsFutureTitle")}</span>'
        f'<span class="dash-card__badge">{format_count(labels, len(future))}</span>'
        '</div>'
        '<div class="dash-card__body">'
        f'<div class="rpt-act-list">{action_list_html(future, "future", labels)}</div>'
        '</div>'
        '</div>'
    )

    return (
        '<div class="dash-tab-panel" role="tabpanel" aria-labelledby="dash-tab-1" data-panel="1">'
        + "".join(parts)
        + '</div>'
    )


# ─────────────────────────────────────────
# A4 Cover & Body — RunPage.tsx:414
# ─────────────────────────────────────────

def a4_cover_page_html(meta: Dict[str, Any], category: str, labels: Dict[str, str]) -> str:
    a4_meta = (
        t(labels, "customerAnalysis.a4.coverMeta")
        .replace("{keywordCount}", str(meta.get("keywordCount", "")))
        .replace("{personaCount}", str(meta.get("personaCount", "")))
        .replace("{altCount}", str(meta.get("altCount", "")))
    )
    return (
        '<div class="rpt-page rpt-page--cover" id="page-0">'
        '<div class="cover-body">'
        '<div>'
        '<div class="cover-lm">ListeningMind.AI</div>'
        f'<div class="cover-title">{t(labels, "agent.customerAnalysis.name")}</div>'
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


def a4_body_page_html(
    personas: List[Dict[str, Any]],
    actions: Dict[str, Any],
    category: str,
    market_label: Optional[str],
    labels: Dict[str, str],
    overview: Optional[str] = None,
) -> str:
    """All A4 body content lives on a single .rpt-page that grows to fit.
    Each persona card and the actions blocks carry `break-inside: avoid` so
    the browser keeps them whole when paginating for print.

    `actions` may be a bare synthesis string (legacy call shape) or the full
    lm_actions dict — 인쇄본에도 인사이트·now/future 실행 카드가 포함된다.
    """
    if isinstance(actions, str) or actions is None:
        actions = {"synthesis": actions}
    cards = "".join(persona_card_html(p, i, labels) for i, p in enumerate(personas))
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
            f'<div class="rpt-act-list">{action_list_html(items, kind, labels)}</div>'
        )
    return (
        '<div class="rpt-page" id="page-1">'
        '<div class="page-body">'
        + purpose_box_html(category, market_label, labels, "a4", overview=overview)
        + cards
        + "".join(parts)
        + '</div>'
        '</div>'
    )
