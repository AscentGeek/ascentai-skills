# AGENTS.md · SaaS 스킬 저작 원칙 (ascent-skills-saas)

`lima-skills/AGENTS.md` 를 승계하되, **데이터 경로가 MCP 라는 점에서 갈라지는 부분**만
여기 다시 쓴다. 언급 없는 항목은 lima-skills 원칙을 그대로 따른다.

---

## 0. 이 리포의 전제 — DaaS 에 과금되면 안 된다

SaaS 고객이 이 스킬을 쓸 때 **DaaS 계정에 크레딧이 나가면 안 된다.** 그래서:

- `scripts/daas_call.py` · `listeningmind-data-api.ascentlab.io` · `LM-API-KEY` ·
  `LIMA_DAAS_*` 는 **이 리포에 존재할 수 없다.** pre-commit 훅이 파일명·문자열 양쪽으로 막는다.
- 데이터는 **ListeningMind MCP 4도구**로만 받는다 ·
  `intent_finder` · `keyword_info` · `cluster_finder` · `path_finder`
- 사용자에게 **API 키를 묻지 않는다.** MCP 커넥터 연결이 전제다.

> 훅을 `--no-verify` 로 우회하지 말 것. 우회하면 과금 주체가 조용히 바뀐다.

---

## 1. MCP 호출 규약

### 호출 주체가 코드가 아니라 LLM 이다

DaaS 판은 `daas_call.py` 가 HTTP 를 치고 응답을 파일로 떨궜다. MCP 는 **LLM 이 도구를
호출하고 응답이 컨텍스트로만 온다.** 그래서 세 가지가 LLM 책임으로 넘어온다:

1. **덤프** · 응답 원문을 `{WORKDIR}/*.json` 으로 옮겨 적는다 (집계기 입력)
2. **크레딧 기록** · 봉투의 `cost_detail.total_cost` 를 읽어 `log_event.py` 에 전달
3. **캐시 확인** · 호출 전 `mcp_cache.py lookup`, 호출 후 `store`

### 덤프 원칙

집계기(`_shared/render/*_aggregate.py`)의 **입력 스키마는 DaaS 판과 동일하다.** 그래서
MCP 응답을 **가공 없이 원문 그대로** 덤프해야 한다. 요약·발췌·재구성 금지 — 하는 순간
집계기가 못 읽거나 수치가 어긋난다.

- 잘린 JSON 은 `mcp_cache.py store` 가 파싱 단계에서 잡아 거부한다
- 건수 대조가 필요하면 `--expect <N>` 로 봉투에서 읽은 수와 맞춘다
- 레코드 0건이면 저장하지 않는다 (반쪽 데이터가 캐시에 눌러앉는 것을 막는다)

### 규모 정책

DaaS 판의 상한을 그대로 승계한다 — `intent_finder` 상위 1,000 · `keyword_info` 최대 1,000.
**임의로 줄이지 말 것.** 200개 등으로 자르면 총검색량·그룹 합산이 과소집계되어
프로덕션과 어긋난다.

---

## 2. 세션 캐시 (`~/.lima-agents/mcp-cache/`)

같은 대화에서 같은 데이터를 두 번 사지 않는 것이 캐시의 목적이다.
크레딧은 봉투의 `cost_detail.total_cost` 실측값으로만 판단한다 (추정 금지).

```
~/.lima-agents/mcp-cache/<session_id>/<tool>__<hash>.json
```

- `<hash>` = `sha256(도구이름 + 정렬된 파라미터)[:24]` · 파라미터 하나만 달라도 다른 키
- `user_query` 는 키에서 제외 — 질의 문구가 달라져도 같은 데이터를 가리킨다
- 스킬이 달라도 **같은 세션·같은 파라미터면 적중**한다
  단, 적중은 **파라미터가 같을 때만**이다:
  - 구조 조회(`intent_finder`·`path_finder`·`cluster_finder`) — 형제 스킬과 1a 파라미터가
    같아 그대로 적중한다 (lm-pathfinder-report-kr 뒤에 lm-total-report-kr 을 돌리면
    `path_finder` 재호출이 사라진다)
  - `keyword_info` — 스킬마다 넘기는 키워드 목록이 달라 적중하지 않는다. total 은 3파인더
    합집합으로 **한 번만** 부르므로, 형제 캐시를 못 쓰는 대신 자기 안의 중복 조회가 사라진다
- `LIMA_MCP_REFRESH=1` 로 강제 재호출

호출 하나가 파일 하나라, 사람이 열어보고 디버깅할 수 있다.

