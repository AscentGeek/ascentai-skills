#!/usr/bin/env python3
"""demand-shift v4 렌더러 · facts.json + narrative.json → 자기완결형 HTML (대시보드 ↔ A4).

섹션은 두 개로 고정된다: 1 시장 흐름 비교(external) · 2 타겟 키워드 의도 변화(internal). 섹션·제목·표·차트·색은 여기서만 정한다.
LLM 문장은 <b>/<strong> 만 허용하고 나머지는 이스케이프한다.

사용: python3 ds_render.py --facts facts.json --narrative narrative.json --out search-demand-report.html
"""

import argparse
import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ds_common as C  # noqa: E402
import ds_charts as CH  # noqa: E402
from inline_styles import inline_styles  # noqa: E402
from style_order import SKILL_STYLES  # noqa: E402

PKG = HERE.parent
FONT_HREF = {
    "kr": "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700;900&display=swap",
    "jp": "https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;900&display=swap",
    "us": "https://fonts.googleapis.com/css2?family=Noto+Sans:wght@400;500;600;700;900&display=swap",
}
HTML_LANG = {"kr": "ko", "jp": "ja", "us": "en"}
# 리포트를 쓸 수 있는 언어 · 시장(gl)과 독립이다 (미국 시장을 일본어로 쓸 수 있다)
REPORT_LANGS = ("kr", "jp", "us")
LOCALE_FONT_OVERRIDE = {
    "kr": "",
    "jp": "html { --font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, Sans-serif; }",
    "us": "html { --font-family: 'Noto Sans', -apple-system, BlinkMacSystemFont, Sans-serif; }",
}
# 데이터에 들어 있는 한국어 계약값(plan · scope 가 쓰는 값) → 화면 라벨 키. 값 자체는 바꾸지 않고 표시만 옮긴다.
UNIT_KEY = {"의도": "ui.unit.purpose", "제품 라인": "ui.unit.line", "SKU": "ui.unit.line", "방법": "ui.unit.method", "구분": "ui.unit.other"}  # i18n-ok · 계약값
HOW_KEY = {"사용자 선택": "ui.how.user", "적합 1개 · 자동": "ui.how.auto", "직접 입력": "ui.how.manual"}  # i18n-ok · 계약값
PAL = ["#f96e6e", "#46b2f2", "#ff99f5", "#4685ff", "#00ad98", "#ebaa03", "#35ca00"]  # LM lineChart[1~7] · 시드(기준)는 lineChart[0] = var(--ds-seed)
CHEV = ('<svg class="ds-dd-chev" viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M6 3.5 10.5 8 6 12.5" '
        'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>')

F, N, LB = {}, {}, {}
_UID = [0]


def L(key, **kw):
    s = LB.get(key, key)
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


_SLOT = re.compile(r"\{(\w+)(?:\|(\w+))?\}")


def T(key, **kw):
    """문장 틀 라벨 · {name} 은 값, {name|은는} 은 값 + 받침에 맞는 조사 (kr 틀만 조사 표시를 쓴다)."""
    return _SLOT.sub(lambda m: josa(str(kw[m.group(1)]), m.group(2)) if m.group(2) else str(kw[m.group(1)]), LB.get(key, key))


def bundle(name):
    """묶음 이름 표시 · 코드가 만드는 한국어 묶음 이름(계급도·순위 등)은 라벨로 옮기고, 사용자가 고른 이름은 그대로."""
    return LB.get("bundle." + str(name), name)


def how_label(sc):
    """scope.how (계약값 · 좁히기 방식) → 화면 라벨. 비어 있으면 사용자 선택."""
    how = sc.get("how") or next(k for k, v in HOW_KEY.items() if v == "ui.how.user")
    return L(HOW_KEY[how]) if how in HOW_KEY else how


def unit_label(u):
    return L(UNIT_KEY[u]) if u in UNIT_KEY else u


def e(s):
    return html.escape(str(s if s is not None else ""))


_ALLOWED = re.compile(r"&lt;(/?)(strong|b)&gt;")


def rich(t):
    return _ALLOWED.sub(lambda m: f"<{m.group(1)}{m.group(2)}>", html.escape(str(t or "")))


def tier(d):
    """method-v5 · 증감률 크기 단계: t1 < 10% · t2 10~30% · t3 ≥ 30% (진할수록 큼)."""
    a = abs(d or 0)
    return "t3" if a >= 0.30 else ("t2" if a >= 0.10 else "t1")


OPA = [0.3, 0.45, 0.6, 0.75, 0.9, 1.0]  # method-v5 · 증감률 10% 구간별 불투명도 (50% 이상은 원색)


