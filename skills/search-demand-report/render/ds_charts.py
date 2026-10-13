"""demand-shift 차트 · 인라인 SVG (JS·CDN 없음 → A4·오프라인에서 그대로 보인다)."""

import html
import math

import ds_common as C

PALETTE = ["var(--ds-line-1)", "var(--ds-line-2)", "var(--ds-line-3)", "var(--ds-line-4)", "var(--ds-line-5)",
           "var(--success-main)", "var(--warning-main)"]


def _nice_max(v):
    if v <= 0:
        return 1
    import math
    e = 10 ** int(math.floor(math.log10(v)))
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * e:
            return m * e
    return 10 * e


VAR_HEX = {"var(--ds-seed)": "#b775e8", "var(--gray-800)": "#333333"}


def kid_shades(col, n=10):
    """method-v5.4.5 · 묶음 안 검색어 선 색 = 묶음 선 색에 흰색을 조금씩 더 섞는다.
    1위 = 흰색 10% → 마지막 = 흰색 55% (등간격). 옅어져 안 보이지 않게 상한을 55% 로 둔다 — 선끼리 비교가 돼야 한다 (리뷰).
    CSS 변수 색은 아는 hex 로 바꾸고, 모르면 회색."""
    h = VAR_HEX.get(col, col)
    if not (isinstance(h, str) and h.startswith("#") and len(h) == 7):
        h = "#777777"
    rgb = [int(h[i:i + 2], 16) for i in (1, 3, 5)]
    out = []
    for k in range(n):
        w = 0.10 + 0.45 * k / (n - 1) if n > 1 else 0.10
        out.append("#" + "".join(f"{round(c + (255 - c) * w):02x}" for c in rgb))
    return out


def legend(items):
    """items: [(label, color, dashed)] 또는 (label, color, dashed, group, member) — method-v5: member 는 표에서 묶음을 누를 때만 보인다."""
    out = []
    for it in items:
        lab, col, dashed = it[0], it[1], it[2]
        g = it[3] if len(it) > 3 else None
        mem = it[4] if len(it) > 4 else False
        style = f"background:{col}" if not dashed else f"background:repeating-linear-gradient(90deg,{col} 0 4px,transparent 4px 7px)"
        attrs = (f' data-g="{html.escape(g, quote=True)}"' if g else "") + (" data-mem=\"1\"" if mem else "")
        # method-v5 · 체크 칩: 누르면 그 계열만 선택(나머지 흐리게 + 최고·최저·최신 표시) · × 는 숨기기
        out.append(f'<span class="ds-legend__i{" ds-mem" if mem else ""}"{attrs} data-name="{html.escape(lab, quote=True)}" style="--c:{col}">'
                   f'<span class="ds-legend__ck"></span>'
                   f'<span class="ds-legend__t">{html.escape(lab)}</span>'
                   f'<span class="ds-legend__x ds-legend__eye" role="button" tabindex="0"><svg class="ds-eye-on" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M1.5 12S5.5 4.5 12 4.5 22.5 12 22.5 12 18.5 19.5 12 19.5 1.5 12 1.5 12Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/></svg><svg class="ds-eye-off" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path d="M1.5 12S5.5 4.5 12 4.5 22.5 12 22.5 12 18.5 19.5 12 19.5 1.5 12 1.5 12Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="12" r="3.2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M3 3l18 18" stroke="currentColor" stroke-width="2"/></svg></span></span>')  # v5.5.3 · × (숨기기) 없음 — 칩 클릭 = 그 묶음만 보기
    return f'<div class="ds-legend">{"".join(out)}</div>'


