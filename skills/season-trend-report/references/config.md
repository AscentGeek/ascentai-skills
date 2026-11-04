# config.json — relevance filter and theme rules

These are the two things you decide. Code makes the numbers. Filters and themes apply **after** the keyword_info lookup,
so changing them never calls MCP again.

```json
{
  "seed": "후드티",
  "gl": "kr",
  "lang": "kr",
  "collected": "2026-10-16",
  "rel": "(후드 ?티|후디|hoodie|hoody)",
  "exc": "(영어|일본어|뜻|유래|그리기|그림|일러|도안|짤|프사|셀카|뒷모습|스킨|로블록스)",
  "themes": [
    ["lux",    "명품·컨템포러리", "(발렌시아가|구찌|프라다|크롬하츠|아미|ami |메종|우영미|명품)"],
    ["street", "스트릿·디자이너", "(스투시|슈프림|예일|브라운 ?브레스|아이앱|iab|커버낫)"],
    ["sport",  "스포츠·아웃도어", "(나이키|아디다스|뉴발란스|노스페이스|스파이더(?!맨)|알로|살로몬)"],
    ["style",  "핏·소재·디자인", "(오버핏|크롭|반팔|기모|니트|집업|와플)"],
    ["color",  "색상",            "(회색|검정|흰|블랙|화이트|버건디|노란|분홍|네이비)"],
    ["season", "계절·날씨",       "(가을|겨울|여름|봄|날씨|온도)"],
    ["compare","추천·브랜드·가격", "(추천|브랜드|순위|가성비|가격|싸게)"]
  ],
  "skip_month": ["후드티"]
}
```

| Key | Meaning |
|---|---|
| `seed` | The seed query (report cover) · in the market's language, exactly as searched |
| `gl` | Target market `kr` · `jp` · `us` (Step 0) |
| `lang` | Report language `kr` · `jp` · `us` (Step 0) · decides UI labels and the number units in facts.md |
| `collected` | Collection date `YYYY-MM-DD` (today) |
| `min_total` | (optional) Analysis floor — queries whose 4-year total is below this are dropped from every tab. Default 1000. Leave it unchanged as a rule |
| `rel` | Regex of queries to **keep** (case-insensitive). The seed and its spelling variants and other-script spellings. Empty keeps everything |
| `exc` | Regex of queries to **drop**. Other meanings · searches unrelated to the interest |
| `themes` | A list of `[id, name, regex]`. A query goes **only into the first theme it matches, top to bottom** |
| `skip_month` | Queries to leave out of the monthly seasonal keywords (default: the bare seed) |

The regexes match the market's queries, so write them **in the market's language** (`gl`).
Theme **names** appear in the report, so write them **in the report language** (`lang`).
With `gl kr · lang us`, the regex is Korean (`(오버핏|크롭)`) and the name is English (`Fit · material · design`).

## 1. Relevance filter (rel / exc)

- **rel** = the rule that keeps only queries containing the seed. Include spacing (`후드 ?티`) · other scripts (`hoodie`) · abbreviations.
  For a brand seed you may add the brand's flagship product names (e.g. `홍삼` → `정관장|에브리타임|한삼인`). Widening it lets other
  items in, so check with `off.txt`.
- **exc** = searches that match rel but are not the interest. Common types:
  - word meaning · etymology: `뜻|유래|영어|일본어` (jp `意味|英語` · us `meaning|definition|translate`)
  - drawing · images: `그리기|그림|일러|도안|짤|프사|셀카` (jp `イラスト|描き方|画像` · us `drawing|clipart|png`)
  - games · virtual items: `스킨|로블록스` (us `roblox|skin`)
  - same letters, another meaning: (홍삼) `축제|스파|호텔|화장품|샴푸` · (텀블러) `tumblr`
- After the build, look at the top 50 of `off.txt`. If something relevant was dropped, fix rel/exc.
- Keep `rel` limited to the seed's spellings where possible — the build treats a query left empty after removing the seed and
  `rel` matches as "bare seed" and leaves it out of the unclassified check.

## 2. Theme rules

A theme is a group of "what people attach to the seed when they search". It becomes a row of the seasonal calendar by theme
and a group in the last-12-month trends by theme.

**Count and size**
- 8–15 themes. 10 or more queries per theme is preferred. Merge ones that are too small.
- Aim for unclassified queries (in no theme), not counting the bare seed query and its spelling variants, to be **10% or less** of the
  last-12-month volume and **20% or less** of the queries. The build prints the count and warns above either.

