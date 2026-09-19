# ascent-skills-saas

ListeningMind **SaaS 고객용** 리포트 스킬. 데이터는 **ListeningMind MCP** 로만 받는다.

## lima-skills 와의 관계

`lima-skills` 의 report 4종을 SaaS 용으로 이식한 것이다. 분석틀·렌더 계층은 같고,
**데이터 경로만 다르다.**

| | lima-skills (DaaS) | ascent-skills-saas (SaaS) |
|---|---|---|
| 데이터 | DaaS REST · `listeningmind-data-api.ascentlab.io` | **ListeningMind MCP 4도구** |
| 인증 | `LM-API-KEY` 를 사용자에게 입력받음 | **없음** · MCP 커넥터 연결이 전제 |
| 호출 주체 | `scripts/daas_call.py` (코드) | **LLM** (MCP 툴 호출) |
| 세션 캐시 | `~/.lima-agents/rest-cache/<sid>.json` | `~/.lima-agents/mcp-cache/<sid>/` |
| 크레딧 기록 | 코드가 봉투에서 자동 추출 | LLM 이 봉투를 읽어 전달 |

> **SaaS 스킬이 DaaS 에 과금되면 안 된다.** 이 리포에 `daas_call.py` 나
> `listeningmind-data-api.ascentlab.io` 송신이 들어오면 그 전제가 깨진다.
> pre-commit 훅이 이를 차단한다.

## 스킬 4종

| 스킬 | 리포트 | 쓰는 MCP 도구 |
|---|---|---|
| `lm-queryfinder-report` | 쿼리 기회 분석 | `intent_finder` + `keyword_info` |
| `lm-clusterfinder-report` | 검색 클러스터 지형 | `cluster_finder` + `keyword_info` |
| `lm-pathfinder-report` | 검색 여정 분석 | `path_finder` + `keyword_info` |
| `lm-total-report` | 3파인더 통합 | 위 3종 + `keyword_info` 1회 |

스킬 이름은 `lm-<스킬명>` 이다 — 국가 코드는 붙지 않는다.

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

# 검사
python3 scripts/skill_common_check.py

# 배포 (PUBLISHED.json 에 적힌 것만)
scripts/publish-dist.sh --dry-run
```

저작 원칙은 [`AGENTS.md`](./AGENTS.md) 참조.
