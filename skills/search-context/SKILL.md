---
name: lm-search-context
description: >-
  Search Context 분석 · 한 키워드(시드)를 지나는 소비자 검색 경로를 ListeningMind MCP(path_finder · keyword_info · serp)로
  읽어, 짧은 요약과 마케팅 관점의 할 일, 그리고 경로 맵 페이지를 만든다. 사용자는 맵에서 키워드를 눌러 경로를 고르고,
  페이지 안에서 바로 그 경로의 검색 목적을 SERP(AI 개요 + 검색 결과 1~3위) 근거로 분석·저장한다.
  "서치 컨텍스트", "Search Context 분석", "검색 맥락 분석", "이 키워드 왜 검색해?", "이 키워드 앞뒤로 뭘 검색해?",
  "검색 경로 맵", "경로 분석", "검색 목적 분석", "SERP 기반 검색 의도 분석", "키워드 마케팅 할 일" 같은 요청,
  영어("search context analysis", "search path map", "search intent from paths and SERP") ·
  일본어(「検索コンテキスト分析」「検索経路マップ」「このキーワードの前後の検索」)로 물을 때 반드시 사용한다.
  경로 전체 구조나 상위 여정 리포트만 원하면 lm-pathfinder-report를 쓴다.
allowed-tools: Bash, Read, Write, path_finder, keyword_info, serp
metadata:
  author: AscentKorea
  category: output
  tags: report, search context, search intent, serp
---

# lm-search-context — Search Context 분석

키워드 하나는 여러 검색 경로가 지나가는 교차점이다. 경로 하나만 떼어 보면 목적이 하나로 보이지만,
실제로는 서로 다른 맥락(앞에서 무엇을 찾다 왔고 뒤에서 어디로 가는지)이 겹쳐 있다. 이 스킬은
**포커스 키워드**를 지나는 모든 경로를 두 시점으로 모아 그 맥락의 갈래와 변화를 읽고, 대표 경로는
SERP 근거와 함께 처음부터 끝까지 연결해 검색 목적을 해석한다.

## 전제 조건

- **ListeningMind MCP 커넥터가 연결돼 있어야 한다** — 데이터는 `path_finder` · `keyword_info` · `serp`
  세 도구에서만 온다. 도구 호출이 "tool not found"로 실패하면 커넥터 연결을 요청하고 멈춘다.
- python3(표준 라이브러리)만 쓴다. pip 설치가 필요 없다.
- **API 키를 묻지 않는다.** 사용자가 API 키를 주어도 쓰지 않는다. **데이터를 지어내지 않는다.**
- 요청에 개인정보(전화번호 · 이메일 · 신분증·카드·계좌 번호 등)가 있으면 MCP를 부르기 전에 멈추고 다시 요청받는다(아래 「user_query」).

## 실행

요청이 들어오면 **먼저 `references/workflow.md`를 Read**하고 Step 0부터 순서대로 실행한다.
`{SKILL_DIR}`는 이 SKILL.md가 있는 폴더의 절대 경로다.

## 무엇을 만드나 (v2)

- **현재 시점 하나만** 본다. 과거와의 비교는 하지 않는다.
- 결과물은 내용을 적게: **요약(2~3문장) + 마케팅 관점에서 할 일(3~5개) + 경로 맵**.
- **경로 수(PATHS)는 사용자가 100 · 200 · 300 중에서 고르고, 기본은 300**이다. 고른 수만큼 받아서 요약·마케팅 분석·처음 맵에 모두 쓴다.
  페이지에서는 받은 범위 안에서 100 · 200 · 300으로 줄여 볼 수 있다(추가 호출 없음).
- **주 기능은 경로 맵에서 경로를 골라 분석하는 것**이다. 키워드를 누르면 시드부터 그 키워드까지의 경로가 선택되고,
  「경로 분석」을 누르면 페이지가 경로의 키워드마다 SERP(AI 개요 + 오가닉 1~3위)를 불러와 **사용자의 Claude로 바로 분석**해 보여 준다.
  맵 아래 「질문·경로 분석」 채팅에서 경로 데이터에 대해 바로 질문할 수도 있다(사용자의 Claude가 이 페이지의 경로 데이터로 답함).
  Claude나 ListeningMind 커넥터가 연결돼 있지 않으면 연결·권한 허용을 안내한다. 분석과 대화는 저장돼 다시 볼 수 있다.