**Order (a query goes only into the first matching theme)**
1. **Specific names first** — brand clusters (luxury · street · sports · fast fashion), product forms (stick · extract · capsule), people (celebrities), groups and makers
2. **Attributes** — fit and material · colour · target (gender · age)
3. **Use and care** — outfits · straps, folding, sizes · how to take, storage
4. **Season and weather**
5. **Broad objects last** — recommendation · comparison · ranking · price · where to buy

e.g. "아미 후드티 사이즈" → luxury, "스투시 후드티 코디" → street. Because brand themes come first, the outfit and size themes only get queries without a brand.
Keep this order so that a broad theme like "recommendation" does not take brand searches.

**Regex cautions**
- Watch short strings that also catch other meanings. `스파이더` → `스파이더(?!맨)`, `정환` → `(?<!김)정환`, `설` → `설$|설 |설날`
  (us `\\bnike\\b` style word boundaries for short brand names).
- Put both scripts in brand themes (`아미|ami `, `아이앱|iab` · jp `ナイキ|nike`).
- After the build, skim each theme's top queries in facts.md to check that no other meaning slipped in.

**Names**
- Join 2–3 words with `·` (`명품·컨템포러리`, `끈·접기·사이즈` · us `Luxury · contemporary`). They appear in the report as is.
- The id is short English (`lux`, `street`).

## Example · 홍삼 (product-group seed · gl kr · lang kr)

```json
"rel": "(홍삼|인삼|정관장|에브리|everytime|한삼인|진생|kgc|공진단|경옥고|산삼|수삼|흑삼|녹용|침향)",
"exc": "(축제|스파|사우나|호텔|족욕|온천|찜질|게임|샴푸|비누|화장품|설화수|삼계탕|영어|중국어)",
"themes": [
  ["kids",   "어린이·청소년 홍삼", "(어린이|키즈|아이|아기|유아|청소년|수험생|학생|주니어|홍이장군)"],
  ["gift",   "선물·명절",         "(선물|세트|추석|설$|설 |설날|명절|어버이|부모님|쇼핑백|포장)"],
  ["body",   "체질·부작용·질환",  "(부작용|체질|임산부|고혈압|혈압|당뇨|갑상선|갱년기)"],
  ["effect", "효능·성분",         "(효능|효과|성분|사포닌|면역|이뮨|다당체|피로)"],
  ["howto",  "먹는 법·만들기·보관", "(먹는|복용|시간|공복|만들|만드는|달이|오쿠|보관|유통기한)"],
  ["buy",    "가격·구매처",       "(가격|최저가|할인|구매|면세|코스트코|쿠팡|px|군마트|다이소|매장)"],
  ["compare","추천·비교·순위",    "(추천|비교|순위|브랜드|종류|차이|디시)"],
  ["stick",  "스틱·포",           "(에브리 ?타임|everytime|스틱|\\d+ ?포|짜먹|데일리)"],
  ["extract","홍삼정·농축액·진고", "(홍삼정(?!과|환|차)|농축액|진고|진액|공진단)"],
  ["drink",  "홍삼원·음료·드링크", "(한뿌리|홍삼원|음료|드링크|톤|즙|달임액|홍삼차)"],
  ["snack",  "절편·캔디·젤리",    "(절편|캔디|사탕|젤리|양갱|정과|꿀)"],
  ["pill",   "캡슐·환·분말",      "(캡슐|환$|환 |(?<!김)정환|분말|가루|앰플)"],
  ["root",   "인삼·수삼·뿌리삼 (원물)", "(인삼|수삼|뿌리|6년근|산삼|흑삼|금산|풍기|강화)"]
]
```

## Example · hoodie (category seed · gl us · lang jp)

```json
"seed": "hoodie", "gl": "us", "lang": "jp",
"rel": "(hoodie|hoody|hooded sweatshirt)",
"exc": "(meaning|drawing|roblox|clipart|png)",
"themes": [
  ["brand", "ブランド",       "(nike|adidas|essentials|carhartt|champion|gap)"],
  ["style", "フィット・素材", "(oversized|cropped|zip|fleece|heavyweight)"],
  ["who",   "対象",           "(\\bmen\\b|mens|women|womens|kids|boys|girls)"],
  ["buy",   "価格・購入先",   "(cheap|sale|amazon|walmart|target|price)"]
]
```

Regexes inside JSON double the backslash (`\\d`).
