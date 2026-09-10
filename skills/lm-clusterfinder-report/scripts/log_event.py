#!/usr/bin/env python3
"""log_event.py · 대화 이벤트 CLI 진입점 (v0.9.2 · turn 폐지).

v0.9.2 배경 (2026-08-12 · 사용자 결정):
turn 개념이 로깅 이슈의 절반 이상 뿌리였음 (turn 밀림·fcntl 락·정렬 뒤바뀜 등). 로깅 목적은
세션 시작~끝 대화 기록 유지 하나 · turn 그룹핑은 admin UI 가 event_type 기준으로 자동.
turn 파일 상태·락·payload turn 필드 모두 삭제. CLI --turn 옵션은 하위 호환용으로 무시.

Usage:
  # Turn 1 원샷 (세션 시작 + 첫 발화·응답 페어)
  python3 scripts/log_event.py --session-init \\
      --user-id "..." --environment "claude" \\
      --user-utterance "..." --assistant-response "..."

  # Turn 2+ 매 응답 마지막 · emit_turn.py 로 통합 발행 (권장)
  python3 scripts/emit_turn.py --user-utterance "..." --assistant-response "..."

  # tool_call 은 매 도구 호출 직후 · 별도 발행 (crd 실측 배지 위해)
  python3 scripts/log_event.py --type tool_call --tool <name> \\
      --request-body '{...}' --used-credits-delta <int> --used-credits-cumulative <int>

  # 이벤트 발행 이력 조회 (event_type 만 · turn 개념 없음 · v0.9.2 재정의)
  python3 scripts/log_event.py --verify-recent

Fire-and-forget · exit code 0 항상.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

from api import logging as lima_log  # noqa: E402


def _default_session_id() -> str | None:
    return lima_log.resolve_conversation_id()


def main() -> int:
    p = argparse.ArgumentParser(description="lima-agents 대화 이벤트 로깅 CLI")
    p.add_argument("--session-id", default=None,
                   help="세션 ID · 미지정 시 · session-init 은 새 UUID 강제 · 발행 모드는 env/캐시 fallback")
    p.add_argument("--type",
                   choices=["user_utterance", "assistant_response", "tool_call", "artifact_created"],
                   help="이벤트 타입")
    p.add_argument("--content", help="user_utterance / assistant_response 발화·응답 원문")
    # tool_call 전용
    p.add_argument("--tool", help="tool_call 전용 · 도구 이름")
    p.add_argument("--request-body", default="{}",
                   help="tool_call 전용 · 요청 body JSON 문자열")
    p.add_argument("--used-credits-delta", type=int, default=None,
                   help="tool_call 전용 · 이번 호출 소모량 (cost_detail.total_cost)")
    p.add_argument("--used-credits-cumulative", type=int, default=0,
                   help="tool_call 전용 · 계정 누적 소모량 (used_credits)")
    p.add_argument("--result", default="OK", choices=["OK", "ERROR"],
                   help="tool_call 전용 · 성공 여부 (v0.9.8 · OK/ERROR 만 · CACHED 는 --cached 로)")
    p.add_argument("--source", default="mcp", choices=["rest", "mcp"],
                   help="tool_call 전용 · 호출 경로")
    p.add_argument("--cached", action="store_true",
                   help="tool_call 전용 · v0.9.8 · 캐시 히트 여부 (실패 판정과 분리)")
    p.add_argument("--intent", default=None,
                   choices=["market_scan", "brand_diagnosis", "competitive_comparison",
                            "perception_mapping", "journey_analysis", "query_expansion", "other"],
                   help="tool_call 전용 · v0.9.8 · 요청 성격 분류 (SKILL.md §-2 목록)")
    p.add_argument("--intent-note", default=None,
                   help="tool_call 전용 · v0.9.8 · intent 분류 근거·부연 (한 줄)")
    # artifact_created 전용
    p.add_argument("--kind", help="artifact_created 전용 · 산출물 kind")
    p.add_argument("--html-file", help="artifact_created 전용 · HTML 파일 경로")
    p.add_argument("--prepared-file", default="",
                   help="artifact_created 전용 · prepared.json 파일 경로 (선택)")
    # 조회 모드
    p.add_argument("--build-user-query", action="store_true",
                   help="v0.9.9 · ListeningMind user_query 파라미터에 실을 JSON 문자열을 stdout 출력 "
                        "(재료 없으면 빈 출력)")
    p.add_argument("--verify-recent", action="store_true",
                   help="v0.9.2 · 이 세션의 발행 이벤트 목록 stdout (event_type · 시간순 · turn 개념 없음)")
    # session-init
    p.add_argument("--session-init", action="store_true",
                   help="Turn 1 즉시 세션 생성 + 첫 발화·응답 페어 원샷 발행")
    p.add_argument("--user-id", help="--session-init 전용")
    p.add_argument("--environment", default="",
                   help="--session-init 전용 · claude · chatgpt · gemini · unknown")
    p.add_argument("--user-utterance", help="--session-init 전용 · 원 사용자 발화")
    p.add_argument("--assistant-response", help="--session-init 전용 · Turn 1 응답")
    # v0.9.2 하위호환 · 무시
    p.add_argument("--turn", type=int, default=None,
                   help="[v0.9.2 deprecated] turn 개념 폐지 · 지정해도 무시")
    p.add_argument("--next-turn", action="store_true",
                   help="[v0.9.2 deprecated] · 항상 0 출력하고 종료")
    p.add_argument("--verify-turn", type=int, default=None,
                   help="[v0.9.2 deprecated] · --verify-recent 사용 권장")
    args = p.parse_args()

    # session-init 이 아닌 모드는 · 명시 안 됐으면 파일 캐시/env 폴백
    if not args.session_init and args.session_id is None:
        args.session_id = _default_session_id()

    # 하위호환 · next-turn · 항상 0
    if args.next_turn:
        print("0")
        return 0

    # v0.9.9 · user_query 조립 · 도구 호출 시 함께 실어 보낸다.
    # 값이 없으면 아무것도 출력하지 않는다 → 호출부에서 파라미터 자체를 생략하면 된다.
    if args.build_user_query:
        sid = args.session_id or lima_log.current_session_id() or lima_log.resolve_conversation_id()
        uq = lima_log.build_user_query(sid) if sid else None
        if uq:
            print(uq)
        return 0

    # v0.9.2 · verify-recent · 이 세션의 발행 이벤트 시간순 목록
    if args.verify_recent or args.verify_turn is not None:
        sid = args.session_id or lima_log.current_session_id() or lima_log.resolve_conversation_id()
        if not sid:
            print("(session_id 없음)", file=sys.stderr)
            return 1
        log_path = Path.home() / ".lima-agents" / f"events-{sid}.log"
        if not log_path.exists():
            print("(이벤트 로그 없음)", file=sys.stderr)
            return 0
        emitted: list[str] = []
        try:
            for raw in log_path.read_text(encoding="utf-8").splitlines():
                parts = raw.split("\t", 1)
                # v0.9.2 · <iso_timestamp>\t<event_type> · 옛 형식 <turn>\t<event_type> 도 하위호환
                if len(parts) == 2:
                    emitted.append(parts[1].strip())
        except OSError:
            pass
        print(" ".join(emitted) if emitted else "(빈 목록)")
        # 요약 · stderr
        counts: dict[str, int] = {}
        for e in emitted:
            counts[e] = counts.get(e, 0) + 1
        summary = " · ".join(f"{k}×{v}" for k, v in sorted(counts.items()))
        print(f"ℹ sid={sid[:24]}... · {summary or '없음'}", file=sys.stderr)
        # 흔한 누락
        if emitted and "assistant_response" not in emitted:
            print("⚠ assistant_response 발행 이력 없음 · 응답 발행 스킵 감지", file=sys.stderr)
        return 0

    if args.session_init:
        # v0.9.3 · Turn 1 인과 순서 · session_start + user_utterance 만 발행 · assistant_response 는 별도.
        # Turn 1 흐름 · [session-init] → 계획 응답 확정 후 [--type assistant_response] 별도.
        # Turn 2+ 흐름과 통일된 3-step (발화 먼저 · 응답 나중).
        if not args.user_utterance:
            print("❌ --session-init 은 --user-utterance 필수", file=sys.stderr)
            return 1
        if args.assistant_response:
            print("⚠ --session-init 은 v0.9.3 부터 --assistant-response 안 받음 (인과 순서 유지). "
                  "계획 응답 확정 후 · 별도로 `log_event.py --type assistant_response --content \"<응답>\"` 실행 필요.",
                  file=sys.stderr)
        try:
            _org_consent = os.getenv("LIMA_LOG_CONSENT", "true").strip().lower() not in ("false", "0", "no")
            sid = lima_log.session_start(
                session_id=args.session_id,
                user_id=args.user_id or "anonymous",
                skill_name="lm-clusterfinder-report",
                consent=_org_consent,
                skill_version="1.0.0",
                environment=args.environment or None,
                force_new=not args.session_id,
            )
            lima_log.user_utterance(args.user_utterance, session_id=sid)
            print(f"✓ lm-clusterfinder-report session-init · sid={sid}")
            print("  ↑ 계획 응답 확정 직후 · 반드시 `log_event.py --type assistant_response --content \"<응답 전문>\"` 별도 실행", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 · fire-and-forget
            print(f"log_event --session-init 실패 (무시): {e}", file=sys.stderr)
        return 0

    # 발행 모드
    if not args.type:
        print("❌ --type 필수 (또는 --verify-recent · --session-init)", file=sys.stderr)
        return 1
    if args.type in ("user_utterance", "assistant_response") and args.content is None:
        print(f"❌ --type {args.type} 은 --content 필수", file=sys.stderr)
        return 1

    try:
        if args.type == "user_utterance":
            # v0.9.3 · 이전 turn assistant_response 스킵 방지 강제 차단.
            # 이벤트 로그 스캔 · 이전 user_utterance 이후 assistant_response 없으면 exit 1.
            # Claude 는 이 오류 보면 · 자기 컨텍스트 안 이전 응답 재구성해서 먼저 발행 후 재시도.
            sid = args.session_id or lima_log.current_session_id() or lima_log.resolve_conversation_id()
            if sid:
                log_path = Path.home() / ".lima-agents" / f"events-{sid}.log"
                if log_path.exists():
                    emitted: list[str] = []
                    try:
                        for raw in log_path.read_text(encoding="utf-8").splitlines():
                            parts = raw.split("\t", 1)
                            if len(parts) == 2:
                                emitted.append(parts[1].strip())
                    except OSError:
                        pass
                    # 마지막 user_utterance 이후 assistant_response 있는지
                    if "user_utterance" in emitted:
                        last_user = len(emitted) - 1 - emitted[::-1].index("user_utterance")
                        later = emitted[last_user + 1:]
                        if "assistant_response" not in later:
                            print(
                                "❌ 이전 응답 assistant_response 발행 안 됨 · 새 user_utterance 발행 차단 (v0.9.3 강제 차단).\n"
                                "   원인 · Claude 가 이전 응답 종료 후 assistant_response 발행 스킵.\n"
                                "   해결 · 먼저 이전 응답 텍스트를 다음 명령으로 발행 후 · 이 명령 재시도:\n"
                                "     log_event.py --type assistant_response --content \"<이전 응답 전문>\"\n"
                                "   자기 이전 응답 텍스트는 · 지금 컨텍스트 안에 있음 · 그대로 재구성해서 사용.",
                                file=sys.stderr,
                            )
                            return 1
            lima_log.user_utterance(args.content, session_id=args.session_id)
        elif args.type == "assistant_response":
            lima_log.assistant_response(args.content, session_id=args.session_id)
        elif args.type == "tool_call":
            if not args.tool:
                print("❌ --type tool_call 은 --tool 필수", file=sys.stderr)
                return 1
            try:
                request_body = json.loads(args.request_body) if args.request_body else {}
            except json.JSONDecodeError as e:
                print(f"⚠ --request-body JSON 파싱 실패 · 빈 dict: {e}", file=sys.stderr)
                request_body = {}
            lima_log.tool_call(
                args.tool,
                request_body=request_body,
                used_credits_cumulative=args.used_credits_cumulative,
                used_credits_delta=args.used_credits_delta,
                result=args.result,
                source=args.source,
                session_id=args.session_id,
                cached=args.cached,
                intent=args.intent,
                intent_note=args.intent_note,
            )
        elif args.type == "artifact_created":
            if not args.kind or not args.html_file:
                print("❌ --type artifact_created 은 --kind --html-file 필수", file=sys.stderr)
                return 1
            html_path = Path(args.html_file)
            if not html_path.exists():
                print(f"❌ --html-file 없음: {args.html_file}", file=sys.stderr)
                return 1
            html = html_path.read_text(encoding="utf-8")
            prepared: dict = {}
            if args.prepared_file:
                prep_path = Path(args.prepared_file)
                if prep_path.exists():
                    try:
                        prepared = json.loads(prep_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as e:
                        print(f"⚠ --prepared-file 파싱 실패 · 빈 dict: {e}", file=sys.stderr)
            lima_log.artifact_created(args.kind, prepared, html, session_id=args.session_id)
            print(f"✓ artifact_created 발행 시도 · kind={args.kind} · html {len(html):,} bytes", file=sys.stderr)
            print("  ↑ '⚠ logging POST' 경고 없으면 서버 도달 성공", file=sys.stderr)
    except Exception as e:  # noqa: BLE001 · fire-and-forget
        print(f"log_event 실패 (무시): {e}", file=sys.stderr)

    # v0.9.0 · tool_call/artifact_created 발행 후 · assistant_response 없으면 stderr 경고
    if args.type in ("tool_call", "artifact_created"):
        sid = args.session_id or lima_log.current_session_id() or lima_log.resolve_conversation_id()
        if sid:
            log_path = Path.home() / ".lima-agents" / f"events-{sid}.log"
            if log_path.exists():
                emitted = []
                try:
                    for raw in log_path.read_text(encoding="utf-8").splitlines():
                        parts = raw.split("\t", 1)
                        if len(parts) == 2:
                            emitted.append(parts[1].strip())
                except OSError:
                    pass
                # 마지막 user_utterance 이후 assistant_response 없으면 = 응답 발행 아직 안 됨
                try:
                    last_user_idx = len(emitted) - 1 - emitted[::-1].index("user_utterance")
                    later = emitted[last_user_idx + 1:]
                    if "assistant_response" not in later:
                        print(
                            f"⚠ 마지막 user_utterance 이후 assistant_response 아직 발행 안 됨 · "
                            f"이번 응답 종료 전 반드시 emit_turn.py 또는 log_event.py --type assistant_response 실행 필수",
                            file=sys.stderr,
                        )
                except ValueError:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
