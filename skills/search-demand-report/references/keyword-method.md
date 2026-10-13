# Keyword-set classification method (method-v5.12)

This document defines **which search terms go into** section 1 Market flow comparison · section 2 Target keyword intent change. Given the same seed, anyone who runs it must get the same keyword set.
`ds_classify.py` builds the classification according to the rules in this document. The LLM acts only at the four **[Choice]** points below,
and every time it chooses it records the rule number (M1–M9) as the reason. Do not add or remove a keyword for any reason that is not in the rules.

## At a glance

| Section | finder input | Brand/product mode | Category mode | Modifiers |
|---|---|---|---|---|
| 1 Market flow comparison | upper (entity: target category · category: higher-level parent category) → cluster (if available) · intent | Only the brand changes · the same item names as the target are mixed in (아디다스 런닝화 · 아디다스 러닝화 · 아디다스 조깅화 · adidas 러닝화) | Other items in the same parent category (테니스화 (tennis shoes) · 농구화 (basketball shoes)) | Generic item words only |
| 2 Target keyword intent change | entity: own brand + target category · category: seed | Product lines (페가수스 (Pegasus) · 보메로 (Vomero) — they take the place of the search purposes in category mode · generation/model names are search terms inside a line) | Intent bundles (브랜드·모델 탐색 (brand/model exploration) · topics · 계급도·순위 (tier list/ranking) · 추천·입문 (recommendation/beginner) …) | entity: no explore/attribute words · category: intent words = the bundle basis |

