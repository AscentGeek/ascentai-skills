#!/usr/bin/env python3
"""skill_check.py · search-demand-report 고유 검사 (pre-commit 이 스킬 변경 시 자동 실행 · zip 에는 실리지 않는다).

리포트 화면 문구는 labels/demand-shift.{kr,jp,us}.json 에서만 온다. 렌더 코드에 한국어 문구가 남으면
jp · us 리포트에 한국어가 섞인다. 렌더 결과(센티널 라벨)로는 '애초에 라벨로 빠지지 않은 문자열'이 안 보이고
경우의 수에 따라 타지 않는 분기도 있어서, 렌더 결과가 아니라 **소스**를 본다 (#8 brand-competition 과 같은 방식).

  1) 렌더 코드의 한글 문자열 리터럴 · 독스트링 · 주석은 제외. 허용 = '# i18n-ok' 표시 줄 · LEGACY 함수
  2) 차트 스크립트(templates/ds_assets.js.html)의 한글 문자열 리터럴 · 주석은 제외
  3) 라벨 3벌 · 키 집합이 같은가 · 자리표시자({x})가 kr 과 같은가 · jp · us 값에 한글이 없는가 (bundle.* 키 이름은 예외)

사용: python3 skills/search-demand-report/scripts/skill_check.py   · exit 0 통과 / 1 실패
"""
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[가-힣]")
RENDER = ["render/ds_render.py", "render/ds_charts.py", "render/ds_common.py"]
# v5 화면에서 쓰지 않는 함수 (어디서도 호출되지 않는다 · 기획 원본과 맞추기 쉽게 지우지 않고 둔다).
# 다시 쓰게 되면 여기서 빼고 문구를 라벨로 옮긴다.
LEGACY = {
    "render/ds_render.py": {"_kw_share_v5", "intent_mix_table", "intent_top", "corrections_html", "sec_actions"},
    "render/ds_charts.py": {"monthly_bars", "year_overlay", "flow_card", "bump_chart", "bump_list"},
}
# 화면 문구가 아닌 계약값 (lint 가 서술문 숫자를 읽는 단위)
CONTRACT_FUNCS = {"render/ds_common.py": {"extract_numbers", "canon_number"}}
LANGS = ("kr", "jp", "us")


def check_python(rel, errs):
    src = (ROOT / rel).read_text(encoding="utf-8")
    lines = src.split("\n")
    tree = ast.parse(src)
    doc, owner = set(), {}
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.Module)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(getattr(n.body[0], "value", None), ast.Constant):
            doc.add(n.body[0].value.lineno)
        if isinstance(n, ast.FunctionDef):
            for i in range(n.lineno, n.end_lineno + 1):
                owner.setdefault(i, n.name)
    skip = LEGACY.get(rel, set()) | CONTRACT_FUNCS.get(rel, set())
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str) and HANGUL.search(n.value)):
            continue
        if n.lineno in doc or "i18n-ok" in lines[n.lineno - 1] or owner.get(n.lineno) in skip:
            continue
        if rel == "render/ds_common.py" and owner.get(n.lineno) is None and "_NUM_RE" in lines[n.lineno - 1]:
            continue  # lint 숫자 단위 (계약값)
        errs.append(f"{rel}:{n.lineno} 한글 문구 · 라벨로 옮기거나 계약값이면 '# i18n-ok' · {n.value[:40]!r}")


def check_js(rel, errs):
    src = (ROOT / rel).read_text(encoding="utf-8")
    body = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    for i, line in enumerate(body.split("\n"), 1):
        code = re.sub(r"(^|\s)//.*$", "", line)
        for m in re.finditer(r"'[^'\n]*'|\"[^\"\n]*\"", code):
            if HANGUL.search(m.group(0)):
                errs.append(f"{rel}:{i} 한글 문구 · js.* 라벨(DSL)로 옮긴다 · {m.group(0)[:40]!r}")


def check_labels(errs):
    data = {lg: json.loads((ROOT / f"labels/demand-shift.{lg}.json").read_text(encoding="utf-8")) for lg in LANGS}
    keys = set(data["kr"])
    slot = re.compile(r"\{(\w+)(?:\|\w+)?\}")
    for lg in ("jp", "us"):
        if set(data[lg]) != keys:
            errs.append(f"labels {lg} 키가 kr 과 다르다 · 빠짐 {sorted(keys - set(data[lg]))[:5]} · 더 있음 {sorted(set(data[lg]) - keys)[:5]}")
        for k in keys & set(data[lg]):
            if set(slot.findall(data["kr"][k])) != set(slot.findall(data[lg][k])):
                errs.append(f"labels {lg}.{k} 자리표시자가 kr 과 다르다")
            if HANGUL.search(data[lg][k]):
                errs.append(f"labels {lg}.{k} 값에 한글이 있다")
            if "|" in "".join(re.findall(r"\{[^}]*\}", data[lg][k])):
                errs.append(f"labels {lg}.{k} 조사 표시({{x|은는}})는 kr 틀에서만 쓴다")


def main():
    errs = []
    for rel in RENDER:
        check_python(rel, errs)
    check_js("templates/ds_assets.js.html", errs)
    check_labels(errs)
    for e in errs:
        print("  ✗ " + e)
    print(f"  · search-demand-report 고유 검사 · {'실패 ' + str(len(errs)) + '건' if errs else '통과'}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
