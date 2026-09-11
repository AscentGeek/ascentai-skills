## 사전 조건 확인

`{SKILL_DIR}/_shared/render/{query_aggregate.py,render_report.py,components.py}`,
`{SKILL_DIR}/_shared/{styles,labels,templates}` 가 함께 존재해야 합니다.
python3(표준 라이브러리)만 사용합니다. 리포트는 zip customer-analysis 와 동일한 카드 형태입니다.

이 리포트는 ListeningMind **QueryFinder(인텐트파인더)** 의 실제 분석 프롬프트(agent_query v0.4.7)
분석틀을 이식해, 연관 쿼리를 **검색 목적**과 **브랜드/논브랜드**로 묶어 카드로 제시합니다.

<!-- 원본 프롬프트 스냅샷: references/prompts/agent_query.1958.kr.md (v0.4.7, 2026-07-01)
     + agent_system_prompt.1758.kr.md — gpt_prompt DB(intent-finder-dev)에서 2026-07-20 export.
     3단계 프롬프트가 이 원본의 분석틀(타겟/의도 키워드 분해·의도 유형·Top5 검색목적·Top5
     브랜드/논브랜드·volume_avg 전용·상위 1,000개 캡)을 JSON 출력형으로 번안한 것임을
     대조·검증할 때 이 스냅샷과 diff 하세요. 챗 전용 마크업(:k[]/:::accordion/➊)과
     "정확한 수치 명시" 규칙은 의도적으로 제외(수치는 Python 이 채움 — 결정 1).
     kbf 필드는 원본에 없는 스킬 자체 확장(zip persona-card 스키마 유래)입니다.
     운영 프롬프트 갱신 여부는 분기 1회 gpt_prompt 의 KR 최신 활성 행과 재대조. -->

## 실행 절차

### 0단계 — 입력 수집 + 작업 폴더

데이터는 **ListeningMind MCP 도구**로 받습니다. **API 키를 묻지 마세요** —
환경변수·`.env`·DB 등에서 키를 찾으려 하지도 마세요.

필요한 입력은 둘뿐입니다:

> 쿼리 기회 분석을 시작하겠습니다.
> 1. **시드 키워드** — 이미 주셨다면 생략
> 2. **국가** — 기본 `kr` (별도 언급 없으면 kr 로 진행)

시드가 이미 주어졌으면 바로 진행합니다.

**MCP 커넥터가 없으면** · 1단계의 도구 호출이 "도구를 찾을 수 없음" 으로 실패합니다.
그때는 사용자에게 **ListeningMind MCP 커넥터 연결**을 요청하고 중단하세요.
데이터를 지어내지 마세요.

확보되면:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-query-opportunity-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "작업 폴더: $WORKDIR"
```

이후 `{WORKDIR}` 는 위 절대경로로 치환합니다.

### 1단계 — 데이터 수집 (MCP 2회 호출)

연관 키워드 **목록**과 키워드 **상세**가 도구가 나뉘어 있습니다.
`intent_finder` 로 연관 키워드 문자열 목록을 받고, 그 목록을 `keyword_info` 로 넘겨
검색량·의도·월별추이가 담긴 상세를 받아 `lm_query.json` 으로 저장합니다.

> **매 호출은 예외 없이 3단계다** (SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ② (미적중이면) MCP 호출 + 덤프 + `store` → ③ `log_event.py --type tool_call`
>
> ①이 **exit 0** 이면 파일이 이미 채워진 것이니 **MCP 를 부르지 말고** ③으로 갑니다
> (`--cached --used-credits-delta 0`). **exit 2** 면 ②로 진행합니다.

**1a. 연관 키워드 목록** — `intent_finder`

```bash
# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup intent_finder \
  --params '{"keywords":["<SEED>"],"gl":"<GL>","limit":1000,"sort":"volume_avg","order":"desc","volume_threshold":0}' \
  --out "{WORKDIR}/lm_keyword_list.json"
```

미적중이면 **`intent_finder` MCP 도구**를 아래 파라미터로 호출합니다:

```json
{"keywords": ["<SEED>"], "gl": "<GL>", "limit": 1000,
 "sort": "volume_avg", "order": "desc", "volume_threshold": 0,
 "user_query": "<사용자 발화 원문 그대로>"}