| Attached word | Handling |
|---|---|
| Spelling variants/synonyms (런닝화 · 러닝 슈즈 · 조깅화) · generic item words (운동화 (sneakers) · 신발 (shoes)) | Include in 1 (analysis target and comparison set) |
| Explore (추천 (recommendation) · 가격 (price) · 비교 (comparison) · 후기 (review)) · attribute (6인용 (6-person) · 여성 (women's) · 스텐 (stainless) · 트레일 (trail)) | Do not include in 1 or 2 (entity) · in 2 (category) they are the intent-bundle basis |
| Proper names not in the dictionary (페가수스) | Go to 2, not 1 |
| Use/care (사용법 (how to use) · AS (after-sales service)) · purchase channel (쿠팡 (Coupang) · 중고 (used)) · community (디시 (DCInside)) · info (뜻 (meaning) · 차이 (difference)) · year | Do not include anywhere |

## M0. Mode decision (code · `check`)

Decided from the composition of the seed's related search terms (lm_intent_seed). If it differs from `mode` in seed.json, ask with ask.md.

| Mode | Condition |
|---|---|
| entity | Related search terms containing the seed brand (B*) ≥ 50% — mostly searches for one brand's product names, lines, and usage |
| category | Words directly before the item (I) that are not in the dictionary (brands) ≥ 2, and any single brand's share < 50% — generic modifiers + several brands |
| Undecidable | Neither → ask |

## M1. Seed decomposition (LLM · seed.json)

Narrow a broad seed (뷰티 (beauty) · a multi-item brand on its own) with `scope.md` before M1. If it was narrowed, record `scope` (from · siblings) in seed.json —
siblings become candidates for the section 1 comparison set in M4 (source intent), and are excluded from the M3a same-meaning-name candidates.

| Seed | B | I | upper | Mode (expected) |
|---|---|---|---|---|
| 나이키 러닝화 | 나이키 | 러닝화 | 러닝화 | entity |
| 나이키 | 나이키 | 러닝화 (itemOptional) | 러닝화 | entity |
| 쿠쿠 밥솥 | 쿠쿠 | 밥솥 | 밥솥 | entity |
| 러닝화 | — | 러닝화 | 운동화 | category |
| 전기압력밥솥 | — | 전기압력밥솥 | 밥솥 | category |

- Write the **B\* spelling variants** (나이키 · nike). The code ignores spacing.
- **I is the seed item name only.** Synonyms are chosen in M3a, with reasons.
- **upper** = the target category in entity mode, the higher-level parent category in category mode. Section 1's cluster/intent and the analysis target's same-meaning-name candidates come from here.
- **If the seed is a brand alone** (bhc · 나이키), set `"itemOptional": true` and put the brand's own target category in item.
- **Parent-category heads H** (heads) — used in category mode to find sibling items. 러닝화 → H = {화, 슈즈}.
- **Generic item words `generic`** (method-v5) — words that, used together with the seed item, still name the same thing. **You must fill this in if the item is not footwear** (`[]` if none).
  If omitted, the default footwear generic words (운동화 · 신발 · 슈즈 · 러닝 · 런닝 · 달리기) are used, and ‘필라테스 신발’ · ‘헬스 운동화’ get mixed into the target and comparison set (measured).
  Example: 러닝화 → omit (default) · 필라테스 (Pilates) → `"generic": []`

## M2. Modifier dictionary (fixed · per market · code `ds_market.py`)

Remove B* and I* from a search term and classify the remaining words with the dictionary. Words not in the dictionary are **residual words**.
Classes: `generic` generic item word · `explore` exploration · `use` use/care · `howto` usage/application · `attr` attribute · `channel` purchase channel · `community` community · `info` non-purchase information · `year` year.
If you change the dictionary, bump the METHOD version. Do not edit the dictionary to fit a single case.

**There is one dictionary per market (`seed.gl`) (method-v5.12).** kr · jp · us live in `ds_market.py` and are selected by `gl` in seed.json.
The 8 dictionaries · patterns · intent-bundle words · topic-type/purchase signals · M5-0 comparison-mention words · region-name suffixes · broad-seed thresholds are all per market.
- kr · jp find dictionary words even inside joined fragments (`ランニングシューズおすすめ` → explore). us matches whole words only (including plurals)
- A search term mixed with another market's script is a mis-entry (`info`) · kr: kana · jp: Hangul · us: Hangul, kana, kanji
- Do not put words that overlap with multi-word brands (new · under · on) into the us dictionary (new balance · under armour · on running)
- The broad-seed thresholds (scope.md) are calibrated on measured data for kr only. jp · us temporarily use the kr values

## M3. Analysis target = seed + names with the same meaning (method-v5)

The target is **only the names that call the seed itself**. A search term is a target if it consists only of **B\* (entity only) + I\* + 0–2 generic item words**.
I\* = the seed item + the other names chosen in M3a (spelling variants, English). **The moment anything is attached after it, it is an intent search** — it goes to section 2 intent change.

| Search term | Verdict |
|---|---|
| 필라테스 · pilates · (나이키 러닝화 · nike 러닝화 · 나이키 런닝화) | ○ target |
| 필라테스 1:1 · 필라테스 학원 · 근처 필라테스 (class format / place intent) | × → 2 |
| 필라테스 신발 · 필라테스 운동 (a different thing / higher-level term) | × |
| 나이키 러닝화 추천 (explore) · 나이키 여성 러닝화 (attribute) | × |

## M3a. [Choice 1] Choosing names with the same meaning (spelling variants)

| Case | Candidates | Choose | Verification |
|---|---|---|---|
| cluster available | Search terms in the upper's cluster · intent that consist only of an item name, with no brand or dictionary word | **Only other names for the same thing** (`synonyms.pick`) | finder results as-is + code-generated strings via keyword_info measurements |
| no cluster | The list above + spellings the LLM comes up with (`synonyms.analyst` · e.g. pilates) | Same | Only those with keyword_info measurements remain (build) |

- ○ 런닝화 · 러닝 슈즈 · 조깅화 (for 러닝화) · pilates (for 필라테스) · yoga (for 요가) · 홈트레이닝 (for 홈트 (home training))
- × Higher/lower-level items (밥솥 (rice cooker) ≠ 전기압력밥솥 (electric pressure rice cooker)) · different items (테니스화 → section 1 comparison set) · words with a place attached (헬스장 (gym)) · words with an intent word attached (필라테스 1:1)
- `synonyms.intent` (putting same-intent expressions into the target) is not used in v5. Intent expressions go to section 2's topic and search-for bundles.

## M4. Discovering section 1 comparison-set candidates (code)

| Mode | Candidate = | Discovered in |
|---|---|---|
| entity | B′ from **another brand B′ + I\*** | upper cluster first → upper intent → analyst |
| category | **Other item names in the searched-object slot (last fragment) of the seed cluster** (v5.10 · `시드 cluster 등장 N` ≥ 2) + other item names ending in H + **M5-0 substitute/adjacent candidates (seed.near · v5.11)** · each candidate gets a proximity grade (가까움 (close) / 근거 약함 (weak evidence) / 영역만 (same domain only)) | **seed cluster** → upper cluster → upper intent → (cluster of another upper term) → near (lm_intent_near) → analyst |

Each candidate carries its **source (cluster/intent/analyst)** and **finder appearance rank**, and the source is shown in the report's comparison-target table.

**method-v5.10 · Why the seed cluster is used first.** The upper-term cluster comes back empty when the upper term overlaps with other meanings (후드티 (hoodie) → 상의 (tops): 상의하다 (to consult) · 상위어 (hypernym) get mixed in, 0 same-level candidates).
If Claude fills that gap with items it knows, the comparison set becomes a judgement rather than data (measured: 가디건 (cardigan) · 반팔티 (short-sleeve tee) appear once in the 후드티 cluster, 맨투맨 (sweatshirt) 53 · 후드집업 (zip-up hoodie) 84).
Other items in the seed cluster = items people searched together with the seed, so they are direct evidence of 'the same market'.

## M5-0. Close market = substitute/adjacent (method-v5.11 · category)

Section 1's question is "Did the whole market move together?". Here **market = the items people weigh side by side for the same demand**, not the same domain (beauty) or the same store shelf.
The comparison market for 향수 (perfume) is not 샴푸 (shampoo) · 마스크팩 (sheet mask) (same beauty domain) but 바디미스트 (body mist) · 헤어미스트 (hair mist) (same purpose · different form).

| Grade (code · `NEAR`) | Condition | Use |
|---|---|---|
| **가까움** (close) | Any one of: seed cluster appearances ≥ 2 · **co-mentions** ≥ 2 (seed item and candidate in one search term: '향수 바디미스트') · **comparison mentions** ≥ 1 ('바디미스트 향수 차이' · '향수 대신 바디미스트') | Choose the comparison set from here first |
| 근거 약함 (weak evidence) | None of the evidence above (LLM candidates · items from the upper-term finder) | Only when close candidates are insufficient · if chosen, M5-7 confirmation |
| 영역만 (same domain only) | Same-domain candidates carried over from narrowing a broad seed (scope siblings) · no evidence | Last resort · if chosen, M5-7 confirmation |

**If there are fewer than 4 close candidates (the ⚠ line in classify.md) — the LLM proposes substitute/adjacent candidates.**
1. Write `near` in seed.json (4–8 entries). There are only two selection criteria; write which one applies in `why`:
   - **Substitute** — an item that fulfils the same purpose in a different form (향수 → 바디미스트 · 헤어미스트 · 퍼퓸 오일 / 선크림 (sunscreen) → 선스틱 · 선쿠션 / 러닝화 → 워킹화 (walking shoes))
   - **Adjacent** — an item chosen together with it or bought alternately in the same situation (향수 → 섬유향수 (fabric perfume) / 필라테스 → 요가 · 홈트)
   - × Merely the same domain (향수 → 샴푸) · a kind of the seed (향수 → 니치 향수 · 고체향수 → M3a/3) · a higher level · a different object (향수 → 디퓨저 (diffuser) = scent for a space · if the object differs, skip)
   ```json
   "near": [{"name": "바디미스트", "variants": ["바디미스트", "바디 미스트"], "why": "대체 · 몸에 향을 입히는 같은 목적, 가벼운 형태"},
            {"name": "헤어미스트", "why": "대체 · 머리에 향"}]
   ```
2. Query all `near` names at once with intent_finder, receive the result as `lm_intent_near.json` (1 MCP call), and rerun propose.
   The code counts co-mentions and comparison mentions in that result and re-grades. If a name is missing from the query result, its source is analyst.
3. If a co-mention like '향수 샴푸' is a case where **one side is an attribute of the other** (향 좋은 샴푸 (good-smelling shampoo)), it is not adjacency evidence — skip under M5-1.

## M5. [Choice 2] Choosing the section 1 comparison set

1. **Same position and same level only.** entity = brands selling the same item, category = other items in the same parent category. Synonyms (M3a) are not part of the comparison set.
   Do not include a comparison target that is a lower level contained within another target (필라테스 → 요가 · 홈트 · 헬스 ○ / 근력 운동 (strength training) · 타바타 (Tabata) · 스트레칭 (stretching) are workout methods inside 홈트, so ×).
   Do not mix items (운동화 · 요가매트 (yoga mat) · 레깅스 (leggings)) with activities (필라테스 · 요가).
2. **(v5.11) The 가까움 grade first**, within it **by seed cluster appearances + co-mentions, highest first (category)**, then the upper-term cluster, then the intent source in order of appearance rank. Even seed cluster candidates must follow M5-1 —
   a kind of the seed (후드 · 후디 → M3a synonym candidates) · a higher level (티셔츠 · 집업 ⊃ 후드집업) · brands · purpose words (제작 (custom-made) · 세트 (set)) · other meanings (영화 (movie) · 다시보기 (rewatch)) go into skip with the rule number.
3. **Target 6 · maximum 10 (v5.7).** If cluster candidates alone give 6 or more, take up to the top 10 by rank from the cluster. 10 is only a ceiling — if there are no same-position, same-level candidates, do not fill up to it.
   **v5.10 · Do not fill up to 6 with weak-evidence candidates.** If there are 4 or more same-level candidates with seed cluster evidence (appearances ≥ 2), use only those.
4. With 3 comparison targets a verdict is still produced, but leave-one-out (the check that drops one at a time) runs only with 4 or more — the report says so.
4a. **(v5.10) If fewer than 4, run cluster once more with another upper term.** Call cluster_finder with an upper term whose meaning does not get mixed (for 후드티 → a neighbouring item that appears often in the seed cluster, such as 맨투맨 · 티셔츠), put `lm_cluster_alt.json` into `--cluster`, and rerun propose.
5. **(For category, from v5.11 on, M5-0 replaces this step — if fewer than 4 close candidates, substitute/adjacent candidates.)** entity is unchanged: **only if there are still fewer than 3, the LLM proposes candidates and verifies them with intent_finder** (v5.10 · previously: when finder candidates did not reach 6) (`lm_intent_analyst.json` → source `analyst` · v5.7: fewer than 3 → fewer than 6). Do not directly add a name that is in neither the finder candidate list nor the verification result. Supplemented names remain as-is in picks.external.pick (source analyst).
6. **Size threshold (code · v5.7).** build drops from the verdict and the report any comparison target whose last-12-month search volume is under 5% of the analysis target (small bundles show large growth rates and pull the baseline up). build prints `규모 미달 제외 ○○` (excluded for insufficient size) · recorded in facts.md. So there is no need to deliberately include very small brands when choosing.
7. **(v5.11) Confirmation — M5-7.** If any chosen comparison target is '근거 약함' or '영역만', or there are fewer than 4 close ones, show it to the user **once only**, before calling keyword_info:
   "비교 시장을 이렇게 잡았습니다: 바디미스트(함께 언급 3) · 헤어미스트(근거 약함) · 샴푸(같은 뷰티 영역일 뿐)" (We set the comparison market as: …) + buttons (ask_user_input): `이대로 진행` (proceed as is) / `가까운 것만 (n개)` (close ones only (n)) / `직접 고치기` (edit myself) (wording and buttons in the user's language · item names exactly as the search terms).
   If there are 4 or more close ones only, proceed without asking and state the comparison market and evidence in one line in the chat answer. build also warns about any comparison target that is not '가까움' with `⚠ 가까운 시장 근거 없는 비교 대상` (comparison target without close-market evidence).

## M5a. [Choice 2-1] Choosing representative spellings of comparison targets (method-v5.6 · optional — it was required in v5.2–5.5)

> v5.6 · Section 1 is for comparison, so a representative spelling is enough (measured on 나이키 런닝화: brand × 런닝화 · 러닝화 is 96–99% of the bundle search volume, verdict unchanged). In brand/product mode, use only the combinations of the chosen spellings (English etc.) × the representative item names, and do not mix in all item-side synonyms (조깅화 · 러닝 슈즈). plan does not stop even if nothing is recorded.

Just as the target narrows down its same-meaning names via M3a, **make the same judgement for every chosen comparison target.** If only the target is expanded and the comparison set is left with one representative name, only the target gets wider and the comparison is skewed.

| Candidates (code · classify.md) | Choose | Verification |
|---|---|---|
| Candidates with overlapping names — a one-word spelling, or also appearing in a joined form (호카 ⊂ 호카오네오네 · 뉴발 ⊂ 뉴발란스 · 홈트 ⊂ 홈트레이닝) | Only other names for the same thing, `synonyms.pick` | finder results as-is + code-generated strings via keyword_info measurements |
| English-spelling candidates (hoka · brooks · yoga) — the code does not know which target they belong to | Only the ones matching each target, `synonyms.pick` | Same |
| Known spellings not among the candidates (adidas · asics) | `synonyms.analyst` | Only those with measurements remain (build) |

- ○ Abbreviation / full name (뉴발 · 호카오네오네) · English (hoka · yoga) · spacing (온 러닝) · alternative spelling (홈트레이닝)
- × Name + product name (아디다스 제로 · 호카 본디) · attribute (뉴발란스 4e) · place (헬스장) · single-letter-like English (on — mixes in a generic word)
- Record: `{"name": "호카", "synonyms": {"pick": [...], "analyst": [...], "skip": {"호카 본디": "M5a 제품명"}}}` · if there is no other spelling, `{"none": "이유"}`.
  If nothing is recorded, only the single name is used (v5.6). On the item side, only the representative names (seed item + first M3a synonym) (entity).
- Spellings that differ only in spacing are the same measurement record, so they are counted once (plan · build).

## M6. Section 1 comparison-set bundles = same rules as the target (code)

Bundle each chosen B′ (or sibling item I′) with the same rules as M3 (entity: B′\* + I\* + generic words). The rules must match the target's, or the comparison is skewed.
- **method-v5.1 · entity also mixes in same-meaning names.** If the target is `나이키 × {런닝화·러닝화·러닝 슈즈·조깅화}`, the comparison set is `아디다스·adidas × {the same item names}`.
  plan builds the strings B′ spellings (variants) × I\* (seed item + M3a synonyms), passes those not in the finder results to `verify`, and keeps only those with keyword_info measurements.
  The target follows the same rule — all B\* spellings (나이키 · nike) × I\*. Other spellings of comparison brands are chosen via M5a.
- **method-v5.6.2 · Coverage check.** For each section 1 bundle, also measure `broad` (the finder strings consisting only of a spelling + item name + generic words · in any order + all spelling × item name combinations); if representative-spelling search volume ÷ broad is under 90%, flag '대표 표기 커버 낮음' (low representative-spelling coverage). For the analysis target, broad is the detailed bundle (`plan.target` · M3).
- **method-v5.6 · M6-lite (entity).** Instead of the rule above, section 1 uses only the exact combination strings `spelling × 2 representative item names (런닝화 · 러닝화)` — for both the comparison brands and the analysis target (`plan.marketTarget`). All combinations are verified with keyword_info. The detailed bundle (M3 · `plan.target`) is used only for the coverage check.
- **method-v5.9 · M6-lite (category).** Category mode also uses only `up to 2 representative names` in section 1 (spacing variants are the same measurement record, counted once).
  Analysis target = seed item + the first name chosen in M3a (`synonyms.pick` → `analyst` order) · comparison target = name + the first other spelling from M5a (`synonyms.pick` → `analyst` order).
  The detailed bundles found by the finder are used only as `broad` for the coverage check (warn if representative names ÷ detailed < 90%). The detailed bundle (M3 · `plan.target`) is not shown in the report.
  **When writing same-meaning names into picks, list them by search volume, largest first** (measured on 후드티: 후디 > hoodie > 후드 티셔츠 · putting 후디 first gives 93.8% coverage).
- method-v5 · Comparison targets too are **only the name and its spelling variants** — write them in `external.pick` as `{"name": "요가", "variants": ["요가", "yoga"]}`.
  Spellings not in the finder results are passed by plan to `verify` and kept if they have keyword_info measurements (same as the target's analyst). The verification result is printed as one line at the bottom of the report.

## M7. Discovering section 2 internal candidates (code)

| Mode | Part = | Candidates |
|---|---|---|
| entity | **Product line P** | Residual words that appear with B\* 2 or more times · and appear with the seed item at least once |
| category | **Topics** (form · ingredient · audience · class format, etc.) · **search-for bundle** (region names · brand names · nearby) | Attribute/residual words that appear with the item (2 or more times · excluding fixed intent words) · residual words before the item |

## M8. [Choice 3] Choosing section 2 internal parts

- **entity — product lines are only proper names the brand gave.** ○ 페가수스 · 보메로 · 트윈프레셔 · 락토핏 골드 / × 미니 (mini) · 저당 (low-sugar) · 스텐 · 신형 (new model) · 6인용 · 여성 · technology names (에어 (Air) · 줌x (ZoomX) · 플라이니트 (Flyknit))
  - Names made of a function, material, or shape (저당밥솥 (low-sugar rice cooker) · 무쇠 (cast iron)) are treated as generic words and excluded. Spelling variants of the same thing (줌플라이/줌 플라이) form one line.
  - Generation and sub-model names (페가수스 41 · 보메로 플러스) are **not chosen as separate lines** — they go in as search terms inside the line, and new ones show up with a new badge (v5.1).
- **category — topics (`topics`) and the search-for bundle (`catchall`).** Topics are only the axes along which demand splits within the category (필라테스: 기구 (apparatus) · 매트 (mat) · 리포머 (reformer) · 캐딜락 (Cadillac) · 바레 (barre) · 재활 (rehab) · 임산부 (pregnancy) · 산후 (postpartum) · 소도구 (small props) · 수업 방식(1:1·그룹) (class format: 1:1 / group)).
  Intent words such as recommendation, ranking, and price already have fixed bundles, so do not choose them as topics. Name topics in marketer language (place exploration → 근처·학원 검색 (nearby/studio search) · class/lesson → 수업 방식(1:1·그룹)).
  - `pick` for choosing brands separately (→ the '브랜드명 검색' (brand-name search) fixed bundle, placed first) is **not used in v5** — searches with price or certification attached get pulled into the brand, and only the few chosen brands get in. The search-for bundle collects all brands.
- Up to 8, in order of appearance count, highest first. **If fewer than 3, verify LLM candidates with intent_finder** (`lm_intent_analyst_internal.json`) and supplement.

## M9. Building section 2 internal bundles (code)

**entity — product lines (method-v5.1 · the same bundle as the search purposes in category mode · same table, bump chart, and expansion)**
- Search terms containing line P. Generation numbers and sub-model names are allowed; terms with explore/attribute modifiers or `use` · `howto` · `channel` · `community` · `info` attached are excluded. Terms containing two lines go into neither.
- **Spellings with and without the brand name go into one line** ('나이키 페가수스 41' + '페가수스 41'). Spellings without the brand are used only if they come from the seed-side intent results (seed · internal · sku · brand) — this blocks same-named products mixed into other brands' results.
- **There is no sub-SKU level (v5.1).** Expanding a line shows its search terms ordered by the last 12 months (top 10 + show all), and the '가장 크게 변한 검색어' (search term with the largest change) column shows why the line changed — the same as category mode.
- Exclude a different item with the same name (if 'B + X' appears together with the seed item < 20% of the time → it is a line of a different item).

**category — intent bundles**
- Only search terms containing the item (I\*) that have none of `use` · `howto` · `channel` · `community` · `info` · `year`. Search terms with only the item name (+ generic words) are the analysis target itself, so they are not included.
- Each search term goes into only one bundle, in this order: (브랜드명 검색 · not used in v5) → **topics** (in chosen order) → **계급도·순위** → **추천·입문** → **비교·후기** (comparison/review) → **가격** (price) → **신제품** (new product) (code `INTENT_BUNDLES`) → **search-for bundle** (catchall · last). If it fits nowhere, do not include it; only record the count.
- So ‘이모란 필라테스 가격’ goes to 가격, and ‘이모란 필라테스’ goes to 브랜드명 검색.

**Common — bundles are not truncated.** finder appearance ranks cannot be compared across files, so truncating can drop large keywords.

## Record (picks.json · v5.2 — external.pick uses the M5a format)

```json
{
  "synonyms": {"pick": ["런닝화", "러닝 슈즈"], "analyst": ["달리기 신발"], "skip": {"테니스화": "M3a 다른 품목"}},
  "external": {"pick": [{"name": "아디다스", "synonyms": {"analyst": ["adidas"], "skip": {"아디다스 제로": "M5a 제품명"}}},
                        {"name": "아식스", "synonyms": {"analyst": ["asics"]}}], "skip": {"아디다스 운동화": "M5-1 위치 다름"}},
  "internal": {"pick": ["페가수스", "보메로"], "skip": {"여성": "M8 속성", "에어": "M8 기술명"}}
}
```

internal for category (v5 · final version for 필라테스):

```json
{"pick": [],
 "topics": [{"name": "수업 방식(1:1·그룹)", "variants": ["1:1", "pt", "개인레슨", "그룹", "수업", "체험", "레슨", "클래스"]},
            {"name": "기구", "variants": ["기구", "바렐"]}, {"name": "매트", "variants": ["매트"]}, {"name": "바레", "variants": ["바레"]},
            {"name": "임산부·산후", "variants": ["임산부", "산전", "산후"]}, "..."],
 "catchall": {"name": "지역·브랜드 검색", "split": true,
              "subNames": {"words": "근처·학원 검색", "region": "지역명 검색", "brand": "브랜드명 검색"},
              "variants": ["근처", "학원", "스튜디오", "센터"],
              "exclude": ["다이어트", "요가", "양정원", "…인물·일반어·한 글자"], "regions": ["노원", "강남", "…"], "notRegion": ["바시", "루시"]},
 "skip": {"강사": "M8 직업·자격"}}
```

For topic type (ask.md topic A), use `"unit": "방법"`.

`ds_classify.py plan` builds plan.json from picks.json. **Do not write plan.json by hand.** The reasons for each choice are printed as-is in "키워드셋 분류 근거" (keyword-set classification rationale) at the bottom of the report.


## method-v5 · Section 2 intent change 'search-for bundle' (catchall)

Instead of a separate brand-name bundle, searches looking for a place to go or a place to buy can be merged into one bundle (picks.internal.catchall).

```json
"catchall": {"name": "지역·브랜드 검색", "subNames": {"words": "근처·학원 검색", "region": "지역명 검색", "brand": "브랜드명 검색"}, "variants": ["근처", "학원", "스튜디오", "센터"],
             "exclude": ["다이어트", "요가", "양정원", "..."], "regions": ["노원", "강남", "..."], "notRegion": ["바시", "루시"]}
```

- Among search terms not caught by another topic or fixed intent (price, recommendation, etc.), those with only 1–2 proper names **before the item** (region · studio), or those containing variants (근처 (nearby) · 학원 (studio/academy)).
  Words attached after the item (필라테스 양말 (Pilates socks) · 효과 (effect)) are not included. People's names and generic words go in exclude.
- The code splits it into 3: search-for expressions (variants) / region names (regions, or ending in 역 · 동 · 구 · 시 · 지구, excluding notRegion) / brand names (the rest). With `"split": true` each becomes an independent search purpose (recommended default); otherwise they are sub-bundles of one bundle.
- A brand search with price attached (이모란 필라테스 가격) goes to the 가격 bundle (the search-for bundle is last in order).
