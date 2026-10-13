"""demand-shift 공용 헬퍼 · 로딩 · 정규화 · 숫자 서식.

표준 라이브러리만 쓴다. 숫자 서식은 이 파일 하나에서만 정한다 —
facts.md(LLM이 읽는 요약)와 리포트(사람이 보는 화면)가 같은 문자열을 쓰게 하려는 것이다.
그래야 lint 가 서술문 안의 숫자를 facts 와 대조할 수 있다.
"""

import json
import re
from pathlib import Path

MINUS = "\u2212"  # 화면 표기용 마이너스(−)


# ─────────────────────────── 로딩 ───────────────────────────

def unwrap_content_blocks(raw):
    """호스트가 [{"type":"text","text":"<JSON>"}] 로 저장한 결과를 벗긴다 (claude.ai 컨테이너 실측)."""
    if isinstance(raw, list) and raw:
        blocks = [b for b in raw if isinstance(b, dict) and b.get("type") == "text" and "text" in b]
        if blocks and len(blocks) == len(raw):
            try:
                return json.loads("".join(str(b.get("text") or "") for b in blocks))
            except (json.JSONDecodeError, TypeError):
                return raw
    return raw


def load_json(path):
    return unwrap_content_blocks(json.loads(Path(path).read_text(encoding="utf-8")))


def num(v, default=0):
    if isinstance(v, bool):
        return default
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            f = float(v.replace(",", ""))
        except ValueError:
            return default
        return int(f) if f.is_integer() else f
    return default


def norm_kw(s):
    """키워드 대조용 키 · 공백·대소문자 무시 (API 가 '오메가3'를 '오메가 3'로 돌려주는 경우 실측)."""
    return re.sub(r"\s+", "", str(s or "")).lower()


# ─────────────────────────── 원자료 파서 ───────────────────────────

def keyword_records(raw):
    """keyword_info 응답 → {norm_kw: {keyword, months:[...], nv:[...], gg:[...], total:[...]}}"""
    raw = unwrap_content_blocks(raw)
    rows = raw.get("data") if isinstance(raw, dict) else raw
    out = {}
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("keyword"):
            continue
        mv = [m for m in (r.get("monthly_volume") or []) if isinstance(m, dict) and m.get("month")]
        mv.sort(key=lambda m: m["month"])
        # 엔진별 값(nv · gg)이 없고 합계(total)만 오는 시장(jp · us 실측 2026-10-08)은 total 을 구글 값으로 읽는다.
        #   집계는 nv + gg 로 검색량을 만들기 때문에, 그대로 두면 모든 값이 0 이 된다. 원자료 파일은 바꾸지 않는다.
        split = any(m.get("nv") is not None or m.get("gg") is not None for m in mv)
        rec = {
            "keyword": r["keyword"],
            "months": [m["month"] for m in mv],
            "nv": [num(m.get("nv")) for m in mv],
            "gg": [num(m.get("gg")) if split else num(m.get("total")) for m in mv],
            "engineSplit": split,
        }
        rec["total"] = [
            num(m.get("total")) if m.get("total") is not None else a + b
            for m, a, b in zip(mv, rec["nv"], rec["gg"])
        ]
        out[norm_kw(r["keyword"])] = rec
    return out


def intent_strings(raw):
    raw = unwrap_content_blocks(raw)
    data = raw.get("data") if isinstance(raw, dict) else raw
    return [s for s in (data or []) if isinstance(s, str)]


def path_list(raw):
    raw = unwrap_content_blocks(raw)
    data = raw.get("data") if isinstance(raw, dict) else raw
    if isinstance(raw, dict) and isinstance(raw.get("result"), dict):
        data = raw["result"].get("paths", data)
    return [[str(x) for x in p] for p in (data or []) if isinstance(p, list) and p]


def path_seed(raw, fallback=""):
    raw = unwrap_content_blocks(raw)
    if isinstance(raw, dict):
        rd = raw.get("request_detail") or {}
        if rd.get("keyword"):
            return rd["keyword"]
    return fallback


def path_time_point(raw, fallback="curr"):
    raw = unwrap_content_blocks(raw)
    if isinstance(raw, dict):
        rd = raw.get("request_detail") or {}
        if rd.get("time_point"):
            return str(rd["time_point"])
    return fallback


