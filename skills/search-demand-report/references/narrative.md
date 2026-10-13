# narrative.json writing rules (v5)

narrative only fills fixed slots with sentences. Use numbers **only as the exact strings written in facts.md** (lint blocks anything else).
Real example: the "Pilates final version" below.

**Output language = REPORT LANGUAGE (`--lang`).** Write overview, titles and bodies in the report language (kr → Korean, jp → Japanese, us → English) whatever the target market is. Keep search terms in the market's original spelling.

```json
{
  "overview": "커버 '배경과 목적' 아래 요약 · 1~2문장(100~200자) · 결론부터",
  "sections": {
    "external": {"insights": []},
    "internal": {"insights": [{"group": "검색 목적 이름", "title": "결론 한 줄", "body": "목적 안 검색어를 보니 …"}]}
  }
}
```

(Skeleton meaning: `overview` = summary under the cover's '배경과 목적' (Background and purpose) · 1–2 sentences (100–200 characters) · conclusion first; `title` = one-line conclusion; `body` = 1–2 sentences of evidence; `group` = search-purpose name; internal `body` starts from "looking at the search terms inside the purpose …".)

## Slot rules (checked by lint)

| Slot | Rule |
|---|---|
| `overview` | 1–2 sentences, 100–200 characters. Placed directly under the cover's fixed phrase ('배경과 목적', Background and purpose).<br>· Synthesize the conclusions of both sections (01 · 02) — not section 01 alone<br>· Analyze search volume (scale) and trend (change) together to derive the insight<br>· Write only what the data shows, accurately and in plain words — no guesses or causal claims<br>· Bold (`<b>`) 2 conclusion phrases; never bold a number on its own<br>Examples: 'Overview examples' below |
| `sections.external.insights` | **0–3.** The verdict card (a code-written sentence) is the conclusion, so usually 0 — do not repeat what the verdict card says |
| `sections.internal.insights` | 1–3 · **`group` required** on every card (exactly the search-purpose name in the section 2 table · in brand/product mode, the product line name — 페가수스) |
| Removed | `lead` (section summary sentence) · `synthesis` (summary tab) · `actions` (action suggestions) · top-level `actions` — lint error if present |

Section ids are only `external · internal` (report order = 1 Market flow comparison · 2 Target keyword intent change).

## How insight cards are placed on screen (code)

- At the **top** of each section, directly under the title. There is no 'Insights' subheading · (i) · bullet marker — the card title itself is the conclusion.
- On section 2 card headers the code adds `[검색 목적 칩] 4년 ±x% · a위 → b위` ([search-purpose chip] 4-year ±x% · rank a → rank b) (or `신규 YYYY-MM` (new) if new). **Do not repeat these numbers in the body.**
- In section 2 card bodies the code turns search-purpose names and search terms into links (clicking moves to · expands · highlights that purpose in the table below). So write search terms in their exact spelling inside ‘…’.

## 2 Target keyword intent change — "this purpose changed like this, and looking inside, it is because of these search terms"

Brand/product mode (v5.1) is written the same way — a product line simply takes the place of the purpose. e.g. “보메로가 페가수스와 나란히 설 만큼 커졌습니다 / ‘나이키 런닝화 보메로’(+336.1%)처럼 라인 이름으로 찾는 검색이 크게 늘었고 …” (“Vomero has grown enough to stand alongside Pegasus / searches by line name, like ‘나이키 런닝화 보메로’ (+336.1%), rose sharply and …”).
Quote generation · model names (‘나이키 러닝화 페가수스 42’) as search terms inside the line. `목적 안 비중` (share within purpose) in facts.md is the share within the line.

Draw the body from the facts.md lines `검색어 '…' 최근 12개월 · 목적 안 비중 · 4년 · 전년 · 4년 증감` (search term '…' last 12 months · share within purpose · 4 years · prior year · 4-year change).
Order: **search terms that moved the purpose (large share · large change) → search terms that moved the opposite way → what the data shows overall (no guesses or causal claims).**
Pick purposes where there is movement the total alone does not show (diverging inside · new · large rank change).

## Style — readable for a marketer at once (neither hedging nor overclaiming)

The rules and examples below are the rules for Korean output. For jp/us output apply the same intent (plain, conclusion first, no exaggeration).

| Don't | Do |
|---|---|
| 묶음의 96.4%가 단어 ‘필라테스’라 타겟의 흐름은 곧 이 단어의 흐름입니다 (Because 96.4% of the group is the word ‘필라테스’, the target's flow is this word's flow) | ‘필라테스’가 사실상 유일한 주요 키워드입니다. 검색량의 96.4%가 이 한 단어에서 나옵니다 (‘필라테스’ is effectively the only major keyword. 96.4% of search volume comes from this one word) |
| 장소 탐색 묶음의 구성비가 2.2%에서 4.5%로 올랐습니다 (The composition ratio of the place-search group rose from 2.2% to 4.5%) | ‘근처 필라테스’ 같은 검색이 늘어 순위가 11위에서 8위까지 올라왔습니다 (Searches like ‘근처 필라테스’ grew, moving up from 11th to 8th) |
| 업계와 같은 흐름입니다 (verdict word only) | 요가·홈트·헬스도 비슷하게 줄어, 필라테스는 운동 시장 전체와 같은 흐름입니다 (Yoga · home training · gym fell similarly, so Pilates moves the same way as the whole exercise market) |
| 스튜디오명 검색의 세대 교체 (noun-phrase title: "generational change in studio-name searches") | 대형 브랜드는 줄고 새 브랜드가 뜨고 있습니다 (Large brands are falling and new brands are rising) |

- **The title is a one-sentence conclusion** (“~가 늘고 있습니다” (… is increasing), “~가 사실상 유일한 주요 키워드입니다” (… is effectively the only major keyword)).
- Body: **what → how much → what the data shows overall (no guesses or causal claims).** Use real search terms as examples (‘근처 필라테스’).
- Do not use analysis jargon. Replace: 묶음 (group) → 검색어 (search terms) · 구성비 (composition ratio) → 순위 (rank) · 중앙값 (median) → 평균 (average) · 유사의도 (similar intent) → 같은 뜻의 검색어 (search terms with the same meaning) · 시드 (seed) → 분석 대상 (analysis target) · 구간 (interval) → 1년 단위 (per year) · %p → 차이 (difference) · 의도 묶음 (intent group) → 검색 목적 (search purpose).
- Write only what the data shows — no guesses or causal claims (추측·인과 표현 없이 데이터가 보여 주는 것만 쓴다). Do not end without a conclusion on “추가 확인이 필요합니다” (further checking is needed).
- Search volume is an indicator of interest — do not restate it as sales · market share. Do not write “A 에서 B 로 이동/옮겨 갔다” (moved/shifted from A to B) (go only as far as “A 는 줄고 B 는 늘었다” (A fell and B rose)).
- No exaggerated or aggressive expressions (lint).

## Overview examples (2026-10-12 · kr)

Category mode — 마그네슘 영양제 (magnesium supplement):
```json
"overview": "비교한 영양제 검색이 모두 줄어드는 추세인데, <b>마그네슘은 검색량이 줄지 않아 유산균 다음으로 많이 찾는 영양제가 됐습니다.</b> 검색량 대부분인 ‘마그네슘’은 거의 그대로였고 ‘마그네슘 영양제’가 꾸준히 늘었으며(+24.7%), 세부 목적 중에서는 <b>브랜드명 검색이 가장 많이, 젖산·킬레이트 등 형태 검색이 가장 빠르게 늘었습니다.</b>"
```

Brand (entity) mode — 나이키 운동화 (Nike sneakers):
```json
"overview": "나이키 운동화는 비교한 브랜드 중 여전히 가장 많이 검색되지만, <b>시장보다 빠르게 줄어 뉴발란스·호카와의 차이가 좁혀졌고</b> 최근 12개월 내내 전년보다 적게 검색됐습니다. 제품 라인에서는 <b>에어포스가 줄어든 만큼을 늘어나는 보메로·페가수스·샥스가 메우지 못하고 있습니다.</b>"
```

## Pilates final version (2026-10-06 · kr) — section insight example (for overview see 'Overview examples' above)

```json
{
 "sections": {
  "external": {"insights": []},
  "internal": {"insights": [
   {"group": "지역명 검색", "title": "번화가보다 생활권 역·동네로 찾고 있습니다", "body": "‘서울대입구 필라테스’(<b>+163.9%</b>)·‘이수역 필라테스’(<b>+190.1%</b>)… 반면 ‘강남역 필라테스’(<b>−76.0%</b>)… 번화가 역보다 생활권 역 이름으로 찾는 검색이 늘었습니다."},
   {"group": "브랜드명 검색", "title": "대형 브랜드는 줄고 새 브랜드가 뜨고 있습니다", "body": "모던필라테스(<b>−50.6%</b>)… 이브필라테스는 <b>+23.5%</b> 늘었고 이모란 필라테스처럼 새로 생긴 이름도…"},
   {"group": "바레", "title": "‘바레 필라테스’가 새 수요를 만들고 있습니다", "body": "‘바레 필라테스’가 목적 안 <b>84%</b>로 대부분이고 …"}]}
 }
}
```
