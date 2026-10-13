# Verdict and correction rules (rules-v5 · 2026-10-06)

All numbers live in one place, `RULES` in `_shared/render/ds_aggregate.py`; this document copies those values. If you change a value, update the code and this document together.
The LLM does not apply the rules — it puts the results the code applied into sentences. Both modes use the same rules (the per-mode rule differences of v2 were removed).

## Aggregation

| Item | Value |
|---|---|
| Intervals | Non-overlapping 12 months × 4 · 4-year change = last 12 months ÷ first 12 months − 1 · prior year = last 12 months ÷ previous 12 months − 1 |
| Engines | Naver + Google summed |
| Group metric | Median |
| No measured value | 48-month total < 12 → excluded from the table, listed at the bottom |
| New | First appears after the first 3 months and (first 12 months = 0 or first 12 months < last 12 months × 10%) → 4-year change rate not computed, show since |
| Prior-year '신규' (new) (rules-v5) | If the first month of appearance is within the last 24 months (the previous 12-month interval or the latest interval), show "신규" (new) instead of the prior-year change rate — same for lines · SKUs · keywords |
| Flow type (2 category) | Direction of the 3 interval steps: ↑↑↑ up 3 years in a row · ↓↓↓ down 3 years in a row · last ↑ with a ↓ before it: down then up · last ↓ with a ↑ before it: up then down · otherwise flat |
| Composition ratio (2 category) | Share of the intent-group total in that interval · first interval → latest interval |
| Top-2 share (2 share bar) | Sum of the 1st and 2nd items in that interval ÷ interval total |
| Per-interval change rate (1 · 2 bars) | That 12-month total ÷ previous 12-month total − 1 (3 columns) · 4 years = last 12 months ÷ first 12 months − 1 · if the comparison interval is 0, — |

## Why 12-month (rolling) interval totals are used

1. The current year is not over, so a calendar-year analysis based on forecast values carries too many risks.
2. Each interval must include every month once so that seasonal effects cancel out when totals are compared.

Test evidence: '나이키 러닝화' August 2026 single month vs prior year −44%, 12-month rolling vs prior year −9% (keyword_info, 22.09–26.08). Comparing single months alone reads a seasonal drop as a fall in demand.

## Data notes (rules-v4 · values are not changed)

**All values are Naver + Google totals.** The detections below are written only as facts in "데이터 참고 사항" (Data notes) at the bottom of the report; no labels are attached to tables · charts.
A detection is a suspicion, not proof, so do not remove values to change the conclusion. If a 단일 엔진 급증 (single-engine surge) looks large, do not delete the values;
first check that all spelling variants of that keyword are in the group (쿠쿠 real case: '쿠쿠 6인용 압력밥솥' moved to '쿠쿠 압력밥솥' in the same month).

| Record | Detection formula | Handling |
|---|---|---|
| 단일 엔진 급증 (single-engine surge) | One engine jumps 2.5× or more from a previous 3-month average ≥ 100 and holds for 3 months · still 2× after 3–6 months · the other engine changes < 50% in the same month | Record only |
| 구글 동일값 중복 (duplicate identical Google values) | Two keywords have exactly the same 48-month Google values | **Sum the Google values only once** (prevent double counting · unique-value handling) |
| 표기 이동 (spelling shift) | Within a group, one keyword drops to half or less of its 3-month average and in the same month another keyword rises by 0.6–1.6× the dropped amount · dropped side ≥ max(100, 5% of the group's monthly average) | Record only (same group, so the total is unchanged) |
| 특정 키워드 집중 증가 (increase concentrated in one keyword) | Group 3-month average ≥ 1.8× the previous one, still 1.5× after 3–6 months · one keyword makes 70% or more of the increase and that share is 30%p or more above its original share | Record only |
| 일시적 급등 (temporary spike) | Single month ≥ median of the surrounding 3 months × 3 · returns to 1.5× or less within 2 months | Record only |

## 1 Market flow comparison verdict (comparison group)

| Item | Value |
|---|---|
| Baseline | Median of the 4-year change of the external groups (excluding new) |
| Verdict | \|seed − baseline\| < 15.0%p → **업계와 같은 흐름** (same flow as the industry) / seed 15.0%p or more lower → **업계 대비 약세** (weaker than the industry) / higher → **업계 대비 강세** (stronger than the industry) |
| Withheld | External groups with a 4-year change rate < 3, or seed 4-year change rate not computed → **판정 보류** (verdict withheld) |
| Stability | leave-one-out: whether the verdict holds when each external group is removed one at a time. If it changes, note that item and write "경계에 있다" (it is on the borderline) |

## KPI

| id | Value |
|---|---|
| external | 1 seed − baseline difference · verdict |
| seed | 1 analysis-target row 4-year change · monthly average · prior year |
| internal | 2 share of the top line · group in the last 12 months · 4-year change |
