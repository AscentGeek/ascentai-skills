## 사전 조건 확인

`{SKILL_DIR}/_shared/render/{path_aggregate.py,render_report.py,components.py,components_path.py}`,
`{SKILL_DIR}/_shared/{styles,labels,templates}` 가 함께 존재해야 합니다.
python3(표준 라이브러리)만 사용합니다. 리포트는 zip customer-analysis 와 동일한 카드 셸 위에
검색 여정 흐름도·경로 카드·허브 카드를 얹은 형태입니다(외부 JS 의존 없음).

이 리포트는 ListeningMind **PathFinder(패스파인더)** 에이전트의 분석틀 —
검색행동을 **방향 그래프(고객 검색여정/CDJ)** 로 보고 **주요 경로(Top 5)** 와
**핵심 분기점(Hub, Top 3)** 을 도출하는 틀 — 을 이식한 것입니다.

<!-- 원본 분석틀 스냅샷: references/prompts/agent_path.framework.kr.md
     (ascentkorea-hubble-ai-api prompt_builder.py:56-109 DEFAULT_PROMPTS["path"]).
     프로덕션 운영 프롬프트는 gpt_prompt DB 의 `agent_path` 행이며 리포지토리에
     노출돼 있지 않으므로, 인리포 fallback 프레임워크를 스냅샷으로 보존한다.
     3단계 프롬프트는 이 틀(구조 파악 → Top5 경로(3 흐름유형) → Hub&Branch 3개)을
     JSON 출력형으로 번안한 것이다. 챗 전용 마크업(:k[]/:::accordion)과 "수치 명시"
     규칙은 의도적으로 제외(수치는 Python 이 채움). -->

**PathFinder 데이터 계약**: 공개 `path_finder` 는 순수 경로(`data: List[List[str]]`)만
주고 노드 지표가 없습니다. 프로덕션 에이전트가 보는 내부 `PathDataDTO`(paths + info +
intent)를 재현하기 위해, **2회 호출**합니다 — `path_finder`(여정 구조) +
`keyword_info`(경로 내 고유 노드의 검색량·의도·월추이). 이렇게 하면 queryfinder 와 동일한
"**수치는 Python 이 실API 에서 계산**" 원칙이 성립하며, 경로·허브 랭킹은 프로덕션 에이전트와
같이 `volume`(월평균 검색량) 을 1순위 지표로 씁니다.

## 실행 절차

### 0단계 — 입력 수집 + 작업 폴더

데이터는 **ListeningMind MCP 도구**로 받습니다. **API 키를 묻지 마세요** —
환경변수·`.env`·DB 등에서 키를 찾으려 하지도 마세요.

필요한 입력은 셋뿐입니다:

> 검색 여정 분석을 시작하겠습니다.
> 1. **시드 키워드** — 이미 주셨다면 생략
> 2. **국가** — 기본 `kr` (별도 언급 없으면 kr 로 진행)
> 3. **시점** — 기본 `curr`(현재). 과거 대비는 `3m`/`6m`/`9m`/`12m`

시드가 이미 주어졌으면 바로 진행합니다.

**MCP 커넥터가 없으면** · 1단계의 도구 호출이 "도구를 찾을 수 없음" 으로 실패합니다.
그때는 사용자에게 **ListeningMind MCP 커넥터 연결**을 요청하고 중단하세요.
데이터를 지어내지 마세요.

확보되면:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-path-opportunity-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "작업 폴더: $WORKDIR"
```

이후 `{WORKDIR}` 는 위 절대경로로 치환합니다.

### 1단계 — 데이터 수집 (MCP 2회 호출)

> **매 호출은 예외 없이 3단계다** (SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ② (미적중이면) MCP 호출 + 응답 파일 확보 + `store` → ③ `log_event.py --type tool_call`
>
> ①이 **exit 0** 이면 파일이 이미 채워진 것이니 **MCP 를 부르지 말고** ③으로 갑니다
> (`--cached --used-credits-delta 0`). **exit 2** 면 ②로 진행합니다.

**1a. 검색 여정(경로)** — `path_finder` (응답 `data` = 경로 배열 `List[List[str]]`)

```bash
# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup path_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","time_point":"<TIME_POINT>","limit":300}' \
  --out "{WORKDIR}/lm_path.json"
