#!/usr/bin/env python3
"""demand-shift v4 집계기 · plan.json + MCP 원자료 → facts.json (+ facts.md).

경로 검증을 쓰지 않는다. 리포트는 두 섹션으로 고정된다 (두 모드 공통):
  1 external · 시장 흐름 비교      — 분석 대상 vs 비교군 (상위어 cluster·intent) · 판정의 대조군
  2 internal · 타겟 키워드 의도 변화 — 브랜드/제품: 제품 라인 · 카테고리: 의도 묶음 (v5.1 · 두 모드 같은 화면)
plan.target(시드 + 유사의도 상세 묶음)은 섹션이 아니다 — 1 분석 대상의 대표 표기 커버 검사 기준(broad)으로만 쓴다.

리포트의 **모든 숫자와 모든 판정**은 여기서 나온다. LLM 은 plan.json 으로 '무엇을 셀지'만,
narrative.json 으로 '어떻게 읽을지'만 정한다.

사용:
  python3 ds_aggregate.py build --plan plan.json --kw lm_keyword_info*.json \\
      --intent lm_intent_*.json --cluster lm_cluster.json --gl kr --lang kr --date 2026-10-01 \\
      --out facts.json --brief facts.md
  python3 ds_aggregate.py lint --facts facts.json --narrative narrative.json

표준 라이브러리만 사용한다.
"""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import ds_common as C  # noqa: E402

VERSION = "1.0.0"
# method-v5.1 · 2 섹션(내부 동향)을 '검색 목적처럼' 보이는 단위 — 카테고리 = 의도 묶음 · 브랜드/제품 = 제품 라인 (같은 표·그래프·facts)
PURPOSE_UNITS = ("의도", "제품 라인")
SECTION_ORDER = ["external", "internal"]
MODES = ("entity", "category")
MIN_VOL_Y = 12  # 48개월 합계 12 미만 = 측정값 없음

# ───────────────────────── 판정 규칙 (rules-v3) ─────────────────────────
# 모든 수치 임계값은 여기서만 정한다. references/rules.md 가 같은 값을 문서로 옮긴 것이다.
RULES = {
    "version": "rules-v5 (2026-10-06)",
    "newEntryRatio": 0.10,      # 첫 12개월 < 최근 12개월 × 값 → 신규 (since 로 본다)
    "stepMinBase": 100,         # 단일 엔진 급증: 직전 3개월 평균이 이 미만이면 보지 않는다
    "stepJump": 2.5,            # 단일 엔진 급증: 직전 3개월 평균 대비 배수 (값은 빼지 않고 기록만 한다)
    "stepHoldRatio": 2.0,       # 3~6개월 뒤에도 이전의 이 배수 이상 유지
    "stepOtherEngineMax": 0.5,  # 같은 달 다른 엔진 변화 < 값
    "spikeRatio": 3.0,          # 이슈 스파이크: 단월 ≥ 전후 3개월 중앙값 × 값
    "spikeReturnMonths": 2,     # 이후 N개월 안에 기준의 1.5배 이하로 복귀
    "levelJump": 1.8,           # 묶음 수준 변화: 3개월 평균이 직전 3개월의 이 배수 이상
    "levelHold": 1.5,           # 그리고 3~6개월 뒤에도 이 배수 이상 유지
    "levelDominance": 0.7,      # 증가분의 이 비율 이상을 한 키워드가 만들고
    "levelExcess": 0.3,         # 그 몫이 그 키워드의 원래 묶음 내 몫보다 30%p 이상 크면 '단일 키워드 급증'
    "platformPp": 0.15,         # 02 판정: |시드 − 외부 중앙값| < 15.0%p → 업계와 같은 흐름
    "coverMin": 0.90,            # v5.6.2 · 1 묶음(대표 표기) ÷ 상세 묶음 최근 12개월 검색량 — 이 미만이면 '대표 표기 커버 낮음'
    "minExternal": 3,
    "maxExternal": 10,           # v5.7 · 비교 대상 최대 (목표 6 · 없으면 그만)
    "minScale": 0.05,            # v5.7 · 비교 대상 최근 12개월 검색량 ≥ 분석 대상의 5%           # 4년 변화율이 있는 외부 키워드가 이 수 미만이면 판정 보류
    "yoyMinBase": 30,           # 월별 전년 동월 대비: 전년 값이 이 미만이면 칸을 비운다
    "yoyNewWindow": 24,         # 처음 등장한 달이 마지막 24개월(직전 12개월 구간 이후) 안이면 전년 증감률 대신 '신규'
    "topN": 5,                  # 카테고리 모드 02 · 묶음별 대표 검색어 수
}
VERDICT_LABEL = {
    "same": "업계와 같은 흐름",
    "weak": "업계 대비 약세",
    "strong": "업계 대비 강세",
    "hold": "판정 보류",
}
BANNED = ["거짓말", "속인다", "속이", "충격", "몰락", "폭망", "망했", "사기", "처참", "참패", "괴멸"]
TAG_KO = {"new": "신규"}  # rules-v4: 데이터 이상 감지는 태그로 달지 않고 하단 참고 사항에만 적는다


# ───────────────────────── 시계열 ─────────────────────────

class Store:
    def __init__(self, recs):
        self.recs = recs
        months = sorted({m for r in recs.values() for m in r["months"]})[-48:]
        self.n_years = len(months) // 12
        self.months = months[len(months) - self.n_years * 12:]
        self.idx = {m: i for i, m in enumerate(self.months)}
        self.years = [C.year_label(self.months[i * 12:(i + 1) * 12]) for i in range(self.n_years)]

    def get(self, kw):
        return self.recs.get(C.norm_kw(kw))

    def aligned(self, kw, engine="total"):
        r = self.get(kw)
        out = [0] * len(self.months)
        if r:
            for m, v in zip(r["months"], r[engine]):
                if m in self.idx:
                    out[self.idx[m]] = v
        return out

    def has_data(self, kw):
        return bool(self.get(kw)) and sum(self.aligned(kw)) >= MIN_VOL_Y


def mean(xs):
    return sum(xs) / len(xs) if xs else 0


def yearly(vals, n):
    return [sum(vals[i * 12:(i + 1) * 12]) for i in range(n)]


