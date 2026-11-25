# Search Context v2 · 실행 절차

현재 시점 하나만 본다. 결과물은 **요약 + 마케팅 할 일 + 경로 맵**이고, 경로 분석은 사용자가 맵에서 경로를 골라
**페이지 안에서** 실행한다(사용자의 Claude와 ListeningMind 커넥터 사용, 결과 저장). 숫자는 `scripts/sc.py`가 계산하고,
당신(LLM)은 Step 5에서 요약과 마케팅 할 일만 쓴다.

모든 Bash 명령 맨 앞에서 SKILL.md 방법으로 `SKILL_DIR`를 찾는다.

## Step 0 — 입력 확인 + 작업 폴더
**개인정보 확인이 먼저다** · 사용자 메시지에 전화번호 · 이메일 · 신분증·카드·계좌 번호 같은 개인정보가 있으면 여기서 멈추고, 개인정보를 뺀 문장으로 다시 보내 달라고 요청한다(MCP 0회 · SKILL.md 「user_query」).
**HOST를 먼저 정한다** · 당신이 Claude면 `claude`, ChatGPT면 `chatgpt`. 사용자에게 묻지 않는다.
**커넥터 이름(`LM_SERVER`)** · 이 대화의 도구 목록에 보이는 ListeningMind 커넥터의 표시 이름(예: `ListeningMind`, `ListeningMind MCP Server`). Step 6에 넘긴다.
필요한 입력: 시드 · TARGET MARKET(`gl`) · REPORT LANGUAGE(`lang`) · PATHS(경로 수 100 · 200 · 300, 기본 300).
시장과 언어가 분명하지 않으면 한 번에 묻고, **그 질문에 경로 수도 함께 묻는다**(예: 「경로는 100 · 200 · 300개 중 몇 개로 볼까요? 기본은 300개예요.」).
경로 수만 빠졌고 시장·언어가 분명하면 따로 묻지 않고 300으로 진행한다.
비용을 짧게 알린다(경로 수 포함): 「경로 <PATHS>개 · 리포트 약 5 Lima · 경로 분석은 SERP 1개당 0.1 Lima」. 호출 내역은 나열하지 않는다.

```bash
SAFE=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
WORKDIR="$PWD/tmp/reports/listeningmind-search-context-${SAFE}-$(date +%Y%m%d-%H%M%S)"; mkdir -p "$WORKDIR/serp"
```

## Step 1 — 경로 (path_finder × 1, 현재 시점)
경로는 **Step 0에서 정한 PATHS(100 · 200 · 300, 기본 300)만큼 받고, 받은 경로 전부를 요약·마케팅 분석·처음 맵에 쓴다**(Step 3 `--show <PATHS>`).
`limit`을 PATHS로 넘긴다. limit이 다르면 서버가 돌려주는 경로 묶음도 다르므로(limit 100 ≠ limit 300의 앞 100개) 다른 limit의 응답을 잘라 쓰지 않는다.
페이지에서는 받은 범위 안에서 「경로 100 / 200 / 300」으로 줄여 볼 수 있다(추가 호출 없음).
`mcp_cache.py lookup path_finder --params '{"keyword":"<SEED>","gl":"<MARKET>","time_point":"curr","limit":<PATHS>}' --out "{WORKDIR}/lm_path.json"`
→ 미적중이면 `path_finder`를 같은 파라미터 + `"response_format":"download_url"` + `user_query` + `"is_skills":true` + `skill_desc`로 부르고
`fetch_download.py`로 `{WORKDIR}/lm_path.json`에 받은 뒤 `store` (SKILL.md 프로토콜).

## Step 2 — 검색량 (keyword_info × 1)
```bash
python3 {SKILL_DIR}/scripts/sc.py kwparams --paths "{WORKDIR}/lm_path.json" --gl <MARKET> --out "{WORKDIR}/kw_params.json"
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info --params-file "{WORKDIR}/kw_params.json" --out "{WORKDIR}/lm_nodes.json"
```
미적중이면 `kw_params.json` 내용 + `"response_format":"download_url"` + `user_query` + `"is_skills":true` + `skill_desc`로 부르고, 내려받아 `store`.

## Step 3 — 계획
```bash
python3 {SKILL_DIR}/scripts/sc.py plan --paths "{WORKDIR}/lm_path.json" --nodes "{WORKDIR}/lm_nodes.json" \
  --seed "<SEED>" --gl <MARKET> --lang <REPORT_LANGUAGE> --date <YYYY-MM-DD> --show <PATHS> --out "{WORKDIR}/plan.json"
```
SERP를 볼 키워드(E1 = 시드, E2… = 시드 다음의 주요 분기)를 출력한다. 경로 수 기준은 `--show`(= PATHS, 기본 300)다.

## Step 4 — SERP (serp × E 개수)
코드마다 `{WORKDIR}/serp/serp_<코드>.json`. `serp`를 `{"keyword":…,"gl":…,"num":10,"response_format":"download_url","user_query":…,"is_skills":true,"skill_desc":{"name":"__SKILL_NAME__","version":"__SKILL_VERSION__"}}`로 **하나씩 차례로**
부르고 `fetch_download.py … --collected-at "<응답 collected_at>"`로 받는다(같은 대화에 이미 받은 같은 키워드 파일이 있으면 복사).
```bash
python3 {SKILL_DIR}/scripts/sc.py serp-trim --plan "{WORKDIR}/plan.json" --serp-dir "{WORKDIR}/serp" --out "{WORKDIR}/evidence.json"
python3 {SKILL_DIR}/scripts/sc.py brief --plan "{WORKDIR}/plan.json" --evidence "{WORKDIR}/evidence.json" --out "{WORKDIR}/brief.md"
```