def line_chart(series, months, years, lang, height=230, shade_last=0, highlight_years=True, peaks=True):
    """series: [{name, values, color, dash(bool), width}] · months: ['2022-09', ...]
    peaks=True 면 첫 계열의 12개월 구간별 정점을 점과 값으로 표시한다."""
    W, H = 760, height
    L, R, T, B = 52, 12, 10, 26
    n = len(months)
    vmax = _nice_max(max((max(s["values"]) if s["values"] else 0) for s in series) * 1.05)
    x = lambda i: L + (W - L - R) * (i / max(n - 1, 1))
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet">']
    ny = len(years)
    if highlight_years:
        for k in range(ny):
            if k % 2 == 1:
                x0 = x(k * 12) - (x(1) - x(0)) / 2
                x1 = x(min(k * 12 + 11, n - 1)) + (x(1) - x(0)) / 2
                parts.append(f'<rect class="yrband" x="{x0:.1f}" y="{T}" width="{x1 - x0:.1f}" height="{H - T - B}"/>')
    if shade_last:
        x0 = x(n - shade_last) - (x(1) - x(0)) / 2
        parts.append(f'<rect class="hl" x="{x0:.1f}" y="{T}" width="{W - R - x0:.1f}" height="{H - T - B}"/>')
    for k in range(5):
        v = vmax * k / 4
        yy = y(v)
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        parts.append(f'<text class="tick" x="{L - 6}" y="{yy + 4:.1f}" text-anchor="end">{C.fmt_compact(v, lang)}</text>')
    for k, lab in enumerate(years):
        cx = (x(k * 12) + x(min(k * 12 + 11, n - 1))) / 2
        parts.append(f'<text class="tick" x="{cx:.1f}" y="{H - 8}" text-anchor="middle">{html.escape(lab)}</text>')
    parts.append(f'<line class="ax" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>')
    for s in series:
        vals = s["values"]
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        dash = ' stroke-dasharray="5 4"' if s.get("dash") else ""
        ga = (f' data-g="{html.escape(s["group"], quote=True)}"' if s.get("group") else "") + (' class="ds-mem" data-mem="1"' if s.get("member") else "")
        parts.append(f'<polyline fill="none" stroke="{s["color"]}" stroke-width="{s.get("width", 2)}" '
                     f'stroke-linejoin="round" stroke-linecap="round"{dash}{ga} points="{pts}"/>')
    # method-v5.4 · 묶음 안 검색어 선 (칩을 눌러 그 묶음을 고르면 상위 10개가 함께 보인다 · 이름은 마우스를 올리면 툴팁으로)
    #   lines/legend 짝 맞춤(JS)을 깨지 않도록 class="ds-kwl" 로 따로 그리고 기본은 숨긴다. data-v = 월별 값 (축 재조정용)
    for si, s in enumerate(series):
        KC = kid_shades(s["color"], len((s.get("kids") or [])[:10]))  # v5.4.5 · 흰색 10% → 55% 섞기
        for j, kd in enumerate((s.get("kids") or [])[:10]):
            kv = kd["values"]
            kp = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(kv))
            parts.append(f'<polyline class="ds-kwl" data-o="{si}" data-name="{html.escape(kd["name"], quote=True)}" data-v="{",".join(str(int(v or 0)) for v in kv)}" '
                         f'fill="none" stroke="{KC[j % len(KC)]}" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" style="display:none" points="{kp}"/>')
    if peaks and series:
        v0 = series[0]["values"]
        for k in range(ny):
            seg = v0[k * 12:(k + 1) * 12]
            if not seg or max(seg) <= 0:
                continue
            i = k * 12 + seg.index(max(seg))
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(v0[i]):.1f}" r="4" fill="{series[0]["color"]}" stroke="#fff" stroke-width="1.5"/>')
            parts.append(f'<text class="tick" x="{x(i):.1f}" y="{y(v0[i]) - 8:.1f}" text-anchor="middle">{html.escape(months[i][2:7].replace("-", "."))} · {C.fmt_compact(v0[i], lang)}</text>')
    # 월별 네이티브 툴팁 (마우스오버)
    step = (W - L - R) / max(n - 1, 1)
    for i, m in enumerate(months):
        tip = m + " · " + " / ".join(f'{s["name"]} {C.fmt_int(s["values"][i])}' for s in series if i < len(s["values"]))
        parts.append(f'<rect x="{x(i) - step / 2:.1f}" y="{T}" width="{step:.1f}" height="{H - T - B}" fill="transparent">'
                     f'<title>{html.escape(tip)}</title></rect>')
    parts.append("</svg>")
    return '<div class="ds-chart">' + "".join(parts) + "</div>"