def stats(vals, st):
    t = yearly(vals, st.n_years)
    gt = (t[-1] / t[0] - 1) if t and t[0] > 0 else None
    yoy = (t[-1] / t[-2] - 1) if len(t) >= 2 and t[-2] > 0 else None
    dirs = "".join("↑" if t[i] > t[i - 1] else ("↓" if t[i] < t[i - 1] else "→") for i in range(1, len(t)))
    tags, since = [], None
    first = next((i for i, v in enumerate(vals) if v > 0), None)
    if t and t[-1] > 0 and first is not None and first >= 3 and (t[0] == 0 or t[0] < t[-1] * RULES["newEntryRatio"]):
        since = st.months[first]
        tags.append("new")
        gt = None
    # rules-v5: 직전 12개월 구간 안(또는 최근 구간)에 처음 등장했으면 전년 증감률 대신 '신규'
    yoy_new = first is not None and t and t[-1] > 0 and first >= len(vals) - RULES["yoyNewWindow"]
    if yoy_new:
        yoy = None
    # rules-v4.1: '소형' 구분을 없앴다 — 첫 12개월이 작아도 4년 변화율을 숫자로 낸다
    # 월별 전년 동월 대비 (13~48번째 달)
    myoy = []
    for i in range(12, len(vals)):
        b = vals[i - 12]
        myoy.append((vals[i] / b - 1) if b >= RULES["yoyMinBase"] else None)
    peak_i = max(range(len(vals)), key=lambda i: vals[i]) if vals else 0
    return {"t": t, "avg": round(t[-1] / 12) if t else 0, "gt": gt, "yoy": yoy, "yoyNew": bool(yoy_new), "dir": dirs,
            "since": since, "tags": tags, "m": vals, "myoy": myoy,
            "peak": {"month": st.months[peak_i], "v": vals[peak_i]} if vals else None}


def detect_step(st, kw, engine):
    """한 엔진의 계단형 재집계 (rules-v3 = rules-v1 판별식)."""
    R = RULES
    other = "nv" if engine == "gg" else "gg"
    a, b = st.aligned(kw, engine), st.aligned(kw, other)
    for m in range(3, len(a) - 6):
        pre, post = mean(a[m - 3:m]), mean(a[m:m + 3])
        if pre >= R["stepMinBase"] and a[m] >= R["stepJump"] * pre and post >= R["stepJump"] * pre and mean(a[m + 3:m + 7]) >= R["stepHoldRatio"] * pre:
            ob = max(mean(b[m - 3:m]), 1)
            if abs(b[m] / ob - 1) < R["stepOtherEngineMax"]:
                return {"type": "step", "engine": engine, "kw": st.get(kw)["keyword"], "month": st.months[m],
                        "before": round(pre), "after": round(a[m]), "otherChange": round(b[m] / ob - 1, 3)}
    return None


def detect_spike(vals, st):
    R = RULES
    for i in range(3, len(vals) - 1):
        ctx = vals[i - 3:i] + vals[i + 1:i + 4]
        base = statistics.median(ctx) if ctx else 0
        if base <= 0 or vals[i] < base * R["spikeRatio"]:
            continue
        back = vals[i + 1:i + 1 + R["spikeReturnMonths"]]
        if back and min(back) <= base * 1.5:
            return {"month": st.months[i], "v": round(vals[i]), "base": round(base)}
    return None


def detect_notation(st, bundle, kws, total=None):
    """같은 묶음 안에서 한쪽이 빠지고 같은 달 다른 쪽이 비슷한 양만큼 오르는 표기 이동 (묶음당 최대 2건).
    빠진 쪽이 묶음 월평균의 5% 미만이면 모델 교체 같은 잔변동이라 보고하지 않는다."""
    ser = {k: st.aligned(k) for k in kws if st.has_data(k)}
    floor = max(100, 0.05 * mean(total)) if total else 100
    ev = []
    for a in ser:
        for b in ser:
            if a == b:
                continue
            A, B = ser[a], ser[b]
            for m in range(3, len(A) - 2):
                pa, qa, pb, qb = mean(A[m - 3:m]), mean(A[m:m + 3]), mean(B[m - 3:m]), mean(B[m:m + 3])
                if pa < floor:
                    continue
                loss, gain = pa - qa, qb - pb
                if qa < 0.5 * pa and 0.6 * loss <= gain <= 1.6 * loss and qb > 1.5 * max(pb, 1):
                    ev.append({"type": "notation", "bundle": bundle, "month": st.months[m],
                               "from": st.get(a)["keyword"], "to": st.get(b)["keyword"],
                               "fromBefore": round(pa), "fromAfter": round(qa), "toBefore": round(pb), "toAfter": round(qb),
                               "_fit": abs(gain / loss - 1)})
                    break
    ev.sort(key=lambda e: e["_fit"])
    used, out = set(), []
    for e in ev:
        if e["from"] in used or e["to"] in used:
            continue
        used |= {e["from"], e["to"]}
        e.pop("_fit")
        out.append(e)
        if len(out) >= 2:
            break
    return out


def detect_level_jump(st, bundle, total, member_series):
    """묶음 합계의 수준 변화를 한 키워드가 대부분 만들었는지 (v3 신설).
    재집계 판별식을 통과하지 않은 급증도 묶음 전체의 상승처럼 보일 수 있어, 근거를 남기고 태그만 단다."""
    R = RULES
    for m in range(3, len(total) - 6):
        pre, post = mean(total[m - 3:m]), mean(total[m:m + 3])
        if pre < 100 or post < R["levelJump"] * pre or mean(total[m + 3:m + 7]) < R["levelHold"] * pre:
            continue
        inc = post - pre
        best, share, prior = None, 0, 0
        for kw, s in member_series.items():
            d = mean(s[m:m + 3]) - mean(s[m - 3:m])
            if inc > 0 and d / inc > share:
                best, share, prior = kw, d / inc, mean(s[m - 3:m]) / pre
        # 원래 묶음 대부분을 차지하던 키워드가 증가분도 대부분 만든 것은 정상 성장이다.
        # 원래 몫보다 증가분 몫이 levelExcess 이상 큰 경우만 '한 키워드가 끌어올렸다'고 본다.
        if best and share >= R["levelDominance"] and share - prior >= R["levelExcess"] and len(member_series) >= 2:
            return {"type": "jump", "bundle": bundle, "month": st.months[m], "kw": best,
                    "before": round(pre), "after": round(post), "share": round(share, 3), "prior": round(prior, 3)}
        return None
    return None


