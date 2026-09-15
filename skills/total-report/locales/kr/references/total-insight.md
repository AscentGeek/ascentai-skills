## 사전 조건 확인

`{SKILL_DIR}/_shared/render/{render_report.py,components.py,components_total.py,query_aggregate.py,path_aggregate.py,cluster_aggregate.py,components_path.py,components_cluster.py}`,
`{SKILL_DIR}/_shared/{styles,labels,templates}` 가 함께 존재해야 합니다.
python3(표준 라이브러리)만 사용합니다. 리포트는 zip customer-analysis 카드 셸 위에
**외곽 4탭**(통합요약 / 쿼리 / 여정 / 클러스터)을 얹은 **하나의 자체완결 HTML** 이며,
탭 2~4 는 형제 스킬(query/path/cluster)의 대시보드 본문을 **그대로** 임베드하고,
탭 1 은 이 스킬에서만 만드는 **통합 요약** — 세 파인더를 합쳐야만 나오는 **6개 교차 인사이트 모듈**
(커버리지 갭 · 허브 역할 · 페르소나×여정 · 수익 누수 · 전환 회랑 · 우선순위 백로그)입니다.

이 리포트는 ListeningMind **3파인더** — QueryFinder(intent_finder) · PathFinder(path_finder) ·
ClusterFinder(cluster_finder) — 를 **각각의 원본 분석틀 그대로** 돌린 뒤, 그 결과를
가로질러 하나의 소비자 검색 여정(오디언스 → 의도 → 여정)으로 종합합니다.

<!-- 프로방스(provenance):
     탭 2~4 의 3단계 분석 프롬프트는 각각 프로덕션 원본을 이식한 것입니다 —
       · query  : agent_query  v0.4.7 (references/prompts/agent_query.1958.kr.md)
       · path   : agent_path   framework (references/prompts/agent_path.framework.kr.md)
       · cluster: agent_cluster v0.7.0 (references/prompts/agent_cluster.v0.7.0.kr.md)
     이 통합 리포트의 각 파인더 단계(1~4)는 형제 참조 문서
     (references/{query-opportunity,path-opportunity,cluster-landscape}.md)의
     동일 단계를 그대로 호출합니다 — 여기서 재기술하지 않고 그 문서로 위임합니다.

     ★ 5단계 "통합 분석" 프롬프트에는 프로덕션 원본이 없습니다(신규 저작). ★
     3파인더의 개별 원본 프롬프트와 달리, gpt_prompt DB 나 인리포 DEFAULT_PROMPTS 에
     대응 행이 없습니다. 이 스킬의 6개 교차 인사이트 모듈(커버리지 갭 / 허브 역할 /
     페르소나×여정 / 수익 누수 / 전환 회랑 / 우선순위 백로그)과 통합 요약을 위해 이
     문서 안에 인라인으로 새로 작성한 것이며, 세 파인더의 공통 규율(수치 단정 금지·
     마크업 금지·데이터 근거만)만 계승합니다.
     운영 프롬프트로 승격/갱신될 경우 이 인라인 규칙을 단일 출처(SSOT)로 삼으세요.

     ★ 숫자·구조·좌표 = Python, 정성 1줄 = LLM (id 로 머지) ★
     통합 수치·좌표·항목별 안정 id 는 total_aggregate.py 가 lm_total_facts.json 에
     이미 계산해 둡니다. LLM(5단계)은 그 **id 에 대응하는 정성 노트만** lm_total.json
     에 씁니다 — 자유 키워드·수치 저작 금지. 노트 키드 계약:
       overview(문자열) · hubNotes[{id,rx}] · cellNotes[{id,note}] ·
       bridgeNotes[{id,note}] · backlogNotes[{id,title,body}].
     id 는 facts 의 hub#/cell#/bridge#/bl# 을 그대로 씁니다. 렌더러
     (components_total)는 facts+notes 를 **id 로 머지**하므로, facts 에 없는 id 의
     노트는 조용히 무시됩니다(별도 환각필터 불필요) — 없는 항목을 노트로 만들어낼 수
     없습니다. 반대로 노트 없는 facts 항목은 숫자만 렌더됩니다. -->

## 실행 절차

### 0단계 — 입력 수집 + 작업 폴더

데이터는 **ListeningMind MCP 도구**로 받습니다. **API 키를 묻지 마세요** —
환경변수·`.env`·DB 등에서 키를 찾으려 하지도 마세요.