def sparkline(vals, w=96, h=24, color="var(--gray-600)", vmax=None, since=None):
    """since = 처음 등장한 달의 index (신규) → 그 지점에 세로선 + 점 (method-v5)."""
    if not vals or max(vals) <= 0:
        return f'<svg class="ds-spark" width="{w}" height="{h}"></svg>'
    vmax = vmax or max(vals)
    n = len(vals)
    X = lambda i: (w - 2) * i / max(n - 1, 1) + 1
    Yv = lambda v: h - 2 - (h - 4) * v / vmax
    pts = " ".join(f"{X(i):.1f},{Yv(v):.1f}" for i, v in enumerate(vals))
    mk = ""
    if since is not None and 0 <= since < n:
        mk = (f'<line x1="{X(since):.1f}" x2="{X(since):.1f}" y1="1" y2="{h - 1}" stroke="var(--lm-purple-main)" stroke-width="1" stroke-dasharray="2 2"/>'
              f'<circle cx="{X(since):.1f}" cy="{Yv(vals[since]):.1f}" r="2.4" fill="var(--lm-purple-main)"/>')
    return (f'<svg class="ds-spark" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
            f'<polyline fill="none" stroke="{color}" stroke-width="1.3" points="{pts}"/>{mk}</svg>')


def pair_chart(a_name, a_vals, b_name, b_vals, years, w=760, h=110):
    """이동 가설 시각화 · 출발(A)과 도착(B)의 48개월을 각자 최댓값으로 정규화해 겹쳐 그린다 (모양 비교용)."""
    def norm(vs):
        m = max(vs) if vs and max(vs) > 0 else 1
        return [v / m for v in vs]
    A, Bv = norm(a_vals), norm(b_vals)
    n = max(len(A), len(Bv), 2)
    x = lambda i: 4 + (w - 8) * i / (n - 1)
    y = lambda v: h - 16 - (h - 24) * v
    parts = [f'<svg class="ds-pairchart" viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">']
    for k in range(1, len(years)):
        xx = x(k * 12)
        parts.append(f'<line x1="{xx:.1f}" x2="{xx:.1f}" y1="6" y2="{h - 16}" stroke="var(--gray-200)" stroke-dasharray="2 3"/>')
    for vals, col, wd in ((A, "var(--ds-seed)", 2), (Bv, "var(--brand-coral-main)", 2)):
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals))
        parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="{wd}" stroke-linejoin="round" points="{pts}"/>')
    for k, lab in enumerate(years):
        parts.append(f'<text class="tick" x="{(x(k * 12) + x(min(k * 12 + 11, n - 1))) / 2:.1f}" y="{h - 4}" text-anchor="middle">{html.escape(lab)}</text>')
    parts.append("</svg>")
    return "".join(parts)


def monthly_bars(items, lang, height=150):
    """items: [{month, v, prev, r}] · 막대=올해, 점선=전년 같은 달, 위 라벨=전년 대비."""
    W, H = 760, height
    L, R, T, B = 52, 12, 22, 22
    n = len(items)
    vmax = _nice_max(max(max(it["v"], it["prev"]) for it in items) * 1.05) if items else 1
    bw = (W - L - R) / max(n, 1)
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img">']
    for k in range(4):
        v = vmax * k / 3
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        parts.append(f'<text class="tick" x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{C.fmt_compact(v, lang)}</text>')
    for i, it in enumerate(items):
        x0 = L + i * bw + bw * 0.18
        w = bw * 0.64
        parts.append(f'<rect x="{x0:.1f}" y="{y(it["v"]):.1f}" width="{w:.1f}" height="{H - B - y(it["v"]):.1f}" rx="2" fill="var(--gray-700)">'
                     f'<title>{it["month"]} {C.fmt_int(it["v"])} (전년 {C.fmt_int(it["prev"])})</title></rect>')
        parts.append(f'<line x1="{x0 - 2:.1f}" x2="{x0 + w + 2:.1f}" y1="{y(it["prev"]):.1f}" y2="{y(it["prev"]):.1f}" '
                     f'stroke="var(--brand-magenta-main)" stroke-width="2" stroke-dasharray="3 2"/>')
        r = it["r"]
        cls = "up" if (r or 0) > 0 else "dn"
        col = "var(--ds-up)" if cls == "up" else "var(--ds-down)"
        parts.append(f'<text class="tick" x="{x0 + w / 2:.1f}" y="{y(max(it["v"], it["prev"])) - 5:.1f}" text-anchor="middle" '
                     f'style="fill:{col};font-weight:700;font-size:10px">{C.fmt_pct(r, digits=0)}</text>')
        parts.append(f'<text class="tick" x="{x0 + w / 2:.1f}" y="{H - 7}" text-anchor="middle">{it["month"][2:4]}.{it["month"][5:]}</text>')
    parts.append("</svg>")
    return '<div class="ds-chart">' + "".join(parts) + "</div>"


