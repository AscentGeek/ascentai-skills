#!/usr/bin/env python3
"""ds_scope.py · 넓은 시드(뷰티 · 나이키 단독)를 리포트가 잘 나오는 시드로 좁힌다 (references/scope.md · scope-v1).

  score   : scope.json(LLM 후보) + keyword_info + intent_finder(후보 전부 한 번에) → 후보별 리포트 적합도 판정
            exit 0  = 적합 1개 → 그 후보로 자동 진행 (통지만)
            exit 10 = 적합 2개 이상 → scope.md 고정 질문 (상위 3개 + 직접 입력)
            exit 12 = 적합 0개 → 주의 후보를 보여 주고 직접 입력을 받는다
  extract : 고른 후보에 귀속된 연관 검색어를 lm_intent_seed.json 으로 꺼낸다 (충분하면 intent_finder 재호출을 아낀다)

scope.json (LLM · 후보는 품목 = 사는 물건 한 종류 · 시드 연관 검색어에 보인 것은 src intent, 아니면 analyst):
  {"from": "뷰티", "gl": "kr", "type": "domain", "candidates": [{"name": "쿠션", "variants": ["쿠션"], "src": "analyst"}, ...]}
  gl = 시장 (kr · jp · us · 없으면 kr) · 구매 탐색 단어와 넓은 시드 기준값이 시장마다 다르다 (ds_market.py)
  {"from": "나이키", "type": "brand", "brand": ["나이키", "nike"], "candidates": [{"name": "러닝화"}, {"name": "운동화"}]}

표준 라이브러리만 사용한다.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ds_common as C  # noqa: E402
import ds_classify as K  # noqa: E402

VERSION = "scope-v2"
# headMax · tokenMax 는 시장별 (ds_market · set_market 이 채운다). kr 은 2026-10-06 실측 보정값, jp · us 는 kr 값을 임시로 쓴다.
SCOPE = {
    "headMax": 0.45,      # 넓은 시드: 시드가 검색어 끝(찾는 대상 자리)에 오는 비율 < 값
    "tokenMax": 0.70,     #            그리고 시드가 독립 단어로 쓰인 비율 < 값 (다른 이름 안에 붙어 쓰임 · 디올뷰티 · 뷰티라운지의원)
    "calibrated": True,   # 이 시장 기준값이 실측 보정됐는가 (False 면 brief 에 경고)
    "minAvg": 1000,       # 후보 최근 12개월 월평균 < 값 → 부적합 (변화 해석이 불안정)
    "minRelated": 30,     # 후보에 귀속된 연관 검색어 < 값 → 주의 (2·3 묶음이 얇다)
    "minSiblings": 3,     # 1 시장 동향 비교군 최소 (고른 후보 외 부적합이 아닌 후보 수)
    "reuseMin": 300,      # extract: 귀속 검색어가 이 이상이면 intent_finder(시드) 재호출 없이 쓴다
    "showTop": 3,         # 질문에 올리는 후보 수 (+ 직접 입력)
}


def set_market(gl):
    """시장 기준값 · 구매 탐색 단어를 그 시장 것으로 (ds_classify 와 함께 바꾼다)."""
    K.set_market(gl)
    SCOPE.update(K.MARKET["scope"])


def head_token_share(q_variants, strings):
    """시드(또는 후보)가 든 검색어 중 · 끝 단어가 시드로 끝나는 비율(head) · 시드가 독립 단어인 비율(token)."""
    vs = [v.replace(" ", "").lower() for v in q_variants]
    mine = [K.norm(x) for x in strings if any(v in x.replace(" ", "").lower() for v in vs)]
    if not mine:
        return 0, None, None
    head = sum(1 for x in mine if any(x.replace(" ", "").endswith(v) for v in vs)) / len(mine)
    token = sum(1 for x in mine if any(v in x.split(" ") or (" " + v + " ") in (" " + x + " ") for v in [w.lower() for w in q_variants])) / len(mine)
    return len(mine), round(head, 3), round(token, 3)


def gate(seed, seed_intent):
    """넓은 시드인가 (check 가 부른다). domain = 업종·영역어 · brandwide = 여러 품목을 파는 브랜드 단독."""
    # check 는 ds_classify 를 __main__ 으로 돌리므로 여기서 import 한 K 는 별도 인스턴스다 · 시장을 seed 로 다시 맞춘다
    set_market(seed.get("gl"))
    q = [seed["seed"]] if seed["mode"] == "category" else (seed.get("brand") or [seed["seed"]])
    n, head, token = head_token_share(q, seed_intent)
    sig = {"related": n, "headShare": head, "tokenShare": token}
    if seed.get("seedType") == "domain" or (seed["mode"] == "category" and head is not None
                                           and head < SCOPE["headMax"] and token < SCOPE["tokenMax"]):
        return "broad", sig, (f"'{seed['seed']}'가 찾는 대상 자리(검색어 끝)에 오는 비율 {head:.0%} · 독립 단어 비율 {token:.0%} — "
                              f"품목이 아니라 여러 품목을 묶는 영역어로 보인다" if head is not None else "seedType = domain")
    if seed["mode"] == "entity" and seed.get("itemOptional") and len(seed.get("brandItems") or []) >= 2:
        return "brandwide", sig, f"브랜드 단독 시드이고 품목이 {len(seed['brandItems'])}개({' · '.join(seed['brandItems'][:4])}) — 어느 품목의 수요인지 정해야 한다"
    return None, sig, ""


def years(rec):
    t = (rec or {}).get("total") or []
    if len(t) < 48:
        return None
    t = t[-48:]
    return [sum(t[i * 12:(i + 1) * 12]) for i in range(4)]


def score(scope, kw, strings):
    brand = scope.get("brand") or []
    out = []
    for c in scope["candidates"]:
        vs = c.get("variants") or [c["name"]]
        query = f"{brand[0]} {c['name']}" if scope.get("type") == "brand" and brand else c["name"]
        y = years(kw.get(C.norm_kw(query)))
        avg = round(y[-1] / 12) if y else 0
        gt = (y[-1] / y[0] - 1) if y and y[0] > 0 else None
        req = [v.replace(" ", "").lower() for v in vs]
        mine = [x for x in strings if any(v in x.replace(" ", "").lower() for v in req)
                and (not brand or scope.get("type") != "brand" or any(b.replace(" ", "").lower() in x.replace(" ", "").lower() for b in brand))]
        n, head, token = head_token_share(vs, mine)
        buy = (sum(1 for x in mine if K.MK.text_has(K.norm(x), K.FIT["buyWords"], K.MARKET["substr"])) / len(mine)) if mine else 0
        hard, soft = [], []
        if not y:
            hard.append("48개월 검색량 없음")
        elif avg < SCOPE["minAvg"]:
            hard.append(f"월평균 {avg:,} < {SCOPE['minAvg']:,} — 변화 해석이 불안정")
        if y and gt is None:
            hard.append("첫 12개월이 0 — 4년 변화 산출 불가")
        if head is not None and head < SCOPE["headMax"] and scope.get("type") != "brand":
            hard.append(f"찾는 대상 자리 비율 {head:.0%} — 아직 넓은 영역어")
        if n < SCOPE["minRelated"]:
            soft.append(f"연관 검색어 {n}개 < {SCOPE['minRelated']} — 타겟·내부 묶음이 얇다")
        grade = "부적합" if hard else ("주의" if soft else "적합")
        out.append({"name": c["name"], "query": query, "src": c.get("src", "analyst"), "avg": avg, "gt": gt,
                    "years": y, "related": n, "headShare": head, "buyShare": round(buy, 3),
                    "grade": grade, "why": hard + soft})
    order = {"적합": 0, "주의": 1, "부적합": 2}
    out.sort(key=lambda r: (order[r["grade"]], -r["avg"]))
    ok = [r for r in out if r["grade"] != "부적합"]
    sib_ok = len(ok) - 1 >= SCOPE["minSiblings"]
    return {"version": VERSION, "from": scope["from"], "type": scope.get("type"), "rows": out,
            "fit": [r["name"] for r in out if r["grade"] == "적합"], "siblingsEnough": sib_ok,
            # scope-v2 · 선택지 라벨 = 분석할 검색어 그대로 ('삼성 냉장고' · '선크림') — '삼성 > 냉장고' 같은 계층 표기를 쓰지 않는다
            "show": [r["query"] for r in out if r["grade"] == "적합"][:SCOPE["showTop"]],
            "options": [f"{r['query']} · 월평균 {r['avg']:,}" for r in out if r["grade"] == "적합"][:SCOPE["showTop"]],
            # 직접 입력 예시 = 선택지에 없는 후보 하나 (없으면 첫 후보) — 입력 형식을 보여 주는 용도
            "example": next((r["query"] for r in out if r["grade"] != "부적합" and r["query"] not in
                             [x["query"] for x in out if x["grade"] == "적합"][:SCOPE["showTop"]]),
                            next((r["query"] for r in out), None))}


def brief(R):
    o = [f"# scope · '{R['from']}' 좁히기 · {VERSION}",
         "판정은 코드가 했다. 아래 표와 '질문' 줄을 scope.md 고정 형식 그대로 사용자에게 보인다.", "",
         "| 후보 | 월평균(최근 12개월) | 4년 변화 | 연관 검색어 | 찾는 대상 자리 | 구매 탐색 결합 | 판정 | 이유 |", "|---|---|---|---|---|---|---|---|"]
    for r in R["rows"]:
        o.append(f"| {r['query']} | {r['avg']:,} | {C.fmt_pct(r['gt']) if r['gt'] is not None else '—'} | {r['related']} | "
                 f"{'—' if r['headShare'] is None else format(r['headShare'], '.0%')} | "
                 f"{r['buyShare']:.0%} | {r['grade']} | {' · '.join(r['why']) or '—'} |")
    o.append("")
    if not SCOPE["calibrated"]:
        o.append("- 주의: 이 시장의 넓은 시드 기준값(찾는 대상 자리 · 독립 단어 비율)은 아직 실측 보정 전이다 (kr 값을 임시 사용)")
    if not R["siblingsEnough"]:
        o.append(f"- 주의: 부적합이 아닌 후보가 {SCOPE['minSiblings'] + 1}개 미만 — 1 시장 동향 비교군을 upper·analyst 로 보충해야 한다")
    kind = "브랜드" if R.get("type") == "brand" else "영역"
    how = ("‘브랜드 + 품목’ 한 검색어" if R.get("type") == "brand" else "품목 하나")
    ex = R.get("example") or ("삼성 냉장고" if R.get("type") == "brand" else "선크림")
    o.append(f"- 안내: ‘{R['from']}’은(는) 주제가 넓어서 그대로 분석하면 비교할 시장과 검색 의도가 흐려집니다. "
             f"세부 시장을 정하면 더 정확하게 분석할 수 있습니다 — {kind}라면 {how}로 정해 주세요 (예: {ex}).")
    if R["show"]:
        o.append("- 선택지: " + " / ".join(R["options"]) + f" / 직접 입력 (예: {ex}) · 추천 = " + R["show"][0])
    else:
        o.append(f"- 선택지: 적합 후보 없음 — 주의 후보를 보이고 직접 입력을 받는다 (예: {ex})")
    return "\n".join(o) + "\n"


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("score")
    s.add_argument("--scope", required=True)
    s.add_argument("--kw", nargs="+", required=True)
    s.add_argument("--intent", required=True, help="lm_intent_scope.json (후보 전부 한 번에)")
    s.add_argument("--out", required=True)
    s.add_argument("--brief", required=True)
    x = sp.add_parser("extract")
    x.add_argument("--scope", required=True)
    x.add_argument("--intent", required=True)
    x.add_argument("--pick", required=True)
    x.add_argument("--out", required=True)
    a = ap.parse_args()
    scope = C.load_json(a.scope)
    set_market(scope.get("gl"))  # method-v5.12 · 시장별 기준값 · 없으면 kr
    strings = C.intent_strings(C.load_json(a.intent))
    if a.cmd == "score":
        kw = {}
        for f in reversed(a.kw):
            kw.update(C.keyword_records(C.load_json(f)))
        R = score(scope, kw, strings)
        Path(a.out).write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
        Path(a.brief).write_text(brief(R), encoding="utf-8")
        nf = len(R["fit"])
        print(f"후보 {len(R['rows'])} · 적합 {nf} · " + ("자동 진행: " + R["show"][0] if nf == 1 else ("질문" if nf >= 2 else "적합 없음 · 직접 입력")))
        sys.exit(0 if nf == 1 else (10 if nf >= 2 else 12))
    c = next((c for c in scope["candidates"] if c["name"] == a.pick), {"name": a.pick})
    vs = [v.replace(" ", "").lower() for v in (c.get("variants") or [c["name"]])]
    brand = [b.replace(" ", "").lower() for b in scope.get("brand") or []] if scope.get("type") == "brand" else []
    mine = [x for x in strings if any(v in x.replace(" ", "").lower() for v in vs)
            and (not brand or any(b in x.replace(" ", "").lower() for b in brand))]
    if len(mine) < SCOPE["reuseMin"]:
        print(f"귀속 검색어 {len(mine)}개 < {SCOPE['reuseMin']} — intent_finder 로 시드를 다시 부른다")
        sys.exit(13)
    Path(a.out).write_text(json.dumps({"data": mine, "from": "scope"}, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {a.out} · {len(mine)}개 (scope intent 에서 재사용)")


if __name__ == "__main__":
    main()