### 호출 절차 (모든 MCP 호출에 공통)

```bash
# ① 호출 전
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup <tool> \
    --params '<MCP 파라미터 JSON>' --out "{WORKDIR}/<파일>.json"
# exit 0 = 적중 → MCP 호출 건너뛰고 ③ 으로 (단, --cached 로 로깅)
# exit 2 = 미적중 → ② 로

# ② MCP 호출 → 응답 원문을 {WORKDIR}/<파일>.json 에 덤프 → 캐시에 저장
python3 {SKILL_DIR}/scripts/mcp_cache.py store <tool> \
    --params '<동일한 파라미터 JSON>' --file "{WORKDIR}/<파일>.json"

# ③ tool_call 로깅 (아래 §3)
```

`--params` 는 lookup 과 store 가 **반드시 같아야** 한다. 다르면 다음 실행에서 적중하지 않는다.

---

## 3. 로깅 규약

lima-skills 와 **같은 admin 서버**(`llm-skill-admin.ascentlab.io`)에 발행한다.
3-step 인과 순서(user_utterance → tool_call → assistant_response → artifact_created)도 동일.

갈라지는 부분은 `tool_call` 하나다:

```bash
# MCP 호출 후 · 봉투 값을 눈으로 읽어 전달
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call \
    --tool keyword_info --request-body '<MCP 파라미터 JSON>' \
    --used-credits-delta <cost_detail.total_cost 실측> \
    --used-credits-cumulative <used_credits 실측> \
    --intent <목록값>

# 캐시 적중 시 · 재소모가 없으므로 0 + --cached
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call \
    --tool keyword_info --request-body '<동일>' \
    --used-credits-delta 0 --used-credits-cumulative 0 --cached \
    --intent <목록값>
```

- `--source` 는 기본값이 `mcp` 라 생략한다
- **호출 수로 크레딧을 계산하지 말 것.** 봉투에 값이 없으면 `--used-credits-delta` 를
  아예 생략한다 (지어낸 값보다 낫다)
- `intent_finder`·`cluster_finder` 를 `1` 로 발행 중이면 100% 위반 (기본 최소 90)

### user_query

DaaS 판은 `daas_call.py` 가 자동으로 붙였다. **MCP 경로는 자동 첨부가 없다.**
MCP 도구가 `user_query` 파라미터를 받으므로, **사용자 발화 원문을 그대로** 넣는다
(번역·요약·의역 금지). 캐시 키에는 들어가지 않는다.

---

## 3-1. 스킬 작명 규약

```
lm-<스킬명>-<언어>   ListeningMind MCP 를 쓰는 판 (SaaS · 이 리포) · kr · jp · us
lm-<스킬명>-daas    DaaS API 를 직접 호출하는 판 (lima-skills 리포)
```

언어 코드는 **모든 판이 단다** — 한국어판도 `-kr` 이다. 기본 판만 접미사를 빼면
이름만 보고 언어를 알 수 없고, 언어가 늘 때 규칙이 두 갈래가 된다.

두 판을 한 호스트에 나란히 설치해도 이름이 충돌하지 않고, admin 대시보드에서
`skill_name` 으로 사용량이 갈린다.

---

## 3-2. 세션 격리

한 대화 = 한 세션. `api/logging.py` 가 호스트별 env 로 세션을 갈라낸다:

| 호스트 | env | 상태 |
|---|---|---|
| Claude Desktop / Code | `CLAUDE_CODE_SESSION_ID` · `CLAUDE_CODE_REMOTE_SESSION_ID` | 실측 |
| Codex Desktop | `CODEX_THREAD_ID` | **실측 (2026-09-10)** |
| Gemini | `GEMINI_SESSION_ID` 등 | 미확인 |
| 공통 폴백 | `LIMA_SESSION_ID` | — |

env 를 못 찾으면 `~/.lima-agents/current-session` 파일로 떨어지는데, 이 파일은
**머신 전체에 하나**라 동시에 여러 대화를 돌리면 서로 덮어쓴다. 실제로 ChatGPT 에서
두 대화를 동시에 돌렸을 때 한쪽 응답·산출물이 옆 세션에 기록된 사고가 있었다
(2026-09-10 · `CODEX_THREAD_ID` 미채택이 원인이었고 지금은 채택됨).

**그래서 스킬 문서는 `session-init` 이 출력한 `sid` 를 고정해 모든 후속 로깅에
`--session-id` 로 명시하도록 지시한다.** env 가 없는 빌드에서도 안전하게 만드는 이중 방어다.