def year_overlay(vals, months, years, lang, height=200):
    """같은 달끼리 비교 · x = 구간 내 월(1~12), 구간마다 선 하나. 최근 구간은 굵게. '전년 같은 달 대비' 막대를 대신한다."""
    W, H = 760, height
    L, R, T, B = 52, 16, 12, 26
    ny = len(years)
    vmax = _nice_max(max(vals) * 1.05) if vals and max(vals) > 0 else 1
    x = lambda i: L + (W - L - R) * (i / 11)
    y = lambda v: T + (H - T - B) * (1 - v / vmax)
    cols = ["var(--gray-300)", "var(--gray-400)", "var(--gray-600)", "var(--ds-line-1)"]
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet">']
    for k in range(5):
        v = vmax * k / 4
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>')
        parts.append(f'<text class="tick" x="{L - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{C.fmt_compact(v, lang)}</text>')
    for i in range(12):
        m = months[i][5:7] if i < len(months) else str(i + 1)
        parts.append(f'<text class="tick" x="{x(i):.1f}" y="{H - 8}" text-anchor="middle">{int(m)}월</text>')
    parts.append(f'<line class="ax" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>')
    for k in range(ny):
        seg = vals[k * 12:(k + 1) * 12]
        if not seg:
            continue
        col = cols[min(k, ny - 1) - (ny - 4) if ny >= 4 else k] if ny >= 4 else cols[k + (4 - ny)]
        last = k == ny - 1
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(seg))
        parts.append(f'<polyline fill="none" stroke="{col}" stroke-width="{2.6 if last else 1.6}" stroke-linejoin="round" points="{pts}"/>')
    parts.append("</svg>")
    leg = "".join(f'<span class="ds-legend__i"><span class="ds-legend__sw" style="background:{cols[k + (4 - ny)] if ny <= 4 else cols[-1]}"></span>{html.escape(years[k])}</span>' for k in range(ny))
    return f'<div class="ds-legend">{leg}</div><div class="ds-chart">' + "".join(parts) + "</div>"


