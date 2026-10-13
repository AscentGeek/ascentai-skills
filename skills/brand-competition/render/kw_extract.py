#!/usr/bin/env python3
"""화면에 실제로 뜨는 검색어만 모은다 — 번역 단계의 입력.

회차 폴더의 judge/curate/walk 를 읽어 리포트가 글자로 찍는 시장 언어 문자열
(카테고리 · 묶음 · 세부 수요 · 경쟁 브랜드 · 대표 연관어)만 뽑는다. 수집한 원응답
전량이 아니다 — 화면에 없는 말을 번역하면 크레딧도 시간도 헛돈다.

자사 브랜드명은 넣지 않는다. 표지 제목·<title>·data-* 속성에 같은 문자열이 들어가는데
그 자리에는 두 벌 span 을 심을 수 없어, 번역하면 한 리포트 안에서 표기가 갈린다.
"""
import argparse, json, os, sys


def collect(run):
    R = run.rstrip("/") + "/"
    own = json.load(open(R + "config.json", encoding="utf-8"))["brand"]
    J = json.load(open(R + "work/judge.json", encoding="utf-8"))
    C = json.load(open(R + "work/curate.json", encoding="utf-8")); C.pop("_note", None)
    out = []

    def add(v):
        v = (v or "").strip()
        if v and v != own and v not in out:
            out.append(v)

    for c, meta in C.items():
        add(c)
        add((meta or {}).get("group"))
        for b in (meta or {}).get("comp") or []:
            add(b)
        for f in (meta or {}).get("cep") or []:
            add(f)
    for x in J:
        add(x.get("term"))
        for c in x.get("comp") or []:
            add(c.get("brand"))
        for q in x.get("ceps") or []:
            add(q.get("cep")); add(q.get("kw"))
        w = x.get("walk") or {}
        add(w.get("top"))
    wk = R + "work/walk.json"
    if os.path.exists(wk):
        for v in json.load(open(wk, encoding="utf-8")).values():
            add((v or {}).get("top"))
    return own, out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Collect on-screen search terms for translation.")
    ap.add_argument("run", help="run folder (config.json · work/)")
    ap.add_argument("--out", required=True, help="output JSON path")
    a = ap.parse_args(argv)
    own, kws = collect(a.run)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"own": own, "count": len(kws), "keywords": kws}, f,
                  ensure_ascii=False, indent=2)
    print(f"{a.out} {len(kws)}개 (자사 「{own}」 는 제외)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