class Bundler:
    """키워드 묶음 → 행. 재집계 키워드는 해당 엔진을 빼고 합산, 중복 구글 버킷은 한 번만."""

    def __init__(self, st):
        self.st = st
        self.corrections = []
        self.dropped = []
        self._step_cache = {}

    def step_of(self, kw):
        k = C.norm_kw(kw)
        if k not in self._step_cache:
            s = detect_step(self.st, kw, "gg") or detect_step(self.st, kw, "nv")
            if s:
                other = "nv" if s["engine"] == "gg" else "gg"
                if sum(self.st.aligned(kw, other)) < MIN_VOL_Y:
                    s = None  # 다른 엔진 값이 없으면 합산 유지
            self._step_cache[k] = s
            if s:
                self.corrections.append(s)
        return self._step_cache[k]

    def row(self, name, kws, ctx, **extra):
        st, n = self.st, len(self.st.months)
        tot, seen_gg, members, dup, mser, tags = [0] * n, {}, [], [], {}, set()
        seen_rec = set()
        for kw in kws:
            if not st.has_data(kw):
                self.dropped.append({"kw": kw, "reason": "nodata", "ctx": ctx})
                continue
            rk = st.get(kw)["keyword"]
            if rk in seen_rec:  # 띄어쓰기만 다른 표기(온러닝 · 온 러닝)가 같은 측정 레코드를 가리키면 한 번만 센다
                continue
            seen_rec.add(rk)
            nv, gg = st.aligned(kw, "nv"), st.aligned(kw, "gg")
            step = self.step_of(kw)  # rules-v4: 감지만 하고 값은 그대로 합산한다
            key = tuple(gg)
            if sum(gg) > 0 and key in seen_gg:
                # 구글 동일값 중복: 같은 검색을 두 번 세지 않도록 한 번만 합산 (판단이 아니라 이중 계산 방지)
                dup.append({"type": "dup", "kw": st.get(kw)["keyword"], "same_as": seen_gg[key], "ctx": ctx})
                gg = [0] * n
            elif sum(gg) > 0:
                seen_gg[key] = st.get(kw)["keyword"]
            own = [a + b for a, b in zip(nv, gg)]
            tot = [a + b for a, b in zip(tot, own)]
            s = stats(own, st)
            mser[st.get(kw)["keyword"]] = own
            members.append({"kw": st.get(kw)["keyword"], "t": s["t"], "avg": s["avg"], "gt": s["gt"], "yoy": s["yoy"], "yoyNew": s["yoyNew"],
                            "dir": s["dir"], "m": own, "tags": s["tags"], "since": s["since"]})
        if not members:
            return None
        self.corrections += dup
        members.sort(key=lambda x: -x["avg"])
        s = stats(tot, st)
        r = {"name": name, **s, "members": members, "n": len(members), **extra}
        r["tags"] = sorted(set(s["tags"]) | tags)
        sp = detect_spike(tot, st)
        if sp:
            r["spike"] = sp
            self.corrections.append({"type": "spike", "bundle": name, **sp})
        if len(members) >= 2:
            self.corrections += detect_notation(st, name, [m["kw"] for m in members], tot)
            lj = detect_level_jump(st, name, tot, mser)
            if lj:
                self.corrections.append(lj)
                r["jump"] = lj
        return r


# ───────────────────────── 섹션 ─────────────────────────

def verdict_of(seed_gt, ext_gts):
    pp = RULES["platformPp"]
    if seed_gt is None or len(ext_gts) < RULES["minExternal"]:
        return "hold", None, None
    base = statistics.median(ext_gts)
    d = seed_gt - base
    v = "same" if abs(d) < pp else ("weak" if d < 0 else "strong")
    return v, base, d


def build_external(B, plan, target):
    rows = []
    for g in plan.get("external") or []:
        r = B.row(g["name"], g.get("keywords") or [], "external", src=g.get("_src"))
        if r:
            rows.append(r)
    rows.sort(key=lambda r: -r["avg"])
    # v5.7 · 규모 기준: 최근 12개월 검색량이 분석 대상의 5% 미만인 비교 대상은 뺀다 (작은 묶음은 성장률이 크게 나와 기준선을 끌어올린다)
    small = []
    if target.get("t") and target["t"][-1]:
        floor = RULES["minScale"] * target["t"][-1]
        small = [{"name": r["name"], "ratio": r["t"][-1] / target["t"][-1]} for r in rows if r["t"][-1] < floor]
        rows = [r for r in rows if r["t"][-1] >= floor]
    rows = rows[:RULES["maxExternal"]]
    gts = [r["gt"] for r in rows if r["gt"] is not None]
    v, base, d = verdict_of(target["gt"], gts)
    loo = None
    if v != "hold" and len(gts) > RULES["minExternal"]:
        flips = []
        for r in rows:
            if r["gt"] is None:
                continue
            rest = [x["gt"] for x in rows if x is not r and x["gt"] is not None]
            v2, _, _ = verdict_of(target["gt"], rest)
            if v2 != v:
                flips.append(r["name"])
        loo = {"stable": not flips, "flips": flips}
    for r in rows:
        r["rel"] = (r["gt"] - base) if (base is not None and r["gt"] is not None) else None
    ups = sum(1 for r in rows if (r["gt"] or 0) > 0)
    return {"rows": rows, "small": small, "baseline": base, "diff": d, "verdict": v, "verdictLabel": VERDICT_LABEL[v], "loo": loo,
            "nGt": len(gts), "ups": ups, "downs": sum(1 for r in rows if r["gt"] is not None and r["gt"] < 0)}


def flow_type(dirs):
    """흐름 유형 (카테고리 모드 02) · 구간 3개의 방향 화살표로 정한다."""
    d = dirs or ""
    if len(d) < 2:
        return "—"
    if set(d) == {"↑"}:
        return f"{len(d)}년 연속 증가"
    if set(d) == {"↓"}:
        return f"{len(d)}년 연속 감소"
    if d[-1] == "↑" and "↓" in d:
        return "감소 후 증가"
    if d[-1] == "↓" and "↑" in d:
        return "증가 후 감소"
    return "보합"


def canon_key(kw, variants, canon):
    """표기 변형 합산 키 · 품목 동의어(러닝화·런닝화)를 대표 이름으로 바꾸고 공백을 지운다."""
    t = re.sub(r"\s+", "", str(kw).lower())
    for v in sorted({re.sub(r"\s+", "", x.lower()) for x in variants}, key=len, reverse=True):
        if v and v != canon:
            t = t.replace(v, canon)
    return t


def top_queries(members, variants, n):
    """묶음별 대표 검색어 Top N · 표기 변형은 합산 · 최근 12개월 검색량 순."""
    canon = re.sub(r"\s+", "", (variants or [""])[0].lower())
    groups = {}
    for m in members:
        k = canon_key(m["kw"], variants or [], canon)
        g = groups.setdefault(k, {"kw": m["kw"], "lead": m["t"][-1], "t": [0] * len(m["t"]), "names": []})
        g["t"] = [a + b for a, b in zip(g["t"], m["t"])]
        g["names"].append(m["kw"])
        if m["t"][-1] > g["lead"]:
            g["kw"], g["lead"] = m["kw"], m["t"][-1]
    out = []
    for g in sorted(groups.values(), key=lambda g: -g["t"][-1])[:n]:
        yoy = (g["t"][-1] / g["t"][-2] - 1) if len(g["t"]) >= 2 and g["t"][-2] > 0 else None
        out.append({"kw": g["kw"], "last": g["t"][-1], "yoy": yoy, "merged": [x for x in g["names"] if x != g["kw"]]})
    return out