def multi_line_log(series, months, years, lang, ref=None, height=300):
    """여러 계열을 로그 축에 겹쳐 그린다(한 칸 = 10배). ref 는 기준선(시드·헤드) — 흰/검은 실선.
    각 계열은 정점에 이름을 붙인다. series: [{name, values, color}]"""
    W, H = 760, height
    L, R, T, B = 60, 96, 14, 26
    allv = [v for s in series for v in s["values"] if v > 0] + ([v for v in ref["values"] if v > 0] if ref else [])
    if not allv:
        return ""
    lo = 10 ** math.floor(math.log10(max(min(allv), 1)))
    hi = 10 ** math.ceil(math.log10(max(allv)))
    if hi <= lo:
        hi = lo * 10
    n = len(months)
    x = lambda i: L + (W - L - R) * (i / max(n - 1, 1))
    y = lambda v: T + (H - T - B) * (1 - (math.log10(max(v, lo)) - math.log10(lo)) / (math.log10(hi) - math.log10(lo)))
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet">']
    p = lo
    while p <= hi:
        parts.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(p):.1f}" y2="{y(p):.1f}"/>')
        parts.append(f'<text class="tick" x="{L - 6}" y="{y(p) + 4:.1f}" text-anchor="end">{C.fmt_compact(p, lang)}</text>')
        p *= 10
    for k, lab in enumerate(years):
        cx = (x(k * 12) + x(min(k * 12 + 11, n - 1))) / 2
        parts.append(f'<text class="tick" x="{cx:.1f}" y="{H - 8}" text-anchor="middle">{html.escape(lab)}</text>')
        if k:
            parts.append(f'<line x1="{x(k * 12):.1f}" x2="{x(k * 12):.1f}" y1="{T}" y2="{H - B}" stroke="var(--gray-200)" stroke-dasharray="2 3"/>')
    parts.append(f'<line class="ax" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/>')
    def poly(vals, col, wd, dash=""):
        pts = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals) if v > 0)
        return f'<polyline fill="none" stroke="{col}" stroke-width="{wd}" stroke-linejoin="round"{dash} points="{pts}"/>'
    labels = []
    for s in series:
        vals = s["values"]
        parts.append(poly(vals, s["color"], 1.8))
        if any(v > 0 for v in vals):
            i = max(range(len(vals)), key=lambda j: vals[j])
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(vals[i]):.1f}" r="3" fill="{s["color"]}"/>')
            labels.append([y(vals[-1]) if vals[-1] > 0 else y(vals[i]), s["name"], s["color"], 600])
    if ref:
        parts.append(poly(ref["values"], "var(--gray-900)", 2.6))
        labels.append([y(ref["values"][-1]), ref["name"], "var(--gray-900)", 700])
    # 오른쪽 끝 이름표 · 겹치지 않게 12px 간격으로 밀어낸다
    labels.sort(key=lambda l: l[0])
    for j in range(1, len(labels)):
        if labels[j][0] - labels[j - 1][0] < 12:
            labels[j][0] = labels[j - 1][0] + 12
    for yy, name, col, wt in labels:
        parts.append(f'<text class="tick" x="{W - R + 4:.1f}" y="{yy + 4:.1f}" text-anchor="start" style="fill:{col};font-weight:{wt}">{html.escape(name)}</text>')
    parts.append("</svg>")
    return '<div class="ds-chart">' + "".join(parts) + "</div>"


def histogram(bins, median, seed, height=170):
    """bins: [(lowPct(int, 10단위), count)]"""
    W, H = 760, height
    L, R, T, B = 36, 12, 12, 26
    if not bins:
        return ""
    lo = min(b for b, _ in bins)
    hi = max(b for b, _ in bins) + 10
    cmax = max(c for _, c in bins)
    x = lambda p: L + (W - L - R) * (p - lo) / max(hi - lo, 10)
    y = lambda c: T + (H - T - B) * (1 - c / cmax)
    parts = [f'<svg viewBox="0 0 {W} {H}" role="img">']
    for b, c in bins:
        col = "var(--brand-coral-main)" if b < 0 else "var(--success-main)"
        parts.append(f'<rect x="{x(b) + 1:.1f}" y="{y(c):.1f}" width="{x(b + 10) - x(b) - 2:.1f}" height="{H - B - y(c):.1f}" '
                     f'rx="2" fill="{col}" opacity="0.75"><title>{b}%~{b + 10}%: {c}</title></rect>')
    for p in range(lo, hi + 1, 50 if hi - lo > 150 else 20):
        parts.append(f'<text class="tick" x="{x(p):.1f}" y="{H - 8}" text-anchor="middle">{p}%</text>')
    if median is not None:
        mx = x(max(lo, min(hi, median * 100)))
        parts.append(f'<line x1="{mx:.1f}" x2="{mx:.1f}" y1="{T}" y2="{H - B}" stroke="var(--gray-800)" stroke-width="1.5" stroke-dasharray="4 3"/>')
    if seed is not None:
        sx = x(max(lo, min(hi, seed * 100)))
        parts.append(f'<line x1="{sx:.1f}" x2="{sx:.1f}" y1="{T}" y2="{H - B}" stroke="var(--ds-seed)" stroke-width="2.5"/>')
    parts.append(f'<line class="ax" x1="{L}" x2="{W - R}" y1="{H - B}" y2="{H - B}"/></svg>')
    return '<div class="ds-chart">' + "".join(parts) + "</div>"