```

미적중이면 **`path_finder` MCP 도구**를 아래 파라미터로 호출합니다:

```json
{"keyword": "<SEED>", "gl": "<GL>", "time_point": "<TIME_POINT>", "limit": 300,
 "user_query": "<사용자 발화 원문 그대로>"}
```

> `limit`(경로 수) 기본 300. `time_point` 는 0단계에서 받은 값(기본 `curr`).
> 응답 `data` 의 각 내부배열이 **하나의 순서 있는 검색 여정**(q0 → q1 → q2 …)입니다.
>
> `user_query` 는 캐시 키에서 제외되므로 `--params` 에는 넣지 않습니다(위 lookup 참조).

응답을 `{WORKDIR}/lm_path.json` 으로 확보한 뒤 캐시에 저장합니다
(응답이 커서 호스트가 파일로 저장했으면 그 경로를 `cp` · 본문으로 왔으면 heredoc —
SKILL.md §응답 파일 규칙 참조):

```bash
# ② 캐시 저장
python3 {SKILL_DIR}/scripts/mcp_cache.py store path_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","time_point":"<TIME_POINT>","limit":300}' \
  --file "{WORKDIR}/lm_path.json"

# ③ tool_call 발행
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool path_finder \
  --request-body '{"keyword":"<SEED>","gl":"<GL>","time_point":"<TIME_POINT>","limit":300}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent journey_analysis
```

**1b. 노드 검색량 보강** — 경로에 등장한 **고유 키워드**를 뽑아 `keyword_info`
(`data_type=all` → `ads_metrics`·`intents`·`monthly_volume` 포함)로 노드별 지표를 받습니다:

```bash
python3 - "{WORKDIR}/lm_path.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
data = d.get("data") or (d.get("result", {}) or {}).get("paths") or []
# 경로에 등장 순서대로 고유 키워드 수집 (keyword_info maxItems=1000 상한)
seen, kws = set(), []
for path in data:
    for kw in (path if isinstance(path, list) else []):
        if isinstance(kw, str) and kw.strip() and kw not in seen:
            seen.add(kw); kws.append(kw.strip())
kws = kws[:1000]
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_nodes.json"
```

미적중이면 **`keyword_info` MCP 도구**를 `kw_params.json` 의 내용 + `user_query` 로
호출하고, 응답을 `{WORKDIR}/lm_nodes.json` 으로 확보한 뒤 저장합니다:

```bash
# ② 캐시 저장
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_nodes.json" --expect <data 배열 길이>

# ③ tool_call 발행
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent journey_analysis
```

- 두 응답 모두 `result` 가 `FAILED` 이거나 도구 호출이 실패하면 중단·보고
  (커넥터·시드·gl 확인). 지어내지 마세요.
- `path_finder` 의 `data`(경로)가 비어 있으면 시드/국가/시점을 확인하고 중단합니다.
- `keyword_info` 가 일부 키워드를 못 돌려줘도 진행됩니다(해당 노드는 검색량 0으로 렌더 —
  경로 구조는 유지). 다만 대부분이 0이면 노드 검색량 보강이 실패한 것이니 gl 을 재확인하세요.

### 2단계 — 여정 그래프 집계

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py context \
  --paths "{WORKDIR}/lm_path.json" --nodes "{WORKDIR}/lm_nodes.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> --time-point <TIME_POINT> \
  --out "{WORKDIR}/lm_path_result.json"
```

`lm_path_result.json` 에는 노드(검색량·의도)·엣지(경로 인접에서 도출)·허브(분기 수)·여정
흐름도(flowTree)와, LLM 분석에 넣을 `pathsText`(후보 경로)·`hubsCsv`(후보 허브)·`nodesCsv`
가 들어있습니다. `{WORKDIR}/lm_path_result.json` 을 읽어 그 안의 `pathsText`·`hubsCsv`
값을 3단계 분석 입력으로 사용합니다.

