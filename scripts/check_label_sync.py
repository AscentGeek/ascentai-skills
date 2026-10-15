#!/usr/bin/env python3
"""check_label_sync.py · 스킬 간 같아야 하는 라벨이 갈렸는지 검사한다.

왜 필요한가
-----------
라벨은 스킬 폴더마다 따로 있다(`skills/<스킬>/labels/<슬러그>.{kr,jp,us}.json`).
대부분의 키는 그 스킬 고유라 문제가 없지만, 화면의 공용 문구 — 「종합 시사점」·
「핵심 인사이트」·「한국/일본/미국」 — 는 어느 리포트에서나 같아야 한다.

폴더가 갈려 있으니 한쪽만 고치면 조용히 어긋난다. 실제로 그랬다: 번역 수정을
쿼리파인더에만 반영했더니 클러스터·패스파인더의 JP 가 옛 문구로 남아, 같은
화면 요소가 리포트마다 다른 말로 나왔다(2026-10 · 15건).

무엇을 검사하나
---------------
`SHARED_KEYS` 에 적힌 키만 본다. 두 개 이상의 스킬에 있으면서 값이 다르면 실패다.
**모든 중복 키를 보지 않는다** — 스킬마다 달라야 하는 중복도 많기 때문이다.
예: `personaWhoLabel` 은 클러스터가 "이 클러스터를 검색하는 사람들", 쿼리가
"이 키워드를 검색하는 사람들" 이라 같으면 오히려 틀린다.

새 공용어가 생기면 SHARED_KEYS 에 추가한다. 반대로 "이 키는 스킬마다 달라야
한다" 가 밝혀지면 목록에서 뺀다 — 목록이 곧 **의도의 기록**이다.

사용
  python3 scripts/check_label_sync.py            # 검사
  python3 scripts/check_label_sync.py --list     # 지금 갈린 키를 보여준다(후보 발굴)

exit · 0 통과 / 1 불일치
"""
import argparse
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LANGS = ("kr", "jp", "us")

# 스킬 간 **같아야 하는** 키. 화면 공용 문구와 고정 명칭만 올린다.
SHARED_KEYS = {
    # 시장·국가 이름
    "country.KR", "country.JP", "country.US",
    "report.marketLabel.KR", "report.marketLabel.JP", "report.marketLabel.US",
    # 검색 의도 4종 — 리포트마다 다른 말로 부르면 안 된다
    "customerAnalysis.stage.informational",
    "customerAnalysis.stage.navigational",
    "customerAnalysis.stage.commercial",
    "customerAnalysis.stage.transactional",
    # 액션·인사이트 절 제목
    "customerAnalysis.dash.actionsEmpty",
    "customerAnalysis.dash.actionsFutureTitle",
    "customerAnalysis.dash.actionsInsightsTitle",
    "customerAnalysis.dash.actionsNowTitle",
    "customerAnalysis.dash.actionsSynthesisTitle",
    # 페르소나 카드 공용 문구
    "customerAnalysis.dash.personaEvidenceMore",
    "customerAnalysis.dash.personaEvidenceNote",
    "customerAnalysis.dash.personaInsightLabel",
    "customerAnalysis.dash.personaInsightTitle",
    "customerAnalysis.dash.personaKeywordCount",
    "customerAnalysis.dash.personaMetaStage",
    "customerAnalysis.dash.personaNeeds",
    "customerAnalysis.dash.personaPainpoint",
    "customerAnalysis.dash.personaSituation",
    "customerAnalysis.dash.personaVolumeBadge",
    "customerAnalysis.dash.personaWhoBadge",
    # 검색량 툴팁 · 번역 버튼
    "customerAnalysis.dash.volTooltipClose",
    "customerAnalysis.dash.volTooltipHint",
    "customerAnalysis.dash.volTooltipTitle",
    "customerAnalysis.dash.keywordTranslateBtn",
}


def _slug(skill_dir: Path):
    y = skill_dir / "skill.yaml"
    if not y.exists():
        return None
    for line in y.read_text(encoding="utf-8").splitlines():
        if line.startswith("slug:"):
            return line.split(":", 1)[1].strip().strip('"')
    return None


def load_all():
    """{(key, lang): {skill: value}}"""
    out = collections.defaultdict(dict)
    for d in sorted((ROOT / "skills").iterdir()):
        if not d.is_dir():
            continue
        slug = _slug(d)
        if not slug:
            continue
        for lang in LANGS:
            f = d / "labels" / f"{slug}.{lang}.json"
            if not f.exists():
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                print(f"  ✗ {f.relative_to(ROOT)} · JSON 오류 {e}", file=sys.stderr)
                continue
            for k, v in data.items():
                out[(k, lang)][d.name] = v
    return out


def _report(groups, title, hint):
    print(f"\n{title}")
    for (key, lang), per in groups:
        print(f"  {key}  [{lang}]")
        for skill, val in sorted(per.items()):
            print(f"      {skill:<24} {val}")
    print(f"\n{hint}")


def main():
    ap = argparse.ArgumentParser(description="스킬 간 공용 라벨이 갈렸는지 검사")
    ap.add_argument("--list", action="store_true",
                    help="SHARED_KEYS 밖에서 갈린 중복 키도 보여준다 (후보 발굴용 · 실패시키지 않는다)")
    args = ap.parse_args()

    all_labels = load_all()

    bad = [((k, l), per) for (k, l), per in sorted(all_labels.items())
           if k in SHARED_KEYS and len(per) > 1 and len(set(per.values())) > 1]

    if bad:
        _report(bad, f"✗ 공용 라벨이 스킬 간 갈렸습니다 · {len(bad)}건",
                "같은 화면 문구는 어느 리포트에서나 같아야 합니다. 한쪽에 맞춰 주세요.\n"
                "스킬마다 달라야 하는 키라면 scripts/check_label_sync.py 의 SHARED_KEYS 에서 빼세요.")
        return 1

    checked = sum(1 for (k, _), per in all_labels.items() if k in SHARED_KEYS and len(per) > 1)
    print(f"✓ 공용 라벨 일치 · {len(SHARED_KEYS)}키 정의 · {checked}건 대조")

    if args.list:
        other = [((k, l), per) for (k, l), per in sorted(all_labels.items())
                 if k not in SHARED_KEYS and len(per) > 1 and len(set(per.values())) > 1]
        if other:
            _report(other, f"· SHARED_KEYS 밖에서 갈린 중복 키 {len(other)}건 (참고)",
                    "대부분은 스킬마다 달라야 하는 것이 정상입니다(분석 단위가 다릅니다).\n"
                    "같아야 하는 것이 섞여 있으면 SHARED_KEYS 에 추가하세요.")
        else:
            print("· SHARED_KEYS 밖에서 갈린 중복 키 없음")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