def flow_card(name, totals, years, flow, share_a, share_b, w=232, h=92):
    """카테고리 02 · 의도 묶음 하나의 흐름 유형 미니 차트 (method-v5).
    12개월 구간 4개의 합계 막대 · 직전 구간보다 늘면 초록, 줄면 코랄 · 첫 구간은 회색."""
    vmax = _nice_max(max(totals) if totals and max(totals) > 0 else 1)
    n = len(totals)
    pad_l, pad_r, top, bot = 4, 4, 14, 18
    bw = (w - pad_l - pad_r) / n
    parts = [f'<svg class="ds-flowcard__svg" width="100%" viewBox="0 0 {w} {h}" preserveAspectRatio="none" role="img">']
    for i, v in enumerate(totals):
        bh = (h - top - bot) * (v or 0) / vmax
        x = pad_l + i * bw + bw * 0.18
        y = h - bot - bh
        if i == 0:
            col = "var(--gray-300)"
        else:
            col = "var(--ds-up)" if (v or 0) > (totals[i - 1] or 0) else "var(--ds-down)"
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw * 0.64:.1f}" height="{max(bh, 0.5):.1f}" rx="2" fill="{col}"><title>{html.escape(years[i])} · {C.fmt_int(v)}</title></rect>')
        parts.append(f'<text class="tick" x="{x + bw * 0.32:.1f}" y="{y - 3:.1f}" text-anchor="middle">{C.fmt_compact(v, "kr")}</text>')
        parts.append(f'<text class="tick" x="{x + bw * 0.32:.1f}" y="{h - 5:.1f}" text-anchor="middle">{html.escape(years[i][:5])}</text>')
    parts.append("</svg>")
    mix = f"{C.fmt_share(share_a)} → <b>{C.fmt_share(share_b)}</b>" if share_a is not None and share_b is not None else ""
    return (f'<div class="ds-flowcard"><div class="ds-flowcard__hd"><span class="ds-flowcard__name">{html.escape(name)}</span>'
            f'<span class="ds-flowcard__flow">{html.escape(flow or "")}</span></div>{"".join(parts)}'
            f'<div class="ds-flowcard__mix">구성비 {mix}</div></div>')


BUMP_PAL = ["#f8cf68", "#be9081", "#f895e8", "#c1a5fc", "#5e9995", "#fb989a", "#6f91ef", "#00ad98", "#89e1dc", "#8bd5ff", "#b5c21d", "#bbd5a6", "#85dda8", "#53b1e7", "#3379e0", "#f96e6e", "#db884d", "#caa932", "#cfdb4d", "#94b2ff", "#65ba72", "#3fa6c6", "#65719c", "#ffb5b5", "#c9547e", "#9d9d9d"]  # LM communityChart[A~Z] (클러스터·CEP·의도 묶음)


def _on_color(hexc):
    """원 안 숫자 색 · 밝은 팔레트 색(노랑·민트 등)은 흰 글자가 안 보여 진한 회색으로 (명도 기준)."""
    h = hexc.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return "#232128" if (0.299 * r + 0.587 * g + 0.114 * b) > 0.68 else "#fff"


def bump_ranks(rows, k):
    n = len(rows)
    ranks = []
    for j in range(k):
        order = sorted(range(n), key=lambda i: -(rows[i]["t"][j] or 0))
        rk = [0] * n
        for pos, i in enumerate(order):
            rk[i] = pos + 1
        ranks.append(rk)
    return ranks


def _era(month, months):
    return months.index(month) // 12 if month and month in months else None


def new_info(r, months, k):
    """묶음 r 의 구간별 신규: (묶음이 처음 등장한 구간, [구간별 처음 등장한 검색어 목록])."""
    first = _era(r.get("since"), months) if "new" in (r.get("tags") or []) else None
    kws = [[] for _ in range(k)]
    for m in r.get("members") or []:
        if "new" in (m.get("tags") or []):
            e = _era(m.get("since"), months)
            if e is not None:
                kws[e].append(f'{m["kw"]} ({m["since"]})')
    return first, kws


