#!/usr/bin/env python3
"""check_upstream.py · 정본(lm-brand-competition)과 이 리포의 이식본이 갈라졌는지 본다.

`skills/brand-competition/` 은 **빌드 산출**이다. 정본은 `~/git/lm-brand-competition/` 이고,
기능·판정 변경은 거기서 먼저 일어난다. 이 스크립트는 그 사이가 벌어졌는지 두 가지로 검사한다.

  ① 같아야 하는 파일 — 판정·수집 스크립트 6종은 **바이트 동일**해야 한다.
     다르면 한쪽만 고쳐진 것이고, 조회 목록(분모)과 판정이 서로 다른 집합을 보게 된다.
  ② 손으로 옮기는 파일 — 렌더러·문서는 이식하며 모양이 바뀐다(문자열 → 라벨 · 한국어 → 영어 ·
     경로 재배치). 기계로 못 맞추므로 **마지막으로 맞춘 시점의 해시**를 적어 두고,
     정본이 그 뒤로 바뀌었으면 「이식 필요」로 알린다.

사용:
  python3 scripts/check_upstream.py            # 검사
  python3 scripts/check_upstream.py --record   # 지금 상태를 맞춘 시점으로 기록

정본 경로는 $LM_BRAND_COMPETITION_SRC 로 바꿀 수 있다. 없으면 검사를 건너뛴다(exit 0) —
정본이 없는 머신·CI 에서 빌드를 막지 않기 위해서다.

exit · 0 통과 또는 건너뜀 / 1 갈라짐
"""
import hashlib, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "brand-competition"
RECORD = SKILL / "upstream.json"
DEFAULT_SRC = Path.home() / "git" / "lm-brand-competition" / "skills" / "lm-brand-competition"

# ① 바이트 동일해야 하는 것 · 정본 경로 → 이식본 경로
MIRRORED = {
    "scripts/judge.py":      "render/judge.py",
    "scripts/cep_deep.py":   "render/cep_deep.py",
    "scripts/check_run.py":  "render/check_run.py",
    "scripts/brandkw.py":    "render/brandkw.py",
    "scripts/modifiers.py":  "render/modifiers.py",
    "scripts/pathcand.py":   "render/pathcand.py",
    "scripts/mcp_cache.py":  "../../_core/scripts/mcp_cache.py",
}
# ② 손으로 옮기는 것 · 정본이 바뀌면 이식이 필요하다
PORTED = [
    "scripts/build_report.py",      # → render/render_report.py (문자열이 라벨로 빠져 있다)
    "scripts/fetch_dl.py",          # → render/fetch_dl.py (mcp_cache 경로만 다르다)
    "scripts/assets/report.css",    # → styles/brand-competition.css (+ 렌더러 인라인분)
    "SKILL.md",                     # → SKILL.md(규약) + references/brand-competition.md(절차) · 영어
    "references/judging-rules.md",
    "references/limits.md",
    "references/report-spec.md",
]

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()[:16]

def src_root():
    env = os.environ.get("LM_BRAND_COMPETITION_SRC")
    return Path(env) if env else DEFAULT_SRC

def main(argv):
    src = src_root()
    if not src.is_dir():
        print(f"· 정본을 찾지 못해 건너뜁니다: {src}")
        print("  (경로는 $LM_BRAND_COMPETITION_SRC 로 지정)")
        return 0

    ver = ""
    sk = (src / "SKILL.md").read_text(encoding="utf-8")
    for line in sk.splitlines():
        if line.strip().startswith("version:"):
            ver = line.split(":", 1)[1].strip().strip('"'); break

    if "--record" in argv:
        rec = {"_note": "정본을 마지막으로 맞춘 시점. check_upstream.py --record 로 갱신한다.",
               "upstream_version": ver,
               "ported": {p: sha(src / p) for p in PORTED}}
        RECORD.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"✓ 기록했습니다 · 정본 v{ver} · 파일 {len(PORTED)}개 → {RECORD.relative_to(ROOT)}")
        return 0

    bad = []
    print(f"▶ 정본 v{ver} · {src}")
    for a, b in MIRRORED.items():
        pa, pb = src / a, (SKILL / b).resolve()
        if not pa.exists() or not pb.exists():
            bad.append(f"없음: {a} 또는 {b}"); continue
        if pa.read_bytes() != pb.read_bytes():
            bad.append(f"**바이트가 달라졌다** {a} ≠ {b} — 한쪽만 고쳐졌다")
    print(f"  ① 같아야 하는 파일 {len(MIRRORED)}개 · {'일치' if not bad else str(len(bad))+'건 어긋남'}")

    stale = []
    if RECORD.exists():
        rec = json.loads(RECORD.read_text(encoding="utf-8"))
        for p, h in rec.get("ported", {}).items():
            f = src / p
            if not f.exists(): stale.append(f"{p} (정본에서 사라짐)"); continue
            if sha(f) != h: stale.append(p)
        print(f"  ② 손으로 옮기는 파일 {len(rec.get('ported',{}))}개 · "
              f"{'변화 없음' if not stale else str(len(stale))+'개가 정본에서 바뀜'}"
              f"   (맞춘 시점 v{rec.get('upstream_version','?')})")
    else:
        print("  ② 맞춘 시점 기록이 없습니다 — `--record` 로 한 번 적어 두세요")

    if bad:
        print("\n✗ 갈라짐")
        for x in bad: print("   ", x)
    if stale:
        print("\n⚠ 정본이 바뀌었습니다 — 이식이 필요합니다")
        for x in stale: print("   ", x)
        print("   옮긴 뒤 `python3 scripts/check_upstream.py --record` 로 시점을 갱신하세요.")
    if not bad and not stale:
        print("\n✓ 정본과 맞아 있습니다")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
