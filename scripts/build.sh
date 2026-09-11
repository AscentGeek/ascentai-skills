#!/usr/bin/env bash
# build.sh · _core + skills/<name> + locales/<locale> → dist/lm-<name>[-<locale>].zip
#
# 왜 빌드인가:
#   스킬 하나에서 언어에 따라 바뀌는 건 문서와 라벨뿐이고(약 6%), 코드는 전부 같다.
#   언어별로 폴더를 복제하면 코드가 언어 수만큼 불어나 버그 수정이 그만큼 늘어난다.
#   그래서 소스는 스킬당 1벌로 두고, zip 만 (스킬 × 언어) 만큼 만든다.
#
#   skills/ 에 보이는 폴더 = 스킬 수 (언어를 늘려도 안 늘어난다)
#   dist/ 에 나오는 zip   = 스킬 수 × 언어 수
#
# 사용:
#   scripts/build.sh                 # 전 스킬 · 각 skill.yaml 의 locales 전부
#   scripts/build.sh queryfinder-report        # 한 스킬만
#   scripts/build.sh queryfinder-report kr     # 한 스킬 · 한 언어만
#
# 산출 zip 의 내부 구조는 기존과 동일하다 (스킬 루트 아래 _shared/ api/ scripts/ references/).
# 구조를 바꾸면 설치된 스킬이 자기 파일을 못 찾으므로 여기서 원래 배치로 되돌려 놓는다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE="$ROOT/_core"
SRC="$ROOT/skills"
OUT="$ROOT/dist"

ONLY_SKILL="${1:-}"
ONLY_LOCALE="${2:-}"

# kr 은 접미사 없음 (기본 판) · 나머지는 -<locale>
zip_name() {
  local name="$1" loc="$2"
  if [[ "$loc" == "kr" ]]; then echo "lm-$name"; else echo "lm-$name-$loc"; fi
}

# skill.yaml 에서 값 하나 읽기 (외부 의존 없이)
yval() { sed -n "s/^$2: *//p" "$1" | head -1 | tr -d '"'; }

build_one() {
  local name="$1" loc="$2"
  local sdir="$SRC/$name"
  local ldir="$sdir/locales/$loc"
  [[ -d "$ldir" ]] || { echo "  ✗ $name/$loc · locales/$loc 없음" >&2; return 1; }

  local skill_name; skill_name="$(zip_name "$name" "$loc")"
  local version;    version="$(yval "$sdir/skill.yaml" version)"
  local vendor;     vendor="$(yval "$sdir/skill.yaml" vendor_chart)"

  local stage; stage="$(mktemp -d)"
  local d="$stage/$skill_name"
  mkdir -p "$d"/{_shared/{render,styles,templates,labels},api,scripts,references}

  # ── 공통 코드 (_core) ──
  cp "$CORE"/styles/*.css              "$d/_shared/styles/"
  cp "$CORE"/render/*.py               "$d/_shared/render/"
  cp "$CORE"/api/*.py                  "$d/api/"
  cp "$CORE"/scripts/*.py              "$d/scripts/"

  # ── 스킬 전용 ──
  cp "$sdir"/render/*.py               "$d/_shared/render/"
  cp "$sdir"/styles/*.css              "$d/_shared/styles/" 2>/dev/null || true
  cp "$sdir"/templates/*               "$d/_shared/templates/"
  [[ "$vendor" == "true" ]] && { mkdir -p "$d/_shared/vendor"; cp "$sdir"/vendor/* "$d/_shared/vendor/"; }
  [[ -d "$sdir/prompts" ]] && cp -R "$sdir/prompts" "$d/references/prompts"
  cp "$sdir/LICENSE.txt"               "$d/LICENSE.txt"

  # ── 로케일 (문서 · 라벨) ──
  cp "$ldir/SKILL.md"                  "$d/SKILL.md"
  cp "$ldir"/references/*.md           "$d/references/" 2>/dev/null || true
  cp "$ldir"/labels/*.json             "$d/_shared/labels/"

  # ── 플레이스홀더 주입 ──
  #   _core 의 logging.py · log_event.py 는 스킬·버전을 모른다. 여기서 박아 넣는다.
  #   안 박으면 admin 에 __SKILL_NAME__ 으로 기록된다.
  local py
  for py in "$d/api/logging.py" "$d/scripts/log_event.py"; do
    sed -i '' -e "s/__SKILL_NAME__/$skill_name/g" -e "s/__SKILL_VERSION__/$version/g" "$py"
  done

  # ── zip ──
  mkdir -p "$OUT"
  rm -f "$OUT/$skill_name.zip"
  (cd "$stage" && zip -qr "$OUT/$skill_name.zip" "$skill_name" \
      -x "*.pyc" -x "**/__pycache__/**" -x "*.DS_Store")
  rm -rf "$stage"

  echo "  ✓ $skill_name.zip  v$version  ($(unzip -Z1 "$OUT/$skill_name.zip" | wc -l | tr -d ' ')파일)"
}

echo "▶ 빌드"
for sdir in "$SRC"/*/; do
  name="$(basename "$sdir")"
  [[ -n "$ONLY_SKILL" && "$name" != "$ONLY_SKILL" ]] && continue
  [[ -f "$sdir/skill.yaml" ]] || { echo "  · $name · skill.yaml 없음 · 건너뜀"; continue; }

  locales="$(sed -n 's/^locales: *\[\(.*\)\]/\1/p' "$sdir/skill.yaml" | tr -d ' ' | tr ',' ' ')"
  for loc in $locales; do
    [[ -n "$ONLY_LOCALE" && "$loc" != "$ONLY_LOCALE" ]] && continue
    build_one "$name" "$loc"
  done
done
echo "▶ 완료 · $OUT"