필요한 입력:

> 통합 검색 인사이트 분석을 시작하겠습니다.
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
WORKDIR="$PWD/tmp/reports/listeningmind-total-insight-${SAFE_SEED}-${TIMESTAMP}"
mkdir -p "$WORKDIR/q" "$WORKDIR/p" "$WORKDIR/c"
echo "작업 폴더: $WORKDIR"
```

이후 `{WORKDIR}` 는 위 절대경로로 치환합니다. 파인더별 산출물은
`{WORKDIR}/q`(쿼리) · `{WORKDIR}/p`(여정) · `{WORKDIR}/c`(클러스터) 에 담고,
통합 산출물(`lm_total.json`, 최종 HTML)은 `{WORKDIR}` 루트에 둡니다.

> **`<GL>`·`<SEED>`·`<TIME_POINT>`·`<YYYY-MM-DD>`(=`$(date +%F)`)** 는 전 단계에서 동일 값으로
> 치환합니다. `<GL>` 은 현재 `kr` 만 지원(라벨 JSON 이 kr 만 제공).

### 1단계 — 3파인더 데이터 수집 (부분 실패 시 우아하게 축소)

세 파인더의 **구조 조회를 먼저 끝내고**, 검색량·의도 보강(`keyword_info`)은 **키워드를 합쳐
한 번만** 호출합니다.

> **왜 합치나** · 파인더별로 따로 부르면 같은 시드에서 겹치는 키워드를 중복 조회하게
> 됩니다. 실측(시드 "전통주")에서 단순 합 719개 → 합집합 644개로 **75개(10%)** 가
> 중복이었습니다. 시드가 좁을수록 겹침은 더 커집니다. 한 번만 부르면 중복이 사라지고
> 캐시 적중률도 올라갑니다.

**1-A. 구조 조회 (파인더별 1콜씩)** — 형제 문서의 1a 블록을 그대로 쓰되 저장 경로만 바꿉니다.

> **세 파인더는 한 번에 하나씩 순서대로 호출합니다.** ListeningMind MCP 는 동시 요청 한도가 1이라,
> 한꺼번에 부르면 뒤의 호출이 `429 concurrent request limit` 로 실패합니다. 앞 호출의 저장까지 끝낸 뒤 다음을 부릅니다.

| 파인더 | 필수도 | MCP 도구 | 참조(1a 그대로) | 저장 |
|---|---|---|---|---|
| 쿼리 | **필수** | `intent_finder` | `references/query-opportunity.md` §1a | `{WORKDIR}/q/lm_keyword_list.json` |
| 여정 | 권장 | `path_finder` | `references/path-opportunity.md` §1a | `{WORKDIR}/p/lm_path.json` |
| 클러스터 | 선택(플랜) | `cluster_finder` | `references/cluster-landscape.md` §1a | `{WORKDIR}/c/lm_cluster.json` |

각 호출은 형제 문서와 동일하게 **3단계**(`mcp_cache.py lookup` → MCP 호출 + 응답 파일
확보 + `store` → `log_event.py --type tool_call`)를 거칩니다. 저장 경로만 위 표대로 바꿉니다.

**1-B. 키워드 합집합 → `keyword_info` 1회** — 성공한 파인더의 결과에서 키워드를 모읍니다.

```bash
python3 - "{WORKDIR}" <<'MKPARAM' > "{WORKDIR}/kw_params.json"
import json, sys
from pathlib import Path

W = Path(sys.argv[1])
seen, kws = set(), []          # 등장 순서 유지 · 앞쪽(쿼리)이 상한에 먼저 들어가게

def add(k):
    if isinstance(k, str) and k.strip() and k not in seen:
        seen.add(k); kws.append(k.strip())

# 쿼리 · 검색량순으로 이미 정렬돼 있다
f = W / "q/lm_keyword_list.json"
if f.exists():
    for k in (json.loads(f.read_text(encoding="utf-8")).get("data") or []):
        add(k if isinstance(k, str) else (k or {}).get("keyword"))

# 여정 · 경로에 등장하는 노드
f = W / "p/lm_path.json"
if f.exists():
    d = json.loads(f.read_text(encoding="utf-8"))
    for path in (d.get("data") or (d.get("result") or {}).get("paths") or []):
        for k in (path if isinstance(path, list) else []):
            add(k)

