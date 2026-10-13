# plan.json schema (v5.6)

> plan.json is created by `ds_classify.py plan`. **Do not write it by hand.** What goes into it is decided by `keyword-method.md` (method-v4).
> This document is a structural reference only.

```json
{
  "seed": "나이키 러닝화",
  "mode": "entity",                       // entity (brand/product) | category
  "modeReason": "연관 검색어 1000개 중 '나이키' 포함 84.0% — 한 브랜드의 제품·라인·사용 검색이 대부분이다",  // written by check
  "method": "method-v4",
  "upper": "러닝화",                       // finder input for 1 (comparison set · same-meaning names)
  "itemVariants": ["러닝화", "런닝화", "조깅화"],  // I* = seed item + same-meaning names
  "target":   {"name": "나이키 러닝화", "keywords": ["나이키 러닝화", "나이키 런닝화", "나이키 조깅화"],
               "verify": ["나이키 조깅화"]},   // detailed bundle of the analysis target · used only for the cover check (not a report section) · verify = strings made from same-meaning names, verified with keyword_info
  "marketTarget": {"name": "나이키 런닝화", "keywords": ["나이키 런닝화", "나이키 러닝화", "nike 런닝화", "nike 러닝화"],
                   "verify": ["..."], "items": ["런닝화", "러닝화"], "broad": ["..."]},   // v5.6 entity · broad = detailed group for the cover check (v5.6.2) · the analysis-target row of 1 (if missing, build uses target)
  "external": [{"name": "아디다스 러닝화", "keywords": ["...", "adidas 러닝화", "아디다스 조깅화"], "src": "cluster",
                "verify": ["adidas 러닝화", "아디다스 조깅화"]}],   // v5.1 entity · B′ spelling × I* verification strings · src: cluster | intent | analyst
  "internal": {"unit": "제품 라인", "parts": [{"name": "페가수스", "keywords": ["나이키 런닝화 페가수스", "나이키 러닝화 페가수스 41", "..."]}]},
               // v5.1 · no sub-SKUs (skus) — the screen is the same as the search purposes in category mode
               // category: {"unit": "의도", "parts": [{"name": "브랜드·모델 탐색", ...}, {"name": "추천·입문", ...}], "unassigned": 12}
  "picks": {"synonyms": {}, "external": {"pick": [], "skip": {}}, "internal": {"pick": [], "skip": {}}},
  "otherLines": ["식기세척기", "..."]      // other item lines with the same name, filtered out by M9
}
```

The LLM writes only two files.

| File | Content | Rule |
|---|---|---|
| `seed.json` | seed · mode · brand (spelling variants) · item (seed item) · upper (parent term) · heads (top-level category heads) · itemOptional — modeReason is written by check | M1 |
| `picks.json` | pick and skip (name → rule number and reason) for synonyms (similar-intent picks · analyst) · external (comparison group for 1) · internal (lines / brands + topics for 2) | M3a · M5 · M8 |