```

> **`volume_threshold` 는 반드시 `0`** — ListeningMind 웹 UI 와 동일하게 연관 키워드를
> **전량** 수집합니다. 올리면 월평균 검색량이 그 값 미만인 키워드가 잘려 나가 지형이
> 왜곡됩니다(예: `100` 이면 검색량 100 미만 롱테일이 통째로 누락). 수량은 `limit:1000`
> + 이후 상위 1,000개 상한으로 이미 제한되므로, 하한으로 추가로 자르지 마세요.
>
> `user_query` 는 캐시 키에서 제외되므로 `--params` 에는 넣지 않습니다(위 lookup 참조).

응답 원문을 그대로 덤프하고 캐시에 저장합니다 (`data` = 키워드 문자열 배열, 검색량순 정렬):

```bash
cat > "{WORKDIR}/lm_keyword_list.json" <<'DUMP_EOF'
<intent_finder 응답 JSON 원문 전체>
DUMP_EOF

# ② 캐시 저장 · --expect 에 봉투의 data 배열 길이를 넣어 대조
python3 {SKILL_DIR}/scripts/mcp_cache.py store intent_finder \
  --params '{"keywords":["<SEED>"],"gl":"<GL>","limit":1000,"sort":"volume_avg","order":"desc","volume_threshold":0}' \
  --file "{WORKDIR}/lm_keyword_list.json" --expect <data 배열 길이>

# ③ tool_call 발행
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool intent_finder \
  --request-body '{"keywords":["<SEED>"],"gl":"<GL>","limit":1000,"volume_threshold":0}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent query_expansion
```

**1b. 키워드 상세** — `keyword_info` · 위 목록의 **상위 1,000개**
(프로덕션 QueryFinder 와 동일한 상한 — `ai-context-intent` size=1000 / `MAX_KEYWORDS=1000`)

먼저 목록에서 상위 1,000개를 뽑아 파라미터 파일을 만듭니다:

```bash
python3 - "{WORKDIR}/lm_keyword_list.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
# 프로덕션과 동일하게 상위 1,000개 전부 상세 조회 (keyword_info maxItems=1000).
# 200개 등으로 자르면 총검색량·그룹 합산이 과소집계되어 프로덕션과 어긋난다.
kws = [k for k in d.get("data", []) if isinstance(k, str)][:1000]
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_query.json"
```

미적중이면 **`keyword_info` MCP 도구**를 `kw_params.json` 의 내용 + `user_query` 로
호출합니다. **`data_type` 은 반드시 `all`** 이고, **키워드는 상위 1,000개 전부**입니다.

> **규모를 임의로 줄이지 마세요.** 응답이 크다는 이유로 300개로 자르거나
> `data_type` 을 `ads_metrics` 로 낮추면 총검색량·그룹 합산이 과소집계되고
> 월별 추이 차트가 비어 프로덕션과 어긋납니다. 응답이 크면 아래 **경로 A** 로
> 처리하면 되므로, 조회 범위를 줄일 이유가 없습니다.

응답을 받는 방법은 응답 크기에 따라 둘로 갈립니다.

#### 경로 A — 응답이 커서 호스트가 파일로 저장한 경우 (1,000개는 대개 여기)

도구 결과가 본문 대신 이런 안내로 올 때가 있습니다:

```
Tool result too large for context, stored at
/mnt/user-data/tool_results/ListeningMind_keyword_info_<id>.json.
Use grep to search for specific content or head/tail to read portions.
```

**이건 실패가 아닙니다. 응답 전체가 이미 그 파일에 들어 있습니다.**
옮겨 적을 필요 없이 **그 경로를 그대로 넘기면 됩니다**:

> 저장 파일이 봉투가 아니라 `[{"type":"text","text":"<JSON 문자열>"}]` 래퍼로
> 감싸져 있을 수 있습니다(실측 · claude.ai 웹 컨테이너). `mcp_cache.py store` 가
> **자동으로 벗겨 정규화**하므로 손대지 마세요. 벗긴 뒤의 레코드 수가
> `--expect` 와 대조됩니다.

```bash
# 호스트가 저장한 경로를 그대로 사용 (원문 손실 없음)
SAVED="/mnt/user-data/tool_results/ListeningMind_keyword_info_<id>.json"