def build_internal(B, plan, st):
    it = plan.get("internal") or {}
    unit = it.get("unit") or ("제품 라인" if plan["mode"] == "entity" else "의도")
    if unit == "SKU":  # v5.0 이전 plan 호환 · 제품 라인으로 읽는다
        unit = "제품 라인"
    rows = []
    for g in it.get("parts") or []:
        r = B.row(g["name"], g.get("keywords") or [], "internal")
        if not r:
            continue
        if g.get("skus"):  # 라인 안의 하위 SKU · 같은 키워드라 보정 기록은 라인 행에서만 남긴다
            QB = Bundler(st)
            subs = [QB.row(x["name"], x.get("keywords") or [], "internal") for x in g["skus"]]
            r["subs"] = sorted((x for x in subs if x), key=lambda x: -x["avg"])
        rows.append(r)
    if not rows:
        return {"rows": [], "unit": unit}
    n = len(st.months)
    tot = [sum(r["m"][i] for r in rows) for i in range(n)]
    total = {"name": "합계", **stats(tot, st)}
    ty = total["t"]
    for r in rows:
        r["shareY"] = [(a / b) if b else None for a, b in zip(r["t"], ty)]
        r["share"] = r["shareY"][-1]
        for x in r.get("subs") or []:
            x["share"] = (x["t"][-1] / ty[-1]) if ty[-1] else None
        r["flow"] = flow_type(r["dir"])
    rows.sort(key=lambda r: -r["avg"])

    def top2(i):
        vals = sorted((r["t"][i] for r in rows), reverse=True)
        return (sum(vals[:2]) / ty[i]) if ty[i] else None
    growers = [r for r in rows if r["gt"] is not None]
    out = {"rows": rows, "total": total, "unit": unit,
           "conc": {"from": top2(0), "to": top2(-1), "byYear": [top2(i) for i in range(len(ty))]},
           "ups": sum(1 for r in growers if r["gt"] > 0), "downs": sum(1 for r in growers if r["gt"] < 0),
           "topGrow": (max(growers, key=lambda r: r["gt"])["name"] if any(r["gt"] > 0 for r in growers) else "없음"),
           "topDrop": (min(growers, key=lambda r: r["gt"])["name"] if any(r["gt"] < 0 for r in growers) else "없음")}
    # method-v5 · 구간별 순위(범프 차트와 같은 기준 · 그 구간 검색량 순)와 구간별 신규 검색어 수
    for k in range(len(ty)):
        for pos, r in enumerate(sorted(rows, key=lambda r: -(r["t"][k] or 0))):
            r.setdefault("rankY", [0] * len(ty))[k] = pos + 1
    for r in rows:
        nk = [0] * len(ty)
        for m in r.get("members") or []:
            if "new" in (m.get("tags") or []) and m.get("since") in st.months:
                nk[st.months.index(m["since"]) // 12] += 1
        r["newKwY"] = nk
    if unit in PURPOSE_UNITS:
        for r in rows:
            r["top"] = top_queries(r["members"], plan.get("itemVariants") or [plan["seed"]], RULES["topN"])
        out["unassigned"] = it.get("unassigned")
    return out


# ───────────────────────── 검증 ─────────────────────────

def discovered_strings(intent_files, cluster_file):
    S, CL = set(), set()
    for f in intent_files or []:
        try:
            S |= {C.norm_kw(x) for x in C.intent_strings(C.load_json(f))}
        except Exception:  # noqa: BLE001
            pass
    if cluster_file and Path(cluster_file).exists():
        comm, rels = C.cluster_parts(C.load_json(cluster_file))
        for a, b in rels:
            CL |= {C.norm_kw(a), C.norm_kw(b)}
        for v in comm.values():
            CL |= {C.norm_kw(x) for x in v}
    return S | CL, CL


def validate(plan, found, cluster_nodes):
    dropped = []

    def keep(kws, ctx):
        out = []
        for k in kws or []:
            if C.norm_kw(k) in found:
                out.append(k)
            else:
                dropped.append({"kw": k, "reason": "notfound", "ctx": ctx})
        return out
    t = plan.get("target") or {}
    ver = {C.norm_kw(k) for k in t.get("verify") or []}  # 유사의도로 만든 문자열 = keyword_info 측정값으로 검증 (측정값 없으면 build 가 뺀다)
    t["keywords"] = [k for k in t.get("keywords") or [] if C.norm_kw(k) in ver] + keep(
        [k for k in t.get("keywords") or [] if C.norm_kw(k) not in ver], "target")
    for g in ([plan["marketTarget"]] if (plan.get("marketTarget") or {}).get("items") else []) + (plan.get("external") or []):
        gv = {C.norm_kw(k) for k in g.get("verify") or []}  # method-v5 · 거울 문자열은 측정값으로 검증
        g["keywords"] = [k for k in g.get("keywords") or [] if C.norm_kw(k) in gv] + keep(
            [k for k in g.get("keywords") or [] if C.norm_kw(k) not in gv], "external")
        # 출처: plan 에 적힌 것(ds_classify 가 M5 규칙으로 태깅) 우선 · 없으면 cluster 등장 여부로
        g["_src"] = g.get("src") or ("cluster" if any(C.norm_kw(k) in cluster_nodes for k in g["keywords"]) else "intent")
    for g in (plan.get("internal") or {}).get("parts") or []:
        g["keywords"] = keep(g.get("keywords"), "internal")
    return dropped


# ───────────────────────── facts.md ─────────────────────────

def line(r, years):
    p = " / ".join(f"{y} {C.fmt_int(v)}" for y, v in zip(years, r["t"]))
    gt = C.fmt_pct(r["gt"]) if r["gt"] is not None else "—"
    yoy = "신규" if r.get("yoyNew") else C.fmt_pct(r["yoy"])
    s = f"- {r['name']} — {p} · 월평균 {C.fmt_int(r['avg'])} · 4년 {gt} · 전년 {yoy} · 방향 {r['dir']} · 키워드 {r.get('n', 1)}개"
    tg = [TAG_KO[x] for x in r.get("tags") or [] if x in TAG_KO]
    if r.get("since"):
        tg = [f"신규(since {r['since']})" if x == "신규" else x for x in tg]
    if tg:
        s += " · " + " · ".join(tg)
    if r.get("rel") is not None:
        s += f" · 기준선 대비 {C.fmt_pp(r['rel'])}"
    if r.get("share") is not None:
        s += f" · 비중 {C.fmt_share(r['share'])}"
    if r.get("src"):
        s += f" · 출처 {r['src']}"
    return s


def write_brief(F):
    Y = F["years"]
    S = F["sections"]
    o = [f"# facts · {F['seed']} · mode={F['mode']} · {Y[0]} ~ {Y[-1]}",
         "숫자는 이 문서에 적힌 문자열 그대로만 인용한다. 여기 없는 숫자를 만들면 lint 가 막는다.",
         f"판정 규칙 {RULES['version']} · 모드 판정 근거: {F.get('modeReason', '')}", "", "## KPI"]
    for k in F["kpis"]:
        o.append(f"- {k['id']}: {k['text']}")
    e = S["external"]
    sr = e["seedRow"]
    o += ["", "## section:external (1 시장 흐름 비교 · 분석 대상 vs 비교군)", f"- 판정: {e['verdictLabel']}"
          + (f" — 시드 4년 {C.fmt_pct(sr['gt'])} vs 외부 중앙값 {C.fmt_pct(e['baseline'])} · 차이 {C.fmt_pp(e['diff'])}" if e["baseline"] is not None else
             f" — 4년 변화율이 있는 외부 키워드 {e['nGt']}개 (최소 {RULES['minExternal']}개) 또는 시드 4년 변화율 미산출")]
    if e.get("loo"):
        o.append("- leave-one-out: " + ("안정" if e["loo"]["stable"] else "불안정 (빼면 판정이 바뀌는 항목: " + ", ".join(e["loo"]["flips"]) + ")"))
    o.append(f"- 기준: |시드 − 외부 중앙값| < {C.fmt_pp(RULES['platformPp']).lstrip('+')} → 업계와 같은 흐름 · 낮으면 업계 대비 약세 · 높으면 업계 대비 강세")
    o.append(f"- 비교군 {len(e['rows'])}개 중 4년 증가 {e['ups']}개 · 감소 {e['downs']}개")
    if e.get("small"):
        o.append(f"- 규모 기준으로 뺀 비교 대상 (최근 12개월 검색량 < 분석 대상의 {round(RULES['minScale'] * 100)}%): "
                 + " · ".join(f"{x['name']} {round(x['ratio'] * 100, 1)}%" for x in e["small"]) + " — 리포트·판정에 넣지 않는다")
    if e.get("seedLite"):
        o.append(f"- 대표 표기 커버 (최근 12개월 · 대표 표기 ÷ 상세 묶음 · 기준 {round(RULES['coverMin'] * 100)}%): " + " · ".join(
            f"{r['name']} {round(r['cover'] * 100, 1)}%" for r in [sr] + e["rows"] if r.get("cover") is not None))
        if e.get("lowCover"):
            o.append("- ⚠ 커버 낮음: " + " · ".join(f"{x['name']} {round(x['cover'] * 100, 1)}%" for x in e["lowCover"])
                     + " — 리포트 전에 보완한다: 상세 묶음에서 빠진 큰 표기를 확인해 대표 이름 순서를 바꾸거나(분석 대상: picks.synonyms 맨 앞 · 비교 대상: picks.external 의 M5a 첫 번째) 표기를 더하고 plan 부터 다시 (리포트에는 표시하지 않는다)")
        o.append("- 분석 대상 (비교용 대표 표기 묶음)")
    else:
        o.append("- 분석 대상")
    o.append(line(sr, Y))
    for m in sr.get("members") or []:
        o.append("  " + line({**m, "name": m["kw"], "n": 1}, Y))
    sd = e.get("seed") or {}
    if sd.get("upMonths") is not None:
        o.append(f"- 분석 대상 최근 12개월 중 전년 같은 달보다 높은 달 {sd['upMonths']}개월")
    if sr.get("peak"):
        o.append(f"- 분석 대상 48개월 정점 {sr['peak']['month']} {C.fmt_int(sr['peak']['v'])}")
    if sd.get("lead"):
        o.append(f"- 분석 대상 최대 검색어 '{sd['lead']['kw']}' 비중 {C.fmt_share(sd['lead']['share'])} (최근 12개월)")
    for r in e["rows"]:
        o.append(line(r, Y))
        # method-v5.2 · M5a · 이 비교 대상에 섞인 같은 뜻의 검색어 (측정값이 있어 들어간 것)
        o.append("  - 구성 검색어 " + " · ".join(m["kw"] for m in r.get("members") or []))
    if e.get("farPeers"):
        o.append("- ⚠ 가까운 시장 근거 없는 비교 대상 (method-v5.11): " + " · ".join(f"{x['name']}({x['near']})" for x in e["farPeers"])
                 + " — 같은 영역이라는 것만으로는 비교 시장이 아니다. M5-0 으로 다시 고르거나 사용자 확인(M5-7)을 받은 경우에만 그대로 낸다")
    i = S["internal"]
    o += ["", f"## section:internal ({(F.get('sectionOrder') or SECTION_ORDER).index('internal') + 1} 내부 동향 · 단위: {i.get('unit')})"]
    if i["rows"]:
        o.append(line({**i["total"], "n": sum(r["n"] for r in i["rows"])}, Y))
        o.append(f"- 상위 2개 비중 " + " / ".join(f"{y} {C.fmt_share(v)}" for y, v in zip(Y, i["conc"]["byYear"])))
        o.append(f"- 4년 증가 {i['ups']}개 · 감소 {i['downs']}개 · 가장 크게 증가 {i['topGrow']} · 가장 크게 감소 {i['topDrop']}")
        for r in i["rows"]:
            o.append(line(r, Y))
            if i.get("unit") in PURPOSE_UNITS:
                o.append(f"  - 구성비 {Y[0]} {C.fmt_share(r['shareY'][0])} → {Y[-1]} {C.fmt_share(r['shareY'][-1])} · 흐름 유형 {r['flow']}")
                if r.get("rankY"):
                    o.append("  - 순위 " + " → ".join(f"{x}위" for x in r["rankY"])
                             + (" · 신규 검색어 " + " / ".join(f"{y} {c}개" for y, c in zip(Y, r["newKwY"]) if c) if any(r.get("newKwY") or []) else ""))
                for q in r.get("top") or []:
                    o.append(f"  - 대표 검색어 '{q['kw']}' 최근 12개월 {C.fmt_int(q['last'])} · 전년 {C.fmt_pct(q['yoy'])}"
                             + (f" (합산 표기 {len(q['merged'])}개)" if q["merged"] else ""))
                # method-v5 · 인사이트가 '목적 안 상세'를 근거로 쓸 수 있게 검색어별 수치를 모두 적는다 (최근 12개월 순)
                tot = r["t"][-1] or 1
                for m in sorted(r.get("members") or [], key=lambda m: -(m["t"][-1] or 0)):
                    gt = ("신규(since " + m["since"] + ")") if "new" in (m.get("tags") or []) else C.fmt_pct(m.get("gt"))
                    o.append(f"    - 검색어 '{m['kw']}' 최근 12개월 {C.fmt_int(m['t'][-1])} · 목적 안 비중 {round(m['t'][-1] / tot * 100)}% "
                             f"· 4년 {gt} · 전년 {'신규' if m.get('yoyNew') else C.fmt_pct(m.get('yoy'))} · 4년 증감 {C.fmt_int(m['t'][-1] - m['t'][0])}")
                for x in r.get("subs") or []:  # method-v5 · 하위 묶음 (스튜디오 찾기 → 지역명 / 스튜디오 이름 / 찾기 표현)
                    o.append("  " + line({**x, "n": x.get("n", 1)}, Y).replace("- ", "- 하위 묶음 ", 1)
                             + f" · 목적 안 비중 {round(x['t'][-1] / tot * 100)}%")
                continue
            last = [x for x in r["myoy"][-12:]]
            pos = sum(1 for x in last if x is not None and x > 0)
            neg = sum(1 for x in last if x is not None and x < 0)
            o.append(f"  - 최근 12개월 전년 동월 대비 증가 {pos}개월 · 감소 {neg}개월")
            o.append("  - 구간별 비중 " + " / ".join(f"{y} {C.fmt_share(v)}" for y, v in zip(Y, r["shareY"])))
            for x in r.get("subs") or []:
                o.append("  " + line({**x, "n": x.get("n", 1)}, Y).replace("- ", "- 하위 SKU ", 1))
        if i.get("unassigned"):
            o.append(f"- 어느 의도 묶음에도 들지 않은 검색어 {i['unassigned']}개 (표에 넣지 않음)")
    o += ["", "## 데이터 참고 사항 (footer · 값은 바꾸지 않았다 · 구글 동일값 중복만 한 번 합산)"]
    for c in F["corrections"]:
        o.append("- " + corr_text(c))
    for d in F["dropped"]:
        o.append(f"- 제외({'finder 결과에 없음' if d['reason'] == 'notfound' else '측정값 없음'}) {d['kw']} [{d['ctx']}]")
    return "\n".join(o) + "\n"


def corr_text(c):
    """하단 '데이터 참고 사항' 문장. 값은 어느 경우에도 바꾸지 않는다 (구글 동일값 중복만 한 번 합산)."""
    if c["type"] == "step":
        eng, oth = ("구글", "네이버") if c["engine"] == "gg" else ("네이버", "구글")
        return (f"단일 엔진 급증({eng}) · '{c['kw']}' · {c['month']} · 3개월 평균 {C.fmt_int(c['before'])} → {C.fmt_int(c['after'])} · "
                f"같은 달 {oth} 변화 {C.fmt_pct(c['otherChange'])} · 값은 합계 그대로")
    if c["type"] == "dup":
        return f"구글 동일값 중복 · '{c['kw']}' = '{c['same_as']}' · 구글 값 한 번만 합산"
    if c["type"] == "notation":
        return (f"표기 이동 · [{c['bundle']}] · {c['month']} · '{c['from']}' {C.fmt_int(c['fromBefore'])} → {C.fmt_int(c['fromAfter'])} / "
                f"'{c['to']}' {C.fmt_int(c['toBefore'])} → {C.fmt_int(c['toAfter'])} · 같은 묶음이라 합계에 영향 없음")
    if c["type"] == "jump":
        return (f"특정 키워드 집중 증가 · [{c['bundle']}] · {c['month']} · 묶음 3개월 평균 {C.fmt_int(c['before'])} → {C.fmt_int(c['after'])} · "
                f"증가분의 {C.fmt_share(c['share'])}가 '{c['kw']}' (원래 몫 {C.fmt_share(c.get('prior'))})")
    if c["type"] == "spike":
        return f"일시적 급등 · [{c['bundle']}] · {c['month']} · {C.fmt_int(c['v'])} (전후 3개월 중앙값 {C.fmt_int(c['base'])})"
    return json.dumps(c, ensure_ascii=False)


# ───────────────────────── build ─────────────────────────

def sum_check(F):
    """method-v5.3.1 · 합계 검산. 리포트의 모든 선·행은 '묶음 안 검색어 월 검색량(네이버+구글)의 합'이어야 한다.
    - 묶음 행(타겟 · 비교 대상 · 제품 라인/검색 목적)의 48개월 값 = 구성 검색어 48개월 값의 합 (검색어 값은 중복 제거 뒤의 값)
    - 1년 구간 합계(t) = 그 12개월의 합 · 3 합계 = 묶음들의 합 · 1 '전체'(렌더) = 분석 대상 + 비교 대상 합
    중복 제거는 두 가지뿐이다: 띄어쓰기만 다른 표기(같은 측정 레코드) 한 번 · 구글 월별 값이 완전히 같은 검색어의 구글 값 한 번."""
    S, errs, n = F["sections"], [], 0

    def chk(label, r, members=True):
        nonlocal n
        n += 1
        m = r.get("m") or []
        if members and r.get("members"):
            sm = [sum((x["m"][i] or 0) for x in r["members"]) for i in range(len(m))]
            if sm != m:
                errs.append(f"{label} 월별 값 ≠ 구성 검색어 합")
        t = [sum(m[k * 12:(k + 1) * 12]) for k in range(len(r.get("t") or []))]
        if m and t != r.get("t"):
            errs.append(f"{label} 1년 구간 합계 ≠ 월별 합")
    chk(f"[1 분석 대상] {S['external']['seedRow']['name']}", S["external"]["seedRow"])
    for r in S["external"]["rows"]:
        chk(f"[1 비교] {r['name']}", r)
    inn = S["internal"]
    for r in inn.get("rows") or []:
        chk(f"[2] {r['name']}", r)
    if inn.get("rows"):
        tm = [sum(r["m"][i] for r in inn["rows"]) for i in range(len(inn["rows"][0]["m"]))]
        if inn["total"].get("m") and tm != inn["total"]["m"]:
            errs.append("[2] 합계 ≠ 묶음들의 합")
        n += 1
    return {"checked": n, "errors": errs}


def cmd_build(a):
    plan = C.load_json(a.plan)
    mode = plan.get("mode")
    if mode not in MODES:
        sys.exit(f"plan.mode 는 {MODES} 중 하나여야 한다 (받은 값: {mode})")
    recs = {}
    for f in reversed(a.kw):  # 앞 파일 우선
        recs.update(C.keyword_records(C.load_json(f)))
    st = Store(recs)
    found, cl = discovered_strings(a.intent, a.cluster)
    dropped = validate(plan, found, cl)
    B = Bundler(st)
    # method-v5.6 · 1 의 분석 대상 행 = 비교용 대표 표기 묶음 (plan.marketTarget) · method-v5.9 부터 카테고리 모드도 같다.
    # plan.target(상세 묶음)은 marketTarget 이 없을 때만 분석 대상 행으로 쓴다 (섹션으로는 내지 않는다).
    mt = plan.get("marketTarget") or {}
    mrow = None
    if mt.get("items") and mt.get("keywords"):
        mrow = B.row(mt.get("name") or plan["seed"], mt["keywords"], "target", seed=True)
    if not mrow:
        t = plan.get("target") or {}
        mrow = B.row(t.get("name") or plan["seed"], t.get("keywords") or [], "target", seed=True)
        lite = False
    else:
        lite = True
    if not mrow:
        sys.exit("분석 대상 묶음에 측정 가능한 키워드가 없다 — plan.marketTarget · plan.target 의 keywords 를 확인한다")
    last12 = mrow["myoy"][-12:]
    slead = None
    if mrow["members"]:
        sm = max(mrow["members"], key=lambda m: m["t"][-1])
        slead = {"kw": sm["kw"], "share": (sm["t"][-1] / mrow["t"][-1]) if mrow["t"][-1] else None}
    ext = build_external(B, plan, mrow)
    ext["seedRow"] = mrow
    ext["seedLite"] = lite
    ext["seed"] = {"upMonths": sum(1 for x in last12 if x is not None and x > 0), "lead": slead}
    if lite:  # method-v5.6.2 · 대표 표기 커버 검사 (v5.9 · 두 모드) — 상세 묶음은 별도 Bundler 로 재서 본 리포트 기록을 건드리지 않는다
        B2 = Bundler(st)
        low = []
        pairs = [(mrow, mt)] + [(r, next((g for g in plan.get("external") or [] if g["name"] == r["name"]), {})) for r in ext["rows"]]
        for r, g in pairs:
            br = B2.row(r["name"], list(dict.fromkeys((g.get("broad") or []) + [m["kw"] for m in r.get("members") or []])), "external")
            if br and br["t"][-1]:
                r["cover"] = min(1.0, r["t"][-1] / br["t"][-1])
                r["coverN"] = len(br.get("members") or [])
                if r["cover"] < RULES["coverMin"]:
                    r["coverLow"] = True
                    low.append({"name": r["name"], "cover": r["cover"]})
        ext["lowCover"] = low
    # method-v5.11 · 근접 근거 — 비교 대상이 '가까운 시장'(시드와 함께 찾은 근거)인지 (category · plan.external[].closeness)
    cl = {g["name"]: g.get("closeness") or {} for g in plan.get("external") or []}
    ext["farPeers"] = [{"name": r["name"], "near": cl[r["name"]].get("near")} for r in ext["rows"]
                       if r["name"] in cl and cl[r["name"]].get("near") and cl[r["name"]]["near"] != "가까움"]
    order = list(SECTION_ORDER)
    inn = build_internal(B, plan, st)
    kpis = [{"id": "external", "v": ext["diff"], "fmt": "pp",
             "text": f"{ext['verdictLabel']} (차이 {C.fmt_pp(ext['diff'])}, 외부 중앙값 {C.fmt_pct(ext['baseline'])})",
             "sub": f"{ext['verdictLabel']} · 외부 중앙값 {C.fmt_pct(ext['baseline'])}"},
            {"id": "seed", "v": mrow["gt"], "fmt": "pct",
             "text": f"{C.fmt_pct(mrow['gt'])} (월평균 {C.fmt_int(mrow['avg'])}, 전년 {C.fmt_pct(mrow['yoy'])})",
             "sub": f"월평균 {C.fmt_int(mrow['avg'])} · 전년 {C.fmt_pct(mrow['yoy'])}"}]
    if inn["rows"]:
        top = inn["rows"][0]
        kpis.append({"id": "internal", "v": top["share"], "fmt": "share",
                     "text": f"{top['name']} {C.fmt_share(top['share'])} (4년 {C.fmt_pct(top['gt'])})",
                     "sub": f"{top['name']} · 4년 {C.fmt_pct(top['gt'])}"})
    MIRROR = {C.norm_kw(k) for g in (plan.get("external") or []) + [plan.get("marketTarget") or {}] for k in g.get("verify") or []}
    # v5.6.6 · 판정 문장의 '시장' 이름 — entity: 대표 품목 이름(런닝화) · category: 상위 대분류
    market = ((plan.get("marketTarget") or {}).get("items") or [None])[0] if mode == "entity" else plan.get("upper")
    facts = {"version": VERSION, "rules": RULES["version"], "seed": plan["seed"], "mode": mode, "market": market,
             "modeReason": plan.get("modeReason", ""), "modeSignals": plan.get("modeSignals"), "gl": a.gl, "lang": a.lang, "date": a.date,
             "months": st.months, "years": st.years, "sectionOrder": order, "kpis": kpis,
             "sections": {"external": ext, "internal": inn},
             "corrections": B.corrections,
             # method-v5 · 비교군 거울 문자열(검증용 생성)에 측정값이 없으면 '검색되지 않는 표현'이라 제외 목록에 올리지 않고 개수만 남긴다
             "dropped": dropped + [d for d in B.dropped if not (d["reason"] == "nodata" and C.norm_kw(d["kw"]) in MIRROR)],
             "mirror": {"made": len(MIRROR), "kept": len([k for k in MIRROR if st.has_data(k)]),
                        "keptKw": [k for g in plan.get("external") or [] for k in g.get("verify") or [] if st.has_data(k)]},
             "method": plan.get("method"), "picks": plan.get("picks"),
             "itemVariants": plan.get("itemVariants"), "upper": plan.get("upper"), "scope": plan.get("scope"),
             "verified": [k for k in (plan.get("target") or {}).get("verify") or [] if st.has_data(k)],
             "counts": {"keywords": len({C.norm_kw(m["kw"]) for r in [mrow] + ext["rows"] + inn["rows"] for m in r["members"]})}}
    chk = sum_check(facts)  # method-v5.3.1 · 그래프 선 = 묶음 검색어 합계 · 전체 = 묶음 합계 (어긋나면 리포트를 만들지 않는다)
    facts["sumCheck"] = chk
    if chk["errors"]:
        print("ERROR  합계 검산 실패 — " + " / ".join(chk["errors"][:10]))
        sys.exit(12)
    Path(a.out).write_text(json.dumps(facts, ensure_ascii=False), encoding="utf-8")
    Path(a.brief).write_text(write_brief(facts), encoding="utf-8")
    nd = sum(1 for d in facts["dropped"] if d["reason"] == "nodata")
    nf = sum(1 for d in facts["dropped"] if d["reason"] == "notfound")
    print(f"wrote {a.out} · mode={mode} · 판정={ext['verdictLabel']} · 외부 {len(ext['rows'])} · 내부 {len(inn['rows'])} · "
          f"측정값 없음 {nd} · finder 미발견 {nf} · 합계 검산 {chk['checked']}개 OK"
          + (f" · ⚠ 대표 표기 커버 낮음 {', '.join(x['name'] for x in ext.get('lowCover') or [])}" if ext.get("lowCover") else "")
          + (f" · 규모 미달 제외 {', '.join(x['name'] for x in ext.get('small') or [])}" if ext.get("small") else "")
          + (f" · ⚠ 가까운 시장 근거 없는 비교 대상 {', '.join(x['name'] + '(' + x['near'] + ')' for x in ext['farPeers'])}"
             " — 리포트 전에 M5-0 으로 다시 고르거나 사용자 확인(M5-7)을 받는다" if ext.get("farPeers") else "")
          + (f" · ⚠ 판정 흔들림 (빼면 바뀜: {', '.join(ext['loo']['flips'])}) — 리포트 전에 비교군 구성을 다시 본다"
             if ext.get("loo") and not ext["loo"]["stable"] else ""))


# ───────────────────────── lint ─────────────────────────

def report_labels(lang):
    """리포트 언어 라벨 (jp · us narrative 는 번역된 판정어 · 묶음 이름을 쓴다). 없으면 빈 사전."""
    p = HERE.parent / "labels" / f"demand-shift.{lang or 'kr'}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def cmd_lint(a):
    F = C.load_json(a.facts)
    N = C.load_json(a.narrative)
    LB = report_labels(F.get("lang"))
    brief = write_brief(F)
    allowed = {C.canon_number(x) for x in C.extract_numbers(brief)}
    allowed |= {x.lstrip("+") for x in allowed}  # 양수는 부호 없이 써도 같은 숫자다 (15.0%p = +15.0%p)
    errs, warns = [], []
    if not N.get("overview"):
        errs.append("overview 누락")
    secs = N.get("sections") or {}
    order = F.get("sectionOrder") or SECTION_ORDER
    for sid in secs:
        if sid not in SECTION_ORDER:
            errs.append(f"없는 섹션 id: {sid} (허용: {SECTION_ORDER})")
    # method-v5 · 섹션 요약 문장(lead)은 없앴다 — 판정 카드(코드 문장)와 섹션 맨 위 인사이트 카드가 대신한다
    for sid in SECTION_ORDER:
        if (secs.get(sid) or {}).get("lead"):
            errs.append(f"sections.{sid}.lead 는 v5 에서 없앴다 — 결론은 insights 카드로 쓴다")
    lab = F["sections"]["external"]["verdictLabel"]
    others = [v for k, v in VERDICT_LABEL.items() if v != lab]
    vkey = next((k for k, v in VERDICT_LABEL.items() if v == lab), None)
    others += [LB[f"verdict.{k}"] for k in VERDICT_LABEL if k != vkey and LB.get(f"verdict.{k}") and LB[f"verdict.{k}"] not in others]
    for v in others:
        if v in json.dumps(N, ensure_ascii=False):
            errs.append(f"코드 판정과 다른 판정어 '{v}' 가 narrative 에 있다")
    njson = json.dumps(N, ensure_ascii=False)
    jumps = {c["bundle"] for c in F["corrections"] if c["type"] == "jump"}
    if re.search(r"(단일|한|특정) 키워드 (급증|집중)", njson) and not jumps:
        errs.append("narrative 가 '특정 키워드 집중 증가'를 말하지만 facts 에 해당 기록이 없다")
    for bad in ("계단", "재집계", "중복버킷", "제외·"):
        if bad in njson:
            errs.append(f"narrative 에 옛 보정 용어 '{bad}' 가 있다 — 리포트 용어(단일 엔진 급증·구글 동일값 중복)로 쓴다")
    if N.get("synthesis"):  # method-v5 · 종합 탭 제거 — 정리는 actions 로 (lm-queryfinder-report 와 같은 구성)
        errs.append("synthesis 는 v5 에서 없앴다 — 정리는 actions{synthesis·insights·now·future} 로 쓴다")
    if N.get("actions"):  # method-v5 · 정리는 섹션 안으로 — sections.{sid}.insights · actions
        errs.append("actions 는 쓰지 않는다 — sections.{sid}.insights(1~3) · sections.{sid}.actions(0~3, kind now|future) 로 쓴다")
    for sid, sec in (N.get("sections") or {}).items():
        ins, acts = sec.get("insights") or [], sec.get("actions") or []
        if sid == "internal":
            names = {r["name"] for r in F["sections"]["internal"]["rows"]}
            names |= {LB["bundle." + n] for n in list(names) if LB.get("bundle." + n)}  # 화면에 번역된 묶음 이름도 인정
            for it in ins:
                if it.get("group") not in names:
                    errs.append(f"sections.internal.insights 카드마다 group(검색 목적 이름)이 필요하다 — 허용: {sorted(names)}")
        lo = 0 if sid == "external" else 1  # 1 시장 동향은 판정 카드가 결론이라 인사이트를 생략할 수 있다 (같은 말 반복 금지)
        if not (lo <= len(ins) <= 3):
            errs.append(f"sections.{sid}.insights 는 {lo}~3개")
        if acts:  # method-v5 · 실행 제안은 없앴다
            errs.append(f"sections.{sid}.actions 는 v5 에서 없앴다 — 지운다")
        for it in ins + acts:
            if not (it.get("title") and it.get("body")):
                errs.append(f"sections.{sid} 카드는 title·body 둘 다")
        # method-v5 · actions 는 우선순위 순서로 쓴다 (kind 표식 없음)

    def walk(o, p):
        if isinstance(o, str):
            for b in BANNED:
                if b in o:
                    errs.append(f"{p}: 금지 표현 '{b}'")
            if re.search(r"경로|이동이 확인|이탈 경로|옮겨 ?갔|옮겨 ?가|이동했|넘어갔|넘어가", o):
                warns.append(f"{p}: v3 는 경로 검증을 하지 않는다 — 경로·이동 주장 문장을 쓰지 않는다")
            for tok in C.extract_numbers(o):
                if C.canon_number(tok) not in allowed:
                    warns.append(f"{p}: 숫자 '{tok}' 가 facts 에 없다")
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, f"{p}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{p}[{i}]")
    walk(N, "narrative")
    for x in errs:
        print("ERROR  " + x)
    for x in warns:
        print("WARN   " + x)
    if errs:
        sys.exit(2)
    if warns:
        print(f"\n경고 {len(warns)}건 — facts.md 의 문자열로 고친다.")
        sys.exit(3)
    print("lint OK")


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--plan", required=True)
    b.add_argument("--kw", nargs="+", required=True)
    b.add_argument("--intent", nargs="*", default=[])
    b.add_argument("--cluster")
    b.add_argument("--gl", default="kr")
    b.add_argument("--lang", default="kr")
    b.add_argument("--date", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--brief", required=True)
    l = sp.add_parser("lint")
    l.add_argument("--facts", required=True)
    l.add_argument("--narrative", required=True)
    a = ap.parse_args()
    cmd_build(a) if a.cmd == "build" else cmd_lint(a)


if __name__ == "__main__":
    main()