# 클러스터 · 군집 구성원 + 엣지 양끝
f = W / "c/lm_cluster.json"
if f.exists():
    data = json.loads(f.read_text(encoding="utf-8")).get("data") or {}
    for members in (data.get("communities") or {}).values():
        for k in (members if isinstance(members, list) else []):
            add(k)
    for r in (data.get("rels") or []):
        if isinstance(r, dict):
            for fld in ("from", "to", "source", "target"):
                add(r.get(fld))
        elif isinstance(r, list):
            for k in r:
                add(k)

kws = kws[:1000]               # keyword_info maxItems=1000
print(json.dumps({"keywords": kws, "gl": "<GL>", "data_type": "all"}, ensure_ascii=False))
MKPARAM

# ① 캐시 확인
python3 {SKILL_DIR}/scripts/mcp_cache.py lookup keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --out "{WORKDIR}/lm_keyword_info.json"

# 미적중이면 keyword_info MCP 도구를 kw_params.json 내용 + user_query 로 호출하고
# 응답을 {WORKDIR}/lm_keyword_info.json 으로 확보한 뒤:

# ② 캐시 저장
python3 {SKILL_DIR}/scripts/mcp_cache.py store keyword_info \
  --params-file "{WORKDIR}/kw_params.json" \
  --file "{WORKDIR}/lm_keyword_info.json" --expect <data 배열 길이>

# ③ tool_call 발행
python3 "$SKILL_DIR/scripts/log_event.py" --type tool_call --session-id "$SID" \
  --tool keyword_info --request-body "$(cat "{WORKDIR}/kw_params.json")" \
  --used-credits-delta <cost_detail.total_cost> \
  --used-credits-cumulative <used_credits> \
  --intent market_scan
```

> 상한(1,000)에 걸리면 **쿼리 키워드가 먼저** 들어갑니다(검색량 내림차순). 쿼리가 필수
> 파인더이고 잘림에 가장 민감하기 때문입니다.

**1-C. 파인더별로 나눠 쓰기** — 여정·클러스터는 합집합 파일을 **그대로** 넘겨도 됩니다.
두 집계 스크립트는 `{키워드: 값}` 매핑을 만든 뒤 자기 구조(경로·군집)에 있는 키워드만
꺼내 쓰므로, 여분이 섞여도 결과가 달라지지 않습니다.

**쿼리만 걸러내야 합니다** — `query_aggregate context` 는 받은 레코드를 **전부** 연관 쿼리로
취급하므로, 여정·클러스터에서 온 키워드가 섞이면 목록이 오염됩니다.

```bash
python3 - "{WORKDIR}" <<'PY'
import json, sys
from pathlib import Path

W = Path(sys.argv[1])
info = json.loads((W / "lm_keyword_info.json").read_text(encoding="utf-8"))
rows = info.get("data") if isinstance(info.get("data"), list) else (info if isinstance(info, list) else [])

def kw_of(r):
    src = r.get("_source") if isinstance(r.get("_source"), dict) else r
    return src.get("keyword")

# 쿼리 목록에 있는 키워드만 남긴다
want = set()
f = W / "q/lm_keyword_list.json"
if f.exists():
    for k in (json.loads(f.read_text(encoding="utf-8")).get("data") or []):
        want.add(k if isinstance(k, str) else (k or {}).get("keyword"))

