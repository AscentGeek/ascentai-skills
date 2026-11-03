# narrative.json — rules for writing sentences

Report sentences go only into fixed slots. Everything else (explanation boxes · table titles) is written by code.
Read `facts.md` first and use **only the numbers in it**. Ratios computed from facts.md numbers are allowed.

**Output language = the report language (`lang` in config.json).** Write every slot in that language even though facts.md
headings are Korean. Search terms stay exactly as they appear in facts.md (the market's language). Theme names are the
report's names as they appear in facts.md.

```json
{
  "overview": {
    "season": "후드티 관련 검색어는 9–10월(가을 후드티·코디)과 11월(기모·니트)에 해마다 오르는 것이 많고, 5월에는 반팔·여름 후드티가 따로 오릅니다.",
    "trend":  "브라운브레스 같은 스트릿 브랜드 여럿이 늘었고, 스투시 검색은 정품·사이즈까지 함께 줄었습니다.",
    "updown": "가을 후드티 검색이 올랐고, 스투시 후드티는 내렸습니다."
  },
  "month_note": "…",
  "calendar_note": "…",
  "updown_note": "…",
  "years_trends": [
    {"title": "브라운브레스를 중심으로 스트릿 브랜드 여럿이 함께 떠올랐다",
     "basis": "최근 1년 검색량이 직전 1년의 1.5배 이상인 스트릿 브랜드 검색어",
     "insight": "\"브라운브레스 후드티\"를 중심으로 \"아더에러 후드티\"·\"네이더스 후드티\"가 함께 커졌습니다.",
     "memberKeywords": ["브라운브레스 후드티", "아더에러 후드티", "네이더스 후드티"]}
  ]
}
```

(The example is a `lang kr` report. For `lang us` the same slots read e.g. "Hoodie-related queries mostly rise in Sep–Oct …".)

## Rules per slot

| Slot | Where | Length · content |
|---|---|---|
| `overview.season` | Cover summary "Seasonal patterns —" line | **1 sentence**. 2–3 months where seasonal keywords cluster and the representative keywords of those months. The subject is the related queries, not the seed itself ("dessert searches rise" ×, "dessert-related queries mostly rise …" ○) — the bare seed may have no season |
| `overview.trend` | Cover summary "Last 12 months —" line | **1 sentence**. The first 2–3 trends of `years_trends` — what grew and what shrank. Do not write totals that are not on screen ("overall search fell, but") |
| `overview.updown` | Cover summary "Last 3 months —" line | **1 sentence**. 2–3 each of what rose and what fell in the last 3 months, taken only from the "QoQ+YoY" lists (up on both QoQ and YoY · down on both) — not from the "QoQ 순" (QoQ only) lists |
| `month_note` | Seasonal keywords by month · insight box under the criteria | 2–3 sentences. ① First the periods keywords cluster in (adjacent months grouped, 2–3 periods) ② then each period's representative keywords with their names exactly as in the report. Do not give the groups interpretive names ("holiday demand", "seasonal fruit"). ③ Also mention months with no keyword or only one keyword passing |
| `calendar_note` | Seasonal calendar by theme · insight box above the calendar | 1–2 sentences. The flow of when what rises per theme (e.g. "flavours: Feb chocolate → Jul peach → Oct chestnut · sweet potato → Dec strawberry"), themes crowded into one month. Look only at facts.md "테마별 시즌 캘린더" (seasonal calendar by theme) |
| `updown_note` | Tab 3 · insight box under the criteria | **1–2 sentences**. The queries that rose most and fell most, 2–3 representatives per side, from the top of the "QoQ+YoY" lists in facts.md "트렌드 · 최근 3개월". Use the report's wording for the comparison bases ("same 3 months last year", "previous 3 months"). Do not call a query "seasonal" or say it rose "because of the season" — the numbers only show it was similar to the same 3 months last year. Shorten names only by dropping the seed word; do not give interpretive group names. Do not write causes |
| `years_trends` | Tab 2 top "Key trends" | 0–5, **in order of importance** (the order written is the screen order). If there is no clear group, `[]` — do not force groups to fill a count (the card then says "No movement meets the criteria above."). See "Grouping key trends" below |

## Grouping key trends (`years_trends`)

Read: the three branches of facts.md "주요 트렌드 재료" (key-trend material) — candidates code split by comparing the previous 12 months with the last 12 months.

| Branch | Criterion code used (12-month total ≥ 5,000 in either the previous or the last 12 months) |
|---|---|
| new | The previous 12 months are effectively 0 (≤ 2% of the larger side) |
| growing | last 12 months ÷ previous 12 months ≥ 1.5 |
| falling | last 12 months ÷ previous 12 months ≤ 0.5 |

- **Group only same-direction queries.** new and growing are both up and may be grouped together; never mix them with falling (code drops queries whose direction differs from the first one).
- **Write only groups usable for marketing decisions** — a brand · product/menu · ingredient/flavour · channel (shopping mall · convenience store · franchise) · content · use, i.e. something a marketer can act on.
  A change only in the words attached when searching ("○○ dessert cafe" → "○○ dessert spot") is not a trend.
- **Check before adopting** — in the opposite branch and in facts.md's per-theme lists, look for queries with the same basis (same area · same word · same brand) and make sure the title is not wider than reality.
  - If there are counter-examples, narrow the title and scope ("shopping malls" → "Yongsan · Jamsil shopping malls").
  - If counter-examples outnumber the group, do not use it.
  - Reflect the check only in the title and scope; do not write counter-examples as sentences.
- Do not say searches moved ("moved to" · "shifted to" · "replaced" ×). Even if one side grew and another shrank, search data cannot tell whether the same people moved. If both a growing and a shrinking group are clear, write them separately.
- Write `title` from what the grouped queries **actually share**; do not generalise to a wider category. Do not call something that was already large in the previous 12 months "new".
- Do not group queries that spiked together in a month listed in facts.md "확인할 것" (to check).
- Theme totals and rates (sum grown, theme 12-month change, …) are not in the report, so do not write them. Numbers are per query only.
- `basis` — one line on why this group (which branch · what is shared). `insight` — 1–2 sentences.
- `memberKeywords` — the queries exactly as in the facts.md branch lists. If fewer than 2 are in the same direction, code drops the group. With 6 or more, only the top 5 by their largest size remain.

## Style

- The cover summary (`overview`) is insight only. Numbers are in the tabs, so leave them out (at most one if truly needed).
- Plain declarative sentences (kr 합니다체 · jp です・ます調 · us plain past/present tense).
- Numbers exactly as written in facts.md (`1,234` · `12.3만` / `12.3万` / `123K` · `+16.2%` · `−3.0만`). Negative sign `−`.
- Wrap queries in double quotes ("후드티 추천" · jp 「パーカー おすすめ」 is also fine). Theme names exactly as in the report.
- **Words not used** (lint blocks them in the report language):
  - kr: 기회 · 추천합니다 · 해야 합니다 · 예측 · 전망 · 확실히 · 폭망 · 몰락 · 충격 · 대박 · 거짓말 · 때문에 · 의 영향으로 · 옮겨갔 · 넘어갔 · 대체했
  - jp: チャンス · おすすめします · すべきです · 予測 · 見通し · 確実に · 激減 · 崩壊 · 衝撃 · 大ヒット · のせいで · の影響で · 移った · 乗り換えた · 取って代わった
  - us: opportunity · we recommend · you should · should be · predict · forecast · outlook · certainly · collapse · plummet · shocking · skyrocket · because of · due to · driven by · shifted to · moved to · replaced
- Do not assert causes ("because of", "due to" ×). Search data alone cannot tell the cause.
- Do not talk about the future. "will rise next October" (×) → "October was the peak in each of the last 4 years" (○).
- Do not write about 4-year long-term trends, industry comparisons, sales or market share.
