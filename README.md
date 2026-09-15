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

일본어판(`lm-<스킬명>-jp` 4종)은 한국어판 확정 후 추가한다.

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
