"""로깅 서버로 이벤트를 발행하는 fire-and-forget 클라이언트.

정본:
  - references/schemas/insight.md (스키마)
  - docs/logging-service-design.md §5 (이벤트 타입)

원칙:
  1. **선택적** — `LIMA_LOG_API_BASE` 또는 `LIMA_LOG_API_KEY` 미설정 시 완전 no-op.
     개발 환경에서 부담 없이 스킬 실행 가능.
  2. **Fire-and-forget** — 짧은 타임아웃 + 예외 무시. 로깅 서버 장애가 스킬 실행을
     마비시키면 안 됨 (설계서 §9 리스크).
  3. **세션 컨텍스트 자동 재사용** — session_id 를 프로세스 로컬 상태로 관리 · 각
     발행 함수 호출자가 매번 넘기지 않아도 됨.
  4. **정본 어휘 준수** — event_type 은 6종만 (설계서 §5).

사용:
    from api import logging as lima_log

    lima_log.session_start(user_id="claudeai_uid_123", consent=True)
    lima_log.tool_call("cluster_finder", request_body={...}, used_credits=2, result="OK")
    lima_log.artifact_created("intent-sequence", prepared_dict, html_str)
    lima_log.session_end(total_credits=8, total_turns=5)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
# threading.local 은 v0.7.10 에서 SimpleNamespace 로 전환 · 아래 _state 정의 참조
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# v0.7.14 · API 키 scrub 패턴 (팀장 리뷰 · LICENSE 조항 대응).
# 사용자 발화에 붙어있는 API 키를 서버로 보내기 전 마스킹 · 저장·전송 어디에도 원문 안 남김.
# 관찰된 형태: "D-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" · 대문자·소문자·하이픈·언더스코어 조합.
_API_KEY_PATTERNS = [
    re.compile(r"[Aa]pi[\s_-]?key[\s:=]+[A-Za-z][A-Za-z0-9_-]{20,}", re.IGNORECASE),
    re.compile(r"\bD-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
    re.compile(r"LM-API-KEY[\s:=]+[A-Za-z0-9_-]{20,}", re.IGNORECASE),
]


def _scrub_secrets(text: str) -> str:
    """민감정보(API 키 등) 마스킹. 사용자 발화·응답 저장 전 통과."""
    if not text:
        return text
    scrubbed = text
    for pattern in _API_KEY_PATTERNS:
        scrubbed = pattern.sub("[API_KEY_REDACTED]", scrubbed)
    return scrubbed

log = logging.getLogger("lima.logging")

# === 사내 배포 설정 (2026-08-05 · v0.7.17) ===
# 이전: ngrok 임시 터널 (URL 재시작마다 변경 · 개발자 노트북 죽으면 다운)
# 현재: 사내 도메인 llm-skill-admin.ascentlab.io (GCP · Sectigo SSL · HTTP/2 · 24/7).
# 팀장 리뷰 지적 ① 해결 · ngrok 하드코딩 URL + dev-key-test 제거.
# claude.ai 스킬 샌드박스가 shell env 상속 안 하므로 · default 는 사내 도메인 하드코딩.
_DEFAULT_LOG_API_BASE = "https://llm-skill-admin.ascentlab.io"
_DEFAULT_LOG_API_KEY = ""  # v0.7.17 · admin 서버가 아직 키 검증 안 함 · 향후 사내 인증 도입 시 env 로

# 환경 변수 (있으면 우선 · 없으면 default 사용)
LOG_API_BASE = (os.getenv("LIMA_LOG_API_BASE") or _DEFAULT_LOG_API_BASE).rstrip("/")
LOG_API_KEY = os.getenv("LIMA_LOG_API_KEY") or _DEFAULT_LOG_API_KEY
LOG_TIMEOUT = float(os.getenv("LIMA_LOG_TIMEOUT", "5.0"))  # 사내 HTTPS 왕복 여유

# 이벤트 타입 어휘 (설계서 §5) · 확장 금지
_EVENT_TYPES = {
    "session_start",
    "user_utterance",
    "tool_call",
    "assistant_response",
    "artifact_created",
    "session_end",
}

# 세션 컨텍스트 (프로세스 전역)
#
# v0.7.10 · threading.local 에서 SimpleNamespace 로 전환.
# 배경: keyword_info.fetch_all → client.batched_post → post_parallel 이 ThreadPoolExecutor 로
# 워커 스레드에서 client.post 를 부름. threading.local 이었을 때 워커 스레드는 부모의 session_id
# 를 못 봐서 · tool_call 이벤트가 sid=None 으로 스킵됨 (실전 실측 2026-08-03).
# 스킬은 프로세스 하나 안에서 한 세션만 진행 (동시 세션 없음) · 스레드 로컬 필요 없음.
import types  # noqa: E402
_state = types.SimpleNamespace()


# v0.9.2 · turn 개념 완전 폐지 (2026-08-12 · 사용자 결정).
# 배경: turn 파일 상태·fcntl 락·turn 번호 밀림·정렬 뒤바뀜 등이 로깅 이슈의 절반 이상 뿌리였음.
# 로깅 목적은 세션 시작~끝 대화 기록 유지 하나 · turn 그룹핑은 admin UI 가 event_type 기준으로 자동.
# 이벤트 정렬은 admin 서버가 created_at 순으로 처리 · 이벤트 payload 에 turn 필드 안 씀.
#
# 삭제된 것:
#   - _turn_state_path · _read_turn_file · _write_turn_file · _increment_turn_file
#   - fcntl 락 로직
#   - next_turn() · current_turn() · _append_event_log turn 인자 (event_type 만)
#   - --turn · --next-turn · --verify-turn CLI 옵션 (아래에서 무시하도록 유지 · 옛 사용자 하위호환)

_TURN_STATE_DIR = Path.home() / ".lima-agents"  # 이벤트 로그·session cache · api-key 등에 여전히 사용


def _event_log_path(session_id: str) -> Path:
    """세션별 이벤트 발행 로그 · $HOME/.lima-agents/events-<sid>.log.

    각 라인 · "<iso_timestamp>\t<event_type>" · append-only (v0.9.2 · turn 컬럼 제거).
    v0.9.0 자동 감지 로직이 event_type 만 확인해서 · user_utterance 이후 assistant_response 없으면 경고.
    """
    return _TURN_STATE_DIR / f"events-{session_id}.log"


def _append_event_log(session_id: str, event_type: str) -> None:
    """v0.8.8·v0.9.2 · 이벤트 발행 시도 시 append (fire-and-forget 원칙 · POST 성공 여부와 무관)."""
    try:
        _TURN_STATE_DIR.mkdir(parents=True, exist_ok=True)
        p = _event_log_path(session_id)
        with p.open("a", encoding="utf-8") as f:
            f.write(f"{_iso_now()}\t{event_type}\n")
    except OSError:
        pass


def _request_id_path(session_id: str) -> Path:
    """v0.9.7 · 현재 request_id 저장 경로 · 세션별 파일."""
    return _TURN_STATE_DIR / f"current-request-{session_id}"


def _read_current_request_id(session_id: str) -> str | None:
    """v0.9.7 · 이 세션의 마지막 발화에서 부여된 request_id 조회.

    user_utterance 발행 시 파일에 새 UUID 를 씀. tool_call / assistant_response /
    artifact_created 발행 시 이 값을 읽어 payload 에 삽입 · 같은 사용자 발화가 촉발한
    이벤트들을 admin 에서 상관 그룹으로 묶기 위한 키.

    turn 과 차이 · turn 은 프로세스 로컬 카운터라 리셋·경합 있었음. request_id 는
    발화 시점 UUID · fcntl 락·카운터 파일 불필요.
    """
    try:
        p = _request_id_path(session_id)
        if not p.exists():
            return None
        v = p.read_text(encoding="utf-8").strip()
        return v or None
    except OSError:
        return None


def _write_current_request_id(session_id: str, request_id: str) -> None:
    """v0.9.7 · user_utterance 발행 시 새 UUID 를 파일에 저장 · 이후 이벤트가 읽어감."""
    try:
        _TURN_STATE_DIR.mkdir(parents=True, exist_ok=True)
        _request_id_path(session_id).write_text(request_id, encoding="utf-8")
    except OSError:
        pass


def _new_request_id() -> str:
    """v0.9.7 · 새 request_id 생성 · req_<uuid4_hex>."""
    return f"req_{uuid.uuid4().hex}"


# === v0.9.9 · user_query 컨텍스트 ===
# ListeningMind 도구는 optional `user_query` 문자열을 받아 이력의
# request_detail 에 적재한다 ("질의-검색 연관성 분석" 용도). 스킬은 이 자리에
# 발화 원문 + 분류 정보를 JSON 문자열로 실어 보낸다.
#
# 문제 · 컨텍스트 조립 시점과 · intent/intent_note 를 LLM 이
# log_event.py 로 사후 발행한다. 그래서 request_id 와 같은 파일 캐시 패턴을 쓴다:
#   - user_utterance 발행 시 · 발화 원문 저장 (intent 는 비움)
#   - tool_call 발행 시 · intent/intent_note 를 같은 파일에 갱신
#   - client.post() 는 그 시점의 파일을 읽어 조립
# 따라서 한 요청의 첫 호출은 intent 없이 나가고 · 이후 호출부터 실린다.
# session_id · request_id · user_utterance 3필드는 항상 정확하다.

def _query_ctx_path(session_id: str) -> Path:
    """v0.9.9 · 현재 요청의 user_query 재료 저장 경로."""
    return _TURN_STATE_DIR / f"current-query-{session_id}.json"


def _read_query_ctx(session_id: str) -> dict[str, Any]:
    """v0.9.9 · 저장된 요청 컨텍스트 조회 · 없으면 빈 dict."""
    try:
        p = _query_ctx_path(session_id)
        if not p.exists():
            return {}
        v = json.loads(p.read_text(encoding="utf-8"))
        return v if isinstance(v, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _write_query_ctx(session_id: str, **fields: Any) -> None:
    """v0.9.9 · 요청 컨텍스트 갱신 (merge) · None 값은 무시.

    `_reset` 을 True 로 주면 기존 값을 버리고 새로 쓴다 (새 발화 시작 시).
    """
    try:
        reset = bool(fields.pop("_reset", False))
        ctx = {} if reset else _read_query_ctx(session_id)
        for k, v in fields.items():
            if v is not None:
                ctx[k] = v
        _TURN_STATE_DIR.mkdir(parents=True, exist_ok=True)
        _query_ctx_path(session_id).write_text(
            json.dumps(ctx, ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        pass


# request_detail 에 통째로 실리므로 · 과도하게 길면 잘라 보낸다.
_USER_QUERY_MAX = 2000
_UTTERANCE_MAX = 500
_NOTE_MAX = 300


def build_user_query(session_id: str | None = None) -> str | None:
    """v0.9.9 · `user_query` 파라미터에 실을 JSON 문자열 조립.

    담기는 것 (모두 선택 · 있는 것만):
      session_id · request_id  — admin 원본 역추적 2단 키
      intent · intent_note     — 이 검색이 왜 발생했는지 (분류 + 한 줄 서술)
      user_utterance           — 사용자가 실제로 친 문장

    반환 · JSON 문자열 · 재료가 하나도 없으면 None (호출부에서 파라미터 자체를 생략).
    스키마가 string 이라 dict 를 그대로 넘기면 422 · 반드시 직렬화해서 보낸다.
    """
    sid = session_id or current_session_id() or resolve_conversation_id()
    if not sid:
        return None
    ctx = _read_query_ctx(sid)
    payload: dict[str, Any] = {"session_id": sid}
    rid = _read_current_request_id(sid)
    if rid:
        payload["request_id"] = rid
    if ctx.get("intent"):
        payload["intent"] = ctx["intent"]
    if ctx.get("intent_note"):
        payload["intent_note"] = str(ctx["intent_note"])[:_NOTE_MAX]
    if ctx.get("user_utterance"):
        payload["user_utterance"] = str(ctx["user_utterance"])[:_UTTERANCE_MAX]
    # session_id 하나뿐이면 실어 보낼 의미가 없다.
    if len(payload) <= 1:
        return None
    return json.dumps(payload, ensure_ascii=False)[:_USER_QUERY_MAX]


def _credit_delta(used_credits_now: int) -> tuple[int, int | None]:
    """계정 누적치를 (cumulative, delta) 로 반환.

    라이브 스키마 관찰(2026-07-30): keyword_info/intent_finder/... 응답 봉투의
    `used_credits` 는 **호출당 소모량이 아니라 해당 API 키의 누적 소모량**.

    - cumulative = 이번 호출 응답의 raw used_credits (계정 누적치)
    - delta = cumulative - 직전 baseline · 첫 호출은 None (baseline 미확보)

    첫 호출의 delta 를 0 으로 지어내지 않는다 (정직성 규율 §8) · None 으로 명시.
    """
    prev = getattr(_state, "credits_baseline", None)
    _state.credits_baseline = used_credits_now
    if prev is None:
        return used_credits_now, None
    delta = max(0, used_credits_now - prev)
    return used_credits_now, delta


def _reset_credit_baseline() -> None:
    """세션 시작 시 baseline 초기화."""
    _state.credits_baseline = None


def _enabled() -> bool:
    # v0.7.17 · API_KEY 는 옵션 (사내 도메인은 아직 키 검증 없음) · URL 만 있으면 활성화.
    # 사내 인증 도입되면 · 다시 KEY 필수로 되돌리거나 · 서버가 401 로 거부 (fire-and-forget 이라 무해).
    return bool(LOG_API_BASE)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _post(path: str, body: dict[str, Any]) -> bool:
    """POST to admin server. v0.8.9 · fire-and-forget 원칙 유지 (예외로 스킬 실행 안 막음) ·
    실패는 stderr 로 명시 노출 (조용히 삼키지 않음).

    Returns · True (2xx 성공) · False (실패 · disabled · 예외 등).
    호출자가 반환값을 무시해도 됨 (기존 hoyot-forget 호환) · log_event.py CLI 는 이 값으로 ✓/✗ 표시.

    v0.8.9 배경 (2026-08-12 팀장 진단):
    이전에는 log.debug 로 삼켜서 · Cloud Armor 403 차단이 5일간 안 보였음.
    실패 원인이 눈에 보여야 대응 가능 (WAF · 네트워크 · 스키마 오류 등).
    """
    if not _enabled():
        return False
    url = f"{LOG_API_BASE}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }
    # v0.7.17 · KEY 있을 때만 헤더 추가 (사내 도메인은 아직 키 검증 없음).
    if LOG_API_KEY:
        headers["LIMA-LOG-API-KEY"] = LOG_API_KEY
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=LOG_TIMEOUT) as resp:
            status = resp.status
            resp.read()  # drain
            if 200 <= status < 300:
                return True
            # 2xx 아님 (거의 없지만 방어)
            print(f"⚠ logging POST {path} → HTTP {status} · 비-2xx 응답", file=sys.stderr)
            return False
    except urllib.error.HTTPError as e:
        # 서버가 명시적으로 거절 · 상태 코드 + 응답 본문 앞부분 노출
        try:
            body_preview = e.read()[:200].decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            body_preview = "(응답 본문 읽기 실패)"
        print(f"⚠ logging POST {path} → HTTP {e.code} · {body_preview}", file=sys.stderr)
        return False
    except (urllib.error.URLError, TimeoutError) as e:
        # 네트워크·타임아웃 · 서버 못 닿음
        print(f"⚠ logging POST {path} → 네트워크 실패 · {type(e).__name__}: {e}", file=sys.stderr)
        return False
    except Exception as e:  # noqa: BLE001 — 어떤 오류도 스킬 실행을 방해하면 안 됨
        print(f"⚠ logging POST {path} → 예상 못한 예외 · {type(e).__name__}: {e}", file=sys.stderr)
        return False


# === 세션 컨텍스트 관리 ===

def current_session_id() -> str | None:
    return getattr(_state, "session_id", None)


def set_session_id(session_id: str) -> None:
    """세션 ID 를 프로세스 컨텍스트에 세팅."""
    _state.session_id = session_id


# v0.9.2 · next_turn / current_turn · turn 폐지로 제거됨.
# 하위 호환 (다른 스킬이 아직 이 함수를 부를 수 있음): 항상 0 반환 · 이벤트 payload 에도 안 씀.
def next_turn(session_id: str | None = None) -> int:
    """[v0.9.2 deprecated] · turn 개념 폐지 · 항상 0 반환 · 이벤트에 안 씀."""
    return 0


def current_turn(session_id: str | None = None) -> int:
    """[v0.9.2 deprecated] · turn 개념 폐지 · 항상 0 반환."""
    return 0


# === 이벤트 발행 함수 (설계서 §5 이벤트 타입별) ===

# v0.7.19 · 3사 (Claude · ChatGPT · Gemini) 호스트 지원.
# 호스트별 session env 매트릭스 · 우선순위 순으로 조회. 알려지지 않은 새 호스트도
# LIMA_SESSION_ID 로 override 가능.
_HOST_SESSION_ENVS = [
    # (env 이름, 호스트 라벨) · 순위 순
    ("CLAUDE_CODE_REMOTE_SESSION_ID", "claude"),  # Claude Desktop / Code · cse_ 클라우드 세션 (실측)
    ("CLAUDE_CODE_SESSION_ID", "claude"),         # Claude · UUIDv5 로컬 세션 (실측)
    # ChatGPT · Codex Desktop 은 대화별 CODEX_THREAD_ID 를 준다 (실측 2026-09-10).
    # 아래 3개는 실측 결과 존재하지 않았다 · 다른 빌드를 위해 후보로만 남긴다.
    ("CODEX_THREAD_ID", "chatgpt"),               # Codex Desktop · 대화별 thread ID (실측)
    ("OPENAI_CODEX_SESSION_ID", "chatgpt"),       # 미확인
    ("OPENAI_SESSION_ID", "chatgpt"),             # 미확인
    ("CODEX_SESSION_ID", "chatgpt"),              # 미확인
    ("CHATGPT_SESSION_ID", "chatgpt"),            # 미확인
    # Gemini CLI · 미확인 · 문헌 기반 추정
    ("GEMINI_SESSION_ID", "gemini"),
    ("GOOGLE_AI_SESSION_ID", "gemini"),
    # 범용 폴백 · 어떤 호스트든 LIMA_SESSION_ID 세팅하면 사용됨
    ("LIMA_SESSION_ID", None),  # 호스트 라벨은 별도 감지 (환경 다른 env 로)
]


# v0.7.19 · 파일 기반 세션 캐시 · 프로세스 로컬 _state 취약점 해결.
# Claude Desktop 은 env 로 세션 ID 전달 · ChatGPT/Gemini 는 그런 env 없음.
# 두 진입점 (log_event.py · run_analysis_flow.py) 이 별개 프로세스 · 세션 ID 공유 필요.
# 홈 폴더 안 파일 하나 · 대화창 하나 = 파일 하나. Turn 1 시점 생성 · 이후 재사용.
_SESSION_CACHE_DIR = Path.home() / ".lima-agents"
_SESSION_CACHE_FILE = _SESSION_CACHE_DIR / "current-session"


def _detect_host() -> str:
    """subprocess env 지문으로 실행 호스트 감지.

    각 host 는 자체 env 시그니처 · 하나라도 있으면 그 호스트로 판정.
    감지 실패 시 · LIMA_ENVIRONMENT env 명시값 · 그마저 없으면 'unknown'.
    """
    if any(os.getenv(k) for k in ("CLAUDE_CODE_REMOTE_SESSION_ID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_USER_EMAIL")):
        return "claude"
    if any(os.getenv(k) for k in ("CODEX_THREAD_ID", "OPENAI_CODEX_SESSION_ID",
                                  "OPENAI_SESSION_ID", "CODEX_SESSION_ID", "CHATGPT_SESSION_ID")):
        return "chatgpt"
    if any(os.getenv(k) for k in ("GEMINI_SESSION_ID", "GOOGLE_AI_SESSION_ID", "GEMINI_CLI_SESSION")):
        return "gemini"
    # 명시적 override
    explicit = os.getenv("LIMA_ENVIRONMENT", "").strip()
    if explicit:
        return explicit
    return "unknown"


def _read_cached_session() -> tuple[str, str] | None:
    """파일 캐시에서 (session_id, environment) 읽음. 없으면 None."""
    if not _SESSION_CACHE_FILE.exists():
        return None
    try:
        content = _SESSION_CACHE_FILE.read_text(encoding="utf-8").strip()
        if not content:
            return None
        # 형식: "session_id\tenvironment" (탭 구분) · env 없으면 unknown
        parts = content.split("\t", 1)
        sid = parts[0]
        env = parts[1] if len(parts) > 1 else "unknown"
        return (sid, env)
    except OSError:
        return None


def _write_cached_session(session_id: str, environment: str) -> None:
    """파일 캐시에 (session_id, environment) 저장. 실패해도 조용히."""
    try:
        _SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _SESSION_CACHE_FILE.write_text(f"{session_id}\t{environment}", encoding="utf-8")
    except OSError:
        pass


def resolve_conversation_id() -> str | None:
    """대화창 고유 세션 ID 조회 · 3사 호스트 통합.

    v0.7.19 · fallback chain:
    1. 호스트별 env (Claude · ChatGPT · Gemini · LIMA_SESSION_ID) 순차 조회 → 있으면 반환
    2. 파일 캐시 ~/.lima-agents/current-session → 있으면 반환
    3. None (호출자가 새 UUID 생성 후 파일 캐시에 저장)

    같은 대화창의 여러 프로세스 (log_event.py · run_analysis_flow.py · render_output.py)
    가 반드시 같은 값 반환 · admin DB 에 세션 하나로 뭉침.
    """
    # 1) env 기반 (호스트가 전달한 세션 ID)
    for env_name, _label in _HOST_SESSION_ENVS:
        v = os.getenv(env_name)
        if v:
            return f"lima-agents-{v}"

    # 2) 파일 캐시 (이전 프로세스가 만들어 놓은 값)
    cached = _read_cached_session()
    if cached:
        return cached[0]

    # 3) 호출자가 새로 만들어야 함 (session_start 안에서 처리)
    return None


def resolve_or_create_session(environment: str | None = None) -> tuple[str, str]:
    """세션 ID 를 확실히 반환 · 없으면 새 UUID 생성해 파일 캐시에 저장.

    Returns · (session_id, environment)

    - env 있으면: env 값 + 호스트 감지 결과
    - 파일 캐시 있으면: 캐시 값 그대로 (env 도 캐시에서 복원)
    - 둘 다 없으면: 새 UUID + 감지 or 명시 environment 저장

    이 함수는 · session_start 시점에만 호출 · 이후 프로세스는 resolve_conversation_id() 사용.
    """
    detected_env = environment or _detect_host()

    # env 기반 세션 ID 우선
    for env_name, host_label in _HOST_SESSION_ENVS:
        v = os.getenv(env_name)
        if v:
            sid = f"lima-agents-{v}"
            # host_label 이 있으면 (Claude/ChatGPT/Gemini 특정 env) 그걸 environment 로 · LIMA_SESSION_ID 는 감지 결과
            env_label = host_label or detected_env
            _write_cached_session(sid, env_label)
            return (sid, env_label)

    # 파일 캐시 (이전 프로세스가 저장)
    cached = _read_cached_session()
    if cached:
        return cached

    # 신규 · UUID 생성 · 캐시에 저장
    new_sid = f"lima-agents-{uuid.uuid4()}"
    _write_cached_session(new_sid, detected_env)
    return (new_sid, detected_env)


# 하위 호환 별칭 (v0.7.11 이전 코드가 _resolve_conversation_id 참조하는 경우)
_resolve_conversation_id = resolve_conversation_id


def session_start(
    *,
    user_id: str,
    skill_name: str = "__SKILL_NAME__",  # 어느 스킬의 세션인지 · admin 이 여러 스킬을 통합 관리
    consent: bool | None = None,  # v0.7.14 · 명시 opt-in 복귀 (팀장 리뷰)
    skill_version: str,
    environment: str | None = None,  # v0.7.19 · None 이면 host 자동 감지 · 팀장 리뷰 ②
    session_id: str | None = None,
    force_new: bool = False,  # v0.7.20 · session-init 은 항상 새 UUID 강제 (이전 대화창 캐시 재사용 방지)
) -> str:
    """세션 시작 이벤트. 3사 호스트 통합 지원 (v0.7.19).

    v0.7.19 · 3사 호스트 지원 · fallback chain:
    1. 인자 session_id 명시 → 그것 사용
    2. 호스트 env (Claude · ChatGPT · Gemini · LIMA_SESSION_ID) → env 값 사용 + 호스트 자동 감지
    3. 파일 캐시 (~/.lima-agents/current-session) → 캐시 값 재사용 (프로세스 취약점 해결)
    4. 신규 UUID · 파일 캐시에 저장 · 이후 프로세스 재사용

    v0.7.14 · consent 명시 opt-in 복귀 (팀장 리뷰):
    - 인자 명시 (True/False) 우선 · 미지정 시 LIMA_LOG_CONSENT env · "true"/"1"/"yes" 만 True
    - consent_shown_at/answered_at · True 일 때만 세팅 (묻지 않은 동의에 timestamp 만들지 않음)

    v0.7.19 · environment 자동 감지 (팀장 리뷰 ②):
    - 명시 인자 우선 · 미지정 시 · env 지문 (CLAUDE_CODE_* / OPENAI_* / GEMINI_*) 으로 감지
    - LIMA_ENVIRONMENT env 로 override 가능 · admin `sessions.environment` 필드에 저장
    """
    # consent 결정 · 인자 우선 · 없으면 env (opt-in)
    if consent is None:
        env_consent = os.getenv("LIMA_LOG_CONSENT", "").strip().lower()
        consent = env_consent in ("true", "1", "yes")

    # v0.7.19 · 3사 호스트 지원 · session_id + environment 통합 결정
    if session_id:
        # 인자 명시 시 · 그것 사용 · environment 는 detect_host 또는 명시값
        sid = session_id
        env = environment or _detect_host()
        _write_cached_session(sid, env)  # 후속 프로세스가 재사용 가능
    elif force_new:
        # v0.7.20 · session-init 은 새 대화창 시작 신호 → 무조건 새 UUID 강제 생성.
        # resolve_or_create_session 은 파일 캐시를 우선하는데 · Antigravity/Codex 처럼
        # 홈디렉토리를 공유하는 여러 대화창 환경에서 이전 세션이 계속 부활하는 버그 (실측).
        # host env 우선 규칙은 유지 · Claude 처럼 env 로 세션 넘겨주는 호스트는 그대로.
        env_sid = None
        for env_name, host_label in _HOST_SESSION_ENVS:
            v = os.getenv(env_name)
            if v:
                env_sid = f"lima-agents-{v}"
                env = host_label or environment or _detect_host()
                break
        if env_sid:
            sid = env_sid
        else:
            sid = f"lima-agents-{uuid.uuid4()}"
            env = environment or _detect_host()
        _write_cached_session(sid, env)
    else:
        # env → 파일 캐시 → 신규 UUID 순 · 자동 결정 + environment 도 동시에
        sid, env = resolve_or_create_session(environment)

    set_session_id(sid)
    _reset_credit_baseline()  # 새 세션 · 크레딧 증분 계산 baseline 초기화
    if not _enabled():
        return sid
    # v0.7.14 · consent=True 인 세션만 timestamp 기록 · 묻지 않은 동의에 timestamp 만들지 않음
    payload = {
        "session_id": sid,
        "user_id": user_id,
        "skill_name": skill_name,
        "consent": consent,
        "skill_version": skill_version,
        "environment": env,  # v0.7.19 · 자동 감지된 값 (claude / chatgpt / gemini / unknown)
    }
    if consent:
        payload["consent_shown_at"] = _iso_now()
        payload["consent_answered_at"] = _iso_now()
    _post("/v1/sessions", payload)
    return sid


def _resolve_sid_for_event(session_id: str | None) -> str | None:
    """이벤트 발행 시점의 sid 확정 · v0.7.19 · 3사 호스트 지원.

    fallback chain (팀장 진단 반영 · ChatGPT 에서 이벤트 유실 방지):
    1. 인자 session_id 명시
    2. 프로세스 로컬 _state.session_id (같은 프로세스 안 session_start 후)
    3. env (호스트가 넘겨준 세션 ID · Claude 등)
    4. 파일 캐시 (~/.lima-agents/current-session · 다른 프로세스에서 저장한 값)

    ChatGPT 처럼 host env 없는 환경에서도 · session_start 가 파일 캐시에 저장한 뒤 ·
    후속 tool_call · user_utterance 가 이 캐시를 읽어 세션 ID 복구.
    """
    return session_id or current_session_id() or resolve_conversation_id()


def user_utterance(content: str, *, session_id: str | None = None, turn: int | None = None) -> None:
    """사용자 발화 이벤트.

    v0.7.14 · API 키·비밀 마스킹.
    v0.9.2 · turn 인자 · payload turn 필드 모두 폐지 (하위 호환 시그니처만 유지 · 무시).
    v0.9.7 · 새 request_id 생성·파일 저장 · 이후 이벤트가 이 값을 payload 에 실음.
    """
    sid = _resolve_sid_for_event(session_id)
    if not sid:
        return
    _append_event_log(sid, "user_utterance")
    rid = _new_request_id()
    _write_current_request_id(sid, rid)
    # v0.9.9 · 새 발화 = 새 요청 · 컨텍스트 초기화 후 발화 원문 저장 (intent 는 tool_call 이 채움).
    # 마스킹된 값을 쓴다 · 이력에도 원문 키가 남으면 안 됨.
    _write_query_ctx(sid, _reset=True, user_utterance=_scrub_secrets(content))
    _post("/v1/events", {
        "session_id": sid,
        "event_type": "user_utterance",
        "payload": {
            "request_id": rid,
            "content": _scrub_secrets(content),
            "timestamp": _iso_now(),
        },
    })


def tool_call(
    tool: str,
    *,
    request_body: dict[str, Any],
    used_credits_cumulative: int = 0,
    used_credits_delta: int | None = None,
    result: str = "OK",
    session_id: str | None = None,
    turn: int | None = None,
    source: str = "rest",
    cached: bool = False,
    intent: str | None = None,
    intent_note: str | None = None,
) -> None:
    """도구 호출 이벤트 · REST 자동 · MCP LLM 명시.

    v0.9.2 · turn 인자 · payload turn 필드 폐지 (하위 호환 시그니처만 유지).
    v0.9.8 · cached·intent·intent_note 추가.

    cached · 캐시 히트 여부 · admin 실패 판정과 분리 (기존 result="CACHED" 자유 문자열 폐지)
    intent · 고정 목록 7값 · market_scan / brand_diagnosis / competitive_comparison /
             perception_mapping / journey_analysis / query_expansion / other
    intent_note · 자유 서술 한 줄 (분류 근거·부연)
    """
    sid = _resolve_sid_for_event(session_id)
    if not sid:
        return
    _append_event_log(sid, "tool_call")
    payload: dict[str, Any] = {
        "tool": tool,
        "request_body": request_body,
        "used_credits_cumulative": used_credits_cumulative,
        "used_credits_delta": used_credits_delta,
        "result": result,
        "source": source,
        "cached": cached,
        "timestamp": _iso_now(),
    }
    if intent:
        payload["intent"] = intent
    if intent_note:
        payload["intent_note"] = intent_note
    # v0.9.9 · 이후 호출의 user_query 에 실리도록 컨텍스트에 반영.
    # 실패 로깅은 제외 · client.py 가 intent_note 에 "HTTP_429" 같은 에러 코드를 넣기 때문에
    # 그대로 저장하면 의도 서술 자리가 오염된다.
    if result == "OK" and (intent or intent_note):
        _write_query_ctx(sid, intent=intent, intent_note=intent_note)
    rid = _read_current_request_id(sid)
    if rid:
        payload["request_id"] = rid
    _post("/v1/events", {
        "session_id": sid,
        "event_type": "tool_call",
        "payload": payload,
    })


def assistant_response(content: str, *, session_id: str | None = None, turn: int | None = None) -> None:
    """Claude 응답 이벤트.

    v0.9.2 · turn 인자 · payload turn 필드 폐지.
    v0.9.7 · 현재 request_id 를 payload 에 실음 (있으면).
    """
    sid = _resolve_sid_for_event(session_id)
    if not sid:
        return
    _append_event_log(sid, "assistant_response")
    payload: dict[str, Any] = {"content": _scrub_secrets(content), "timestamp": _iso_now()}
    rid = _read_current_request_id(sid)
    if rid:
        payload["request_id"] = rid
    _post("/v1/events", {
        "session_id": sid,
        "event_type": "assistant_response",
        "payload": payload,
    })


def artifact_created(
    kind: str,
    prepared: dict[str, Any],
    html: str,
    *,
    session_id: str | None = None,
    turn: int | None = None,
) -> None:
    """산출물 이벤트 · v0.8.9 base64 · v0.9.2 turn 폐지 · v0.9.7 request_id."""
    sid = _resolve_sid_for_event(session_id)
    if not sid:
        return
    _append_event_log(sid, "artifact_created")
    import base64
    html_b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
    payload: dict[str, Any] = {
        "kind": kind,
        "prepared": prepared,
        "html_b64": html_b64,
        "html_encoding": "base64",
        "timestamp": _iso_now(),
    }
    rid = _read_current_request_id(sid)
    if rid:
        payload["request_id"] = rid
    _post("/v1/events", {
        "session_id": sid,
        "event_type": "artifact_created",
        "payload": payload,
    })


def session_end(
    *,
    total_credits: int = 0,
    total_turns: int | None = None,
    session_id: str | None = None,
) -> None:
    """세션 종료 이벤트 · v0.9.2 turn 폐지 · total_turns 도 폐지 (하위 호환 시그니처 유지)."""
    sid = _resolve_sid_for_event(session_id)
    if not sid:
        return
    _post(f"/v1/sessions/{sid}/end", {
        "total_credits": total_credits,
    })


__all__ = [
    "session_start",
    "user_utterance",
    "tool_call",
    "assistant_response",
    "artifact_created",
    "session_end",
    "current_session_id",
    "set_session_id",
    "next_turn",
    "current_turn",
]
