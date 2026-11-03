"""st_common.py · 시즌·트렌드 분석 공통 · 원자료 파서와 서식.

MCP 응답 파일은 fetch_dl.py 가 {"data": payload} 로 감싸 저장한다. 호스트가 [{"type":"text","text":...}]
콘텐츠 블록으로 저장한 경우도 벗긴다. 원자료 파일은 바꾸지 않는다.
"""
import json
import re
from pathlib import Path


def unwrap_content_blocks(raw):
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
    return re.sub(r"\s+", "", str(s or "")).lower()


def intent_strings(raw):
    """intent_finder 응답 → 검색어 문자열 목록(검색량 순). 문자열 목록 · {keyword:..} 목록 모두 받는다."""
    raw = unwrap_content_blocks(raw)
    data = raw.get("data") if isinstance(raw, dict) else raw
    out = []
    for s in data or []:
        if isinstance(s, str):
            out.append(s)
        elif isinstance(s, dict) and isinstance(s.get("keyword"), str):
            out.append(s["keyword"])
    return out


def cluster_parts(raw):
    """cluster_finder 응답 → (communities, rels). 응답이 {"data":{...}} 이든 최상위 {"rels",...} 이든 받는다."""
    raw = unwrap_content_blocks(raw)
    data = raw.get("data") if isinstance(raw, dict) else {}
    if not isinstance(data, dict) and isinstance(raw, dict) and ("rels" in raw or "communities" in raw):
        data = raw
    data = data if isinstance(data, dict) else {}
    comm = data.get("communities") if isinstance(data.get("communities"), dict) else {}
    rels = data.get("rels") if isinstance(data.get("rels"), list) else []
    comm = {str(k): [str(x) for x in v if isinstance(x, str)] for k, v in comm.items() if isinstance(v, list)}
    rels = [[str(e[0]), str(e[1])] for e in rels if isinstance(e, list) and len(e) >= 2]
    return comm, rels


def cluster_nodes(raw):
    comm, rels = cluster_parts(raw)
    seen, out = set(), []
    for a, b in rels:
        for s in (a, b):
            if s not in seen:
                seen.add(s)
                out.append(s)
    for v in comm.values():
        for s in v:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def keyword_records(raw):
    """keyword_info 응답 → [{keyword, months, nv, gg}] (월 오름차순). kr 은 네이버(nv) + 구글(gg)."""
    raw = unwrap_content_blocks(raw)
    rows = raw.get("data") if isinstance(raw, dict) else raw
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("keyword"):
            continue
        mv = sorted([m for m in (r.get("monthly_volume") or []) if isinstance(m, dict) and m.get("month")],
                    key=lambda m: m["month"])
        split = any(m.get("nv") is not None or m.get("gg") is not None for m in mv)
        out.append({
            "keyword": r["keyword"],
            "months": [m["month"] for m in mv],
            "nv": [num(m.get("nv")) for m in mv],
            "gg": [num(m.get("gg")) if split else num(m.get("total")) for m in mv],
        })
    return out


# ─────────────── 서식 ───────────────

def fmt(n):
    return f"{round(n):,}"


# 큰 수 단위 · 리포트 언어(--lang)를 따른다. kr 만 · jp 万 (1만 = 10,000) · us K · M (1K = 1,000)
LANG = "kr"
UNIT_10K = {"kr": "만", "jp": "万"}  # i18n-ok · 숫자 단위 (계약값)


def set_lang(lang):
    global LANG
    LANG = lang if lang in ("kr", "jp", "us") else "kr"


def kv(n):
    """1만 이상은 n.n만(jp 万 · us 12K · 1.2M), 아래는 콤마."""
    n = round(n)
    u = UNIT_10K.get(LANG)
    if not u:
        if n >= 1_000_000:
            return f"{n/1_000_000:.1f}M".replace(".0M", "M")
        return f"{n/1000:,.0f}K" if n >= 10000 else f"{n:,}"
    if n >= 10_000_000:
        return f"{n/10000:,.0f}{u}"
    return f"{n/10000:.1f}{u}".replace(f".0{u}", u) if n >= 10000 else f"{n:,}"


def pct(v, d=1):
    return f"{v*100:+.{d}f}%"