### 3단계 — PathFinder 분석 (LLM) → lm_paths_raw.json

아래 규칙에 따라 `lm_path_result.json` 의 `pathsText`(후보 경로)·`hubsCsv`(후보 허브)를
직접 분석하고, 결과를 **JSON 으로만** `{WORKDIR}/lm_paths_raw.json` 에 저장합니다.

---

#### 분석 규칙 (Search Journey Analyst)

당신은 검색 여정 인사이트 분석가입니다. 목표는 소비자가 키워드에서 키워드로 이동하는
**검색 여정(경로)** 과 **핵심 분기점(Hub)** 을 읽어, 어디서 전환에 수렴하고 어디서 이탈하는지를
드러내는 것입니다.

**입력**:
- `pathsText`: 후보 여정 목록. 각 줄 = `번호. A → B → C …  (합산 검색량 N)`. 검색량 내림차순.
- `hubsCsv`: 후보 허브 목록. `name,volume,out_degree,path_count,downstream`.
  `out_degree` = 이 키워드에서 갈라지는 다음 키워드 수(=분기 수). 클수록 중요한 분기점.
- `nodesCsv`: 노드 표(참고용). `id,name,volume,volume_trend,intent,out_degree,path_count,outgoing`.

**전역 규칙**:
- **데이터 근거만**: 위 입력에 없는 키워드·사실을 지어내지 마세요.
- **수치 단정 회피(중요)**: 검색량·순위·분기 수 같은 **수치를 텍스트로 단정하지 마세요**
  ("가장 큰", "N개", "N배" 금지). 수치는 코드가 뱃지·칩에 사실값으로 채웁니다. 당신은
  **정성적 해석**(왜 이 여정인가, 어디서 갈라지고 이탈/수렴하나, 어떻게 공략하나)만 씁니다.
- **마크업**: 강조가 필요한 핵심 명사구는 `<strong>...</strong>` 만 허용. 그 외 마크업
  (`:k[]`, `:::accordion`, `➊`, 코드블록, 표)은 절대 쓰지 마세요.
- **출력 언어** = 분석 시장(`<GL>`) 언어. kr → 한국어.
- `path` 와 `keyword`·`evidenceKeywords` 는 반드시 입력에 **실제로 등장한 키워드 원문**만
  사용합니다(번역·변형·창작 금지). 코드가 미등장 키워드를 후처리에서 제거하므로, 지어내면
  그 항목은 리포트에서 사라집니다.

**① 분석 개요 (overview)**
- 전체 여정 그래프를 관통하는 핵심 통찰 1~2문장(100~200자). 소제목 없이 서술.
- 어떤 축으로 갈라지는지, 어디로 수렴/이탈하는지를 요약. 커버의 데이터 기반 요약문으로 실립니다.

**② 주요 경로 Top 5 (topPaths)** — 최대 5개
- `pathsText` 에서 대표성 있는 여정 5개를 고르고, 각각 **흐름 유형**을 붙입니다:
  1. **전환으로 수렴하는 흐름** → `flowType: "conversion"`
  2. **비교/검증에서 정체되는 흐름** → `flowType: "comparison"`
  3. **리스크/불신으로 이탈하는 흐름** → `flowType: "risk"` (**최대 2개**)
- 각 경로:
  - `flowType`: 위 셋 중 하나(`conversion`|`comparison`|`risk`)
  - `path`: 여정 키워드 시퀀스(입력의 정확한 원문 배열, 순서 유지) — 최소 2개(전이 1개 이상)
  - `intent`: 이 경로를 도는 고객의 의도 한 줄(정성)
  - `leakOrMerge`: 경로에서 **빠져나가는 지점** 또는 경로가 **합류되어 강해지는 지점**(정성)
  - `action`: 해결/강화 액션 1~2문장(정성)
  - `evidenceKeywords`: 이 경로의 근거 키워드/허브(입력에 있는 원문만, 2~4개)