새 호스트를 지원할 때는 그 호스트가 **대화창마다 다른 값**을 주는 env 를 찾아
`_HOST_SESSION_ENVS` 와 `_detect_host()` **양쪽에** 추가한다.

---

## 4. 스킬 구조 · 빌드

**소스는 스킬당 1벌 · zip 은 (스킬 × 언어) 만큼** 나온다. 언어를 늘려도 `skills/` 의
폴더 수는 안 늘어난다 (8종 × 3언어여도 폴더는 8개).

```
_core/                          전 스킬·전 언어 공통 · 여기만 고치면 전부 반영
├── styles/                     CSS 6종 (4스킬 바이트 동일 · 측정 확인)
├── render/components.py        (cluster 판이 상위집합 · 통합)
├── api/{logging.py,__init__.py}
└── scripts/{mcp_cache.py,log_event.py}
     └ skill_name·version 은 __SKILL_NAME__ · __SKILL_VERSION__ 플레이스홀더

skills/<스킬명>/                 스킬 수만큼만
├── skill.yaml                  version · slug · mcp_tools · vendor_chart · locales
├── render/                     이 스킬 전용 렌더러 (스킬마다 실제로 다름)
├── styles/ templates/ vendor/  이 스킬 전용 자산
├── prompts/                    원본 프롬프트 스냅샷 (언어 무관 · 번역 금지)
├── LICENSE.txt
└── locales/<언어>/              ← 언어가 늘어나는 자리
    ├── SKILL.md                name·description·문서 (그 언어로)
    ├── references/*.md
    └── labels/*.json

dist/lm-<스킬명>-<언어>.zip       빌드 산출 (kr 판도 -kr 을 단다)
```

### 빌드

```bash
scripts/build.sh                        # 전 스킬 · skill.yaml 의 locales 전부
scripts/build.sh queryfinder-report     # 한 스킬만
scripts/build.sh queryfinder-report jp  # 한 스킬 · 한 언어
```

빌드가 하는 일 · `_core` + 스킬 전용 + 로케일 문서를 합쳐 **기존과 같은 zip 내부 구조**
(`_shared/` · `api/` · `scripts/` · `references/`)로 되돌리고, 플레이스홀더에 스킬명·버전을
박아 넣는다. **플레이스홀더 주입을 빠뜨리면 admin 에 `__SKILL_NAME__` 으로 기록된다.**

> **코드를 고칠 때는 `_core/` 또는 `skills/<n>/render/` 를 고친다.** zip 안이나
> 빌드 산출물을 직접 고치면 다음 빌드에 덮어써진다.

---

## 5. i18n · 언어 추가

언어 추가 = `skills/<n>/locales/<언어>/` 를 만들고 `skill.yaml` 의 `locales` 에 추가.
**코드는 손대지 않는다.**

번역 대상 (그 언어로 새로 씀):
- `SKILL.md` · frontmatter `name`(`lm-<스킬명>-<언어>`) · `description`(**트리거 문구가
  그 언어여야 스킬이 발동한다**) · 본문
- `references/*.md` · LLM 이 읽고 그 언어로 사용자에게 말한다
- `labels/*.<언어>.json` · 리포트 UI 라벨

번역하지 않는 것:
- `prompts/*.md` · 운영 프롬프트와 diff 대조용이라 번역하면 대조가 깨진다
- 코드 주석·docstring · 유지보수자가 읽는 것
- 리포트 **본문**은 번역 대상이 아니다 · `출력 언어 = 분석 시장(gl) 언어` 규칙이
  이미 있어 `gl=jp` 면 LLM 이 일본어로 쓴다

`render_report.py` 에 `HTML_LANG`·`FONT_HREF`(Noto Sans KR/JP) · 툴바 라벨이 kr/jp/us
로 이미 들어 있다. 라벨 JSON 만 추가하면 UI 가 그 언어로 렌더된다.

`skill_common_check.py` 는 **로케일마다** 검사하므로, 한 언어만 `name` 이 틀리거나
description 이 비면 그 자리에서 잡힌다.

---

## 6. 검증 · 배포

```bash
python3 scripts/skill_common_check.py          # 전체
scripts/publish-dist.sh --dry-run              # 무엇이 나갈지 확인
```

`dist/PUBLISHED.json` 에 적힌 스킬만 · 적힌 버전으로만 공개된다.
**검증이 끝난 스킬만 올린다.**

### 버전 갱신은 세 곳

`SKILL.md` frontmatter · `dist/PUBLISHED.json` · 스크립트 안 하드코딩된 버전 문자열.
하나라도 놓치면 admin 이 옛 버전을 기록한다.