# 레코드 수 확인 (본문을 컨텍스트로 읽지 않고 개수만 센다)
python3 -c "import json;print(len(json.load(open('$SAVED')).get('data',[])))"

# 작업 폴더로 복사 + 캐시 저장
cp "$SAVED" "{WORKDIR}/lm_query.json"
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_query.json" --expect <위에서 센 개수>
```

크레딧은 봉투에서 읽습니다 — 파일이 커도 이 두 값만 뽑으면 됩니다:

```bash
python3 -c "
import json; d=json.load(open('$SAVED'))
print('delta=', (d.get('cost_detail') or {}).get('total_cost'))
print('cumulative=', d.get('used_credits'))"
```

#### 경로 B — 응답이 컨텍스트로 그대로 온 경우 (소규모)

응답 원문을 **가공 없이 그대로** 덤프합니다:

```bash
cat > "{WORKDIR}/lm_query.json" <<'DUMP_EOF'
<keyword_info 응답 JSON 원문 전체>
DUMP_EOF

python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_query.json" --expect <data 배열 길이>
```

#### ③ tool_call 발행 (경로 A·B 공통)

```bash
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent query_expansion
```

> **금지 사항** · 응답이 크다고 ① 키워드 수를 줄이거나 ② `data_type` 을 낮추거나
> ③ 레코드를 요약·발췌해 옮기지 마세요. 셋 다 리포트 수치를 조용히 망가뜨립니다.
> 크면 경로 A 를 쓰고, `--expect` 로 건수를 대조하세요. 어긋나면 `store` 가 거부합니다.
> 축소가 불가피하다고 판단되면 **진행하지 말고 사용자에게 상황을 보고**하세요.

> 프로덕션 대조: 허블 챗 QueryFinder(`ascentkorea-hubble-ai-api`)는 내부 API
> `ai-context-intent` 를 **1회 호출**해 상위 1,000개를 full metrics 로 받는다. 이 내부
> 엔드포인트는 공개돼 있지 않으므로, 공개 도구에서는 `intent_finder`(상위 1,000) +
> `keyword_info`(그 1,000개 상세) **2회 호출**로 동일한 상위 1,000개 데이터셋을 재현한다.
> (양쪽 모두 상위 1,000 상한이라, ListeningMind 웹 UI 의 전체 키워드 총합과는 다를 수 있다.)

`keyword_info` 응답은 최상위에 `data`(레코드 배열)를 담고 있어 집계기가 그대로 읽습니다
(별도 변형 불필요 — 각 레코드에 `keyword`·`ads_metrics`·`intents`·`monthly_volume` 포함).

- 두 응답 모두 `result` 가 `FAILED` 이거나 도구 호출이 실패하면 중단·보고(커넥터·시드·gl 확인).
  지어내지 마세요.
- 연관 키워드가 200개 미만이면 있는 만큼만 넘어갑니다.

### 2단계 — 키워드 컨텍스트 집계

```bash
python3 {SKILL_DIR}/_shared/render/query_aggregate.py context \
  --raw "{WORKDIR}/lm_query.json" --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/lm_query_result.json"
