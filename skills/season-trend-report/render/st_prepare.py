#!/usr/bin/env python3
"""st_prepare.py · intent_finder · cluster_finder 결과에서 keyword_info 로 조회할 검색어 목록을 만든다.

  python3 st_prepare.py --intent lm_intent_seed.json [--cluster lm_cluster_seed.json] --gl kr --out-dir "$WORKDIR"

출력
  kw_list.json         · 조회할 검색어 전체 (intent 순서 먼저, 다음 cluster 노드) + 출처
  kw_params_<n>.json   · keyword_info 호출 파라미터 (1,000개씩). 이 파일 내용을 그대로 <PARAMS> 로 쓴다.

관련성 필터는 여기서 하지 않는다 — 조회 후 st_build.py 가 config.json 의 rel/exc 로 거른다.
(조회 전에 거르면 필터를 고칠 때마다 keyword_info 를 다시 사야 한다.)
exit · 0 성공 / 1 입력 오류
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import st_common as C  # noqa: E402

CHUNK = 1000


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--intent", required=True)
    p.add_argument("--cluster")
    p.add_argument("--gl", default="kr")
    p.add_argument("--out-dir", required=True)
    a = p.parse_args()

    rel = C.intent_strings(C.load_json(a.intent))
    if not rel:
        print("❌ intent_finder 결과가 비었습니다 · 시드를 확인하세요", file=sys.stderr)
        return 1
    clu = C.cluster_nodes(C.load_json(a.cluster)) if a.cluster and Path(a.cluster).exists() else []

    seen, kws, src = set(), [], {}
    for s in rel:
        k = C.norm_kw(s)
        if k and k not in seen:
            seen.add(k)
            kws.append(s)
            src[s] = "rel"
    for s in clu:
        k = C.norm_kw(s)
        if k and k not in seen:
            seen.add(k)
            kws.append(s)
            src[s] = "clu"

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("kw_params_*.json"):
        old.unlink()
    (out / "kw_list.json").write_text(json.dumps({"keywords": kws, "src": src}, ensure_ascii=False), encoding="utf-8")
    n = 0
    for i in range(0, len(kws), CHUNK):
        n += 1
        (out / f"kw_params_{n}.json").write_text(
            json.dumps({"keywords": kws[i:i + CHUNK], "gl": a.gl, "data_type": "all"}, ensure_ascii=False), encoding="utf-8")
    print(f"intent {len(rel)} · cluster 노드 {len(clu)} (새로 {sum(1 for v in src.values() if v == 'clu')}) · 조회 {len(kws)}개 → keyword_info {n}회")
    for i in range(1, n + 1):
        print(f"  kw_params_{i}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
