## 사전 조건 확인

`{SKILL_DIR}/_shared/render/{cluster_aggregate.py,render_report.py,components.py,components_cluster.py}`,
`{SKILL_DIR}/_shared/{styles,labels,templates}` 가 함께 존재해야 합니다.
python3(표준 라이브러리)만 사용합니다. 리포트는 zip customer-analysis 와 동일한 카드 형태 +
클러스터 전용 **허브 키워드 요약 표**·**From→To 흐름** 섹션을 더합니다.

이 리포트는 ListeningMind **ClusterFinder(클러스터파인더)** 의 실제 분석 프롬프트
(agent_cluster v0.7.0)의 분석틀을 이식해, 동시검색 키워드 군집(클러스터)을 **검색 목적**으로
묶고 각 클러스터의 **허브(대표) 키워드**와 클러스터 간 **탐색 흐름**을 카드로 제시합니다.

<!-- 원본 프롬프트 스냅샷: references/prompts/agent_cluster.v0.7.0.kr.md
     (v.0.7.0_cf_KR_0602, 단일 키워드 4섹션: 분석개요 / Top3 검색목적 클러스터 /
     Top3 From→To 흐름 / 인사이트). 이 3단계 프롬프트는 원본 4섹션을 JSON 출력형으로
     번안한 것임(섹션1→overview, 섹션2→clusterGroups, 섹션3→flows, 섹션4→5단계 actions).
     챗 전용 마크업(:k[]/:c[]{#}/:::accordion/➊)과 '정확한 수치 명시' 규칙은 의도적으로
     제외 — 수치·허브·흐름 엣지는 Python 이 실데이터에서 채운다(수치 정책).
     멀티 키워드(agent_cluster_multiple)·클러스터 드릴다운(GEO/페르소나/광고카피)은
     현재 스킬 범위에서 제외(단일 시드 전용). 운영 프롬프트 갱신 시 gpt_prompt DB 의
     type='agent_cluster' locale='KR' 최신 활성 행과 재대조. -->

## 실행 절차

### 0단계 — 입력 수집 + 작업 폴더

데이터는 **ListeningMind MCP 도구**로 받습니다. **API 키를 묻지 마세요** —
환경변수·`.env`·DB 등에서 키를 찾으려 하지도 마세요.

필요한 입력은 둘뿐입니다:

> 검색 클러스터 지형 분석을 시작하겠습니다.
> 1. **시드 키워드** — 이미 주셨다면 생략 (클러스터파인더는 **단일 키워드**만 받습니다)
> 2. **국가** — 기본 `kr` (별도 언급 없으면 kr 로 진행)

시드가 이미 주어졌으면 바로 진행합니다.

**MCP 커넥터가 없으면** · 1단계의 도구 호출이 "도구를 찾을 수 없음" 으로 실패합니다.
그때는 사용자에게 **ListeningMind MCP 커넥터 연결**을 요청하고 중단하세요.
데이터를 지어내지 마세요.

확보되면:

```bash
SAFE_SEED=$(echo "<SEED>" | tr ' /\\:*?"<>|' '_')
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
WORKDIR="$PWD/tmp/reports/listeningmind-cluster-landscape-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR"
echo "작업 폴더: $WORKDIR"
```

이후 `{WORKDIR}` 는 위 절대경로로 치환합니다.

### 1단계 — 데이터 수집 (MCP 2회 호출)

cluster_finder 는 **동시검색 그래프**(클러스터 군집 + 엣지)만 돌려주고 **검색량·의도는 담지
않습니다.** 그래서 ① `cluster_finder` 로 군집·엣지를 받고, ② 그 안의 키워드들을 `keyword_info`
로 넘겨 검색량·의도를 붙입니다.

> **매 호출은 예외 없이 3단계다** (SKILL.md §Step 4):
> ① `mcp_cache.py lookup` → ② (미적중이면) MCP 호출 + 응답 파일 확보 + `store` → ③ `log_event.py --type tool_call`
>
> ①이 **exit 0** 이면 파일이 이미 채워진 것이니 **MCP 를 부르지 말고** ③으로 갑니다
> (`--cached --used-credits-delta 0`). **exit 2** 면 ②로 진행합니다.

**1a. 클러스터 그래프** — `cluster_finder`

```bash
# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup cluster_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}' \
  --out "{WORKDIR}/lm_cluster.json"
```

미적중이면 **`cluster_finder` MCP 도구**를 아래 파라미터로 호출합니다:

```json
{"keyword": "<SEED>", "gl": "<GL>", "data_type": "all", "hop": 2, "limit": 1000,
 "orientation": "UNDIRECTED", "time_point": "curr",
 "user_query": "<사용자 발화 원문 그대로>"}
```

> `data_type` 은 반드시 **`all`** — `communities`(클러스터 dict)와 `rels`(엣지 배열)를 함께
> 받아야 허브(연결 중심성)·흐름(클러스터 간 이동)을 계산할 수 있습니다. `communities` 만
> 받으면(`data_type` 기본값) 흐름 분석이 비고, `rels` 만 받으면 군집이 비어 카드를 못 만듭니다.
> `limit` 은 **관계(엣지) 수** 상한(키워드 수 아님), `hop` 은 그래프 탐색 깊이(1~3)입니다.
>
> `user_query` 는 캐시 키에서 제외되므로 `--params` 에는 넣지 않습니다(위 lookup 참조).

응답을 `{WORKDIR}/lm_cluster.json` 으로 확보한 뒤 캐시에 저장합니다
(응답이 커서 호스트가 파일로 저장했으면 그 경로를 `cp` · 본문으로 왔으면 heredoc —
SKILL.md §응답 파일 규칙 참조):

```bash
# ② 캐시 저장
python3 {SKILL_DIR}/scripts/mcp_cache.py store cluster_finder \
  --params '{"keyword":"<SEED>","gl":"<GL>","data_type":"all","hop":2,"limit":1000,"orientation":"UNDIRECTED","time_point":"curr"}' \
  --file "{WORKDIR}/lm_cluster.json" --expect <rels 길이 + communities 개수>

# ③ tool_call 발행
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool cluster_finder \
  --request-body '{"keyword":"<SEED>","gl":"<GL>","data_type":"all","hop":2,"limit":1000}' \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent perception_mapping
```

**1b. 키워드 상세** — 위 `communities` 의 **모든 키워드**(중복 제거, 상위 1,000개)를
`keyword_info`(`data_type=all` → `ads_metrics`·`intents` 포함)로 검색량·의도 조회:

```bash
python3 - "{WORKDIR}/lm_cluster.json" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
d = json.load(open(sys.argv[1]))
comm = (d.get("data") or {}).get("communities") or {}
# communities 값(각 클러스터의 키워드 리스트)을 펼쳐 중복 제거, 상위 1,000개.
seen, kws = set(), []
for members in comm.values():
    for k in (members or []):
        if isinstance(k, str) and k not in seen:
            seen.add(k); kws.append(k)
kws = kws[:1000]  # keyword_info maxItems=1000
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_keyword_info.json"
```

미적중이면 **`keyword_info` MCP 도구**를 `kw_params.json` 의 내용 + `user_query` 로
호출하고, 응답을 `{WORKDIR}/lm_keyword_info.json` 으로 확보한 뒤 저장합니다:

```bash
# ② 캐시 저장
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_keyword_info.json" --expect <data 배열 길이>

# ③ tool_call 발행
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent perception_mapping
```

- 두 응답 모두 `result` 가 `FAILED` 이거나 도구 호출이 실패하면 중단·보고
  (커넥터·시드·gl·플랜 확인). 지어내지 마세요.
- `communities` 가 비어 있으면(군집 0개) 중단·보고합니다.

### 2단계 — 클러스터 컨텍스트 집계

```bash
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py context \
  --cluster "{WORKDIR}/lm_cluster.json" \
  --keyword-info "{WORKDIR}/lm_keyword_info.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/lm_cluster_result.json"
```

이 스크립트가 두 응답을 융합해:
- 각 키워드에 **클러스터 문자**(0→A, 1→B…)를 배정하고,
- `rels` 로 **허브 키워드**(연결 중심성=degree 최다, 동률·부재 시 검색량 최다)를 클러스터별로 계산하고,
- 각 키워드·클러스터의 **outgoing**(다른 클러스터로의 연결)을 계산하며,
- LLM 분석에 넣을 **`csv`**(컬럼 `n,v,c,h,o,i`)를 만듭니다.

`{WORKDIR}/lm_cluster_result.json` 을 읽어 그 안의 `csv` 값을 3단계 분석 입력으로 사용합니다.

### 3단계 — ClusterFinder 분석 (LLM) → lm_groups_raw.json

아래 규칙(agent_cluster v0.7.0 이식)에 따라 `lm_cluster_result.json` 의 `csv` 를 직접 분석하고,
결과를 **JSON 으로만** `{WORKDIR}/lm_groups_raw.json` 에 저장합니다.

---

#### 분석 규칙 (데이터 인사이트 분석가 — 클러스터파인더)

당신은 검색 데이터 인사이트 분석가입니다. 리스닝마인드 클러스터파인더 결과(동시검색 군집)를
바탕으로 **단일 키워드 시장 내부**의 검색 의도, 사용자 이동 경로, 시장 구조를 해석합니다.

**입력**: `csv` 각 행 = `n, v, c, h, o, i`
- `n` = 키워드, `v` = **월 평균 검색량**(검색량은 항상 이 값 사용).
- `c` = 이 키워드가 속한 **클러스터 문자**(A, B, C…). 동시검색으로 묶인 토픽 군집입니다.
- `h` = **허브 키워드 여부**(`TRUE`=이 클러스터의 대표/중심 키워드).
- `o` = 이 키워드가 연결되는 **다른 클러스터 문자**(`|` 구분). 클러스터 간 이동 경로의 근거입니다.
- `i` = 대표 검색 의도(정보탐색/길찾기/상업조사/거래).

**전역 규칙**:
- **데이터 근거만**: csv 에 없는 키워드·클러스터·수치를 지어내지 마세요.
- **수치 단정 회피(중요)**: 검색량·비중·순위 같은 **수치를 텍스트로 단정하지 마세요**
  ("가장 큰", "OO건", "N배" 금지). 수치·허브·흐름 엣지는 리포트의 뱃지·표·칩에 코드가
  사실값으로 채우므로, 당신은 **정성적 해석**(왜 이렇게 묶이는가, 무슨 의도인가)만 씁니다.
- **마크업 금지**: `:k[]`, `:c[]{#}`, `:::accordion`, `➊➋➌`, 코드블록, 표 등 특수 마크업을
  절대 쓰지 마세요. 순수 텍스트 문자열만 JSON 값으로 넣습니다.
- **클러스터 참조는 문자로**: `memberClusters`·`path` 에는 csv 에 실재하는 클러스터 문자
  (A, B, C…)만 넣습니다. **키워드 원문**(`hubKeyword`)은 csv 의 `n` 값 그대로만 사용합니다.
- **출력 언어** = 분석 시장(`<GL>`) 언어. kr → 한국어.
- 타겟 고객은 연령·성별 추정이 아니라 **검색행동 유형**(브랜드 비교형, 가격 검토형, 기능 검증형,
  정보 입문형, 구매 직전형 등)으로 기술합니다. 인구통계 단정은 금지합니다.

**① 분석 개요 (overview)**
- 이 키워드 시장을 관통하는 핵심 구조 1~2문장(100~200자). 어떤 검색 의도 축이 강한지,
  주요 클러스터의 성격과 수요 무게중심을 서술. 소제목 없이 서술.
- 이 문장은 리포트 커버의 "배경과 목적" 아래 **데이터 기반 요약문**으로 실립니다.

**② Top 3 검색 목적 클러스터 (clusterGroups)** — 최대 5개(핵심 3개 권장)
- **허브 식별**: `h=TRUE` 키워드가 그 클러스터의 대표입니다.
- **의도 기반 병합**: 의미적으로 유사한 검색 목적을 가진 **여러 클러스터를 하나의 그룹으로 묶습니다**
  (예: 브랜드 라인업 탐색, 추천·비교, 가격·구매, 사용법·관리, 후기 등). 클러스터 1개짜리 그룹도
  가능하나, 유사 의도는 반드시 함께 묶으세요.
- 각 그룹:
  - `title`: 검색 목적명(명확·구체적으로, 예: "브랜드 라인업·가격 탐색")
  - `character`: 이 그룹의 성격/타겟 검색행동 유형(예: "브랜드 비교형")
  - `memberClusters`: 이 목적으로 묶이는 **클러스터 문자 목록**(예: `["B","C"]`)
  - `who`: 이 클러스터를 검색하는 사람들의 맥락·심리 1~2문장(정성)
  - `insight`: 마케팅·콘텐츠 관점의 공략 시사점 1~2문장(정성)

**③ Top 3 From → To 흐름 (flows)** — 최대 5개(핵심 3개 권장)
- 허브 키워드의 `o`(outgoing) 컬럼으로 **실제 연결이 있는 경로만** 사용합니다.
- 각 흐름:
  - `hubKeyword`: 기점이 되는 허브 키워드(csv 의 `n` 원문)
  - `character`: 이 이동의 성격(예: "후보 탐색 → 브랜드 확정")
  - `path`: 이동하는 **클러스터 문자 순서**(예: `["D","B"]` = D→B). 2개 이상.
  - `insight`: 왜 이 전환이 발생하는지 해석 1~2문장(정성)

---

#### 출력 형식 — JSON only (마크다운·마크업 금지)

```json
{
  "overview": "이 키워드 시장을 관통하는 핵심 구조 1~2문장",
  "clusterGroups": [
    {
      "title": "검색 목적명",
      "character": "브랜드 비교형",
      "memberClusters": ["B", "C"],
      "who": "이 클러스터를 검색하는 사람들의 맥락 1~2문장",
      "insight": "공략 시사점 1~2문장"
    }
  ],
  "flows": [
    {
      "hubKeyword": "허브 키워드 원문",
      "character": "이동의 성격",
      "path": ["D", "B"],
      "insight": "왜 이 전환이 발생하는지 1~2문장"
    }
  ]
}
```

위 JSON 을 `{WORKDIR}/lm_groups_raw.json` 에 저장합니다.

### 4단계 — 그룹 후처리 (검색량 합산·허브·흐름 검증)

```bash
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py groups \
  --raw-groups "{WORKDIR}/lm_groups_raw.json" \
  --context "{WORKDIR}/lm_cluster_result.json" \
  --out "{WORKDIR}/lm_groups.json"
```

이 스크립트가 각 그룹의 `volume_avg` 합산·정렬, 대표 키워드(검색량 라벨 포함), 그룹 헤더
뱃지용 `volumeLabel`(합산 검색량)·`memberCount`(키워드 수)·`clusterCount`(병합된 클러스터 수),
**허브 키워드 요약 표**(`hubTable`), **From→To 흐름**(`flows`, 각 경로 클러스터의 허브 키워드 +
허브의 `connectivity`(연결성=잇는 클러스터 수) 포함)를 코드로 계산해 저장하고,
3단계의 `overview` 는 커버 요약문으로 통과시킵니다. (수치·허브·흐름 엣지·연결성은 여기서 사실값으로 채워집니다.)
또한 **환각 차단**: `memberClusters`·`path` 중 실재하지 않는 클러스터 문자, csv 에 없는 키워드는
여기서 제거되고, 실클러스터/실키워드가 하나도 없는 그룹은 통째로 버려집니다.
3단계 결과가 이 필터로 비면(그룹 0개) 스크립트가 에러로 중단되니 3단계를 다시 수행하세요.

### 5단계 — 인사이트·실행 제안 (LLM) → lm_actions.json

`{WORKDIR}/lm_groups.json` 의 그룹·흐름을 바탕으로(agent_cluster ④ 인사이트에 해당), 아래 JSON 을
`{WORKDIR}/lm_actions.json` 에 저장합니다. 출력 언어는 gl 매핑(kr→한국어). **수치 단정 금지**
(3단계와 동일), 마크업 금지.

- `synthesis`: 클러스터 지형·흐름을 가로지르는 총평 2~3문장
- `insights`: 세부 인사이트 **정확히 3개** `{"title","body"}` — 데이터에서 발견된 시장 구조·
  탐색 방식을 근거로 한 논리적 결론. title 은 핵심 키워드 기반으로 짧게, body 는 1~2문장.
- `now`: 지금 바로 써볼 실행 제안 2~3개 `{"title","body"}` (특정 클러스터/흐름에 응답)
- `future`: 앞으로 주목할 기회 2~3개 `{"title","body"}`

```json
{
  "synthesis": "총평 2~3문장",
  "insights": [{"title": "핵심 키워드 기반 제목", "body": "구조 기반 결론 1~2문장"}],
  "now": [{"title": "실행 제안 제목", "body": "실행 내용 1~2문장"}],
  "future": [{"title": "기회 제목", "body": "기회 설명 1~2문장"}]
}
```

### 6단계 — HTML 렌더링

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill cluster-landscape \
  --groups "{WORKDIR}/lm_groups.json" \
  --actions "{WORKDIR}/lm_actions.json" \
  --meta "{WORKDIR}/lm_cluster_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/cluster-landscape-report.html"
```

### 7단계 — 사용자 안내

```
✅ 검색 클러스터 지형 분석 리포트 생성 완료: {WORKDIR}/cluster-landscape-report.html
브라우저로 열면 검색목적 클러스터 카드 · 허브 키워드 요약 표 · From→To 흐름과 인사이트를
대시보드/A4 뷰로 볼 수 있고, Cmd+P 로 A4 PDF 저장이 가능합니다.
macOS 즉시 열기: open {WORKDIR}/cluster-landscape-report.html
```