def chip_style(d):
    """method-v5 · 증감률 = 화살표·숫자 색의 '불투명도'로 크기 표현 (1~10% → 30% … 50% 이상 → 100%) · 30% 이상은 굵게."""
    if d is None:
        return ""
    a = abs(d) * 100
    lv = min(len(OPA), max(1, int(-(-a // 10))))
    base = "var(--ds-up)" if d > 0 else "var(--ds-down)"   # LM filter.trend.increase / decrease
    return (f'background:transparent;color:color-mix(in srgb,{base} {OPA[lv - 1] * 100:.0f}%,transparent);'
            f'font-weight:{700 if lv >= 4 else 500}')


def pct(r):
    s = C.fmt_pct(r)
    if r is None:
        return f'<span class="flat">{s}</span>'
    return f'<span class="{"up" if r > 0.005 else ("dn" if r < -0.005 else "flat")} ds-{tier(r)}">{s}</span>'


def gid():
    _UID[0] += 1
    return f"g{_UID[0]}"


# ───────────────────────── 표 ─────────────────────────

def tags_html(r):
    out = ""
    if r.get("seed"):
        out += f'<span class="ds-tag ds-tag--seed">{e(L("tag.seed"))}</span>'

    # method-v5 · 이름 옆 '신규 YYYY-MM' 태그 없음 — 처음 등장한 구간의 '신규 YYYY.MM' 뱃지가 대신한다
    # method-v5 · 출처(intent/cluster/analyst) 태그는 마케터에게 의미가 없어 표에서 뺀다
    return out


def gt_cell(r):
    if r.get("gt") is not None:
        return pct(r["gt"])
    if r.get("since") or "new" in (r.get("tags") or []):  # method-v5 · 신규는 이름 옆 태그·구간 NEW 로 이미 보이므로 여기선 '—'
        return f'<span class="flat" title="{e(L("ui.gt.newNoChange"))}">—</span>'
    return '<span class="flat">—</span>'


def era_of(month):
    """'2024-08' → 그 달이 든 12개월 구간 번호 (0~3) · 없으면 None."""
    ms = F["months"]
    return ms.index(month) // 12 if month in ms else None


def era_cell(t, k, since=None):
    """method-v5 · 12개월 구간 검색량 + 직전 구간 대비 뱃지. 처음 등장한 구간(since 가 든 구간 · 또는 직전 구간이 0)은 NEW."""
    v = t[k]
    new_k = era_of(since) if since else None
    if (new_k is not None and k == new_k and v) or (k > 0 and not t[k - 1] and v):
        lab = L("ui.era.new", since=since.replace('-', '.')) if since else L("ui.era.newBare")
        return (f'<td><span class="ds-era">{C.fmt_int(v)}<span class="ds-era__b ds-era__b--new" '
                f'title="{e(L("ui.era.firstSeen"))}{(" (" + since + ")") if since else ""}">{e(lab)}</span></span></td>')
    if k == 0 or not t[k - 1]:
        return f"<td>{C.fmt_int(v)}</td>"
    d = (v or 0) / t[k - 1] - 1
    cls = "up" if d > 0.0005 else ("dn" if d < -0.0005 else "flat")
    arrow = "▲" if cls == "up" else ("▼" if cls == "dn" else "–")
    prev_new = (new_k is not None and k - 1 == new_k) or (k >= 2 and not t[k - 2] and t[k - 1])
    if prev_new:  # 직전 구간이 등장 구간이면 몇 달만 들어 있어 % 가 수천이 된다 — 방향만 보이고 값은 툴팁으로
        return (f'<td><span class="ds-era">{C.fmt_int(v)}<span class="ds-era__b ds-era__b--{cls}" '
                f'title="{e(L("ui.era.prevNewTip", d=C.fmt_pct(d)))}">'
                f'<span class="ds-era__a" style="{chip_style(d)}">{arrow}</span></span></span></td>')
    # method-v5 · 화살표만 색(불투명도 = 크기) · 숫자는 회색
    return (f'<td><span class="ds-era">{C.fmt_int(v)}<span class="ds-era__b ds-era__b--{cls}" title="{e(L("ui.era.prevTip", d=C.fmt_pct(d)))}">'
            f'<span class="ds-era__a" style="{chip_style(d)}">{arrow}</span><span class="ds-era__n">{abs(d) * 100:.0f}%</span></span></span></td>')


def data_cells(r, extra, seed=False, name=None):
    col = "var(--ds-seed)" if seed else "var(--gray-600)"
    m = r.get("m") or []
    si = F["months"].index(r["since"]) if r.get("since") in F["months"] and "new" in (r.get("tags") or []) else None
    attrs = (f' data-m="{e(json.dumps(m))}" data-name="{e(name or r.get("name") or r.get("kw") or "")}"'
             + (f' data-since="{si}"' if si is not None else "")
             + f' title="{e(L("ui.spark.tip"))}{e(L("ui.spark.since", since=r["since"])) if si is not None else ""}"'
             if m else "")
    tds = [f'<td class="c-spark"{attrs}>{CH.sparkline(m, color=col, since=si)}</td>']
    tds += [era_cell(r["t"], k, r.get("since")) for k in range(len(r["t"]))]
    tds += [f"<td>{C.fmt_int(r.get('avg'))}</td>", f"<td>{gt_cell(r)}</td>"]
    for x in extra:
        tds.append(f"<td>{x(r)}</td>")
    return "".join(tds)


def share_int(x):
    """method-v5 · 비중은 정수 % 로 (17.3% → 17%) · 1% 미만은 '1% 미만'."""
    if x is None:
        return "—"
    p = x * 100
    return L("ui.share.lt1") if 0 < p < 0.5 else f"{round(p)}%"


def kw_share(m, r, ms):
    """method-v5.3.2 · 펼친 검색어의 묶음 안 비중 막대는 없앤다 (리뷰: 표 안에서 막대가 행을 두 줄로 늘리고 읽기 어렵다).
    검색어 행은 이름 + 구간 칸만 — 비중이 필요하면 구간 칸의 검색량으로 읽는다."""
    return ""


def _kw_share_v5(m, r, ms):
    """(v5.3.1 까지) 막대 길이는 묶음 1위 대비, 숫자는 묶음 안 비중."""
    tot = (r.get("t") or [0])[-1]
    v = (m.get("t") or [0])[-1]
    if not tot:
        return ""
    top = max(((x.get("t") or [0])[-1] for x in ms), default=0) or 1
    sh = v / tot
    return (f'<span class="ds-kws" title="최근 12개월 {C.fmt_int(v)} · 이 묶음 안 비중 {share_int(sh)}">'
            f'<span class="ds-kws__bar"><span style="width:{v / top * 100:.1f}%"></span></span>'
            f'<span class="ds-kws__v">{share_int(sh)}</span></span>')


MORE_N = 10  # method-v5 · 펼쳤을 때 먼저 보여 줄 검색어 수 (나머지는 '전체 보기')


def more_row(pid, rest, ncol, depth):
    return (f'<tr class="ds-dd-child {depth} ds-more-row" data-parent="{pid}" data-morebtn="1" hidden><td colspan="{ncol}">'
            f'<button type="button" class="ds-more-btn" data-for="{pid}">{e(L("ui.more", n=f"{rest:,}"))}</button></td></tr>')


def nkw(r):
    """묶음 안 신규 검색어 수 · 묶음 자체가 신규인 구간(그 구간 검색어는 모두 새로 생김)은 뺀다 — 범프 차트 +n 과 같은 기준."""
    nk = r.get("newKwY") or []
    first = era_of(r.get("since")) if "new" in (r.get("tags") or []) and r.get("since") else None
    return sum(c for k, c in enumerate(nk) if k != first)


def table(rows, *, extra_cols=(), total=None, first=None):
    """묶음 행은 이름 앞 화살표로 같은 표 안에서 구성 키워드가 펼쳐진다. 정렬 = 월평균 높은 순, 합계 행은 맨 아래."""
    head = [f"<th>{e(first or L('col.name'))}</th>", f'<th class="c-spark">{e(L("col.spark"))}</th>']
    head += [f"<th>{e(y)}</th>" for y in F["years"]]
    head += [f"<th>{e(L(k))}</th>" for k in ("col.avg", "col.gt")]  # method-v5 · 전년 = 마지막 구간 뱃지와 같아 뺐다
    head += [f"<th>{e(h)}</th>" for h, _ in extra_cols]
    fns = [fn for _, fn in extra_cols]
    ncol = len(head)
    body = []
    for r in rows:
        seed = bool(r.get("seed"))
        subs = r.get("subs") or []
        ms = r.get("members") or []
        multi = len(ms) >= 2 or bool(subs)
        cls = ["is-seed"] if seed else []
        sub = ""
        if not multi and ms and ms[0]["kw"] != r["name"]:
            sub = f'<span class="ds-sub">{e(ms[0]["kw"])}</span>'
        if multi:
            g = gid()
            cls.append("ds-dd-has")
            lab = (f'<div class="ds-dd-lab"><button type="button" class="ds-dd-tog" aria-expanded="false" aria-label="{e(L("ui.expand.group"))}">{CHEV}</button>'
                   f'<span class="ds-dd-body"><span class="ds-name">{e(bundle(r["name"]))}</span>{tags_html(r)}'
                   f'<span class="ds-dd-n">{e(L("ui.n.subs", n=len(subs)) if subs else L("ui.n.items", n=len(ms)))}</span>'
                   + (f'<span class="ds-newkw" title="{e(L("ui.newkw.tip"))}">{e(L("ui.newkw", n=nkw(r)))}</span>'
                      if nkw(r) else "") + '</span></div>')
            body.append(f'<tr class="{" ".join(cls)}" data-id="{g}" data-g="{e(r["name"])}"><td>{lab}</td>{data_cells(r, fns, seed)}</tr>')
            for x in subs:  # 라인 → 하위 SKU (모델명이 다른 것) · 비중 = 내부 합계 대비
                xms = x.get("members") or []
                sg = gid() if xms else None
                tog = (f'<button type="button" class="ds-dd-tog" aria-expanded="false" aria-label="{e(L("ui.expand.kw"))}">{CHEV}</button>' if sg
                       else '<span class="ds-dd-tsp"></span>')
                kid = (f'<td class="ds-dd-first"><div class="ds-dd-lab">{tog}<span class="ds-dd-body">'
                       f'<span class="ds-dd-cname">{e(bundle(x["name"]))}</span>{tags_html({"tags": x.get("tags"), "since": x.get("since")})}'
                       f'<span class="ds-dd-n">{e(L("ui.n.kw", n=x.get("n", 1)))}</span></span></div></td>')
                attrs = f' data-id="{sg}"' if sg else ""
                body.append(f'<tr class="ds-dd-child ds-dd-d1{" ds-dd-has" if sg else ""}" data-parent="{g}"{attrs} hidden>{kid}{data_cells(x, fns)}</tr>')
                # method-v5 · 카테고리 모드 하위 묶음은 한 번 더 펼쳐 검색어를 보여 준다 (최근 12개월 검색량 순 · 하위 묶음 안 지분)
                for mi, m in enumerate(sorted(xms, key=lambda m: -((m.get("t") or [0])[-1] or 0)) if sg else []):
                    mr = {**m, "name": m["kw"]}
                    kk = (f'<td class="ds-dd-first"><div class="ds-dd-lab"><span class="ds-dd-tsp"></span><span class="ds-dd-body">'
                          f'<span class="ds-dd-cname">{e(m["kw"])}</span>{kw_share(m, x, xms)}</span></div></td>')
                    more = ' data-more="1"' if mi >= MORE_N else ""
                    body.append(f'<tr class="ds-dd-child ds-dd-d2" data-parent="{sg}"{more} hidden>{kk}'
                                f'{data_cells(mr, [(lambda rr, fn=fn: "") for fn in fns])}</tr>')
                if sg and len(xms) > MORE_N:
                    body.append(more_row(sg, len(xms) - MORE_N, ncol, "ds-dd-d2"))
            msorted = sorted(ms, key=lambda m: -((m.get("t") or [0])[-1] or 0))
            for mi, m in enumerate([] if subs else msorted):
                mr = {**m, "name": m["kw"]}
                kid = (f'<td class="ds-dd-first"><div class="ds-dd-lab"><span class="ds-dd-tsp"></span><span class="ds-dd-body">'
                       f'<span class="ds-dd-cname">{e(m["kw"])}</span>{tags_html({"tags": m.get("tags"), "since": m.get("since")})}'
                       f'{kw_share(m, r, ms)}</span></div></td>')
                kid_extra = [(lambda rr, fn=fn: "") for fn in fns]
                if any(h == L("col.share") for h, _ in extra_cols) and r.get("t") and r["t"][-1]:
                    kid_extra = [(lambda rr, h=h: share_int(rr["t"][-1] / r["t"][-1]) if h == L("col.share") else "")
                                 for h, _ in extra_cols]
                more = ' data-more="1"' if mi >= MORE_N else ""
                body.append(f'<tr class="ds-dd-child ds-dd-d1{" is-seed" if seed else ""}" data-parent="{g}"{more} hidden>'
                            f'{kid}{data_cells(mr, kid_extra, seed)}</tr>')
            if not subs and len(ms) > MORE_N:
                body.append(more_row(g, len(ms) - MORE_N, ncol, "ds-dd-d1"))
        else:
            body.append(f'<tr class="{" ".join(cls)} ds-g-row" data-g="{e(r["name"])}"><td><span class="ds-name">{e(bundle(r["name"]))}</span>{sub}{tags_html(r)}</td>'
                        f'{data_cells(r, fns, seed)}</tr>')
    if total:
        body.append(f'<tr class="is-total ds-nt-total"><td><span class="ds-name">{e(total.get("name") or L("total"))}</span></td>'
                    f'{data_cells(total, [(lambda rr: "100%") if h == L("col.share") else (lambda rr: "") for h, _ in extra_cols])}</tr>')
    return (f'<div class="ds-tablewrap"><table class="ds-table ds-nt-table"><thead><tr>{"".join(head)}</tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>')



INFO_SVG = ('<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="7" fill="currentColor"/>'
            '<rect x="7.1" y="7" width="1.8" height="4.6" rx=".9" fill="#fff"/><circle cx="8" cy="4.9" r="1.05" fill="#fff"/></svg>')


def info(text, cls=""):
    """method-v5 · 부가 설명은 본문에 늘어놓지 않고 (i) 아이콘 툴팁으로."""
    if not text:
        return ""
    return f'<span class="ds-i {cls}" tabindex="0" role="button" aria-label="{e(L("ui.info"))}" data-tip="{e(text)}">{INFO_SVG}</span>'


def btitle(title, tip="", style=""):
    st = f' style="{style}"' if style else ""
    return f'<div class="ds-blocktitle ds-tl-row"{st}><span>{e(title)}</span>{info(tip)}</div>'


# ───────────────────────── 차트 ─────────────────────────

def kids_of(r, n=10):
    """method-v5.4 · 묶음 안 검색어 상위 n개 (최근 12개월 검색량 순) — 칩을 누르면 합계 선과 함께 그린다."""
    ms = sorted(r.get("members") or [], key=lambda m: -((m.get("t") or [0])[-1] or 0))
    return [{"name": m["kw"], "values": m["m"]} for m in ms[:n] if m.get("m")] if len(ms) > 1 else []


def line_block(series, cap, peaks=True):
    leg = CH.legend([(s["name"], s["color"], s.get("dash"), s.get("group"), s.get("member")) for s in series])
    # method-v5 · 범례 옆 (i) 없음
    return leg + CH.line_chart(series, F["months"], F["years"], F.get("lang", "kr"), peaks=peaks)


def heat_color(r):
    if r is None:
        return None
    k = min(abs(r) / 0.5, 1.0)
    pctv = int(12 + 78 * k)
    var = "var(--ds-up)" if r > 0 else "var(--ds-down)"
    return f"color-mix(in srgb,{var} {pctv}%,transparent)"


def share_bars(rows):
    """구간별 비중 · 구간마다 한 줄 누적 막대 (상위 6개 + 기타) — 꺾은선과 같은 인터랙션(범례 켜고 끄기 · 강조 · 호버 툴팁).
    막대 길이 = 그 구간 합계 ÷ 4구간 중 최대 합계 · 막대 안 칸 = 그 구간 안의 비중. 계열을 끄면 남은 계열로 다시 계산한다."""
    top = rows[:6]
    cols = PAL_SHARE
    nY = len(F["years"])
    totals = [sum(r["t"][k] for r in rows) for k in range(nY)]
    series = [{"name": r["name"], "color": cols[i], "vals": [r["t"][k] for k in range(nY)]} for i, r in enumerate(top)]
    if len(rows) > 6:
        series.append({"name": L("ui.other"), "color": "var(--gray-300)", "other": True,
                       "vals": [totals[k] - sum(r["t"][k] for r in top) for k in range(nY)]})
    mx = max(totals) or 1
    top2 = [((sum(sorted((r["t"][k] for r in rows), reverse=True)[:2]) / totals[k]) if totals[k] else None) for k in range(nY)]
    leg = "".join(f'<span class="ds-legend__i" data-s="{i}" tabindex="0" role="button"><span class="ds-legend__sw" style="background:{x["color"]}"></span>{e(bundle(x["name"]))}</span>'
                  for i, x in enumerate(series))
    bars = []
    for k, y in enumerate(F["years"]):
        tk = totals[k] or 1
        segs = "".join(f'<span class="ds-nt-seg" data-s="{i}" style="width:{x["vals"][k] / tk * 100:.2f}%;background:{x["color"]}"></span>'
                       for i, x in enumerate(series))
        # 합계 숫자를 막대 끝에 붙여 오른쪽 고정 칸을 없앴다 → 최대 구간 막대가 줄 너비(숫자 자리 76px 제외)를 거의 다 쓴다
        bars.append(f'<div class="ds-nt-bar" data-k="{k}" style="grid-template-columns:80px 1fr"><span>{e(y)}</span>'
                    f'<div style="display:flex;align-items:center;gap:8px;min-width:0">'
                    f'<div class="ds-sb-fill" style="display:flex;flex:none;width:calc((100% - 170px) * {totals[k] / mx:.4f});height:18px;border-radius:4px;overflow:hidden">{segs}</div>'
                    f'<span class="ds-nt-bar__v ds-sb-v" style="white-space:nowrap;text-align:left">{C.fmt_int(totals[k])}</span>'
                    f'<span class="ds-sb-top2" style="white-space:nowrap;font-size:11px;color:var(--gray-500)">{e(L("share.top2", v=C.fmt_share(top2[k])))}</span></div></div>')
    data = html.escape(json.dumps({"years": F["years"], "series": series}, ensure_ascii=False), quote=True)
    sb_cap = L("ui.sb.cap")
    return (f'<div class="ds-sb" data-sb="{data}"><div class="ds-legend ds-sb-leg">{leg}{info(sb_cap, "ds-i--leg")}</div><div class="ds-nt-bars">{"".join(bars)}</div></div>')


PAL_SHARE = ["var(--ds-seed)", "var(--brand-magenta-main)", "var(--brand-coral-main)", "var(--gray-600)", "var(--success-main)", "var(--warning-main)"]


def index_series(vals):
    b = (sum(vals[:12]) / 12) if vals else 0
    if b <= 0:
        return None
    return [round(v / b * 100, 1) for v in vals]



# ───────────────────────── 구간별 증감률 막대 (4년) ─────────────────────────

def period_bars(units, groups, title, show_title=True):
    """units = 기준 행(굵게) · groups = [(구분 제목, 행 목록)] · 행 = (이름, 연간 합계 4개, 시드 여부).
    1년 구간 3열(직전 구간 대비)은 ±100% 같은 축, 4년 열은 ±200% 축. 축을 넘는 막대는 끝을 잘라 연하게."""
    Y = F["years"]
    CAPS, K = [1.0, 1.0, 1.0, 2.0], 20

    def vs(tt):
        return [(tt[i] / tt[i - 1] - 1) if tt[i - 1] else None for i in (1, 2, 3)] + [(tt[3] / tt[0] - 1) if tt[0] else None]

    def cell(v, cap, last=False):
        x = " ds-bt-c--4y" if last else ""
        if v is None:
            return f'<div class="ds-bt-c{x}"><span class="ds-bt-na">—</span></div>'
        w = min(abs(v), cap) / cap * K
        cls = "up" if v > 0 else "dn"
        clip = " is-clip" if abs(v) > cap else ""
        side = "left" if v > 0 else "right"
        return (f'<div class="ds-bt-c{x}"><span class="ds-bt-z"></span><span class="ds-bt-b {cls}{clip}" style="{side}:50%;width:{w:.2f}%"></span>'
                f'<span class="ds-bt-v {cls}" style="{side}:calc(50% + {w:.2f}% + 4px)">{e(C.fmt_pct(v))}</span></div>')

    def row(name, tt, seed, unit):
        lab = e(bundle(name)) + (f' <span class="ds-tag ds-tag--seed">{e(L("tag.seed"))}</span>' if seed else "")
        return (f'<div class="ds-bt-row ds-bt-row--4{" is-seed" if seed else ""}{" is-unit" if unit else ""}"><div class="ds-bt-n">{lab}</div>'
                + "".join(cell(v, CAPS[i], i == 3) for i, v in enumerate(vs(tt))) + "</div>")
    hdr = ('<div class="ds-bt-row ds-bt-row--4 ds-bt-hd"><div></div>'
           + "".join(f'<div class="ds-bt-h"><b>{e(Y[i])}</b><span>{e(L("ui.bt.vs", y=Y[i - 1]))}</span></div>' for i in (1, 2, 3))
           + f'<div class="ds-bt-h ds-bt-h--4y"><b>{e(L("col.gt"))}</b><span>{e(Y[0])} → {e(Y[3])}</span></div></div>')
    body = "".join(row(n, t, sd, True) for n, t, sd in units)
    for _gtitle, rows in groups:  # 구분 제목 행은 두지 않는다 (정렬 기준은 블록 제목에)
        body += "".join(row(n, t, sd, False) for n, t, sd in rows)
    cap = L("ui.bt.cap", y=Y[3])
    return (f'<div class="ds-hm-block" style="margin:6px 0 18px">{btitle(title, cap) if show_title else ""}'
            f'<div class="ds-bt">{hdr}{body}</div></div>')


# ───────────────────────── 섹션 ─────────────────────────

def lead(sid):
    s = (N.get("sections") or {}).get(sid) or {}
    return f'<p class="ds-note ds-note--sec">{rich(s.get("lead"))}</p>' if s.get("lead") else ""


def tabwrap(title, cap, views, extra_cls=""):
    """method-v5 · 글자 탭 카드 (48개월 그래프 / 증감률 등) · views = [(key, 탭 이름, html)] · 첫 탭이 기본."""
    btns = "".join(f'<button type="button" class="ds-vt__b{" is-on" if i == 0 else ""}" data-v="{k}" role="tab">{e(lab)}</button>'
                   for i, (k, lab, _h) in enumerate(views))
    panes = "".join(f'<div class="ds-tw__p" data-p="{k}"{"" if i == 0 else " hidden"}>{h}</div>' for i, (k, _l, h) in enumerate(views))
    return (f'<div class="ds-bumpwrap ds-tw {extra_cls}"><div class="ds-bumpwrap__hd">{btitle(title, cap, "margin:0")}'
            f'<div class="ds-vt ds-vt--txt" role="tablist">{btns}</div></div>{panes}</div>')


def agg_row(name, rows):
    """여러 행을 합친 '전체' 행 (월별 합 → 4구간 합 · 월평균 · 4년)."""
    n = len(rows[0]["m"])
    m = [sum((r["m"][i] or 0) for r in rows) for i in range(n)]
    t = [sum(m[k * 12:(k + 1) * 12]) for k in range(len(rows[0]["t"]))]
    return {"name": name, "m": m, "t": t, "avg": round(t[-1] / 12), "gt": (t[-1] / t[0] - 1) if t[0] else None,
            "yoy": (t[-1] / t[-2] - 1) if len(t) > 1 and t[-2] else None, "members": [], "tags": []}


def josa(word, pair):
    """받침 따라 조사 — pair 앞 글자 = 받침 있을 때 (은는 · 이가 · 과와 · 으로로). 한글이 아니면 뒤쪽.
    kr 문장 틀의 {name|은는} 표시에서만 쓴다 (jp · us 틀에는 조사 표시가 없다)."""
    ch = (word or " ")[-1]
    if "가" <= ch <= "힣":  # i18n-ok · 한국어 조사 처리
        jong = (ord(ch) - 0xAC00) % 28
        if pair == "으로로":  # i18n-ok · 한국어 조사 처리
            return word + ("로" if jong in (0, 8) else "으로")  # i18n-ok · 한국어 조사 처리
        return word + (pair[0] if jong else pair[1])
    return word + (pair[1] if pair != "으로로" else "로")  # i18n-ok · 한국어 조사 처리


def verdict_text(v, seed_gt, base, peers):
    """method-v5.6.6 · 판정 카드 문장 — 시장(비교 대상들)이 어떻게 움직였는지 먼저, 그다음 분석 대상이 그 안에서 어땠는지.
    '비슷한 카테고리보다 15%p 넘게 뒤처져' 같은 기준 설명 대신 '런닝화 시장은 커지고 있는데 나이키는 제자리' 식으로.
    문장은 언어별 문장 틀(verdict.tpl.*)에 이름·숫자만 넣는다. 경우의 수(판정 × 대상·시장 증감)는 코드가 고른다."""
    sd = F["seed"]
    x = F["sections"]["external"]
    pn = L("verdict.tpl.peers.sep").join(peers[:4])
    if len(peers) > 4:
        pn = L("verdict.tpl.peers.more", list=pn)
    if v == "hold" or seed_gt is None or base is None:
        return T("verdict.tpl.head.hold", sd=sd), ""
    unit = L("ui.unit." + ("brand" if F["mode"] == "entity" else "category"))
    mk = F.get("market")
    mname = L("verdict.tpl.market", mk=mk) if mk else L("verdict.tpl.market.none")
    n, ups, downs = len(x["rows"]), x.get("ups", 0), x.get("downs", 0)
    sp, bp = C.fmt_pct(seed_gt), C.fmt_pct(base)
    mdir = L("verdict.tpl.mdir." + ("up" if base > 0 else "down"))
    k = ups if base > 0 else downs
    cnt = T("verdict.tpl.cnt." + ("all" if k == n else "some") + "." + ("up" if base > 0 else "down"), unit=unit, n=n, k=k, bp=bp)
    sdn = "down" if seed_gt < 0 else "up"
    kw = dict(sd=sd, pn=pn, sp=sp, mname=mname, mdir=mdir, cnt=cnt)
    if v == "same":
        head = T("verdict.tpl.head.same." + sdn if (seed_gt < 0) == (base < 0) else "verdict.tpl.head.same.mixed", **kw)
        why = T("verdict.tpl.why.same", **kw)
    elif v == "weak":
        head = T("verdict.tpl.head.weak." + sdn, **kw)
        me = T("verdict.tpl.me.weak." + ("flip" if base > 0 and seed_gt < 0 else ("less" if base > 0 else "more")), **kw)
        why = T("verdict.tpl.why.weak", me=me, **kw)
    else:
        head = T("verdict.tpl.head.strong." + sdn, **kw)
        me = T("verdict.tpl.me.strong." + ("flip" if base < 0 and seed_gt >= 0 else ("less" if base < 0 else "more")), **kw)
        why = T("verdict.tpl.why.strong", me=me, **kw)
    return head, why


def sec_external():
    x = F["sections"]["external"]
    t = x["seedRow"]  # method-v5.6 · 비교용 대표 표기 묶음 (v5.9 · 두 모드)
    lite = bool(x.get("seedLite"))
    v = x["verdict"]
    tone = {"same": "info", "weak": "bad", "strong": "good", "hold": "muted"}[v]
    stat = (L("verdict.stat", seed_name=F["seed"], seed=C.fmt_pct(t["gt"]), base=C.fmt_pct(x["baseline"]), diff=C.fmt_pp(x["diff"]))
            if v != "hold" else L("verdict.hold.why"))
    loo = ""
    if x.get("loo"):
        # v5.6.5 · 하나씩 빼는 점검은 작업용 — 리포트에는 싣지 않는다 (build 출력·facts.md 에서 보고, 흔들리면 리포트 전에 비교군을 다시 본다)
        loo = ""
    # v5.6.3 · 대표 표기 커버는 리포트에 싣지 않는다 (작업용 점검 · build 출력·facts.md 에만). 낮으면 리포트 전에 표기를 보완한다.
    head, why = verdict_text(v, t.get("gt"), x.get("baseline"), [r["name"] for r in x["rows"]])
    if F["mode"] == "entity":  # v5.6.2 · 브랜드 모드 판정 문구는 '카테고리' 대신 '브랜드'
        stat, why = stat.replace(L("ui.unit.category"), L("ui.unit.brand")), (why or "").replace(L("ui.unit.category"), L("ui.unit.brand"))
    card = (f'<div class="ds-vcard"><div class="ds-vcard__head"><span class="ds-status ds-status--{tone}">{e(L("verdict." + v))}</span>'
            f'<span class="ds-vcard__title">{e(head)}</span></div>'
            f'<div class="ds-vcard__stat">{e(stat)}</div>' + (f'<div class="ds-vcard__why">{e(why)}</div>' if why else "")
            + (f'<div class="ds-vcard__caveat">{e(loo)}</div>' if loo else "") + "</div>")
    # method-v5 · [48개월 그래프 | 증감률] 탭 · 전체(비교한 카테고리 합계) + 각 카테고리 · 그래프에는 구성 검색어 선을 그리지 않는다 (표에서 펼친다 · v5.3)
    # method-v5.6.1 · 분석 대상 행도 비교 묶음처럼 펼침·하위 칩 (1 의 대표 표기 구성)
    allrows = [{**t, "seed": True}] + x["rows"]
    whole = agg_row(L("ui.all"), allrows)
    # method-v5 · 48개월 그래프 = 실제 검색량 (전체 = 합계라 가장 위) · 칩을 누르면 그 묶음 기준으로 축이 다시 맞춰진다 (v5.5.3 · × 없음)
    series = [{"name": L("ui.all"), "values": whole["m"], "color": "var(--gray-800)", "width": 2.6},
              {"name": t["name"], "values": t["m"], "color": "var(--ds-seed)", "width": 2.6, "kids": kids_of(t)}]
    pal = PAL + ["#9b6cf0", "#a1887f", "#78909c"]  # v5.7 · 비교 대상 최대 10
    for i, r in enumerate(x["rows"][:10]):
        series.append({"name": r["name"], "values": r["m"], "color": pal[i % len(pal)], "width": 1.6, "kids": kids_of(r)})
    chart = line_block(series, L("chart.external.cap"), peaks=False) if len(series) >= 2 else ""
    allr = sorted([(t["name"], t["t"], True, t["avg"])] + [(r["name"], r["t"], False, r["avg"]) for r in x["rows"]], key=lambda z: -z[3])
    pb = period_bars([(L("ui.all"), whole["t"], False)], [("", [(n, tt, sd) for n, tt, sd, _ in allr])], "", show_title=False)
    tw = tabwrap(L("ui.tw.external.title." + F["mode"]), L("ui.tw.external.cap", engines=L("engines." + F["gl"])),
                 [("chart", L("ui.tab.volume"), chart), ("rate", L("ui.tab.rate"), pb)])
    rel = (L("col.rel"), lambda rr: C.fmt_pp(rr.get("rel")) if rr.get("rel") is not None else "—")
    # method-v5.3 · 비교 대상은 같은 뜻의 검색어 묶음이다 — 이름 앞 화살표로 구성 검색어(묶음 안 비중)가 펼쳐진다.
    #   펼침이 없으면 '아디다스 런닝화' 한 검색어처럼 읽힌다 (리뷰). 그래프는 그대로 묶음 합계만.
    cap = (L("ui.ext.cap.lite.entity") if lite and F["mode"] == "entity" else
           L("ui.ext.cap.lite.category") if lite else L("ui.ext.cap.full"))
    return (card + '<div style="height:14px"></div>' + tw
            + btitle(L("ui.table.byUnit", unit=L("ui.unit." + ("brand" if F["mode"] == "entity" else "category"))), cap, "margin-top:18px")
            + table(allrows, extra_cols=[rel], total={**whole, "rel": None}, first=L("ui.unit." + ("brand" if F["mode"] == "entity" else "category"))))

def sec_internal():
    s = F["sections"]["internal"]
    if not s["rows"]:
        return f'<p class="ds-note">{e(L("ui.internal.empty"))}</p>'
    if s.get("unit") in ("의도", "제품 라인", "SKU"):  # i18n-ok · 계약값 · method-v5.1 · 브랜드/제품 모드도 같은 화면 (묶음 기준만 제품 라인)
        return intent_flow_cards(s) + intent_table(s)
    share = (L("col.share"), lambda rr: share_int(rr.get("share")))
    first = unit_label(s.get("unit") or "구분")  # i18n-ok · 계약값
    pb = period_bars([(L("total"), s["total"]["t"], False)], [(L("ui.pb.group", unit=first), [(r["name"], r["t"], False) for r in s["rows"]])],
                     L("ui.pb.title", unit=first))
    return (pb + f'<div class="ds-blocktitle">{e(L("share.title"))}</div>' + share_bars(s["rows"])
            + table(s["rows"], extra_cols=[share], total=s["total"], first=first))


def intent_mix_table(s):
    """카테고리 모드 · 의도별 묶음 검색량: 4구간 합계 · 구성비 변화(첫 구간 → 최근 구간) · 흐름 유형."""
    Y = F["years"]
    head = (f'<th>의도 묶음</th>' + "".join(f"<th>{e(y)}</th>" for y in Y)
            + f'<th>{e(L("col.mix"))} {e(Y[0])} → {e(Y[-1])}</th><th>{e(L("col.flow"))}</th>')
    body = []
    for r in s["rows"]:
        a, b = r["shareY"][0], r["shareY"][-1]
        d = (b - a) if (a is not None and b is not None) else None
        mix = (f'{C.fmt_share(a)} → <b>{C.fmt_share(b)}</b>'
               + (f' <span class="{"up" if d > 0.0005 else ("dn" if d < -0.0005 else "flat")}">({C.fmt_pp(d)})</span>' if d is not None else ""))
        body.append(f'<tr><td><span class="ds-name">{e(r["name"])}</span><span class="ds-dd-n" style="margin-left:6px">{r["n"]}개</span></td>'
                    + "".join(f"<td>{C.fmt_int(v)}</td>" for v in r["t"])
                    + f'<td>{mix}</td><td>{e(r["flow"])}</td></tr>')
    tt = s["total"]
    body.append(f'<tr class="is-total ds-nt-total"><td><span class="ds-name">{e(L("total"))}</span></td>'
                + "".join(f"<td>{C.fmt_int(v)}</td>" for v in tt["t"]) + f'<td>100.0%</td><td>{e(flow_label(tt["dir"]))}</td></tr>')
    cap = "구성비 = 그 구간 의도 묶음 합계 대비 비중 · 흐름 유형 = 12개월 구간 3번의 증감 방향 · 한 검색어는 한 묶음에만 들어갑니다 (브랜드 → 토픽 → 계급도·순위 → 추천·입문 → 비교·후기 → 가격 → 신제품 순)"
    if s.get("unassigned"):
        cap += f" · 어느 목적에도 들지 않은 검색어 {C.fmt_int(s['unassigned'])}개는 넣지 않았습니다"
    return (f'<div class="ds-blocktitle">의도별 묶음 검색량</div><div class="ds-tablewrap"><table class="ds-table ds-nt-table">'
            f'<thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div><div class="ds-chart-cap">{e(cap)}</div>')


def is_line(s):
    """method-v5.1 · 브랜드/제품 모드 3 = 제품 라인 (화면은 카테고리 모드 검색 목적과 같고 이름만 다르다)."""
    return s.get("unit") in ("제품 라인", "SKU")  # i18n-ok · 계약값


def unit_name(s):
    return L("ui.unit.line") if is_line(s) else L("ui.unit.searchPurpose")


def intent_flow_cards(s):
    """method-v5.3.3 · 3 그래프 = [검색량 | 증감률] 탭 — 섹션 1·2 와 같은 꺾은선.
    각 선 = 그 검색 목적(제품 라인)에 든 검색어 월 검색량 합계 · 전체 = 묶음 합계(굵은 실선 · 섹션 2 와 같은 모양). 범프 차트(점유율 순위)는 없앴다 (리뷰)."""
    tot = s["total"]
    series = [{"name": L("ui.all"), "values": tot["m"], "color": "var(--gray-800)", "width": 2.6}]
    for i, r in enumerate(s["rows"][:12]):
        pal = PAL + ["#9b6cf0", "#a1887f", "#78909c", "#d81b60", "#7cb342"]  # 3 은 묶음이 8개를 넘을 수 있어 색을 더 둔다
        series.append({"name": bundle(r["name"]), "values": r["m"], "color": pal[i % len(pal)], "width": 1.8 if i < 3 else 1.4, "kids": kids_of(r)})
    chart = line_block(series, L("chart.external.cap"), peaks=False) if len(series) >= 2 else ""
    pb = period_bars([(L("total"), tot["t"], False)], [("", [(r["name"], r["t"], False) for r in s["rows"]])], "", show_title=False)
    cap = L("ui.if.cap", unit=unit_name(s), engines=L("engines." + F["gl"]))
    return tabwrap(L("ui.if.title." + ("line" if is_line(s) else "purpose")), cap,
                   [("chart", L("ui.tab.volume"), chart), ("rate", L("ui.tab.rate"), pb)])


def intent_table(s):
    """method-v5 · 의도별 묶음 검색량 표 · 이름 앞 화살표로 묶음의 검색어가 펼쳐진다 (대표 검색어 Top 5 블록 대체)."""
    Y = F["years"]

    def mix(r):
        sy = r.get("shareY")
        if not sy:
            return C.fmt_share(r["t"][-1] / s["total"]["t"][-1]) if s["total"]["t"][-1] else ""
        a, b = sy[0], sy[-1]
        d = (b - a) if (a is not None and b is not None) else None
        return (f'{C.fmt_share(a)} → <b>{C.fmt_share(b)}</b>'
                + (f' <span class="{"up" if d > 0.0005 else ("dn" if d < -0.0005 else "flat")}">({C.fmt_pp(d)})</span>' if d is not None else ""))

    def driver(r):
        """method-v5 · 이 목적이 왜 변했나: 4년 사이 검색량이 가장 크게 늘거나 준 검색어 (방향이 묶음과 같은 것 우선)."""
        ms = r.get("members") or []
        if not ms:
            return "—"
        tot = (r["t"][-1] - r["t"][0])
        cand = sorted(ms, key=lambda m: -abs((m["t"][-1] or 0) - (m["t"][0] or 0)))
        same = [m for m in cand if ((m["t"][-1] - m["t"][0]) >= 0) == (tot >= 0)]
        m = (same or cand)[0]
        d = m["t"][-1] - m["t"][0]
        cls = "up" if d > 0 else "dn"
        return (f'<span class="ds-drv"><span class="ds-drv__k">{e(m["kw"])}</span>'
                f'<span class="{cls}">{"▲" if d > 0 else "▼"} {C.fmt_compact(abs(d), F.get("lang", "kr"))}</span></span>')
    cols = [(L("ui.col.driver"), driver)]  # method-v5 · 구성비 열 대신 '왜 변했나'를 보여 준다
    if is_line(s):
        cap = L("ui.it.cap.line")
    else:
        cap = L("ui.it.cap.purpose")
    if s.get("unassigned"):
        cap += L("ui.it.unassigned", n=C.fmt_int(s['unassigned']))
    return (btitle(L("ui.table.byUnit", unit=unit_name(s)), cap, "margin-top:18px")
            + table(s["rows"], extra_cols=cols, total={**s["total"], "name": L("ui.all")}, first=unit_name(s)))


def flow_label(d):
    import ds_aggregate as A
    return A.flow_type(d)


def intent_top(s):
    n = 5
    cards = []
    for r in s["rows"]:
        rows = "".join(f'<tr><td><span class="ds-name">{e(q["kw"])}</span>'
                       + (f'<span class="ds-sub" title="{e(" · ".join(q["merged"]))}">표기 {len(q["merged"]) + 1}개 합산</span>' if q["merged"] else "")
                       + f'</td><td>{C.fmt_int(q["last"])}</td><td>{pct(q["yoy"])}</td></tr>' for q in r.get("top") or [])
        cards.append(f'<div style="min-width:0"><div class="ds-blocktitle" style="margin-top:0">{e(r["name"])}</div>'
                     f'<div class="ds-tablewrap"><table class="ds-table ds-nt-table ds-top-table"><thead><tr><th>검색어</th><th>{e(L("col.last12"))}</th>'
                     f'<th>{e(L("col.yoy"))}</th></tr></thead><tbody>{rows}</tbody></table></div></div>')
    return (f'<div class="ds-blocktitle" style="margin-top:18px">{e(L("top.title", n=n))}</div>'
            f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px 18px">{"".join(cards)}</div>'
            f'<div class="ds-chart-cap">{e(L("top.cap"))}</div>')


def corrections_html():
    items = []
    for c in F["corrections"]:
        items.append(f"<li>{e(corr_text(c))}</li>")
    out = f'<ul class="ds-list">{"".join(items)}</ul>' if items else f'<p class="ds-note">{e(L("corr.none"))}</p>'
    dr = F.get("dropped") or []
    if dr:
        out += (f'<div class="ds-blocktitle" style="margin-top:12px">{e(L("corr.dropped"))}</div><p class="ds-note">'
                + e(" · ".join(f'{d["kw"]}({"finder 미발견" if d["reason"] == "notfound" else "측정값 없음"})' for d in dr)) + "</p>")
    mi = F.get("mirror") or {}
    if mi.get("made"):
        out += (f'<div class="ds-blocktitle" style="margin-top:12px">비교군 이름의 다른 표기</div><p class="ds-note">'
                + e(f'비교 대상도 타겟과 같은 규칙으로 이름 자체의 다른 표기만 더했습니다. finder 결과에 없던 {mi["made"]}개를 검색량으로 확인했고, 검색량이 있는 {mi["kept"]}개를 넣었습니다'
                    + (f' ({" · ".join(mi["keptKw"])})' if mi.get("keptKw") else "") + '.') + "</p>")
    out += (f'<div class="ds-blocktitle" style="margin-top:12px">{e(L("corr.rules"))} · {e(F["rules"])}</div>'
            f'<p class="ds-note">{e(L("corr.rules.text"))}</p>')
    pk = F.get("picks") or {}
    if F.get("method") and pk:
        rows = []
        def nm(xs):
            return [x if isinstance(x, str) else x.get("name") for x in xs or []]
        for sec, lab in (("external", "1 시장 흐름 비교군"), ("synonyms", "1 분석 대상 유사의도"), ("internal", "2 내부")):
            p = pk.get(sec) or {}
            names = nm(p.get("pick")) + [f"{x}(analyst)" for x in nm(p.get("analyst"))] + [f"{x}(토픽)" for x in nm(p.get("topics"))]
            if names:
                rows.append(f'<li><b>{e(lab)} 선택</b> · {e(" · ".join(names))}</li>')
            for k, v in (p.get("skip") or {}).items():
                rows.append(f'<li>{e(lab)} 제외 · {e(k)} — {e(v)}</li>')
        for x in (pk.get("external") or {}).get("pick") or []:  # method-v5.2 · M5a 비교 대상별 유사의도
            sy = x.get("synonyms") if isinstance(x, dict) else None
            if not sy:
                continue
            got = list(sy.get("pick") or []) + [f"{w}(analyst)" for w in sy.get("analyst") or []]
            txt = " · ".join(got) if got else (sy.get("none") or "다른 표기 없음")
            sk = " / ".join(f"{k} — {v}" for k, v in (sy.get("skip") or {}).items())
            rows.append(f'<li>1 비교 대상 유사의도 · <b>{e(x["name"])}</b> · {e(txt)}' + (f' <span class="ds-sub">제외: {e(sk)}</span>' if sk else "") + "</li>")
        ver = F.get("verified") or []
        if ver:
            rows.append(f'<li><b>1 분석 대상 유사의도 · keyword_info 로 검증해 넣은 검색어</b> · {e(" · ".join(ver))}</li>')
        out += (f'<div class="ds-blocktitle" style="margin-top:12px">키워드셋 분류 근거 · {e(F["method"])}</div>'
                f'<p class="ds-note">분석 대상은 시드 + 고른 유사의도로 규칙(M3)에 따라 코드가 묶었고, 시장 흐름 비교군과 내부 동향은 아래 선택을 같은 규칙(M6·M9)으로 묶었습니다. 상위어: {e(F.get("upper") or "—")}</p>'
                f'<ul class="ds-list">{"".join(rows)}</ul>')
    return out


def corr_text(c):
    import ds_aggregate as A  # 같은 문장을 facts.md 와 공유한다
    return A.corr_text(c)


SECS = {"external": sec_external, "internal": sec_internal}


def sec_title(sid):
    if sid == "internal":
        u = (F["sections"].get("internal") or {}).get("unit")
        if u == "방법":  # i18n-ok · 계약값
            return L("sec.internal.category")  # method-v5 · 섹션명 고정
        return L(f"sec.internal.{F['mode']}")
    return L(f"sec.{sid}")


def sec_q(sid):
    u = (F["sections"].get("internal") or {}).get("unit")
    if sid == "internal" and u == "방법":  # i18n-ok · 계약값
        return L("ui.q.internal.method")
    return L(f"q.{sid}.{F['mode']}")


# ───────────────────────── 페이지 ─────────────────────────

def kpis():
    out = []
    for k in F["kpis"]:
        v = k["v"]
        if k["fmt"] == "pct":
            val, cls = C.fmt_pct(v), ("up" if (v or 0) > 0 else ("dn" if (v or 0) < 0 else ""))
        elif k["fmt"] == "pp":
            val, cls = C.fmt_pp(v), ("up" if (v or 0) > 0 else ("dn" if (v or 0) < 0 else ""))
        else:
            val, cls = share_int(v), ""
        sub = k["sub"]
        if k["id"] == "external":
            x = F["sections"]["external"]
            sub = L("ui.kpi.external.sub", verdict=L("verdict." + x["verdict"]), unit=L("ui.unit." + ("brand" if F["mode"] == "entity" else "category")),
                    base=C.fmt_pct(x.get("baseline")))
        elif k["id"] == "seed":
            r = F["sections"]["external"]["seedRow"]
            sub = L("ui.kpi.seed.sub", avg=C.fmt_int(r.get("avg")), yoy=C.fmt_pct(r.get("yoy")))
        elif k["id"] == "internal" and F["sections"]["internal"]["rows"]:
            r = F["sections"]["internal"]["rows"][0]
            sub = L("ui.kpi.internal.sub", name=bundle(r["name"]), gt=C.fmt_pct(r.get("gt")))
        k = {**k, "sub": sub}
        lab = L("kpi.internal.line") if (k["id"] == "internal" and is_line(F["sections"]["internal"])) else L("kpi." + k["id"])
        out.append(f'<div class="ds-kpi"><div class="ds-kpi__l">{e(lab)}</div>'
                   f'<div class="ds-kpi__v {cls}">{e(val)}</div><div class="ds-kpi__s">{e(k["sub"])}</div></div>')
    return f'<div class="ds-kpis ds-kpis--top">{"".join(out)}</div>'


def mode_reason():
    """모드 판정 근거 문장 · kr 은 분류 코드가 쓴 문장 그대로, jp · us 는 숫자 근거(modeSignals)로 그 언어 문장을 만든다."""
    sig = F.get("modeSignals") or {}
    if (F.get("lang") or "kr") == "kr" or not sig:
        return F.get("modeReason") or ""
    n = sig.get("intentCount", 0)
    if F["mode"] == "entity" and sig.get("seedBrandShare") is not None:
        return L("ui.modeReason.entity", n=C.fmt_int(n), brand=sig.get("brand") or F["seed"], share=C.fmt_share(sig.get("seedBrandShare")))
    return L("ui.modeReason.category", n=C.fmt_int(n), k=sig.get("brandsSeen", 0),
             top=L("verdict.tpl.peers.sep").join((sig.get("brandsTop") or [])[:3]), mod=C.fmt_share(sig.get("modifierShare")))


def purpose(variant):
    """method-v5 · lm-queryfinder-report 와 같은 커버 구성: '배경과 목적' 고정 문구 + 데이터 기반 개요(overview 1~2문장).
    모드 판정·시드 좁히기 근거는 칩 + (i) 툴팁 (A4 는 문장 그대로)."""
    box = "mr-summary-box mr-summary-box--dash" if variant == "dash" else "mr-summary-box"
    tc = "mr-summary-text" if variant == "dash" else "mr-summary-text--sm"
    ov = N.get("overview")
    body = L("purpose.body", seed=F["seed"], market=L("market." + F["gl"]))
    head = (f'<div class="{box}"><div class="mr-summary-box__title">{e(L("purpose.title"))}</div>'
            f'<p class="{tc}">{e(body)}</p>' + (f'<p class="{tc} mr-overview">{rich(ov)}</p>' if ov else ""))
    if variant != "dash":
        return (head + f'<p class="{tc} ds-modebasis"><b>{e(L("mode.basis"))}</b> · {e(L("mode." + F["mode"]))} — {e(mode_reason())}</p>'
                + scope_line(tc) + '</div>')
    chips = [f'<span class="ds-chip">{e(L("mode." + F["mode"]))}{info(L("mode.basis") + " · " + mode_reason())}</span>']
    sc = F.get("scope") or {}
    if sc.get("from"):
        how = how_label(sc)
        txt = L("scope.text." + ("brand" if sc.get("type") == "brand" else "domain"), src=sc["from"], seed=F["seed"], how=how,
                n=len(sc.get("candidates") or sc.get("siblings") or []))
        chips.append(f'<span class="ds-chip">{e(sc["from"])} → {e(F["seed"])}{info(L("scope.basis") + " · " + txt)}</span>')
    return head + '</div>'  # method-v5 · 분석 방식·키워드 좁히기 칩 없음 (배경과 목적 + 요약만)


def act_cards(items, kind, dot=True):
    if not items:
        return f'<div class="rpt-act-empty">{e(L("actions.empty"))}</div>'
    d = f'<span class="action-dot action-dot--{kind}"></span>' if dot else ""
    return "".join(f'<div class="rpt-act-card rpt-act-card--{kind}"><div class="rpt-act-card__title">{d}'
                   f'<span>{rich(it.get("title"))}</span></div><div class="rpt-act-card__body">{rich(it.get("body"))}</div></div>' for it in items)


def link_groups(html_text, sid):
    """method-v5 · 2 내부 동향 인사이트 안의 검색 목적 이름·검색어를 누르면 아래 표의 그 목적으로 이동 (펼치고 강조)."""
    if sid != "internal":
        return html_text
    rows = F["sections"]["internal"]["rows"]
    pairs = ([(r["name"], r["name"]) for r in rows] + [(bundle(r["name"]), r["name"]) for r in rows if bundle(r["name"]) != r["name"]]
             + [(m["kw"], r["name"]) for r in rows for m in (r.get("members") or [])])
    pairs.sort(key=lambda p: -len(p[0]))
    out, used = html_text, set()
    for word, grp in pairs:
        if len(word) < 2 or word in used:
            continue
        ew = e(word)
        i = out.find(ew)
        if i < 0 or out.rfind("<a ", 0, i) > out.rfind("</a>", 0, i):
            continue
        out = out[:i] + f'<a class="ds-glink" href="#" data-g="{e(grp)}">{ew}</a>' + out[i + len(ew):]
        used.add(word)
    return out


def ins_cards(ins, sid):
    """method-v5 · 인사이트 카드 = [검색 목적 + 그 목적의 변화(코드)] → 결론 제목 → 목적 안 검색어를 보니 이렇게 변했다(본문). 점 표식 없음."""
    rows = {r["name"]: r for r in (F["sections"]["internal"]["rows"] if sid == "internal" else [])}
    out = []
    for it in ins:
        head = ""
        g = it.get("group") or ""
        r = rows.get(g) or next((x for x in rows.values() if bundle(x["name"]) == g), None)  # 번역된 묶음 이름으로 와도 찾는다
        if r:
            gt = r.get("gt")
            rk = r.get("rankY") or []
            chg = L("ui.ins.new", since=r["since"]) if "new" in (r.get("tags") or []) and r.get("since") else (L("ui.ins.4y", gt=C.fmt_pct(gt)) if gt is not None else "")
            cls = "up" if (gt or 0) > 0 or "new" in (r.get("tags") or []) else "dn"
            rk_txt = L("ui.ins.rank", a=rk[0], b=rk[-1]) if len(rk) > 1 else ""
            head = (f'<div class="ds-insg"><a class="ds-glink ds-insg__name" href="#" data-g="{e(r["name"])}">{e(bundle(r["name"]))}</a>'
                    f'<span class="ds-insg__chg {cls}">{e(chg)}</span>' + (f'<span class="ds-insg__rk">{e(rk_txt)}</span>' if rk_txt else "") + '</div>')
        out.append(f'<div class="rpt-act-card rpt-act-card--insight">{head}<div class="rpt-act-card__title"><span>{rich(it.get("title"))}</span></div>'
                   f'<div class="rpt-act-card__body">{link_groups(rich(it.get("body")), sid)}</div></div>')
    return "".join(out)


def sec_insights(sid):
    """method-v5 · 섹션 맨 위 인사이트 카드 (점 없음)."""
    ins = ((N.get("sections") or {}).get(sid) or {}).get("insights") or []
    if not ins:
        return ""
    # method-v5 · '인사이트' 제목·(i) 없음 — 카드 제목 자체가 결론이다
    return f'<div class="rpt-act-list ds-ins-top">{ins_cards(ins, sid)}</div>'


def sec_actions(sid):
    """섹션 끝에 실행 제안 · 우선순위 순서대로 (점 표식 없음)."""
    acts = ((N.get("sections") or {}).get(sid) or {}).get("actions") or []
    if not acts:
        return ""
    return btitle("실행 제안", "위에서부터 우선순위 순", "margin-top:22px") + f'<div class="rpt-act-list">{act_cards(acts, "act", dot=False)}</div>'


def actions_parts():
    """method-v5 · lm-queryfinder-report 의 정리 구성: 종합 시사점 → 핵심 인사이트(3) → 지금 바로 써볼 수 있는 것 → 앞으로 주목할 기회.
    탭으로 나누지 않고 2 내부 동향 다음에 이어 붙인다."""
    A = N.get("actions") or {}
    out = []
    if A.get("synthesis"):
        out.append((L("actions.synthesis"), None, f'<p class="mr-summary-text">{rich(A["synthesis"])}</p>'))
    for key, kind in (("insights", "insight"), ("now", "now"), ("future", "future")):
        items = A.get(key) or []
        if key == "insights" and not items:
            continue
        out.append((L("actions." + key), len(items), f'<div class="rpt-act-list">{act_cards(items, kind)}</div>'))
    return out


def actions_dash():
    html_ = []
    for title, n, body in actions_parts():
        badge = f'<span class="dash-card__badge">{e(L("actions.count", n=n))}</span>' if n is not None else ""
        html_.append(f'<div class="dash-card"><div class="dash-card__head"><span class="dash-card__title">{e(title)}</span>{badge}</div>'
                     f'<div class="dash-card__body">{body}</div></div>')
    return "".join(html_)


def actions_a4():
    return "".join(f'<div class="persona-subhead">{e(t)}</div>{b}' for t, _n, b in actions_parts())


def scope_line(tc):
    sc = F.get("scope") or {}
    if not sc.get("from"):
        return ""
    how = how_label(sc)
    return (f'<p class="{tc} ds-modebasis"><b>{e(L("scope.basis"))}</b> · {e(L("scope.text." + ("brand" if sc.get("type") == "brand" else "domain"), src=sc["from"], seed=F["seed"], how=how, n=len(sc.get("candidates") or sc.get("siblings") or [])))}</p>')


def meta():
    return L("cover.meta", date=F["date"], to=F["months"][-1], kw=C.fmt_int(F["counts"]["keywords"]), **{"from": F["months"][0]})


def synthesis():
    syn = N.get("synthesis") or {}
    parts = []
    if syn.get("summary"):
        parts.append(("syn.summary", f'<p class="mr-summary-text">{rich(syn["summary"])}</p>'))
    for key in ("now", "future"):
        cards = "".join(f'<div class="rpt-act-card rpt-act-card--{key}"><div class="rpt-act-card__title"><span class="action-dot action-dot--{key}"></span>'
                        f'{rich(x.get("title"))}</div><div class="rpt-act-card__body">{rich(x.get("body"))}</div></div>' for x in syn.get(key) or [])
        if cards:
            parts.append(("syn." + key, f'<div class="rpt-act-list">{cards}</div>'))
    return parts


def card(title, body, num=None, q=""):
    n = f'<span class="ds-sec-num">{num:02d}</span>' if num else ""
    return (f'<div class="dash-card"><div class="dash-card__head"><span class="dash-card__title">{n}{e(title)}{info(q)}</span></div>'
            + f'<div class="dash-card__body">{body}</div></div>')


def build_dash():
    eyebrow = f'{L("report.eyebrow")} · {L("country." + F["gl"])} · {L("mode." + F["mode"])}'
    cover = (f'<div class="dash-cover-block"><div class="dash-card"><div class="dash-cover-gradient">'
             f'<div class="dash-cover-eyebrow">{e(eyebrow)}</div><div class="dash-cover-title">{e(L("report.title"))}</div>'
             f'<div class="dash-cover-category">{e(F["seed"])}</div><div class="dash-cover-meta">{e(meta())}</div></div>'
             f'{purpose("dash")}</div></div>')
    # method-v5 · 종합 탭을 없앴다 — 수요 진단 한 화면만 (탭 내비 없음)
    secs = "".join(card(sec_title(sid), sec_insights(sid) + SECS[sid](), i + 1, sec_q(sid)) for i, sid in enumerate(F["sectionOrder"]))
    p0 = (f'<div class="dash-tab-panel active" data-panel="0">{card(L("kpi.title"), kpis())}{secs}'
          f'</div>')  # method-v5 · 정리 카드·데이터 참고 사항 카드 없음 (인사이트는 섹션 안에)
    return cover + p0


def a4_page(num, inner):
    return (f'<div class="rpt-page" id="page-{num}"><div class="page-hd"><span class="page-hd__brand">ListeningMind.AI</span>'
            f'<span class="page-hd__report">{e(L("report.title"))} · {e(F["seed"])}</span><span class="page-hd__num">{num:02d}</span></div>'
            f'<div class="page-body">{inner}</div></div>')


def sec_hd(eyebrow, title, desc=""):
    return (f'<div class="sec-hd"><div class="sec-eyebrow"><span class="sec-eyebrow__line"></span><span class="sec-eyebrow__text">{e(eyebrow)}</span></div>'
            f'<div class="sec-title">{e(title)}</div>' + (f'<div class="sec-desc">{e(desc)}</div>' if desc else "") + "</div>")


def build_a4():
    cover = (f'<div class="rpt-page rpt-page--cover" id="page-0"><div class="cover-body"><div>'
             f'<div class="cover-lm">ListeningMind.AI</div><div class="cover-type-label">{e(L("mode." + F["mode"]))} · {e(L("country." + F["gl"]))}</div>'
             f'<div class="cover-title">{e(L("report.title"))}</div><div class="cover-category">{e(F["seed"])}</div>'
             f'<div class="cover-meta"><span>{e(meta())}</span></div></div></div></div>')
    pages = [cover]
    pages.append(a4_page(1, sec_hd("00", L("kpi.title")) + purpose("a4") + kpis()))
    for i, sid in enumerate(F["sectionOrder"]):
        _UID[0] += 1000  # A4 복제본의 펼침 id 가 대시보드와 겹치지 않게
        pages.append(a4_page(i + 2, sec_hd(f"{i + 1:02d}", sec_title(sid), sec_q(sid)) + sec_insights(sid) + SECS[sid]()))
    return "".join(pages)


SCRIPT = r"""
(function(){
  var tabs=document.querySelectorAll('.dash-tab'), panels=document.querySelectorAll('.dash-tab-panel');
  tabs.forEach(function(t){ t.addEventListener('click', function(){
    var i=t.getAttribute('data-panel');
    tabs.forEach(function(x){ x.classList.toggle('active', x.getAttribute('data-panel')===i); });
    panels.forEach(function(p){ p.classList.toggle('active', p.getAttribute('data-panel')===i); });
  });});
  var vb=document.querySelectorAll('.mini-toolbar__view button');
  vb.forEach(function(b){ b.addEventListener('click', function(){
    var m=b.getAttribute('data-view');
    document.body.classList.toggle('view-mode-dash', m==='dash');
    document.body.classList.toggle('view-mode-a4', m==='a4');
    vb.forEach(function(x){ x.classList.toggle('active', x===b); });
  });});
})();
"""


def render(facts, narr):
    global F, N, LB
    F, N = facts, narr
    LB = json.loads((PKG / "labels" / f"demand-shift.{facts['lang']}.json").read_text(encoding="utf-8"))
    lang = facts.get("lang") or "kr"
    css = inline_styles(PKG / "styles", "demand-shift", SKILL_STYLES)
    if LOCALE_FONT_OVERRIDE.get(lang):
        css += "\n" + LOCALE_FONT_OVERRIDE[lang]
    tpl = (PKG / "templates" / "demand-shift.html").read_text(encoding="utf-8")
    # zip 안에서 render/*.py 만 _shared/render/ 로 가므로, html 조각은 templates/ 에 둔다
    assets = (PKG / "templates" / "ds_assets.css.html").read_text(encoding="utf-8") + (PKG / "templates" / "ds_assets.js.html").read_text(encoding="utf-8")
    blocks = {"{{LANG}}": HTML_LANG.get(lang, "en"), "{{FONT_HREF}}": FONT_HREF.get(lang, FONT_HREF["us"]), "{{TITLE}}": e(f'{L("report.title")} · {facts["seed"]}'),
              "{{INLINED_CSS}}": css, "{{TOOLBAR_DASH}}": e(L("toolbar.dash")),
              "{{DASH}}": build_dash(), "{{A4}}": build_a4(), "{{SCRIPT}}": SCRIPT}
    pat = re.compile("|".join(re.escape(k) for k in blocks))
    out = pat.sub(lambda m: blocks[m.group(0)], tpl)
    out = out.replace("</head>", f'<meta name="search-demand-report-version" content="{facts["version"]}">\n</head>', 1)
    months = f'<script id="ds-months" type="application/json">{json.dumps({"months": facts["months"], "years": facts["years"]})}</script>'
    # 차트 스크립트(ds_assets.js.html)의 화면 문구 · js.* 라벨만 넘긴다
    jsl = {k[3:]: v for k, v in LB.items() if k.startswith("js.")}
    jsl["lang"] = lang
    months += f'<script id="ds-l10n" type="application/json">{html.escape(json.dumps(jsl, ensure_ascii=False), quote=False)}</script>'
    return out.replace("</body>", months + assets + "\n</body>", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True)
    ap.add_argument("--narrative", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    facts = C.load_json(a.facts)
    if (facts.get("lang") or "kr") not in REPORT_LANGS:
        sys.exit(f"lang 은 {', '.join(REPORT_LANGS)} 중 하나 · 받은 값 {facts.get('lang')!r}")  # i18n-ok · 콘솔
    Path(a.out).write_text(render(facts, C.load_json(a.narrative)), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