**③ 핵심 분기점 Top 3 (hubs)** — 최대 3개
- `hubsCsv` 의 `out_degree` 가 큰 키워드 중 가장 중요한 분기점 3개를 고릅니다.
- 각 허브:
  - `keyword`: 허브 키워드(입력의 원문)
  - `meaning`: 이 분기가 무슨 뜻인가(고객 마음) 1문장
  - `dilemmas`: 고객이 여기서 하는 고민 2~3개(문자열 배열)
  - `actions`: 우리가 바로 실행 가능한 액션 2개(문자열 배열)

---

#### 출력 형식 — JSON only (마크다운·설명 금지)

```json
{
  "overview": "핵심 통찰 1~2문장",
  "topPaths": [
    {
      "flowType": "conversion",
      "path": ["냉장고", "냉장고 가격", "김치냉장고 가격"],
      "intent": "이 경로를 도는 고객 의도 한 줄",
      "leakOrMerge": "이탈/합류 지점 서술",
      "action": "해결/강화 액션 1~2문장",
      "evidenceKeywords": ["근거키워드1", "근거키워드2"]
    }
  ],
  "hubs": [
    {
      "keyword": "냉장고",
      "meaning": "이 분기의 의미(고객 마음) 1문장",
      "dilemmas": ["고객 고민1", "고객 고민2"],
      "actions": ["실행 액션1", "실행 액션2"]
    }
  ]
}
```

위 JSON 을 `{WORKDIR}/lm_paths_raw.json` 에 저장합니다.

### 4단계 — 경로/허브 후처리 (검색량 합산·환각 필터)

```bash
python3 {SKILL_DIR}/_shared/render/path_aggregate.py paths \
  --raw-paths "{WORKDIR}/lm_paths_raw.json" \
  --context "{WORKDIR}/lm_path_result.json" \
  --out "{WORKDIR}/lm_paths.json"
```

이 스크립트가 각 경로의 노드별 검색량 칩·합산 검색량 뱃지·단계수, 각 허브의 검색량·분기 수·
downstream 키워드를 코드로 계산해 카드용 형태로 저장하고, 3단계의 `overview` 는 커버 요약문으로
통과시킵니다. 또한 **환각 차단**: `path`·`evidenceKeywords`·허브 `keyword` 중 실제 그래프
노드가 아닌 것은 제거되고, 실노드 2개 미만 경로/미등장 허브는 통째로 버려집니다.
3단계 결과가 이 필터로 모두 비면 스크립트가 에러로 중단되니 3단계를 다시 수행하세요.

### 5단계 — 인사이트·실행 제안 (LLM) → lm_actions.json

`{WORKDIR}/lm_paths.json` 의 경로·허브를 바탕으로, 아래 JSON 을 `{WORKDIR}/lm_actions.json`
에 저장합니다. 출력 언어는 gl 매핑(kr→한국어). **수치 단정 금지**(3단계와 동일),
`<strong>` 외 마크업 금지.

- `synthesis`: 여정·분기 지형을 가로지르는 총평 2~3문장
- `insights`: 세부 인사이트 **정확히 3개** `{"title","body"}` — 여정에서 발견된 행태 기반 결론.
- `now`: 지금 바로 써볼 실행 제안 2~3개 `{"title","body"}`
- `future`: 앞으로 주목할 기회 2~3개 `{"title","body"}`

```json
{
  "synthesis": "총평 2~3문장",
  "insights": [{"title": "제목", "body": "행태 기반 결론 1~2문장"}],
  "now": [{"title": "실행 제안 제목", "body": "실행 내용 1~2문장"}],
  "future": [{"title": "기회 제목", "body": "기회 설명 1~2문장"}]
}
```

### 6단계 — HTML 렌더링

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill path-opportunity \
  --paths "{WORKDIR}/lm_paths.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_path_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/path-opportunity-report.html"
```

### 7단계 — 사용자 안내

```
✅ 검색 여정 분석 리포트 생성 완료: {WORKDIR}/path-opportunity-report.html
브라우저로 열면 검색 여정 흐름도·경로 카드·허브 카드와 인사이트를 대시보드/A4 뷰로 볼 수 있고,
Cmd+P 로 A4 PDF 저장이 가능합니다.
macOS 즉시 열기: open {WORKDIR}/path-opportunity-report.html
```
