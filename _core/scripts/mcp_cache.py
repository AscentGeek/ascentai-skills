#!/usr/bin/env python3
"""mcp_cache.py · MCP 응답 세션 캐시 · 같은 대화에서 같은 데이터를 두 번 사지 않는다.

MCP 는 호출자가 LLM 이고 응답이 컨텍스트(또는 호스트가 저장한 파일)로 온다.
코드가 호출 순간에 끼어들 자리가 없으므로, 캐시를 **호출 앞뒤 두 지점**으로 나눈다.

  lookup · MCP 를 부르기 전에 물어본다. 있으면 파일로 꺼내주고 exit 0 → LLM 은 호출을 건너뛴다.
  store  · MCP 를 부른 뒤 덤프한 파일을 넘긴다. 다음 번 lookup 이 이걸 찾는다.

왜 중요한가 · MCP 는 **호출당 1 크레딧**이다(키워드 수와 무관 · 실측으로 12개든 141개든 1).
그래서 같은 호출을 다시 하는 것이 그대로 손실이다 — 회차를 이어서 돌거나 턴이 끊겼을 때
앞서 산 호출을 다시 사지 않게 캐시가 막는다.
  (사내 DaaS REST 판은 키워드 1개당 10 crd 로 과금된다. **이 스킬은 MCP 판이다** — 섞지 마라.)

키 규칙은 sha256(도구이름 + 정렬된 파라미터). 파라미터가 하나만 달라도 다른 키다.
`user_query` 는 키에서 뺀다(질의 문구가 달라져도 같은 데이터를 가리키므로, 넣으면
캐시가 무력화되고 크레딧만 더 나간다).

저장 위치 · ~/.lima-agents/mcp-cache/<session_id>/<tool>__<hash>.json
스킬이 달라도 같은 세션·같은 파라미터면 적중한다. 호출 하나가 파일 하나라,
사람이 열어보고 디버깅할 수 있다.

사용:
  # ① 호출 전 — 있으면 꺼내 쓰고 MCP 건너뛰기
  python3 scripts/mcp_cache.py lookup keyword_info \
      --params '{"keywords":["a","b"],"gl":"kr","data_type":"all"}' \
      --out "{WORKDIR}/lm_keyword_info.json"
  # exit 0 = 적중 (--out 에 복사 완료) · exit 2 = 미적중 (MCP 호출 필요)

  # ② 호출 후 — 덤프한 파일을 캐시에 넣기
  python3 scripts/mcp_cache.py store keyword_info \
      --params '{"keywords":["a","b"],"gl":"kr","data_type":"all"}' \
      --file "{WORKDIR}/lm_keyword_info.json"

환경 변수:
  LIMA_MCP_REFRESH=1   이 세션에서 캐시를 무시하고 항상 미적중 처리 (강제 재호출)

exit code · lookup: 0 적중 / 2 미적중 / 1 오류 · store: 0 성공 / 1 오류
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

CACHE_ROOT = Path.home() / ".lima-agents" / "mcp-cache"

# 캐시를 대화창 단위로 가르는 세션 ID · 호스트가 env 로 준 값만 쓴다.
# 머신 전역 파일로 폴백하지 않는다 — 동시에 열린 다른 대화창의 캐시를 집어
# 엉뚱한 데이터를 돌려줄 수 있기 때문이다. env 가 없으면 캐시를 쓰지 않는다
# (매번 MCP 를 부르지만 틀린 답을 주지는 않는다).
_HOST_SESSION_ENVS = (
    "CLAUDE_CODE_REMOTE_SESSION_ID",  # Claude Desktop / Code · 클라우드 세션 (실측)
    "CLAUDE_CODE_SESSION_ID",         # Claude · 로컬 세션 (실측)
    "CODEX_THREAD_ID",                # Codex Desktop · 대화별 thread ID (실측)
    "OPENAI_CODEX_SESSION_ID",
    "OPENAI_SESSION_ID",
    "CODEX_SESSION_ID",
    "CHATGPT_SESSION_ID",
    "GEMINI_SESSION_ID",
    "GOOGLE_AI_SESSION_ID",
    "LIMA_SESSION_ID",                # 범용 폴백 · 호스트가 env 를 안 주면 직접 세팅
)

# 캐시 키에서 제외할 파라미터 · 데이터 동일성과 무관한 것들
_KEY_EXCLUDE = ("user_query",)

# 도구별 최소 무결성 규칙 · store 시점에 덤프가 잘렸는지 잡는다.
# MCP 응답을 LLM 이 손으로 옮겨 적는 구조라, 여기서 안 잡으면 반쪽짜리 데이터가
# 조용히 캐시에 눌러앉아 이후 실행까지 오염시킨다.
_MIN_RECORDS = {
    "keyword_info": 1,
    "intent_finder": 1,
    "cluster_finder": 1,
    "path_finder": 1,
}


def _refresh_enabled() -> bool:
    return os.getenv("LIMA_MCP_REFRESH", "").strip().lower() in ("1", "true", "yes")


def _session_id() -> str | None:
    for name in _HOST_SESSION_ENVS:
        v = os.getenv(name)
        if v and v.strip():
            return f"lima-agents-{v.strip()}"
    return None


def _cache_key(tool: str, params: dict) -> str:
    """sha256(도구이름 + 정렬된 파라미터) · 파라미터 하나만 달라도 다른 키."""
    scrubbed = {k: v for k, v in params.items() if k not in _KEY_EXCLUDE}
    canonical = json.dumps({"tool": tool, "params": scrubbed},
                           ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]


def _cache_file(sid: str, tool: str, key: str) -> Path:
    return CACHE_ROOT / sid / f"{tool}__{key}.json"


def _load_params(args: argparse.Namespace) -> dict | None:
    raw = args.params
    if args.params_file:
        try:
            raw = Path(args.params_file).read_text(encoding="utf-8")
        except OSError as e:
            print(f"❌ 파라미터 파일을 읽지 못했습니다 · {e}", file=sys.stderr)
            return None
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"❌ 파라미터가 올바른 JSON 이 아닙니다 · {e}", file=sys.stderr)
        return None
    if not isinstance(params, dict):
        print("❌ 파라미터가 JSON 객체가 아닙니다", file=sys.stderr)
        return None
    return params


def unwrap_content_blocks(payload: object) -> object:
    """MCP 콘텐츠 블록 래퍼를 벗겨 실제 봉투를 돌려준다.

    호스트가 큰 응답을 파일로 저장할 때 `[{"type":"text","text":"<JSON 문자열>"}]`
    형태로 감싸는 경우가 있다(실측 · Claude.ai 웹 컨테이너). 이걸 그대로 두면
    레코드가 1건으로 세어지고 집계기가 "레코드를 찾지 못했습니다" 로 죽는다.

    이미 봉투(dict)면 그대로 돌려준다 · 판단이 안 서면 원본을 그대로 돌려준다.
    """
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list) and payload:
        # 콘텐츠 블록 배열인가 · 모든 원소가 type/text 를 가진 dict
        blocks = [b for b in payload
                  if isinstance(b, dict) and b.get("type") == "text" and "text" in b]
        if blocks and len(blocks) == len(payload):
            joined = "".join(str(b.get("text") or "") for b in blocks)
            try:
                return json.loads(joined)
            except json.JSONDecodeError:
                return payload
    return payload


def _record_count(payload: object) -> int:
    """응답에서 레코드 수를 센다 · 봉투 모양이 도구마다 달라 관대하게 훑는다."""
    payload = unwrap_content_blocks(payload)
    if isinstance(payload, list):
        return len(payload)
    if not isinstance(payload, dict):
        return 0
    data = payload.get("data")
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        # cluster_finder · communities(dict) + rels(list)
        n = 0
        for v in data.values():
            if isinstance(v, (list, dict)):
                n += len(v)
        return n
    return 0


def cmd_lookup(args: argparse.Namespace) -> int:
    params = _load_params(args)
    if params is None:
        return 1

    if _refresh_enabled():
        print(f"· {args.tool} · LIMA_MCP_REFRESH=1 · 캐시 무시 · MCP 호출 필요")
        return 2

    sid = _session_id()
    if not sid:
        print(f"· {args.tool} · 세션 ID 없음 · 캐시 미사용 · MCP 호출 필요")
        return 2

    key = _cache_key(args.tool, params)
    src = _cache_file(sid, args.tool, key)
    if not src.exists():
        print(f"· {args.tool} · 캐시 미적중 · MCP 호출 필요")
        return 2

    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        # 깨진 캐시는 없는 것으로 친다 · 지우고 재호출을 유도
        print(f"· {args.tool} · 캐시 파일 손상({e}) · 삭제 후 MCP 호출 필요", file=sys.stderr)
        try:
            src.unlink()
        except OSError:
            pass
        return 2

    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, out)
    except OSError as e:
        print(f"❌ 캐시를 꺼내지 못했습니다 · {e}", file=sys.stderr)
        return 1

    n = _record_count(payload)
    print(f"✓ {args.tool} · 캐시 적중 · 레코드 {n:,}건 · 크레딧 소모 없음 → {out}")
    print("  → MCP 호출을 건너뛰고 다음 단계로 진행하세요.")
    return 0


def cmd_store(args: argparse.Namespace) -> int:
    params = _load_params(args)
    if params is None:
        return 1

    src = Path(args.file)
    if not src.exists():
        print(f"❌ 저장할 파일이 없습니다 · {src}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ 덤프 파일이 올바른 JSON 이 아닙니다 · {e}", file=sys.stderr)
        print("  → MCP 응답을 다시 덤프하세요. 잘린 JSON 은 캐시에 넣지 않습니다.", file=sys.stderr)
        return 1

    # 콘텐츠 블록 래퍼가 씌워져 있으면 벗겨서 봉투로 정규화한다.
    # 호스트가 큰 응답을 파일로 저장할 때 [{"type":"text","text":"..."}] 로 감싸는데,
    # 그대로 두면 집계기가 레코드를 못 찾는다. 여기서 한 번 벗겨 두면 이후 단계가
    # 모두 같은 모양을 본다 (캐시에 들어가는 것도 벗겨진 형태).
    unwrapped = unwrap_content_blocks(payload)
    if unwrapped is not payload:
        payload = unwrapped
        try:
            src.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            print(f"· {args.tool} · MCP 콘텐츠 블록 래퍼를 벗겨 정규화했습니다 → {src.name}")
        except OSError as e:
            print(f"❌ 정규화한 응답을 쓰지 못했습니다 · {e}", file=sys.stderr)
            return 1

    # 덤프 무결성 · 레코드가 0건이면 옮겨 적기가 실패한 것이다.
    n = _record_count(payload)
    need = _MIN_RECORDS.get(args.tool, 1)
    if n < need:
        print(f"❌ {args.tool} · 레코드 {n}건 · 최소 {need}건 필요 · 캐시에 넣지 않습니다",
              file=sys.stderr)
        print("  → 덤프가 잘렸거나 빈 응답입니다. 응답 원문을 다시 확인하세요.", file=sys.stderr)
        return 1

    # 기대 건수 대조 (선택) · LLM 이 봉투에서 읽은 수와 실제 덤프가 맞는지
    if args.expect is not None and n != args.expect:
        print(f"❌ {args.tool} · 덤프 {n:,}건 ≠ 기대 {args.expect:,}건 · 캐시에 넣지 않습니다",
              file=sys.stderr)
        print("  → 덤프 중 누락이 있습니다. 응답 전체를 다시 옮기세요.", file=sys.stderr)
        return 1

    sid = _session_id()
    if not sid:
        print(f"· {args.tool} · 세션 ID 없음 · 캐시 저장 생략 (진행에는 지장 없음)")
        return 0

    key = _cache_key(args.tool, params)
    dst = _cache_file(sid, args.tool, key)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    except OSError as e:
        # 캐시는 부가 기능 · 저장 실패가 흐름을 막지 않는다
        print(f"· {args.tool} · 캐시 저장 실패({e}) · 진행에는 지장 없음", file=sys.stderr)
        return 0

    print(f"✓ {args.tool} · 캐시 저장 · 레코드 {n:,}건 → {dst.name}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="MCP 응답 세션 캐시 · lookup(호출 전) · store(호출 후)")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("lookup", "store"):
        sp = sub.add_parser(name)
        sp.add_argument("tool",
                        choices=["intent_finder", "keyword_info",
                                 "cluster_finder", "path_finder"],
                        help="MCP 도구 이름 (bare)")
        g = sp.add_mutually_exclusive_group(required=True)
        g.add_argument("--params", help="MCP 요청 파라미터 JSON 문자열")
        g.add_argument("--params-file", help="MCP 요청 파라미터 JSON 파일 경로")
        if name == "lookup":
            sp.add_argument("--out", required=True, help="적중 시 응답을 쓸 경로")
        else:
            sp.add_argument("--file", required=True, help="덤프한 응답 JSON 파일 경로")
            sp.add_argument("--expect", type=int, default=None,
                            help="기대 레코드 수 · 봉투에서 읽은 값과 대조 (선택)")

    args = p.parse_args()
    return cmd_lookup(args) if args.cmd == "lookup" else cmd_store(args)


if __name__ == "__main__":
    raise SystemExit(main())
