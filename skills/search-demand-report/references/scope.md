# Narrowing the seed (scope-v2) — turn a broad keyword into a seed that makes a good report

This skill assumes the seed is **one kind of thing people buy (an item)** or **brand + item**. An area word ("뷰티" beauty ·
"패션" fashion · "가전" appliances) or a brand that sells many items, alone ("나이키" Nike), produces a meaningless comparison set,
same-meaning names and inside bundles. So when check at Step 1.5 catches a broad seed, **narrow it here, then restart from the beginning.**

Principle: **Claude does not choose the target.** The skill turns the options into data and the user chooses.
Never invent options — even your own candidates are shown only after keyword_info · intent_finder verify them.

## 1. When — code decides (`ds_classify.py check` · kind = broad / brandwide)

| kind | Condition (`SCOPE` · ds_scope.py · per market) | Example |
|---|---|---|
| `broad` | category, and among the seed's related queries **the share where the seed sits in the searched-for slot (end of the query) < 45%** and **the share where the seed is a standalone word < 70%** · or seed.json `seedType: "domain"` | 뷰티 (27% · 50%) — used inside other names: 디올 뷰티 · 뷰티라운지의원 · 뷰티 인사이드 |
| `brandwide` | entity, brand only (`itemOptional`), and seed.json `brandItems` has 2 or more (item categories the brand sells) | 나이키 (러닝화 · 운동화 · 바람막이) · bhc sells only chicken, so not this |

Calibration (2026-10-06 · kr): 뷰티 head 27% · token 50% → broad / 쿠션 71%·83% · 선크림 78%·99% · 마스크팩 85%·92% · 향수 70%·93% ·
앰플 84%·95% · 클렌징폼 89%·76% → item. **jp and us use the kr thresholds for now** (not calibrated · the scope brief warns).
Check order is broad seed → topic → mode. An area word that is also a topic (‘운동’) comes here too. A seed already narrowed
(seed.scope) is not checked again.

## 2. Candidates — you (`scope.json`)

| type | Candidates = | Rules |
|---|---|---|
| `domain` | 8–12 **items** under the area (one kind of thing people buy) | Items seen in the seed's related queries first (src `intent`), then items you know (src `analyst`). Cover the area evenly (뷰티 → base · sun care · lip · skin care · cleansing · mask · hair · fragrance · device). For a homonym shared with another area, use that area's name (쿠션 → also put 쿠션 팩트 in variants) |
| `brand` | the items in `brandItems` (measured as brand + item) | Only items the brand actually sells. Those seen as 'brand + X' in the related queries first |

Always write `"gl"` — the purchase-exploration words and the broad-seed thresholds are per market.

```json
{"from": "뷰티", "gl": "kr", "type": "domain",
 "candidates": [{"name": "쿠션", "variants": ["쿠션"], "src": "intent"}, {"name": "선크림", "variants": ["선크림", "썬크림"], "src": "analyst"}]}
```

## 3. Verification — 2 MCP calls (all candidates at once)

Each call follows SKILL.md "MCP call protocol" (cache lookup → call with `download_url` + `is_skills: true` + `user_query` → `fetch_dl.py`).

| File | Tool · parameters |
|---|---|
| `lm_keyword_info_scope.json` | keyword_info `{"keywords":[all candidate queries],"gl":"<gl>","data_type":"all"}` (brand: 'brand item') |
| `lm_intent_scope.json` | intent_finder `{"keywords":[all candidate queries],"gl":"<gl>","limit":<candidate count × 500>,"volume_threshold":0}` |

```bash
python3 "$R/ds_scope.py" score --scope "$WORKDIR/scope.json" --kw "$WORKDIR/lm_keyword_info_scope.json" \
  --intent "$WORKDIR/lm_intent_scope.json" --out "$WORKDIR/scope_result.json" --brief "$WORKDIR/scope.md"
# exit 0 = exactly one fits → proceed automatically (notify) · exit 10 = ask · exit 12 = none fits → free input
```

## 4. Verdict — code (report fitness)

| Grade | Condition | Why |
|---|---|---|
| 부적합 (unfit) | no 48-month volume · last-12-month monthly avg < 1,000 · first 12 months are 0 · (domain) searched-for slot < 45% | no 4-year change, unstable to interpret, or still broad |
| 주의 (caution) | related queries attributed to the candidate < 30 | target and inside bundles are thin (calling many candidates at once leaves small candidates a small share — once chosen it is called again as the seed) |
| 적합 (fit) | none of the above | |

Order = fit → caution → unfit, and by monthly avg within a grade. If fewer than 4 candidates are not unfit, the brief says the section 1
comparison set must be supplemented from upper · analyst.
Purchase-exploration share (price · recommendation …) is **shown but not used in the verdict** — beauty items are 4–9%, lower than 러닝화
(17%), and the reports are fine.