def cluster_parts(raw):
    raw = unwrap_content_blocks(raw)
    data = raw.get("data") if isinstance(raw, dict) else {}
    # download_url 로 받은 파일은 {"rels", "communities"} 가 최상위에 있다 (v3 실측) · 둘 다 받는다
    if not isinstance(data, dict) and isinstance(raw, dict) and ("rels" in raw or "communities" in raw):
        data = raw
    data = data if isinstance(data, dict) else {}
    comm = data.get("communities") if isinstance(data.get("communities"), dict) else {}
    rels = data.get("rels") if isinstance(data.get("rels"), list) else []
    comm = {str(k): [str(x) for x in v if isinstance(x, str)] for k, v in comm.items() if isinstance(v, list)}
    rels = [[str(e[0]), str(e[1])] for e in rels if isinstance(e, list) and len(e) >= 2]
    return comm, rels


# ─────────────────────────── 서식 ───────────────────────────

def fmt_int(v):
    if v is None:
        return "—"
    return f"{int(round(v)):,}"


def fmt_pct(r, signed=True, digits=1):
    """비율(0.092) → '+9.2%'. None → '—'."""
    if r is None:
        return "—"
    v = r * 100
    s = f"{abs(v):,.{digits}f}%"
    if not signed:
        return s if v >= 0 else MINUS + s
    if round(v, digits) == 0:
        return f"{0:.{digits}f}%"
    return ("+" if v > 0 else MINUS) + s


def fmt_share(r, digits=1):
    return "—" if r is None else f"{r * 100:.{digits}f}%"


def fmt_pp(d, digits=1):
    """퍼센트포인트 차이(0.041) → '+4.1%p'."""
    if d is None:
        return "—"
    v = d * 100
    if round(v, digits) == 0:
        return f"0.0%p"
    return ("+" if v > 0 else MINUS) + f"{abs(v):.{digits}f}%p"


def fmt_ratio(v, digits=2):
    return "—" if v is None else f"{v:.{digits}f}"


def fmt_compact(v, lang="kr"):
    """월평균 같은 큰 수를 짧게: 12,300 → '1.2만' (kr), '1.2万' (jp), '12.3K' (us)."""
    if v is None:
        return "—"
    v = float(v)
    if lang in ("kr", "jp"):  # 만 단위 (kr 만 · jp 万)
        u = {"kr": "만", "jp": "万"}[lang]  # i18n-ok · 숫자 단위
        if v >= 10000:
            return f"{v / 10000:.1f}{u}".replace(f".0{u}", u)
        return f"{int(round(v)):,}"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}M"
    if v >= 1000:
        return f"{v / 1000:.1f}K"
    return f"{int(round(v)):,}"


def year_label(months12):
    """['2022-09',...,'2023-08'] → '22.09–23.08'"""
    a, b = months12[0], months12[-1]
    return f"{a[2:4]}.{a[5:7]}–{b[2:4]}.{b[5:7]}"


# ─────────────────────────── 숫자 lint 용 ───────────────────────────

_NUM_RE = re.compile(r"[+\-−]?\d[\d,]*(?:\.\d+)?\s*(?:%p|%|만|万|배|회|건|개월|개|K|M)?")


def extract_numbers(text):
    """서술문에서 '검사 대상' 숫자 토큰을 뽑는다. 연도·월·순번 같은 작은 정수는 제외."""
    toks = []
    for m in _NUM_RE.finditer(str(text or "")):
        t = m.group(0).strip()
        core = re.sub(r"[^\d.]", "", t)
        if not core:
            continue
        has_unit = bool(re.search(r"(%p|%|만|万|배|K|M)$", t))
        try:
            val = float(core)
        except ValueError:
            continue
        # 연도(2024), 월(04월 등), 작은 순번(1~12)은 사실 검증 대상이 아니다
        if not has_unit and (val <= 12 or 1990 <= val <= 2100):
            continue
        toks.append(t)
    return toks


def canon_number(tok):
    """비교용 정규형 · 부호 통일, 공백·쉼표 제거."""
    t = tok.replace(MINUS, "-").replace(" ", "").replace(",", "")
    # 개수 단위(건·개·회·개월)는 숫자만 비교한다 · %, %p, 배 같은 값 단위는 유지
    t = re.sub(r"(건|개월|개|회)$", "", t)
    return t