- **실행 도구에 맞춰 HTML을 만든다** (`render --host`, workflow.md Step 0·6·7):
  - `claude` · Claude.ai에 게시하면 페이지가 사용자의 Claude와 ListeningMind 커넥터로 경로 분석·질문에 바로 답하고 저장한다.
  - `chatgpt` · 페이지가 LLM을 직접 부를 수 없으므로, 「경로 분석 요청 복사」와 질문 입력이 경로 데이터를 담은 **요청문을 복사**하고
    사용자는 ChatGPT 대화창에 붙여 넣는다(경로 분석의 SERP는 ChatGPT에 연결된 ListeningMind 커넥터가 조회). Claude 연결 안내·저장 기능은 나오지 않는다.
- 필수 기능 목록은 `references/report-features.md`, 확인은 `scripts/check_report.py`.

## 실행 도구 (HOST) · 묻지 않고 스스로 정한다

이 스킬을 실행하는 당신이 어떤 LLM 도구인지가 HOST다. Claude(claude.ai · Claude Code 등)면 `claude`, ChatGPT면 `chatgpt`.
사용자에게 묻지 않는다. Step 6 `render`에 `--host`로 반드시 넘긴다(생략하면 `auto`가 파일 시스템으로 추정하지만, 명시가 기본이다).

## 입력 (Step 0에서 한 번에 확인)

1. **시드 키워드** (예: 패딩)
2. **TARGET MARKET (`gl`)** — `kr` · `jp` · `us`
3. **REPORT LANGUAGE (`lang`)** — `kr` · `jp` · `us` (시장과 독립. 서로 추론하지 않는다)
4. **PATHS (경로 수)** — `100` · `200` · `300`, **기본 300**

시장이나 리포트 언어가 요청에 분명하지 않으면 **한 번, 짧게 묻고** 추측하지 않는다.
그때 **경로 수도 같은 질문에 함께 묻는다**(선택지 100 · 200 · 300, 「기본 300」이라고 표시). 사용자가 경로 수를 고르지 않거나
시장·언어가 이미 분명해 묻지 않는 경우에는 300으로 진행하고, 시작 안내에 「경로 300개」라고 적는다. 100 · 200 · 300 밖의 수를 말하면 가장 가까운 값으로 맞추고 알린다.

## 산출물

`{WORKDIR}/report.html` (단일 HTML · 라이트/다크). Claude.ai에서는 capabilities를 선언해 아티팩트로 게시하고, ChatGPT에서는 HTML 파일로 건넨다.

## 데이터 호출 비용 (사용자에게 미리 알린다)

사용자에게는 이 두 줄로 알린다(REPORT LANGUAGE로 옮겨 쓴다).

- **리포트 1건: 약 5 Lima**
- **경로 분석: SERP 1개당 0.1 Lima**

호출 내역이나 도구별 단가는 사용자에게 나열하지 않는다.
(참고 · 리포트는 처음에 SERP를 최대 6개 받는다. 경로 분석은 경로의 키워드마다 SERP 1개를 쓰고, 이미 받은 SERP — 처음 받은 것 포함 — 는 다시 받지 않는다.
금액은 2026-11-24 실제 청구액 기준. 실행 뒤 비용을 말할 때는 응답의 `cost_detail.total_cost` 합계를 쓴다.)

---

## MCP 호출 프로토콜 (lm-pathfinder-report와 같은 방식)

데이터는 **ListeningMind MCP 도구**에서 온다. 호출자가 코드가 아니라 **당신(LLM)**이므로
① 캐시 확인 ② 응답 파일 확보, 두 가지가 당신 책임이다.

### SKILL_DIR 찾기 (모든 Bash 명령 맨 앞에)

```bash
SKILL_DIR=$(find ~/.claude/skills ~/.claude/plugins /mnt/skills /mnt/user-data \
    ~/.codex/skills ~/.gemini/skills ~/.config/skills ./skills . \
    -maxdepth 4 -type d -name lm-search-context 2>/dev/null \
    | grep -v '\.trash' | head -1)
[ -z "$SKILL_DIR" ] && echo "❌ skill path not found" >&2
echo "SKILL_DIR=$SKILL_DIR"
```

비어 있으면 이 SKILL.md가 실제로 있는 폴더를 찾아 쓴다. 이후 `cd`를 하드코딩하지 않는다.