## 5. Asking — fixed format · once (scope-v2 · note → evidence → options)

Do not ask with just a list of candidates. Show **why it must be narrowed → what to type (format and examples) → the options**, in that order.
Use the `안내` (note) and `선택지` (options) lines of the scope brief (code output) as they are — **if the user writes in another language,
move them into that language keeping meaning and order** (search terms and numbers unchanged · SKILL.md "Chat language").

1. **Note (fixed text)** — "‘{from}’은(는) 주제가 넓어서 그대로 분석하면 비교할 시장과 검색 의도가 흐려집니다. 세부 시장을 정하면 더 정확하게 분석할 수 있습니다."
   ("‘{from}’ is a broad topic, so analysing it as is blurs the markets to compare and the search intent. Choosing a sub-market makes the analysis more accurate.")
2. **Input format and examples** — ask for **one search term** as people actually type it.
   - Area (뷰티 · 가전) → one item: `선크림` · `향수`
   - Brand (삼성 · 나이키) → brand + item as one spaced search term: `삼성 냉장고` · `나이키 러닝화`
   - **Never a hierarchy**: `삼성 > 냉장고` · `냉장고(삼성)` · `삼성/냉장고` are used neither as examples nor as options — the report works on
     search terms, so the answer becomes the seed as is.
3. **Evidence table** — the brief's table as is (candidate · monthly avg · 4-year change · related queries · searched-for slot · grade · reason).
   The candidate column is the search term as typed (`삼성 냉장고`).
4. **Options** — a button question tool (ask_user_input) with the top 3 fits + "직접 입력 (예: …)" (free input, e.g. …). Labels = the brief's
   `선택지` line as is (`삼성 냉장고 · 월평균 48,000`). Code picks the free-input example from candidates not among the options.
5. **One recommendation with a one-line reason** — the top fit. If the user gave another angle (growing items · own items), choose from the table by that.
6. Ask **once**. If exactly one fits, do not ask — say you proceed with it (notify — notes 1 · 2 are still shown). If none fits, show the
   caution candidates and take free input.

Example (삼성 · brand):

> ‘삼성’은 주제가 넓어서 그대로 분석하면 비교할 시장과 검색 의도가 흐려집니다. 세부 시장을 정하면 더 정확하게 분석할 수 있습니다.
> 브랜드라면 ‘브랜드 + 품목’ 한 검색어로 정해 주세요 — 예: **삼성 냉장고** (삼성 > 냉장고 ✕)
> [evidence table] → options: 삼성 냉장고 · 월평균 48,000 / 삼성 세탁기 · 월평균 36,000 / 삼성 에어컨 · 월평균 30,000 / 직접 입력 (예: 삼성 김치냉장고)

## 6. After the choice

1. Rewrite seed.json for the chosen candidate (M1), keeping `gl` and recording `scope`:
   ```json
   {"seed": "선크림", "gl": "kr", "mode": "category", "item": ["선크림"], "upper": "선케어", "heads": ["크림"],
    "scope": {"from": "뷰티", "type": "domain", "how": "사용자 선택", "siblings": ["향수", "마스크팩", "쿠션", "..."]}}
   ```
   `siblings` = the candidates other than the chosen one that are not unfit — propose lists them as section 1 comparison candidates but with
   the grade **'영역만'** (same area only · no evidence of being searched together) at the bottom (향수 → 샴푸 · 마스크팩 were only the same
   beauty area, not similar markets). Choose the comparison set from keyword-method M5-0's nearby market (substitute · adjacent) first.
   brand does not use siblings (competing brands are found in the data).
   **Do not put the broad seed (from · 뷰티) in `upper`** — use the narrowest parent covering the seed and its substitutes · adjacent items
   (향수 → 프래그런스 · 선크림 → 선케어). It becomes the '○○ 시장' (○○ market) name in the verdict sentence.
   `how` = "사용자 선택" (user choice) · "적합 1개 · 자동" (one fit · automatic) · "직접 입력" (free input).
2. Reuse related queries: `ds_scope.py extract --scope "$WORKDIR/scope.json" --intent "$WORKDIR/lm_intent_scope.json" --pick 선크림 --out "$WORKDIR/lm_intent_seed.json"`
   — with 300+ attributed queries intent_finder (seed) is not called again (exit 13 → call it).
3. Keep `lm_intent_scope.json` (the source of comparison strings). `lm_keyword_info_scope.json` may be added at the end of build's `--kw`.
4. Restart from Step 1.5 check. Code adds one "시드 좁히기" (seed narrowing) line under the mode verdict at the top of the report.