```

`lm_query_result.json` 에는 키워드별 `volume_avg`·`intents` 와, LLM 분석에 넣을 `csv` 텍스트가 들어있습니다.
`{WORKDIR}/lm_query_result.json` 을 읽어 그 안의 `csv` 값을 3단계 분석 입력으로 사용합니다.

### 3단계 — QueryFinder 분석 (LLM) → lm_groups_raw.json

아래 규칙에 따라 `lm_query_result.json` 의 `csv`(연관 쿼리 데이터)를 직접 분석하고,
결과를 **JSON 으로만** `{WORKDIR}/lm_groups_raw.json` 에 저장합니다.

---

#### 분석 규칙 (Data Insight Analyst)

당신은 검색 데이터 인사이트 분석가입니다. 목표는 연관 쿼리 데이터를 분석해 **검색 의도(검색 목적)**
와 **브랜드/논브랜드 지형**, 전략적 인사이트를 도출하는 것입니다.

**입력**: `csv` 각 행 = `keyword, volume_avg, i, n, c, t, trend`
- `volume_avg` = **월 평균 검색량**. 검색량은 항상 이 값을 사용합니다(연간 총량·×12 금지).
- `i/n/c/t` = 정보(informational)/길찾기(navigational)/상업조사(commercial)/거래(transactional) 의도 비중.
- `trend` = 검색량 증감 추세(양수=상승세, 음수=하락세). **상승 추세 키워드는 떠오르는
  수요이므로 그룹핑·인사이트에서 주목**하되, 추세 언급은 "상승세/하락세" 같은
  정성 표현만 사용하고 수치·배율은 쓰지 마세요.
- `volume_avg` 내림차순 상위 1,000개까지만 분석합니다(이미 정렬·상한 적용됨).

**전역 규칙**:
- **데이터 근거만**: csv 에 없는 사실을 지어내지 마세요.
- **수치 단정 회피(중요)**: 검색량·비중·순위 같은 **수치를 텍스트로 단정하지 마세요**
  ("가장 큰", "OO%", "N배" 금지). 수치는 리포트의 뱃지·키워드칩에 코드가 사실값으로 채우므로,
  당신은 **정성적 해석**(왜 이렇게 검색하는가, 무슨 의도인가, 어떻게 공략하나)만 씁니다.
- **마크업 금지**: `:k[]`, `:c[]`, `:::accordion`, `➊➋➌`, 코드블록, 표 등 특수 마크업을
  절대 쓰지 마세요. 순수 텍스트 문자열만 JSON 값으로 넣습니다.
- **출력 언어** = 분석 시장(`<GL>`) 언어. kr → 한국어.
- `memberKeywords` 는 반드시 csv 에 실제로 등장한 keyword 원문만 사용합니다(번역·변형 금지).

**① 분석 개요 (overview)**
- 전체 검색 데이터를 관통하는 핵심 통찰 1~2문장(100~200자). 소제목 없이 서술.
- 이 문장은 리포트 커버의 "배경과 목적" 아래 **데이터 기반 요약문**으로 그대로 실립니다.

**② 검색 목적 Top 5 (intentGroups)** — 최대 5개
- 각 키워드를 **타겟 키워드**(제품·브랜드·카테고리 명사)와 **의도 키워드**(맥락·상황을 드러내는 말)로 분해합니다.
- 의도 유형: 정보 탐색형(~사용법/효과/부작용), 문제 해결형(~문제/고장/오류), 구매 의도형(~가격/최저가/구매처/할인/중고),
  간접 경험확인형(~후기/리뷰/평가), 정보형(~뜻/정의/란), 비교형(~vs/비교) 등.
- 의미적으로 유사한 의도 키워드들을 **하나의 검색 목적 그룹으로 묶습니다**(그룹당 여러 키워드; 키워드 1개짜리 그룹 나열 금지).
- 각 그룹:
  - `title`: 검색 목적명(예: "가격·구매처 비교", "사용법·관리 정보 탐색") — 명확하고 구체적으로
  - `intentType`: 위 의도 유형 중 대표 하나(예: "구매 의도형")
  - `memberKeywords`: 이 목적에 속하는 csv 키워드 목록(중요도순)
  - `who`: 이 검색을 하는 사람들의 맥락·심리 1~2문장(정성)
  - `insight`: 마케팅·제품 관점의 공략 시사점 1~2문장(정성)
  - `kbf`: (선택) `[{ "factor": "결정/관심 요인", "evidence_keywords": ["근거키워드", ...] }]` 2~4개

**③ 브랜드/논브랜드 Top 5 (brandGroups)** — 최대 5개
- csv 에서 브랜드 키워드(제품·브랜드명)와 논브랜드 키워드(일반 카테고리)를 식별합니다. 브랜드에 가중치를 둡니다.
- 각 그룹:
  - `name`: **실제 브랜드명 하나**(예: "나이키") 또는 논브랜드 카테고리명
  - `kind`: `"brand"` 또는 `"nonbrand"`
  - `memberKeywords`: 이 브랜드/카테고리로 묶이는 csv 키워드 목록
  - `label`: 그룹 성격 라벨(한국어, 예: "성능 러닝화 대표 브랜드")
  - `analysis`: 이 브랜드/논브랜드에 대한 정성 분석·통찰 1~2문장

---

#### 출력 형식 — JSON only (마크다운·마크업 금지)

```json
{
  "overview": "핵심 통찰 1~2문장",
  "intentGroups": [
    {
      "title": "검색 목적명",
      "intentType": "구매 의도형",
      "memberKeywords": ["키워드1", "키워드2"],
      "who": "이 검색을 하는 사람들의 맥락 1~2문장",
      "insight": "공략 시사점 1~2문장",
      "kbf": [{"factor": "요인", "evidence_keywords": ["근거키워드1"]}]
    }
  ],
  "brandGroups": [
    {
      "name": "실제 브랜드명",
      "kind": "brand",
      "memberKeywords": ["키워드1"],
      "label": "그룹 성격 라벨",
      "analysis": "정성 분석 1~2문장"
    }
  ]
}
```

위 JSON 을 `{WORKDIR}/lm_groups_raw.json` 에 저장합니다.

### 4단계 — 그룹 후처리 (검색량 합산·근거 키워드)

```bash
python3 {SKILL_DIR}/_shared/render/query_aggregate.py groups \
  --raw-groups "{WORKDIR}/lm_groups_raw.json" \
  --context "{WORKDIR}/lm_query_result.json" \
  --out "{WORKDIR}/lm_groups.json"