### 호출마다 2단계 (예외 없음)

```bash
# ① 호출 전 · 캐시 확인
python3 "$SKILL_DIR/scripts/mcp_cache.py" lookup <tool> \
  --params '<MCP 파라미터 JSON>' --out "{WORKDIR}/<file>.json"
```

- **exit 0 = 적중** · 파일이 이미 채워졌다 → **MCP를 부르지 않는다.**
- **exit 2 = 미적중** · ②로 간다.

```bash
# ② MCP 호출 → 원본 응답을 그대로 파일로 → 캐시에 저장
python3 "$SKILL_DIR/scripts/mcp_cache.py" store <tool> \
  --params '<①과 완전히 같은 JSON>' --file "{WORKDIR}/<file>.json" \
  --expect <봉투의 data 배열 길이>
```

`--params`는 ①과 ②에서 **글자까지 같아야** 다음 실행에서 캐시가 맞는다.

### 응답 파일 규칙 (가장 중요)

집계 스크립트는 MCP 응답을 **가공 없이** 읽는다.

- **파일은 경로로만 넘긴다.** 내용을 컨텍스트로 가져와 다시 쓰지 않는다(큰 응답에서 레코드가 빠진다).
- **요약 · 발췌 · 재구성 금지.** **레코드 하나도 빼지 않는다.**
- **호스트가 결과를 파일로 저장한 경우가 기본이다.** 본문 대신
  `Tool result too large for context, stored at /mnt/user-data/tool_results/....json`(Claude.ai) 또는
  `Error: result (N characters) exceeds maximum allowed tokens. Output has been saved to …/tool-results/….txt`(Claude Code)
  가 온다. 앞의 `Error:`나 `.txt` 확장자에 속지 않는다 — 내용은 원본 JSON이다. **도구를 다시 부르지 않고**
  `cp "<저장 경로>" "{WORKDIR}/<file>.json"` 한다.
- **응답이 본문으로 온 경우에만** heredoc으로 원문 전체를 쓴다:
  ```bash
  cat > "{WORKDIR}/<file>.json" <<'DUMP_EOF'
  <MCP 응답 JSON 원문 전체>
  DUMP_EOF
  ```
- **절대 금지** · 응답이 크다고 ① 조회 키워드 수를 줄이거나 ② 경로 `limit`을 낮추거나 ③ 레코드를
  요약·발췌하는 것. 범위를 줄여야 할 것 같으면 진행하지 말고 사용자에게 알린다.
### 큰 응답은 `download_url`로 받는다 (keyword_info · serp 기본)

`keyword_info`(수백 개 키워드)와 `serp`(호출당 약 20~30KB × 최대 8회)는 응답이 커서 본문으로 받으면
컨텍스트를 크게 차지하고, heredoc으로 옮겨 적다가 레코드가 빠질 위험이 있다. 이 두 도구는
**`"response_format": "download_url"`로 부르고 `scripts/fetch_download.py`로 내려받는다**
(`path_finder`도 같은 방식을 쓴다).

```bash
python3 "$SKILL_DIR/scripts/fetch_download.py" \
  --url "<응답 download.browser_download_url>" --sha256 "<download.sha256>" \
  --expect <download.item_count> --out "{WORKDIR}/<file>.json"
# serp 는 수집 시각이 파일에 없고 응답 메타에만 있으므로 --collected-at "<응답 collected_at>" 을 꼭 붙인다
```

- 스크립트가 sha256을 검증한다. 실패하면 **도구를 다시 부르지 말고** 내려받기만 다시 한다.
- 내려받은 파일은 `data` 배열만 들어 있다(봉투 없음). `sc.py` · `mcp_cache.py`는 두 형태를 모두 읽는다.
- 내려받기가 네트워크 정책으로 막히면(github.com 차단) `response_format`을 빼고 다시 부르는 대신,
  사용자에게 상황을 알리고 판단을 구한다(같은 데이터를 두 번 사게 되므로).
- `response_format` · `user_query` · `is_skills` · `skill_desc`는 캐시 키에서 빠진다. 받는 방식이 달라도 같은 데이터로 친다.

### 세션 캐시

