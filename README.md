# ascent-skills-saas

ListeningMind **SaaS 고객용** 리포트 스킬. 데이터는 **ListeningMind MCP** 로만 받는다.

## lima-skills 와의 관계

`lima-skills` 의 리포트 스킬을 SaaS 용으로 이식한 것이다. 분석틀·렌더 계층은 같고,
**데이터 경로만 다르다.** (`brand-competition` 은 `lm-brand-competition` 이 정본이고,
`search-demand-report` 는 이 리포에서 자체 개발한 것이다 — `AGENTS.md` §7-b 참조.)

| | lima-skills (DaaS) | ascent-skills-saas (SaaS) |
|---|---|---|
| 데이터 | DaaS REST · `listeningmind-data-api.ascentlab.io` | **ListeningMind MCP** (스킬이 쓰는 도구 4종) |
| 인증 | `LM-API-KEY` 를 사용자에게 입력받음 | **없음** · MCP 커넥터 연결이 전제 |
| 호출 주체 | `scripts/daas_call.py` (코드) | **LLM** (MCP 툴 호출) |
| 세션 캐시 | `~/.lima-agents/rest-cache/<sid>.json` | `~/.lima-agents/mcp-cache/<sid>/` |
| 크레딧 | 코드가 봉투에서 자동 추출해 기록 | **기록하지 않는다** · 봉투의 `cost_detail.total_cost` 를 읽어 사용자에게만 알린다 |
| 과금 모델 | `150 + 반환건수 × 50` 등 **반환량 비례** | **호출당 고정** (실측 2 Lima · 반환량과 무관) |

> **SaaS 스킬이 DaaS 에 과금되면 안 된다.** 이 리포에 `daas_call.py` 나
> `listeningmind-data-api.ascentlab.io` 송신이 들어오면 그 전제가 깨진다.
> pre-commit 훅이 이를 차단한다.

## 스킬 7종

| 스킬 | 리포트 | 버전 | 쓰는 MCP 도구 |
|---|---|---|---|
| `lm-queryfinder-report` | 쿼리 기회 분석 | 3.1.0 | `intent_finder` + `keyword_info` |
| `lm-clusterfinder-report` | 검색 클러스터 지형 | 3.0.1 | `cluster_finder` + `keyword_info` |
| `lm-pathfinder-report` | 검색 여정 분석 | 3.0.1 | `path_finder` + `keyword_info` |
| `lm-total-report` | 3파인더 통합 | 3.0.1 | 위 3종 + `keyword_info` 1회 |
| `lm-brand-competition` | 브랜드 경쟁 구도 카테고리 지도 | 1.0.1 | `intent_finder` + `path_finder` + `keyword_info` |
| `lm-search-demand-report` | 검색 수요 진단 (시장 흐름 대비 변화) | 1.0.1 | `intent_finder` + `cluster_finder`(선택) + `keyword_info` |
| `lm-season-trend-report` | 시즌·트렌드 분석 (48개월 월별 패턴) | 1.0.0 | `intent_finder` + `cluster_finder` + `keyword_info` |

스킬 이름은 `lm-<스킬명>` 이다 — 국가 코드는 붙지 않는다.

### 씨드 검색어는 스킬마다 개수가 다르다

대부분의 스킬은 씨드 검색어 **1개**를 받는다. `lm-queryfinder-report` 만 **1~10개**를
받으며, 여러 개를 넣어도 **씨드별 리포트가 아니라 연관 쿼리를 합친 리포트 한 장**이
나온다. 한 카테고리 안의 경쟁 브랜드나 대체재를 함께 넣는 용도다.

> `keyword_info` 의 1,000건 상한은 **호출당**이라 씨드 N개가 한 예산을 나눈다.
> 그래서 씨드별로 균등 배분(1000÷N)한 뒤 남는 자리를 검색량 상위로 채운다 —
> 전역 상위 1,000 으로 자르면 검색량 큰 씨드가 작은 씨드를 통째로 밀어내
> 10개를 넣고 3개만 나오는 일이 생긴다.

**버전은 스킬 단위로 간다.** 기존 리포트 4종은 로케일 통합(2.0.0)과 로깅 제거(3.0.0)를
함께 겪어 **3.0.x 로 묶여** 있고, 나중에 추가된 세 스킬은 그 이력이 없어 **1.0.x 에서
시작**한다. 한 저장소에 버전이 섞여 보이는 것이 정상이다. 출처는 `skill.yaml` 하나이며
(`SKILL.md` 에는 적지 않는다) 빌드가 `metadata.version` 으로 넣어 준다.

### 시장과 리포트 언어는 실행할 때 정한다

스킬은 국가별로 나뉘어 있지 않다. 프롬프트는 영어 한 벌이고, 실행할 때 **두 값을 따로**
받는다:

- **타겟 시장(`--gl`)** — 어느 검색 시장을 분석할지 · `kr` · `jp` · `us`
- **리포트 언어(`--lang`)** — 리포트와 대화를 어느 언어로 쓸지 · `kr` · `jp` · `us`

둘은 서로 독립이다. **미국 시장을 일본어로** 쓰는 조합(`--gl us --lang jp`)이 정상이며,
한쪽에서 다른 쪽을 추론하지 않는다. 시장 언어와 리포트 언어가 다르면 리포트 상단에
**검색어 번역 버튼**이 생겨, 화면의 검색어를 원문 ↔ 리포트 언어로 토글할 수 있다.

## 개발

```bash
# 훅 설치 (클론 후 한 번)
ln -sf ../../scripts/hooks/pre-commit .git/hooks/pre-commit

# 빌드 · dist/lm-<스킬명>.zip
scripts/build.sh                     # 전 스킬
scripts/build.sh clusterfinder-report  # 한 스킬만

# 검사
python3 scripts/skill_common_check.py
python3 scripts/check_upstream.py    # 이식본이 정본과 갈라졌는지 (§7-b)

# 배포 (dist/PUBLISHED.json 에 적힌 것만 · 현재 비어 있음 = 공개 대상 없음)
scripts/publish-dist.sh --dry-run
```

> **MCP 호출에는 `is_skills: true` 를 붙인다.** 기본값이 `false` 라서 빠뜨리면 그 스킬의
> 사용량이 사람이 프롬프트로 부른 호출로 잘못 집계된다. 데이터도 과금도 달라지지 않고
> 분류만 달라진다. 캐시 키에서는 빠지므로 `mcp_cache.py --params` 에는 넣지 않는다.

저작 원칙은 [`AGENTS.md`](./AGENTS.md) 참조.