```

이 스크립트가 각 그룹의 `volume_avg` 합산·정렬과 근거 키워드(evidence, 검색량 라벨 포함),
그룹 헤더 뱃지용 `volumeLabel`(합산 검색량)·`memberCount`(키워드 수)를 코드로 계산해
카드용 형태로 저장하고, 3단계의 `overview` 는 커버 요약문으로 통과시킵니다.
(수치는 여기서 사실값으로 채워집니다.)
또한 **환각 차단**: `memberKeywords`·`kbf.evidence_keywords` 중 csv 에 없는 키워드는
여기서 제거되고, 실키워드가 하나도 없는 그룹/kbf 행은 통째로 버려집니다.
3단계 결과가 이 필터로 비면(그룹 0개) 스크립트가 에러로 중단되니 3단계를 다시 수행하세요.

### 5단계 — 인사이트·실행 제안 (LLM) → lm_actions.json

`{WORKDIR}/lm_groups.json` 의 그룹들을 바탕으로, 아래 JSON 을 `{WORKDIR}/lm_actions.json` 에 저장합니다.
출력 언어는 gl 매핑(kr→한국어). **수치 단정 금지**(3단계와 동일), 마크업 금지.

- `synthesis`: 검색 목적·브랜드 지형을 가로지르는 총평 2~3문장
- `insights`: 세부 인사이트 **정확히 3개** `{"title","body"}` — 데이터에서 발견된
  사용자 행태를 근거로 한 논리적 결론. title 은 핵심 키워드 기반으로 짧게,
  body 는 1~2문장. (단순 나열 금지 — 그룹 분석 결과에서 도출)
- `now`: 지금 바로 써볼 실행 제안 2~3개 `{"title","body"}` (특정 검색 목적/브랜드에 응답)
- `future`: 앞으로 주목할 기회 2~3개 `{"title","body"}`

```json
{
  "synthesis": "총평 2~3문장",
  "insights": [{"title": "핵심 키워드 기반 제목", "body": "행태 기반 결론 1~2문장"}],
  "now": [{"title": "실행 제안 제목", "body": "실행 내용 1~2문장"}],
  "future": [{"title": "기회 제목", "body": "기회 설명 1~2문장"}]
}
```

(`summary` 필드는 폐지 — synthesis 와 중복이라 렌더되지 않습니다. 넣어도 무시됩니다.)

### 6단계 — HTML 렌더링

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill query-opportunity \
  --groups "{WORKDIR}/lm_groups.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_query_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/query-opportunity-report.html"
```

### 7단계 — 사용자 안내

```
✅ 쿼리 기회 분석 리포트 생성 완료: {WORKDIR}/query-opportunity-report.html
브라우저로 열면 검색 목적·브랜드 카드와 인사이트를 대시보드/A4 뷰로 볼 수 있고,
Cmd+P 로 A4 PDF 저장이 가능합니다.
macOS 즉시 열기: open {WORKDIR}/query-opportunity-report.html
```