`~/.lima-agents/mcp-cache/<session>/` · 같은 대화에서 같은 `(도구 + 파라미터)`는 다시 부르지 않는다.
`path_finder`는 lm-pathfinder-report 등 형제 스킬과 파라미터가 같으면 그대로 적중한다.
캐시를 우회하려면 `LIMA_MCP_REFRESH=1`.

### user_query · 사용자가 무엇을 물었는지 기록

MCP 도구는 `user_query`를 받는다. 이 호출을 부른 **사용자 발화 원문**을 **모든 호출에** 넣는다(번역·요약·의역 금지).

```json
"user_query": "<사용자 메시지 원문 그대로>"
```

**개인정보가 있으면 멈춘다.** 사용자 메시지에 전화번호 · 이메일 주소 · 주민등록번호 등 신분증 번호 · 카드 번호 · 계좌번호 같은
개인정보가 들어 있으면 **MCP를 하나도 부르지 않고 멈춘다.** 개인정보를 뺀 문장으로 요청을 다시 보내 달라고 사용자에게 요청한다.
개인정보를 스스로 지우거나 가린 문장을 `user_query`에 넣고 진행하지 않는다(원문 그대로라는 규칙과 부딪히므로, 사용자가 다시 보낸 원문을 쓴다).
이름만 있고 연락처·번호가 없으면 개인정보로 보지 않는다.

> 자동으로 붙지 않고, 캐시 키가 아니다 — `mcp_cache.py --params`에는 넣지 않는다.

### is_skills · 스킬 경유 호출 표시

MCP 도구는 `is_skills`를 받는다. 기본값이 `false`이므로 **모든 호출에 `true`로** 보낸다(데이터와 과금은 같다).

```json
"is_skills": true
```

> 자동으로 붙지 않고, 캐시 키가 아니다 — `mcp_cache.py --params`에는 넣지 않는다.

### skill_desc · 어느 스킬·버전이 불렀는지 기록

MCP 도구는 `skill_desc`를 받는다. 아래 객체를 **문자열이 아닌 JSON 객체 그대로**, `"is_skills": true` 옆에 **모든 호출에** 넣는다.
버전은 이 파일 머리의 `metadata.version`과 같아야 한다.

```json
"skill_desc": {"name": "__SKILL_NAME__", "version": "__SKILL_VERSION__"}
```

> 자동으로 붙지 않고, 캐시 키가 아니다 — `mcp_cache.py --params`에는 넣지 않는다.

### 호출은 한 번에 하나

**MCP 도구 두 개를 동시에(병렬로) 부르지 않는다.** `serp`를 여러 키워드에 부를 때도 하나씩 차례로 부른다.
동시 호출은 호출 제한(`Too Many Requests`)에 걸린다.

### 실패한 호출

응답의 `result`가 `OK`가 아니거나(`FAILED` 등) 도구 오류가 오면 `reason`을 보고 다음처럼 한다. 이유를 짐작해 지어내지 않는다.

- `Too Many Requests` — 호출 제한이다. 잠시 기다렸다가 **같은 호출을 한 번 더** 부른다. 다시 실패하면 멈추고 사유를 그대로 알린다.
- `Insufficient Lima` — 잔액이 다 됐다. 다시 불러도 소용없다. 멈추고 사유를 그대로 전하며 충전이 필요하다고 알린다.
- `Account Locked` — 플랜이 만료됐다. 멈추고 사유를 그대로 전한다(잔액 문제가 아니다).
- `Not Authenticated` · `Invalid API Key` — 키가 잘못됐거나 플랜 밖의 도구다. 멈추고 사유를 그대로 전하며 커넥터와 플랜을 확인해 달라고 한다.
- `Internal Server Error` · `Service Unavailable` · 그 밖의 실패 — 서버 쪽 실패다. 과금 문제로 돌리지 않는다. 멈추고 사유를 그대로 전한다.
- **실패한 응답은 캐시에 저장하지 않는다**(`mcp_cache.py store`도 거부한다). 다음 단계로 넘어가거나 데이터를 지어내지 않는다.
- `serp` 하나가 실패하면 그 근거만 빼고 진행할 수 있다(`serp-trim`이 「SERP 없음」으로 표시한다). `path_finder` · `keyword_info`가 실패하면 리포트를 만들 수 없으니 멈춘다.
- 비용은 응답의 `cost_detail.total_cost`로 확인된 값만 말하고, 남은 잔액은 말하지 않는다.