def bump_chart(rows, years, months=None, w=900, row_h=34):
    """method-v5 · 의도 묶음 범프 차트 (자동완성 트렌드 스타일): 묶음마다 다른 색의 반투명 띠 + 순위 숫자 원.
    순위 = 12개월 구간마다 검색량 순 (구간 안에서는 구성비 순위와 같다). 칩·띠에 마우스를 올리면 그 묶음만 강조."""
    n, k = len(rows), len(years)
    if n == 0 or k == 0:
        return ""
    ranks = bump_ranks(rows, k)
    L, R, top, bot = 64, 56, 14, 34
    h = top + row_h * n + bot
    X = lambda j: L + 30 + (w - L - R - 60) * j / max(k - 1, 1)
    Y = lambda r: top + row_h * (r - 0.5)
    ordn = lambda r: f"{r}{'st' if r % 10 == 1 and r != 11 else 'nd' if r % 10 == 2 and r != 12 else 'rd' if r % 10 == 3 and r != 13 else 'th'}"
    o = [f'<svg class="ds-bump2" viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="의도 묶음 순위 변화">']
    for r in range(1, n + 1):
        y = Y(r)
        o.append(f'<line x1="{L}" x2="{w - R}" y1="{y - row_h / 2:.1f}" y2="{y - row_h / 2:.1f}" stroke="var(--gray-200)"/>')
        o.append(f'<text class="ds-bump2__rk" x="{L - 14}" y="{y + 4:.1f}" text-anchor="end">{ordn(r)}</text>')
    o.append(f'<line x1="{L}" x2="{w - R}" y1="{top + row_h * n:.1f}" y2="{top + row_h * n:.1f}" stroke="var(--gray-200)"/>')
    for j, yr in enumerate(years):
        o.append(f'<text class="ds-bump2__x" x="{X(j):.1f}" y="{h - 10}" text-anchor="middle">{html.escape(yr)}</text>')
    for i, r in enumerate(rows):
        col = BUMP_PAL[i % len(BUMP_PAL)]
        pts = " ".join(f"{X(j):.1f},{Y(ranks[j][i]):.1f}" for j in range(k))
        o.append(f'<g class="ds-bump2__s" data-i="{i}"><polyline fill="none" stroke="{col}" stroke-opacity="0.32" stroke-width="13" '
                 f'stroke-linejoin="round" stroke-linecap="round" points="{pts}"/>')
        sy = r.get("shareY") or [None] * k
        first, nk = new_info(r, months or [], k)
        for j in range(k):
            rk = ranks[j][i]
            tip = f'{r["name"]} · {years[j]} · {rk}위 · {C.fmt_int(r["t"][j])}' + (f' · 비중 {round(sy[j] * 100)}%' if j < len(sy) and sy[j] is not None else "")
            if first == j:
                tip += f' · 신규 묶음 (since {r.get("since")})'
            if nk[j]:
                tip += " · 이 구간 신규 검색어: " + ", ".join(nk[j])
            extra = ""
            if first == j:
                nl = "신규 " + (r.get("since") or "")[2:].replace("-", ".")
                extra += (f'<rect x="{X(j) + 13:.1f}" y="{Y(rk) - 8:.1f}" width="58" height="16" rx="8" fill="#fff" stroke="var(--lm-purple-main)"/>'
                          f'<text class="ds-bump2__new" x="{X(j) + 42:.1f}" y="{Y(rk) + 3.5:.1f}" text-anchor="middle" fill="var(--lm-purple-main)">{html.escape(nl)}</text>')
            elif nk[j]:
                extra += (f'<rect x="{X(j) + 13:.1f}" y="{Y(rk) - 8:.1f}" width="24" height="16" rx="8" fill="#fff" stroke="{col}"/>'
                          f'<text class="ds-bump2__new" x="{X(j) + 25:.1f}" y="{Y(rk) + 3.5:.1f}" text-anchor="middle" fill="{col}">+{len(nk[j])}</text>')
            # 강조할 때만 보이는 값: 그 구간 검색량 + 직전 구간 대비 (처음 등장 구간은 NEW · 그 다음 구간은 방향만)
            v = r["t"][j]
            if first == j or (j > 0 and not r["t"][j - 1]):
                chg, cc = "신규", "new"
            elif j == 0:
                chg, cc = "", ""
            else:
                d = v / r["t"][j - 1] - 1
                cc = "up" if d > 0.0005 else ("dn" if d < -0.0005 else "flat")
                ar = "▲" if cc == "up" else ("▼" if cc == "dn" else "–")
                chg = ar if (first is not None and j - 1 == first) else f"{ar}{abs(d) * 100:.0f}%"
                cc += " ds-" + ("t3" if abs(d) >= 0.3 else ("t2" if abs(d) >= 0.1 else "t1"))
            val = (f'<text class="ds-bump2__v" x="{X(j):.1f}" y="{Y(rk) - 15:.1f}" text-anchor="middle">{C.fmt_compact(v, "kr")}'
                   + (f'<tspan class="ds-bump2__d ds-bump2__d--{cc.replace(' ', ' ds-bump2__d--')}"> {chg}</tspan>' if chg else "") + "</text>")
            o.append(f'<g><title>{html.escape(tip)}</title><circle cx="{X(j):.1f}" cy="{Y(rk):.1f}" r="10" fill="{col}"/>'
                     f'<text class="ds-bump2__n" x="{X(j):.1f}" y="{Y(rk) + 4:.1f}" text-anchor="middle" style="fill:{_on_color(col)}">{rk}</text>{extra}{val}</g>')
        o.append("</g>")
    o.append("</svg>")
    chips = "".join(f'<span class="ds-bump2__chip" data-i="{i}"><span class="ds-bump2__dot" style="background:{BUMP_PAL[i % len(BUMP_PAL)]}"></span>{html.escape(r["name"])}</span>'
                    for i, r in enumerate(rows))
    return f'<div class="ds-bump2__chips">{chips}</div>' + "".join(o)


