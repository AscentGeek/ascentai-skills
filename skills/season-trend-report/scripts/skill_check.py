#!/usr/bin/env python3
"""skill_check.py · season-trend-report 고유 검사 (pre-commit 이 스킬 변경 시 자동 실행 · zip 에는 실리지 않는다).

리포트 화면 문구는 labels/season-trend.{kr,jp,us}.json 에서만 온다. 렌더 코드에 한국어 문구가 남으면
jp · us 리포트에 한국어가 섞인다. 렌더 결과로는 '애초에 라벨로 빠지지 않은 문자열'이 안 보이고
데이터에 따라 타지 않는 분기도 있어서, 렌더 결과가 아니라 **소스**를 본다 (search-demand-report 와 같은 방식).

  1) 렌더 코드의 한글 문자열 리터럴 · 독스트링 · 주석 · print(콘솔) 는 제외. 허용 = '# i18n-ok' 표시 줄
     (근거 창 JS 는 st_render.py 안의 문자열이라 여기서 함께 잡힌다)
  2) 라벨 3벌 · 키 집합이 같은가 · 자리표시자({x})가 kr 과 같은가 · jp · us 값에 한글이 없는가
     자리표시자 예외 · {wa}(kr 조사) · {a}{b} / {A}{B}(월 숫자 / 월 이름 · 언어마다 고른다)

사용: python3 skills/season-trend-report/scripts/skill_check.py   · exit 0 통과 / 1 실패
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[가-힣]")
RENDER = ["render/st_render.py", "render/st_common.py"]
LANGS = ("kr", "jp", "us")
SLOT_FREE = {"wa", "a", "b", "A", "B"}


def check_python(rel, errs):
    src = (ROOT / rel).read_text(encoding="utf-8")
    lines = src.split("\n")
    tree = ast.parse(src)
    skip = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.Module)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant):
            skip.add(id(n.body[0].value))
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "print":
            for m in ast.walk(n):
                skip.add(id(m))
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str) and HANGUL.search(n.value)):
            continue
        if id(n) in skip or "i18n-ok" in lines[n.lineno - 1]:
            continue
        # JS 블록 안의 /* 주석 */ · // 주석 은 화면에 나가지 않는다
        body = re.sub(r"/\*.*?\*/", "", n.value, flags=re.S)
        body = re.sub(r"(^|\s)//[^\n]*", "", body)
        if not HANGUL.search(body):
            continue
        hit = HANGUL.search(body)
        errs.append(f"{rel}:{n.lineno} 한글 문구 · 라벨로 옮기거나 계약값이면 '# i18n-ok' · {body[max(0, hit.start()-15):hit.start()+25]!r}")


def check_labels(errs):
    data = {lg: json.loads((ROOT / f"labels/season-trend.{lg}.json").read_text(encoding="utf-8")) for lg in LANGS}
    keys = set(data["kr"])
    slot = re.compile(r"\{(\w+)\}")
    for lg in ("jp", "us"):
        if set(data[lg]) != keys:
            errs.append(f"labels {lg} 키가 kr 과 다르다 · 빠짐 {sorted(keys - set(data[lg]))[:5]} · 더 있음 {sorted(set(data[lg]) - keys)[:5]}")
        for k in keys & set(data[lg]):
            if set(slot.findall(data["kr"][k])) - SLOT_FREE != set(slot.findall(data[lg][k])) - SLOT_FREE:
                errs.append(f"labels {lg}.{k} 자리표시자가 kr 과 다르다")
            if HANGUL.search(data[lg][k]):
                errs.append(f"labels {lg}.{k} 값에 한글이 있다")
    for lg in LANGS:
        if len(data[lg]["fmt.months"].split(",")) != 12:
            errs.append(f"labels {lg}.fmt.months 는 쉼표로 나눈 12개여야 한다")


def main():
    errs = []
    for rel in RENDER:
        check_python(rel, errs)
    check_labels(errs)
    if errs:
        print("✗ season-trend-report 고유 검사 실패")
        for e in errs:
            print("  " + e)
        return 1
    print("  · season-trend-report 고유 검사 · 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