## Step 5 — 요약 + 마케팅 할 일 (LLM) → `marketing_raw.json`
brief.md를 Read하고 **짧게** 쓴다. 사용자는 내용이 많은 것을 원하지 않는다.
- `summary`: 2~3문장. 지금 이 시드를 검색하는 사람들이 어디로 흘러가는지, 무엇을 비교·확인하는지.
- `actions`: 3~5개. 마케터가 바로 할 수 있는 일. 각 항목은 `title`(한 줄), `why`(경로·SERP 근거 1~2문장. 리포트에는 E 번호와 SERP 원문의 대응이 보이지 않으므로 `E2-AI` `E3-1` 같은 번호를 쓰지 말고 「나이키 신발」 AI 개요, 「나이키」 검색 결과 3위(한국경제)처럼 출처를 말로 쓴다),
  `how`(구체 실행 1~2문장: 콘텐츠, SERP 노출, 상품 페이지, 광고 키워드, 가격 노출 등), `keywords`(brief.md에 있는 키워드 그대로 1~4개).
- 원칙: brief.md에 없는 사실·키워드를 지어내지 않는다. 숫자로 단정하지 않는다(경로 수는 표본). 근거가 약하면 "추정". 출력 언어 = REPORT LANGUAGE, 키워드는 원문.

```json
{"summary": "…", "actions": [{"title": "…", "why": "… (「나이키」 검색 결과 3위(한국경제))", "how": "…", "keywords": ["…"]}]}
```

## Step 6 — 렌더링 + 확인
```bash
python3 {SKILL_DIR}/scripts/sc.py render --plan "{WORKDIR}/plan.json" --evidence "{WORKDIR}/evidence.json" \
  --analysis "{WORKDIR}/marketing_raw.json" --lang <REPORT_LANGUAGE> --host <HOST> --lm-server "<LM_SERVER>" --out "{WORKDIR}/report.html"
python3 {SKILL_DIR}/scripts/check_report.py "{WORKDIR}/report.html"
```
`check_report.py`는 HTML에 적힌 HOST에 맞는 기능만 확인한다(chatgpt면 저장·Claude 연결 대신 요청문 복사, 보이는 문구에 Claude 안내가 없는지).
✗가 하나라도 있으면 넘기지 않는다. `⚠ 경로에 없는 키워드를 뺐습니다`가 나오면 해당 action의 keywords를 고친다.

## Step 7 — 게시 (페이지 안 경로 분석을 켜는 단계)
경로 분석·저장은 **Claude.ai에 게시된 아티팩트**에서만 동작한다(사용자의 Claude, ListeningMind 커넥터, 저장소를 페이지가 씀).
- Claude.ai에서 Artifact 도구를 쓸 수 있으면: 먼저 `Artifact` action `capabilities`로 런타임 계약을 확인하고,
  `/mnt/user-data/outputs/<폴더>/index.html`로 복사한 뒤 다음 capabilities로 게시한다.
  ```json
  {"sample": {}, "mcp": {"servers": [{"server": "ListeningMind", "tools": ["serp"]}]}, "db": {}, "user": {}}
  ```
  페이지는 `serp` 응답을 `{"gl","keyword","num"}` 입력과 `payload.data[]`(type `ai_overview` · `organic_results`) 모양으로 읽는다.
  이 대화에서 Step 4의 실제 `serp` 호출로 이 모양을 확인한 뒤에 게시한다.
- Artifact 도구가 없는 Claude 환경(Claude Code 등): HTML 파일을 건네고, 맵은 보이지만 경로 분석은 Claude.ai에 게시해야 동작한다고 알린다.
- **HOST = chatgpt**: 게시 단계가 없다. `report.html`을 다운로드 파일로 건넨다. 페이지에서 경로를 골라 「경로 분석 요청 복사」를 누르거나 질문을 입력하면
  요청문이 복사되고, 그것을 ChatGPT 대화창에 붙여 넣으면 된다고 알린다. 경로 분석 요청문은 ChatGPT가 ListeningMind 커넥터의 `serp`로 SERP를 조회하게 하므로
  ChatGPT에 ListeningMind 커넥터가 연결돼 있어야 한다. 저장 기능은 없다(답은 ChatGPT 대화에 남는다).

### ChatGPT에서 실행할 때 데이터 받기
`fetch_download.py`는 github.com에서 파일을 내려받는다. ChatGPT의 코드 실행 환경은 외부 네트워크가 막혀 있을 수 있으므로,
**HOST = chatgpt면 첫 호출 전에 `python3 -c "import urllib.request;urllib.request.urlopen('https://github.com',timeout=5)"`로 확인**하고,
막혀 있으면 처음부터 `response_format`을 빼고(json 본문) 불러 SKILL.md의 「응답이 본문으로 온 경우」 규칙대로 원문 전체를 파일로 쓴다.
같은 데이터를 두 번 사지 않도록, 이미 download_url로 부른 뒤라면 다시 부르지 말고 사용자에게 알린다.

## Step 8 — 알리기 (REPORT LANGUAGE)
요약 한두 줄과 마케팅 할 일 제목만 짧게 알리고, "맵에서 키워드를 눌러 경로를 고른 뒤 「경로 분석」을 누르면 분석되고 저장된다"고 안내한다.
처음 분석할 때 Claude와 ListeningMind 사용 허용 안내가 뜬다는 점, 경로 분석은 SERP 1개당 0.1 Lima라는 점도 알린다.
이번 리포트에 든 비용은 응답들의 `cost_detail.total_cost` 합계로 알린다.