def bump_list(rows, years, months=None):
    """method-v5 · 범프 차트의 목록 보기: 구간마다 순위 카드 · 직전 구간 대비 순위 변화 (▲ 파랑 · ▼ 빨강 · NEW = 직전 구간 검색량 0)."""
    n, k = len(rows), len(years)
    ranks = bump_ranks(rows, k)
    cards = []
    for j in range(k):
        order = sorted(range(n), key=lambda i: ranks[j][i])
        items = []
        for i in order:
            first, nk = new_info(rows[i], months or [], k)
            if first == j or (j > 0 and not rows[i]["t"][j - 1]):
                ch = f'<span class="ds-bl__new" title="since {rows[i].get("since") or ""}">NEW</span>'
            elif j == 0:
                ch = '<span class="ds-bl__c ds-bl__c--0">-</span>'
            else:
                d = ranks[j - 1][i] - ranks[j][i]
                ch = (f'<span class="ds-bl__c ds-bl__c--up">{d} ▲</span>' if d > 0 else
                      f'<span class="ds-bl__c ds-bl__c--dn">{d} ▼</span>' if d < 0 else '<span class="ds-bl__c ds-bl__c--0">-</span>')
            dot = f'<span class="ds-bump2__dot" style="background:{BUMP_PAL[i % len(BUMP_PAL)]}"></span>'
            plus = (f'<span class="ds-bl__plus" title="{html.escape("이 구간 신규 검색어: " + ", ".join(nk[j]))}">+{len(nk[j])}</span>'
                    if nk[j] and first != j else "")
            items.append(f'<li><span class="ds-bl__r">{ranks[j][i]}</span>{dot}<span class="ds-bl__nm" title="{C.fmt_int(rows[i]["t"][j])}">{html.escape(rows[i]["name"])}</span>{plus}{ch}</li>')
        cards.append(f'<div class="ds-bl__card"><div class="ds-bl__hd"><span>{html.escape(years[j])}</span><span>직전 구간 대비</span></div><ol>{"".join(items)}</ol></div>')
    return f'<div class="ds-bl">{"".join(cards)}</div>'