out = dict(info) if isinstance(info, dict) else {}
out["data"] = [r for r in rows if kw_of(r) in want]
(W / "q/lm_query.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"쿼리 {len(out['data'])}개 / 합집합 {len(rows)}개")
PY

# 여정·클러스터는 합집합을 그대로 쓴다 (여분 키워드는 집계가 무시한다)
cp "{WORKDIR}/lm_keyword_info.json" "{WORKDIR}/p/lm_nodes.json"
cp "{WORKDIR}/lm_keyword_info.json" "{WORKDIR}/c/lm_keyword_info.json"
```

수집 결과 파일명(형제와 동일 · 2단계 집계가 이 이름을 그대로 받습니다):
- 쿼리: `{WORKDIR}/q/lm_keyword_list.json`, `{WORKDIR}/q/lm_query.json`
- 여정: `{WORKDIR}/p/lm_path.json`, `{WORKDIR}/p/lm_nodes.json`
- 클러스터: `{WORKDIR}/c/lm_cluster.json`, `{WORKDIR}/c/lm_keyword_info.json`

**우아한 축소(graceful degradation) 규칙**:
- **쿼리(필수)**: `result=FAILED`·HTTP 오류·빈 결과면 **전체 중단**(키·gl·시드 확인 안내). 쿼리 없이는 통합 리포트를 만들지 않습니다.
- **여정(권장)**: 실패하면 경고만 남기고 **여정 없이 진행**(탭 3 은 "데이터 없음"으로 렌더).
- **클러스터(선택)**: **401**=키 오류 / **402**=결제 필요 / **403**=플랜·gl·권한 부족(cluster_finder 는 professional/advance) / **429**=동시요청 제한 이거나 `communities` 가 비면, 경고만 남기고 **클러스터 없이 진행**(탭 4 는 "데이터 없음"). 특히 403(플랜)은 흔하니 자연스럽게 축소합니다.
- **게이트(최소 2파인더)**: 수집이 끝나면 **성공한 파인더가 쿼리 포함 2개 이상**이어야 계속합니다. 쿼리만 성공(여정·클러스터 모두 실패)했다면 통합할 축이 없으므로 중단하고, 여정/클러스터가 왜 비었는지(플랜·시점·네트워크) 사용자에게 보고합니다. 성공한 파인더에 대해서만 2~6단계를 진행합니다.

> 어느 파인더도 데이터를 **지어내지 마세요**. 실패한 파인더는 그냥 빼면 됩니다 — 렌더러가
> 없는 탭을 "데이터 없음" 카드로 자연스럽게 처리하고, 통합 A4 에서도 해당 파인더 페이지를 생략합니다.

### 2단계 — 파인더별 컨텍스트 집계 (`context`)

성공한 파인더 각각에 대해 형제 문서의 **2단계 집계**를 그대로 실행합니다(경로만 하위 폴더로).

```bash
# 쿼리
python3 {SKILL_DIR}/_shared/render/query_aggregate.py context \
  --raw "{WORKDIR}/q/lm_query.json" --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/q/lm_query_result.json"

# 여정 (수집 성공 시)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py context \
  --paths "{WORKDIR}/p/lm_path.json" --nodes "{WORKDIR}/p/lm_nodes.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> --time-point <TIME_POINT> \
  --out "{WORKDIR}/p/lm_path_result.json"

# 클러스터 (수집 성공 시)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py context \
  --cluster "{WORKDIR}/c/lm_cluster.json" --keyword-info "{WORKDIR}/c/lm_keyword_info.json" \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/c/lm_cluster_result.json"
```

산출된 `*_result.json` 의 LLM 입력(쿼리 `csv` / 여정 `pathsText`·`hubsCsv` / 클러스터 `csv`)을 3단계에서 사용합니다.

### 3단계 — 파인더별 분석 (LLM, 원본 분석틀) → `lm_groups_raw.json` / `lm_paths_raw.json`

파인더 각각을 **그 파인더의 원본 분석 규칙 그대로** 분석합니다. 규칙을 여기서 재작성하지 말고,
형제 참조 문서의 **3단계 "분석 규칙"** 섹션을 그대로 따르세요(수치 단정 금지·마크업 금지·데이터 근거만·시장 언어):

- 쿼리 → `references/query-opportunity.md` §3 **"분석 규칙 (Data Insight Analyst)"** (agent_query v0.4.7 이식). 입력 `{WORKDIR}/q/lm_query_result.json` 의 `csv`. 출력 `{WORKDIR}/q/lm_groups_raw.json`.
- 여정 → `references/path-opportunity.md` §3 **"분석 규칙 (Search Journey Analyst)"** (agent_path framework 이식). 입력 `{WORKDIR}/p/lm_path_result.json` 의 `pathsText`·`hubsCsv`. 출력 `{WORKDIR}/p/lm_paths_raw.json`.
- 클러스터 → `references/cluster-landscape.md` §3 **"분석 규칙 (데이터 인사이트 분석가 — 클러스터파인더)"** (agent_cluster v0.7.0 이식). 입력 `{WORKDIR}/c/lm_cluster_result.json` 의 `csv`. 출력 `{WORKDIR}/c/lm_groups_raw.json`.

각 파인더의 JSON 출력 스키마·필드도 형제 문서 그대로입니다.

### 4단계 — 파인더별 후처리 (`groups`/`paths`, 검색량 합산·환각 필터)

성공한 파인더 각각에 대해 형제 문서의 **4단계 후처리**를 그대로 실행합니다. 이 단계에서
**수치가 사실값으로 채워지고**(검색량 합산·허브·흐름·연결성), **환각 키워드가 제거**됩니다.

```bash
# 쿼리 → q/lm_groups.json
python3 {SKILL_DIR}/_shared/render/query_aggregate.py groups \
  --raw-groups "{WORKDIR}/q/lm_groups_raw.json" --context "{WORKDIR}/q/lm_query_result.json" \
  --out "{WORKDIR}/q/lm_groups.json"

# 여정 → p/lm_paths.json (수집 성공 시)
python3 {SKILL_DIR}/_shared/render/path_aggregate.py paths \
  --raw-paths "{WORKDIR}/p/lm_paths_raw.json" --context "{WORKDIR}/p/lm_path_result.json" \
  --out "{WORKDIR}/p/lm_paths.json"

# 클러스터 → c/lm_groups.json (수집 성공 시)
python3 {SKILL_DIR}/_shared/render/cluster_aggregate.py groups \
  --raw-groups "{WORKDIR}/c/lm_groups_raw.json" --context "{WORKDIR}/c/lm_cluster_result.json" \
  --out "{WORKDIR}/c/lm_groups.json"
```

> 어떤 파인더든 후처리가 "그룹 0개"로 에러 중단되면 그 파인더의 3단계를 다시 수행합니다(형제 문서와 동일).

**파인더별 인사이트·실행(`lm_actions.json`)도 지금 만듭니다** — 탭 2~4 는 각 파인더 리포트 본문을
그대로 임베드하므로, 각 파인더의 **5단계**(형제 문서 §5, `synthesis`·`insights`(3)·`now`·`future`)를
수행해 아래에 저장합니다:

- 쿼리: `{WORKDIR}/q/lm_actions.json` (`references/query-opportunity.md` §5)
- 여정: `{WORKDIR}/p/lm_actions.json` (`references/path-opportunity.md` §5)
- 클러스터: `{WORKDIR}/c/lm_actions.json` (`references/cluster-landscape.md` §5)

### 5단계 — 통합 집계(Python) + 통합 노트(LLM) → `lm_total_facts.json` + `lm_total.json`

이 단계는 **두 부분**입니다. **5-A** Python 집계기가 세 파인더 결과를 가로질러 **모든 수치·좌표·항목 id**
를 계산해 `lm_total_facts.json` 에 담고, **5-B** LLM 이 그 **id 에 대응하는 정성 노트 1줄만** `lm_total.json`
에 씁니다. 수치는 5-A 가 사실값으로 확정하므로, 5-B 는 절대 수치를 재산출하지 않습니다(환각 원천 차단).

#### 5-A. 통합 집계 (Python) → `lm_total_facts.json`

성공한 파인더들의 후처리 결과(2단계 `*_result.json` 메타 + 4단계 `groups`/`paths`)를 `total_aggregate.py total`
로 가로질러 집계합니다. **쿼리 포함 최소 2개 파인더**가 있어야 하며, 존재하는 파인더 플래그만 넘깁니다(우아한 축소).

```bash
python3 {SKILL_DIR}/_shared/render/total_aggregate.py total \
  --seed "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --query-meta    "{WORKDIR}/q/lm_query_result.json"   --query-groups   "{WORKDIR}/q/lm_groups.json" \
  --path-meta     "{WORKDIR}/p/lm_path_result.json"    --path-paths     "{WORKDIR}/p/lm_paths.json" \
  --cluster-meta  "{WORKDIR}/c/lm_cluster_result.json" --cluster-groups "{WORKDIR}/c/lm_groups.json" \
  --out "{WORKDIR}/lm_total_facts.json"
```

- **여정/클러스터 실패 시** 해당 `--path-*` 또는 `--cluster-*` 두 줄을 빼세요(집계기가 자동 축소 — 예: 클러스터가 없으면 전환 회랑·수익 누수의 일부가 줄어듭니다).
- 산출 `lm_total_facts.json` 은 8개 섹션(`meta`·`recap`·`coverage`·`hubDivergence`·`matrix`·`valueLeak`·`bridges`·`backlog`)과 **항목별 안정 id**(`combo#`,`gap#`,`hub#`,`cell#`,`leak#`,`bridge#`,`bl#`)를 담습니다. **여기 숫자는 확정 사실값** — 다음 5-B 노트가 건드리지 않습니다.

#### 5-B. 통합 노트 (LLM, **신규 저작**) → `lm_total.json`

`lm_total_facts.json` 을 읽고, 그 **id 에 대응하는 정성 노트만** JSON 으로 `{WORKDIR}/lm_total.json` 에 저장합니다.

> ⚠ 이 프롬프트는 **프로덕션 원본이 없는 신규 저작**입니다(위 프로방스 주석). 세 파인더 공통 규율만 계승합니다.

**입력**:
- `{WORKDIR}/lm_total_facts.json` — 6개 교차 모듈의 수치·좌표·id (읽기 전용 근거).
- (보조) 성공한 파인더의 `groups`/`paths` — 노트의 정성 맥락 참고용. 여기서도 **수치는 인용만, 재산출 금지**.

---

##### 분석 규칙 (통합 인사이트 노트 작성)

당신은 검색 데이터 통합 분석가입니다. Python 집계기가 세 파인더(WHO·군집 / WHAT·WHY·의도 / HOW·여정)를
가로질러 **6개 교차 결론 모듈**(커버리지 갭 · 허브 역할 · 페르소나×여정 · 수익 누수 · 전환 회랑 · 우선순위
백로그)을 이미 수치로 확정했습니다. 당신의 일은 그 확정된 항목들에 **마케터가 바로 이해할 1줄 해석/처방**을
다는 것뿐입니다.

**전역 규칙**(세 파인더와 동일 + 통합 특칙):
- **id 로만 매핑**: 노트는 반드시 facts 에 **실재하는 id**(`hub#…`,`cell#…`,`bridge#…`,`bl#…`)에만 답니다. facts 에 없는 id 로 쓴 노트는 렌더러가 **조용히 버립니다**(없는 항목을 만들어낼 수 없음) — 그래도 존재하지 않는 id 는 쓰지 마세요.
- **수치·키워드 재저작 금지(중요)**: 검색량·비중·순위·분산·분기 수 같은 수치를 텍스트로 단정하지 마세요("가장 큰", "OO%", "N배", "N개" 금지). 새 키워드를 지어내지 마세요 — 근거 키워드는 facts 가 이미 칩·바에 채워 두었습니다. 당신은 **왜 중요한가 / 무엇을 하나**만 씁니다.
- **평이한 한국어**: 마케터가 즉시 이해하는 문장. 전문용어(dispersion/outDegree/present-absent/leak_factor 등)는 노출하지 마세요.
- **마크업**: 핵심 명사구는 `<strong>…</strong>` 만 허용. 그 외 마크업(`:k[]`, `:::accordion`, `➊`, 코드블록, 표)은 절대 금지.
- **출력 언어** = 분석 시장(`<GL>`) 언어. kr → 한국어.

**① overview** (문자열) — 세 렌즈를 관통하는 핵심 구조 1~2문장(100~200자). 커버·탭1 상단 "통합 요약" 박스에 실립니다. 수치 단정 없이 서술.

**② hubNotes** `[{id, rx}]` — M2(허브 역할)의 `hub#…` 중 **해줄 말이 있는 것만**. `rx` = 이 키워드의 역할 불일치가 마케팅에 갖는 의미 + 처방 1줄(예: 세 곳 모두 핵심이면 "반드시 선점", 한쪽만 뜨면 "그 용도로만 운영").

**③ cellNotes** `[{id, note}]` — M3(페르소나×여정)의 `cell#…` 중 특히 **빈 칸(콘텐츠 갭) 셀** 위주 1줄. 누가 오는데 왜 못 받는지 + 무엇을 채우나.

**④ bridgeNotes** `[{id, note}]` — M5(전환 회랑)의 `bridge#…` 중 판정이 뚜렷한 것 위주 1줄. 방향·이탈 판정을 실행으로 번역(상류 배치·CRM·방어 등).

**⑤ backlogNotes** `[{id, title, body}]` — M6(우선순위 백로그)의 `bl#…` 각 항목. `title` = 마케터용 짧은 실행 과제명(명사구, 근거 키워드 기반). `body` = **(선택)** 1줄 부연. facts 의 target·근거 키워드·버킷을 사람이 읽을 과제명으로 옮기는 역할입니다.

---

##### 출력 형식 — JSON only (마크다운·표 금지, `<strong>` 만 허용)

```json
{
  "overview": "세 렌즈를 관통하는 통합 요약 1~2문장",
  "hubNotes":     [{"id": "hub#0001",   "rx":   "역할 불일치 해석 + 처방 1줄"}],
  "cellNotes":    [{"id": "cell#p1-s1", "note": "콘텐츠 갭 셀 해석 1줄"}],
  "bridgeNotes":  [{"id": "bridge#C-D", "note": "전환 판정 → 실행 1줄"}],
  "backlogNotes": [{"id": "bl#now-1",   "title": "실행 과제명", "body": "(선택) 부연 1줄"}]
}
```

위 JSON 을 `{WORKDIR}/lm_total.json` 에 저장합니다. 모든 컬렉션은 **선택적**(비워도 됨) — 노트 없는 facts 항목은
숫자만 렌더됩니다. **id 는 반드시 facts 의 것을 그대로** 쓰세요(오타 시 그 노트만 무시됩니다). 이 노트 파일에는
자유 키워드·수치를 저작하지 마세요 — 숫자는 전부 5-A 의 `lm_total_facts.json` 에서 옵니다.

### 6단계 — 통합 HTML 렌더링 (`--skill total-insight`)

`render_report.py` 를 **통합 모드**로 호출합니다. `--total`(정성 노트)·`--total-facts`(집계 수치)는 필수,
파인더 3종 플래그는 **성공해서 산출물이 있는 파인더만** 넘깁니다(실패한 파인더 플래그는 생략 — 그 탭은 "데이터 없음"으로 렌더).

```bash
python3 {SKILL_DIR}/_shared/render/render_report.py --skill total-insight \
  --total          "{WORKDIR}/lm_total.json" \
  --total-facts    "{WORKDIR}/lm_total_facts.json" \
  --query-groups   "{WORKDIR}/q/lm_groups.json" \
  --query-actions  "{WORKDIR}/q/lm_actions.json" \
  --query-meta     "{WORKDIR}/q/lm_query_result.json" \
  --path-paths     "{WORKDIR}/p/lm_paths.json" \
  --path-actions   "{WORKDIR}/p/lm_actions.json" \
  --path-meta      "{WORKDIR}/p/lm_path_result.json" \
  --cluster-groups "{WORKDIR}/c/lm_groups.json" \
  --cluster-actions "{WORKDIR}/c/lm_actions.json" \
  --cluster-meta   "{WORKDIR}/c/lm_cluster_result.json" \
  --category "<SEED>" --gl <GL> --date <YYYY-MM-DD> \
  --out "{WORKDIR}/total-insight-report.html"
```

- **필수**: `--total`·`--total-facts`, 그리고 파인더 3종 중 **최소 1개**(쿼리는 항상 성공했으므로 `--query-*` 는 항상 포함). 게이트 규칙상 쿼리 포함 2개 이상이 넘어옵니다.
- **여정 실패 시**: `--path-paths`·`--path-actions`·`--path-meta` 세 줄을 빼세요.
- **클러스터 실패 시**: `--cluster-groups`·`--cluster-actions`·`--cluster-meta` 세 줄을 빼세요.
- `--gl` 은 `kr` 만 지원, `--date` 는 `$(date +%F)`.

### 7단계 — 사용자 안내

생성 결과를 안내합니다. 축소 실행(파인더 일부 생략) 시 어떤 탭이 데이터 없음인지도 함께 알립니다.

```
✅ 통합 검색 인사이트 리포트 생성 완료: {WORKDIR}/total-insight-report.html
브라우저로 열면 상단 4탭(통합 요약 · 쿼리 기회 · 검색 여정 · 클러스터 지형)으로
   · 탭 1: 세 파인더를 합쳐야만 나오는 6개 교차 인사이트 모듈(커버리지 갭 · 허브 역할 · 페르소나×여정 · 수익 누수 · 전환 회랑 · 우선순위 백로그) + 통합 요약
   · 탭 2~4: 각 파인더 리포트 본문(카드/허브 표/여정 흐름도)
을 대시보드/A4 뷰로 볼 수 있습니다.
A4 뷰(우상단 토글)는 통합 → 쿼리 → 여정 → 클러스터 순서로 이어진 하나의 문서라,
Cmd+P 로 인쇄하면 4개 리포트가 한 PDF 로 저장됩니다(4-in-one).
macOS 즉시 열기: open {WORKDIR}/total-insight-report.html
```

(여정·클러스터를 플랜/네트워크 사유로 생략했다면, 그 탭은 "데이터가 없어 이 탭은 생성되지
않았습니다"로 표시되고 A4 에서도 해당 파인더 페이지가 빠진다는 점을 함께 안내하세요.)
