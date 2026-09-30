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
    같아 그대로 적중한다 (lm-pathfinder-report 뒤에 lm-total-report 을 돌리면
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

**스킬당 소스 1벌 · zip 1개.** 스킬은 언어로 나뉘지 않는다 — 프롬프트는 영어 한 벌이고
분석 시장(`--gl`)과 리포트 언어(`--lang`)는 실행할 때 정한다. 리포트 언어를 늘려도
`skills/` 폴더 수도 zip 수도 안 늘어난다 (라벨 JSON 만 한 벌 더 들어간다).

```
_core/                          전 스킬·전 언어 공통 · 여기만 고치면 전부 반영
├── styles/                     CSS 6종 (4스킬 바이트 동일 · 측정 확인)
├── render/components.py        (cluster 판이 상위집합 · 통합)
├── render/inline_styles.py     CSS 이어붙이기 (순서는 스킬의 style_order.py)
├── LICENSE.txt                 스킬 zip 에 들어가는 라이선스 (한 벌)
├── api/{logging.py,__init__.py}
└── scripts/{mcp_cache.py,log_event.py}
     └ skill_name·version 은 __SKILL_NAME__ · __SKILL_VERSION__ 플레이스홀더

skills/<스킬명>/                 스킬 수만큼만
├── skill.yaml                  version · slug · mcp_tools · vendor_chart · borrows
├── SKILL.md                    name·description·문서 (영어)
├── references/*.md             절차 문서 (영어)
├── labels/*.<언어>.json         리포트 UI 라벨 · kr·jp·us 세 벌을 모두 싣는다
├── render/                     이 스킬 전용 렌더러 (스킬마다 실제로 다름)
│   └── style_order.py          이 스킬 슬러그별 CSS 순서 (합치는 코드는 _core)
├── styles/ templates/ vendor/  이 스킬 전용 자산
└── prompts/                    원본 프롬프트 스냅샷 (번역 금지 · zip 에는 안 실린다)
                                 total-report 는 형제 것을 참조한다 · 복제하지 않는다

dist/lm-<스킬명>.zip              빌드 산출 · 스킬당 하나 (국가 코드 없음)
```

### 빌드

```bash
scripts/build.sh                        # 전 스킬
scripts/build.sh queryfinder-report     # 한 스킬만
```

빌드가 하는 일 · `_core` + 스킬 전용 + (있으면) `borrows` 로 빌려온 형제 스킬 코드를 합쳐
**기존과 같은 zip 내부 구조**
(`_shared/` · `api/` · `scripts/` · `references/`)로 되돌리고, 플레이스홀더에 스킬명·버전을
박아 넣는다. **플레이스홀더 주입을 빠뜨리면 admin 에 `__SKILL_NAME__` 으로 기록된다.**

> **코드를 고칠 때는 `_core/` 또는 `skills/<n>/render/` 를 고친다.** zip 안이나
> 빌드 산출물을 직접 고치면 다음 빌드에 덮어써진다.

---

## 5. i18n · 리포트 언어 추가

스킬은 언어별로 나뉘지 않는다. 프롬프트(SKILL.md·references)는 영어 한 벌이고,
**분석 대상 시장(`--gl`)과 리포트 언어(`--lang`)를 실행할 때 따로 받는다.**
둘은 독립이라 미국 시장을 일본어로 쓰는 조합도 정상이다.

리포트 언어 추가 = `skills/<n>/labels/<슬러그>.<언어>.json` 을 한 벌 더 넣고,
`render_report.py` 의 `REPORT_LANGS` · `HTML_LANG` · `FONT_HREF` ·
`scripts/build.sh` 의 `REPORT_LANGS` 에 그 코드를 더한다.

번역 대상:
- `labels/*.<언어>.json` · 리포트 UI 라벨 (키는 기존 언어와 **완전히 동일**해야 한다)
- `SKILL.md` 의 `description` · **트리거 문구가 그 언어로도 들어가야 그 언어 발화에 발동한다**

번역하지 않는 것:
- `prompts/*.md` · DaaS 운영 프롬프트를 무수정으로 뜬 사본이다. 실행에 쓰이지 않고
  `type=<agent> locale=KR` 최신 행과 diff 해 이식본이 뒤처졌는지 보는 용도라,
  번역하거나 이름을 바꾸면 대조가 깨진다. **파일명의 `.kr` 은 원본 DB 행의 locale**
  이지 스킬 언어가 아니다 (스킬은 영어 한 벌이다).
- 코드 주석·docstring · 유지보수자가 읽는 것
- 리포트 **본문**은 라벨이 아니라 LLM 이 쓴다 · `출력 언어 = 리포트 언어(--lang)`
  규칙이 references 에 있어, `--lang jp` 면 시장이 어디든 LLM 이 일본어로 쓴다.
  검색어만 시장 언어 원문으로 남고, 그건 번역 토글이 처리한다.

`render_report.py` 에 `HTML_LANG`·`FONT_HREF`(Noto Sans KR/JP) · 툴바 라벨이 kr/jp/us
로 이미 들어 있다. 라벨 JSON 만 추가하면 UI 가 그 언어로 렌더된다.

`skill_common_check.py` 는 스킬마다 `SKILL.md` 를 검사한다 — `name` 이 `lm-<스킬명>`
과 다르거나 description 이 비면 그 자리에서 잡힌다.

---

## 6. 검증 · 배포

```bash
python3 scripts/skill_common_check.py          # 전체
scripts/publish-dist.sh --dry-run              # 무엇이 나갈지 확인
```

`dist/PUBLISHED.json` 에 적힌 스킬만 · 적힌 버전으로만 공개된다.
**검증이 끝난 스킬만 올린다.**

### 버전의 출처는 `skill.yaml` 하나

값을 적는 곳은 `skills/<n>/skill.yaml` 의 `version` **한 줄뿐**이다. 빌드가 두 곳에 박는다 —
zip 안 `SKILL.md` frontmatter 의 `metadata.version`(admin 이 카탈로그에 기록하는 값)과
`scripts/log_event.py`·`api/logging.py` 의 `__SKILL_VERSION__`(이벤트에 실리는 값).

**소스 `SKILL.md` 에는 version 을 적지 않는다.** 적어도 빌드가 버리지만, 적어 둔 사람은
그 값이 쓰인다고 믿게 된다. 검사기가 이 경우를 실패로 잡는다.

> 과거에 `skill.yaml` 만 2.0.0 으로 올리고 `SKILL.md` 를 놓쳐, admin 카탈로그에는 1.0.0 ·
> 이벤트 로그에는 2.0.0 이 기록될 뻔했다. 사람이 두 곳을 맞추는 구조를 없앤 이유다.

공개할 때는 `dist/PUBLISHED.json` 에 적은 버전이 zip 안 값과 같아야 한다. 다르면
`publish-dist.sh` 가 배포를 중단한다 — 검증이 덜 끝난 빌드가 나가는 걸 막는 장치다.

---

## 7. 새 스킬 추가 체크리스트

앞 절들이 규칙의 정본이고, 여기는 **순서**다. 처음 오는 사람이 §1~§6 을 조립하지 않아도
되게 훑어 가며 체크한다. `[검사]` 표시는 pre-commit 이 자동으로 막아 주는 항목이다.

### 1) 폴더와 이름

```
skills/<스킬명>/                 kebab-case · 국가 코드 붙이지 않는다
├── skill.yaml                  version · slug · mcp_tools · vendor_chart
├── SKILL.md                    영어 · frontmatter + 로깅 프로토콜
├── references/<슬러그>.md        영어 · 실행 절차
├── labels/<슬러그>.{kr,jp,us}.json
├── render/                     렌더러 · 집계기 · style_order.py
├── styles/ templates/
└── prompts/                    (있으면) 원본 프롬프트 스냅샷
```

- `[검사]` `SKILL.md` frontmatter 의 `name` 은 **`lm-<폴더명>`** 과 정확히 같아야 한다
- `[검사]` `description` 은 필수 · `<` `>` 금지 · **트리거 문구를 세 언어로** 넣는다
  (그 언어 발화에 스킬이 발동하려면 그 언어 문구가 description 에 있어야 한다)
- `[검사]` `SKILL.md` 에 `version` 을 적지 않는다 — 출처는 `skill.yaml` (§6)
- `[검사]` `SKILL.md` 가 가리킨 문서가 또 다른 문서를 가리키면 안 된다 (참조 깊이 1단계)
- `category`·`tags` 를 적는다. 없으면 admin 카탈로그가 기본값으로 떨어지고 화면에서 못 고친다

### 2) 라벨은 세 언어 전부

`labels/<슬러그>.kr.json` · `.jp.json` · `.us.json` 세 벌을 만들고 **키를 완전히 동일**하게
맞춘다. 한 언어라도 빠지면 그 `--lang` 으로 렌더할 때 파일을 못 찾아 죽는다 —
빌드가 이건 잡아 준다.

### 3) MCP 호출은 반드시 3단계 (§1·§2)

```
① mcp_cache.py lookup  →  ② (미적중) MCP 호출 + 응답 확보 + store  →  ③ log_event.py --type tool_call
```

`references/` 에 "MCP 도구를 부르세요" 라고만 쓰면 **캐시도 로깅도 빠진다.** DaaS 판은
`daas_call.py` 가 자동으로 했지만, MCP 는 호출 주체가 코드가 아니라 LLM 이라
자동화가 안 된다. 세 단계를 문서에 명시적으로 적어 둘 것.

### 4) 로깅 프로토콜을 SKILL.md 에 담는다 (§3)

`api/logging.py` 와 `scripts/log_event.py` 는 `_core` 에 있어 빌드가 넣어 준다.
문서에 적어야 하는 것은 **절차**다 — SKILL_DIR 동적 탐색 → 호스트 앱 판별 →
사용자 식별자 확보 → `--session-init` 후 **SID 고정** → 도구 호출마다 `tool_call` →
응답 확정 직후 `assistant_response` → HTML 저장 성공 시 `artifact_created`.

`--session-id` 를 명시하지 않으면 머신 전역 파일로 폴백해 **다른 대화창의 세션에
로그가 섞인다** (§3-2). 기존 스킬의 Step 0~6 을 그대로 가져다 쓰는 게 가장 안전하다.

크레딧은 봉투 실측만 싣는다. 호출 수로 계산하거나 잔량을 표기하지 않고, 봉투에 값이
없으면 인자를 아예 생략한다.

### 5) 코드를 어디에 둘지 정한다

| 놓을 곳 | 무엇 |
|---|---|
| `_core/` | 네 스킬이 **똑같이** 쓰는 것. 고치면 전부 반영된다 |
| `skills/<n>/render/` | 이 스킬에서만 다른 것 |
| `skill.yaml` 의 `borrows` | 형제 스킬 코드를 통째로 쓸 때. **복제하지 않는다** |

`_core` 에 올릴지 애매하면 일단 스킬에 두고, 두 번째 스킬이 같은 걸 필요로 할 때 올린다.
복제본을 두면 버그를 두 번 고쳐야 하고 한쪽만 고쳐진다 (실제로 그랬다).

> zip 안이나 `dist/` 산출물을 직접 고치지 않는다. 다음 빌드에 덮어써진다.

### 6) 빌드하고 검사한다

```bash
scripts/build.sh <스킬명>
python3 scripts/skill_common_check.py
```

pre-commit 이 같은 검사를 돌리므로, 통과하지 못하면 커밋이 막힌다.
훅은 클론 후 한 번 설치한다 · `ln -sf ../../scripts/hooks/pre-commit .git/hooks/pre-commit`

### 7) 실데이터로 한 번 돌려 본다

zip 을 **형제 스킬이 없는 빈 디렉터리**에 풀고, 수집부터 렌더까지 `references/` 의 단계를
그대로 밟아 본다. 사용자는 zip 하나만 받아서 쓰므로, 격리 상태에서 도는지가 유일한 기준이다.

`--gl` × `--lang` 조합도 확인한다 (시장 3 × 리포트 언어 3 = 9가지).

### 8) 공개할 때만 매니페스트에 올린다

```bash
scripts/publish-dist.sh --dry-run   # 무엇이 나갈지 확인
```

`dist/PUBLISHED.json` 에 적힌 스킬만 · 적힌 버전으로만 나간다. **검증이 끝난 것만 올린다.**

> 공개 전 zip 안을 직접 열어 볼 것. 과거 다른 저장소에서 개인 이메일이 예시로 박힌
> 문서가 걸린 적이 있다.

### 요약 체크리스트

- [ ] 폴더 `skills/<스킬명>/` · kebab-case · 국가 코드 없음
- [ ] `SKILL.md` — `name` = `lm-<폴더명>` · `description` 3언어 트리거 · `category`/`tags`
- [ ] `SKILL.md` 에 `version` 없음 · `skill.yaml` 에 semver
- [ ] `references/` 1단계 · MCP 3단계 호출 명시 · 로깅 Step 0~6
- [ ] `labels/` kr·jp·us 세 벌 · 키 동일
- [ ] 공통 코드는 `_core` · 형제 코드는 `borrows` (복제 금지)
- [ ] `scripts/build.sh` 통과 · `skill_common_check.py` 통과
- [ ] 격리 zip 에서 실데이터 실행 · `--gl` × `--lang` 조합 확인
- [ ] (공개할 경우) `dist/PUBLISHED.json` 등록 후 `publish-dist.sh`
