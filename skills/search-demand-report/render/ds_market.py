#!/usr/bin/env python3
"""ds_market.py · 시장(gl)별 분류 사전 · 패턴 · 신호 · 기준값 (method-v5.12).

키워드셋 분류(ds_classify)와 시드 좁히기(ds_scope)는 검색어에 붙은 말이 무엇인지(탐색 · 속성 · 구매처 …)를
사전으로 판정한다. 사전은 시장의 검색 언어를 따라야 하므로 시장마다 한 벌씩 둔다.
seed.json · scope.json 의 `gl` 로 고르고, 없으면 kr 이다.

  kr · method-v5.11 까지의 사전을 그대로 옮겼다 (값을 바꾸지 않았다)
  jp · us · 신설. 기준값(scope)은 kr 실측값을 임시로 쓴다 — 시장별 실측 보정 전이다

시장별로 다른 동작:
  substr   · 사전어를 조각 안의 부분 문자열로도 찾는가. kr · jp 는 붙여 쓰는 검색어가 많아 찾는다
             ('4디시' · 'ランニングシューズおすすめ'). us 는 단어 단위로만 찾는다 ('top' ⊂ 'laptop' 오탐 방지)
  foreign  · 이 시장 검색어에 섞이면 오입력으로 보는 문자 (kr: 가나 · jp: 한글 · us: 한글·가나·한자)
  latin    · 비교 대상별 유사의도 후보에 영문 표기 풀을 따로 보일지 (us 는 모두 영문이라 끈다)

알려진 한계 · us 는 여러 단어 브랜드(new balance · under armour · on cloud)가 많다. 분류는 띄어쓰기 단위라
브랜드의 한 조각이 사전어와 겹치면 잘못 읽는다. 그래서 겹치기 쉬운 말(new · under · on)은 us 사전에 넣지 않았다.

표준 라이브러리만 사용한다.
"""

import re

MARKETS = ("kr", "jp", "us")

# ─────────────────────────── kr (method-v5.11 그대로) ───────────────────────────

_KR = {
    "dict": {
        "explore": ["추천", "가격", "비교", "가격비교", "최저가", "순위", "랭킹", "종류", "라인업", "계급도", "등급", "티어", "신상",
                    "신제품", "최신", "최신형", "후기", "리뷰", "좋은", "가성비", "인기", "브랜드", "베스트", "best", "신메뉴", "메뉴", "맛", "맵기"],
        "use": ["사용법", "사용", "청소", "세척", "고장", "as", "a/s", "a", "s", "서비스센터", "서비스", "고객센터", "센터", "패킹", "고무패킹",
                "부품", "내솥", "분해", "수리", "에러", "수명", "교체", "설명서", "사용설명서", "소리", "뚜껑", "세탁", "수선", "초기화", "설정",
                "끈", "신발끈", "밑창", "등록", "단종", "출시일", "환불", "반품", "대리점", "음소거", "냄새", "자동세척", "e01",
                "as센터", "전원", "에러코드", "홈페이지", "본사", "음성", "취사", "모드", "해제", "번호", "모델명", "안됨", "안되요",
                "조절", "분리", "점검", "버튼", "잠금", "버튼잠금", "끄기", "커버", "취소", "위치", "배터리", "깜빡임", "열림", "필터"],
        "howto": ["만들기", "레시피", "삶기", "찌기", "하는법", "요리", "시간", "밥하기", "밥하는법", "코디", "방법", "삶는법", "찌는법", "가루", "시즈닝"],
        "attr": ["사이즈", "발볼", "여성", "남성", "여자", "남자", "여성용", "남성용", "키즈", "주니어", "아동", "어린이", "블랙", "화이트",
                 "핑크", "그레이", "실버", "네이비", "베이지", "스텐", "스테인리스", "스테인레스", "올스텐", "풀스텐", "ih", "카본", "미니",
                 "소형", "대형", "대용량", "업소용", "트레일", "고어텍스", "와이드", "입문", "입문용", "초보", "데일리", "쿠션", "안정화",
                 "가벼운", "편한", "마라톤", "장거리", "겨울", "여름", "평발", "로드", "저가", "저렴한", "싼", "비싼", "일반",
                 "신형", "구형", "프리미엄", "고급", "1인", "2인", "무게", "형광", "흰색", "검정", "레이싱화", "플러스",
                 "스니커즈", "우먼스", "맨즈", "gtx", "색상", "사이즈표", "경량", "일상", "일상용", "입문자", "입문자용",
                 "압력", "전기", "보온", "전기압력", "ih전기압력", "열판", "스텐레스", "자취", "캠핑", "식당", "옛날",
                 "순살", "반반", "반마리", "한마리", "뼈", "콤보", "윙", "다리", "닭다리"],
        # method-v3: 품목을 넓게 부르는 말 — 시드 품목명과 함께 쓰이면 같은 대상을 부르는 말로 본다 ('나이키 운동화 런닝화')
        "generic": ["운동화", "신발", "슈즈", "런", "러닝", "런닝", "달리기", "달리기용"],
        "channel": ["쿠팡", "다나와", "하이마트", "코스트코", "아울렛", "매장", "공식몰", "홈쇼핑", "몰", "할인", "세일", "abc마트",
                    "11번가", "g마켓", "네이버", "백화점", "다이소", "이마트", "렌탈", "중고", "리퍼", "리퍼브", "당근"],
        "community": ["디시", "클리앙", "더쿠", "뽐뿌", "나무위키", "위키", "블로그", "디시인사이드", "카페", "갤러리"],
        "info": ["뜻", "영어로", "원리", "차이", "역사", "주가", "채용", "로고", "폭발", "광고", "매출", "점유율", "시장", "이란",
                 "개념", "구조", "전기세", "소비전력", "금지"],
    },
    "rx": [("year", r"^20\d\d(년)?$"), ("attr", r"^\d+(인용|인분|인|구)$"), ("attr", r"^\d+$"),
           ("attr", r"^\d+(\.\d+)?기압$"), ("attr", r"^\d+만원대?$")],
    "attrSub": ["사이즈", "인용"],   # 붙여 쓴 조각 안에 들면 속성 ('3사이즈' · '6인용밥솥')
    "foreign": r"[぀-ヿ]",   # 일본어가 섞인 오입력 검색어
    "substr": True,
    "latin": True,
    "intentBundles": [
        ("계급도·순위", ["계급도", "순위", "랭킹", "티어", "등급", "top"]),
        ("추천·입문", ["추천", "입문", "입문용", "입문자", "입문자용", "초보", "베스트", "best", "인기", "가성비"]),
        ("비교·후기", ["비교", "후기", "리뷰"]),
        ("가격", ["가격", "최저가", "가격비교", "저렴한", "저가", "싼", "만원대"]),
        ("신제품", ["신상", "신제품", "최신", "최신형", "신형"]),
    ],
    "buyWords": ["가격", "최저가", "할인", "구매", "파는곳", "판매", "쿠팡", "추천", "비교", "순위", "브랜드", "종류", "후기", "가성비"],
    "howWords": ["방법", "식단", "레시피", "효과", "원리", "하는법", "만들기", "운동", "브이로그", "전후", "성공", "실패", "기간", "자극", "짤"],
    # M5-0 비교 언급 · 시드 품목과 후보가 함께 든 검색어에 붙으면 대체재 근거 ('바디미스트 향수 차이')
    "cmpWords": ["차이", "비교", "vs", "대신", "아니면", "중에", "어떤게", "뭐가"],
    "regionSuffix": r"(역|동|구|시|지구|사거리|입구|대)$",
    # 2026-10-06 실측(kr): 뷰티 head 0.27 · token 0.50 / 쿠션 0.71·0.83 · 선크림 0.77·0.99 · 마스크팩 0.78·0.92 · 향수 0.69·0.93 · 앰플 0.84·0.95 · 클렌징폼 0.68·0.76
    "scope": {"headMax": 0.45, "tokenMax": 0.70, "calibrated": True},
}

# ─────────────────────────── jp (신설) ───────────────────────────

_JP = {
    "dict": {
        "explore": ["おすすめ", "オススメ", "お勧め", "人気", "ランキング", "順位", "比較", "比較表", "口コミ", "クチコミ", "評判", "評価",
                    "レビュー", "価格", "値段", "安い", "最安値", "最安", "激安", "格安", "コスパ", "種類", "一覧", "定番", "売れ筋",
                    "新作", "新商品", "新型", "最新", "最新作", "新色", "限定", "ブランド", "メーカー", "best", "選び方", "人気ランキング",
                    "メニュー", "味", "辛さ"],
        "use": ["使い方", "手入れ", "お手入れ", "洗い方", "洗濯", "掃除", "洗浄", "修理", "故障", "寿命", "交換", "説明書", "取扱説明書",
                "取説", "部品", "パーツ", "内釜", "内なべ", "パッキン", "電池", "エラー", "エラーコード", "保証", "返品", "返金", "サポート",
                "問い合わせ", "電話番号", "カスタマー", "紐", "靴紐", "ソール", "設定", "リセット", "初期化", "登録", "廃盤", "発売日",
                "再販", "音", "臭い", "におい", "電源", "蓋", "ふた", "フィルター", "異音", "動かない"],
        "howto": ["作り方", "レシピ", "炊き方", "やり方", "方法", "料理", "時間", "コーデ", "着こなし", "茹で方", "蒸し方", "使い分け"],
        "attr": ["サイズ", "サイズ感", "幅広", "ワイド", "レディース", "メンズ", "女性", "男性", "女性用", "男性用", "キッズ", "ジュニア",
                 "子供", "子ども", "ブラック", "黒", "ホワイト", "白", "ピンク", "グレー", "ネイビー", "ベージュ", "シルバー",
                 "ステンレス", "小型", "大型", "大容量", "業務用", "ミニ", "コンパクト", "軽量", "軽い", "厚底", "初心者", "入門",
                 "上級者", "中級者", "長距離", "マラソン", "フルマラソン", "トレイル", "ゴアテックス", "gtx", "防水", "冬", "夏",
                 "一人暮らし", "高級", "プレミアム", "旧型", "圧力", "電気", "ih", "保温", "カーボン", "扁平足", "偏平足", "通勤",
                 "普段使い", "おしゃれ", "かわいい", "クッション", "安定", "ロード", "レース", "キャンプ"],
        "generic": ["シューズ", "スニーカー", "靴", "くつ", "ランニング", "ラン", "ジョギング"],
        "channel": ["楽天", "アマゾン", "amazon", "ヤフー", "yahoo", "ヤフオク", "メルカリ", "ヨドバシ", "ビックカメラ", "ヤマダ電機",
                    "ケーズデンキ", "エディオン", "コストコ", "ドンキ", "ドンキホーテ", "アウトレット", "店舗", "販売店", "取扱店", "公式",
                    "公式サイト", "通販", "セール", "割引", "中古", "福袋", "abcマート", "ゼビオ", "アルペン", "買取", "レンタル", "ダイソー"],
        "community": ["2ch", "5ch", "知恵袋", "なんj", "ブログ", "wiki", "ウィキ", "ツイッター", "twitter", "インスタ", "ヤフー知恵袋"],
        "info": ["意味", "英語", "読み方", "違い", "歴史", "株価", "採用", "求人", "ロゴ", "広告", "cm", "売上", "シェア", "市場",
                 "とは", "仕組み", "原理", "電気代", "消費電力", "本社", "会社", "年収"],
        "stop": ["の", "と", "で", "や", "に", "は", "を"],
    },
    "rx": [("year", r"^20\d\d(年)?$"), ("attr", r"^\d+(\.\d+)?(合|人用|人分|人前|号|cm|センチ)$"), ("attr", r"^\d+(\.\d+)?$"),
           ("attr", r"^\d+(千|万)?円(台)?$")],
    "attrSub": ["サイズ", "人用"],
    "foreign": r"[가-힣]",
    "substr": True,
    "latin": True,
    "intentBundles": [
        ("계급도·순위", ["ランキング", "順位", "ランク", "格付け", "top"]),
        ("추천·입문", ["おすすめ", "オススメ", "お勧め", "初心者", "入門", "人気", "定番", "売れ筋", "コスパ", "best"]),
        ("비교·후기", ["比較", "口コミ", "クチコミ", "評判", "レビュー", "評価"]),
        ("가격", ["価格", "値段", "最安値", "最安", "安い", "激安", "格安"]),
        ("신제품", ["新作", "新商品", "新型", "最新", "最新作", "新色"]),
    ],
    "buyWords": ["価格", "値段", "最安値", "安い", "通販", "購入", "販売", "楽天", "amazon", "アマゾン", "おすすめ", "比較",
                 "ランキング", "人気", "ブランド", "種類", "口コミ", "レビュー", "コスパ"],
    "howWords": ["方法", "やり方", "レシピ", "作り方", "効果", "痩せる", "ダイエット", "食事", "仕組み", "原理", "運動", "筋トレ",
                 "期間", "成功", "失敗", "ビフォーアフター", "ブログ", "自宅"],
    "cmpWords": ["違い", "比較", "vs", "代わり", "どっち", "どちら", "どれ"],
    "regionSuffix": r"(駅|市|区|町|県|村)$",
    "scope": {"headMax": 0.45, "tokenMax": 0.70, "calibrated": False},
}

# ─────────────────────────── us (신설) ───────────────────────────

_US = {
    "dict": {
        "explore": ["best", "top", "cheap", "cheapest", "affordable", "budget", "price", "prices", "cost", "deal", "deals",
                    "review", "reviews", "rated", "rating", "ratings", "compare", "comparison", "vs", "versus", "alternative",
                    "alternatives", "newest", "latest", "popular", "brands", "brand", "list", "types", "recommended",
                    "recommendation", "ranking", "rankings", "worth", "menu", "flavors", "spicy"],
        "use": ["cleaning", "clean", "wash", "washing", "repair", "fix", "manual", "instructions", "parts", "replacement", "replace",
                "warranty", "return", "returns", "customer", "service", "support", "reset", "setup", "error", "troubleshooting",
                "laces", "lace", "battery", "filter", "lid", "gasket", "seal", "beeping", "login", "registration", "discontinued",
                "release", "date", "smell", "noise"],
        "howto": ["recipe", "recipes", "how", "make", "cook", "cooking", "time", "tips", "outfit", "outfits", "styling", "steps"],
        "attr": ["size", "sizes", "sizing", "women", "womens", "women's", "woman", "men", "mens", "men's", "man", "kids", "kid",
                 "boys", "girls", "youth", "toddler", "black", "white", "pink", "grey", "gray", "navy", "beige", "silver", "red", "blue",
                 "stainless", "steel", "mini", "small", "large", "xl", "wide", "narrow", "lightweight", "light", "cushioned",
                 "cushion", "stability", "trail", "gore-tex", "goretex", "gtx", "waterproof", "winter", "summer", "beginner",
                 "beginners", "marathon", "distance", "flat", "feet", "daily", "everyday", "pressure", "electric", "induction", "ih",
                 "commercial", "travel", "portable", "premium", "luxury", "carbon", "plate", "road", "racing", "neutral", "high", "low"],
        "generic": ["shoes", "shoe", "sneakers", "sneaker", "running", "run", "runner", "trainers", "footwear", "jogging"],
        "channel": ["amazon", "walmart", "target", "costco", "ebay", "kohls", "kohl's", "macys", "nordstrom", "dicks", "dick's",
                    "zappos", "outlet", "store", "stores", "shop", "online", "sale", "discount", "coupon", "clearance", "used",
                    "refurbished", "official", "website", "rental", "rent"],
        "community": ["reddit", "quora", "forum", "wiki", "wikipedia", "blog", "youtube", "tiktok", "instagram", "twitter"],
        "info": ["meaning", "definition", "history", "stock", "jobs", "careers", "logo", "ceo", "revenue", "market", "share",
                 "founder", "owner", "headquarters", "what", "why", "who", "lawsuit", "recall", "wattage"],
        "stop": ["for", "with", "and", "the", "a", "an", "in", "of", "near", "me", "by", "from", "at", "or", "my", "to", "is"],
    },
    "rx": [("year", r"^20\d\d$"), ("attr", r"^\d+(\.\d+)?(qt|quart|cup|cups|oz|in|inch|mm|cm|l|lb|lbs)$"),
           ("attr", r"^\d+(\.\d+)?$"), ("attr", r"^\$\d+k?$")],
    "attrSub": [],
    "foreign": r"[぀-ヿ가-힣一-鿿]",
    "substr": False,
    "latin": False,
    "intentBundles": [
        ("계급도·순위", ["ranking", "rankings", "top", "tier", "list"]),
        ("추천·입문", ["best", "recommended", "beginner", "beginners", "popular"]),
        ("비교·후기", ["vs", "versus", "compare", "comparison", "review", "reviews", "rated"]),
        ("가격", ["price", "prices", "cheap", "cheapest", "cost", "affordable", "budget", "deal", "deals"]),
        ("신제품", ["newest", "latest", "release"]),
    ],
    "buyWords": ["price", "prices", "cheap", "cheapest", "best", "buy", "sale", "deal", "deals", "review", "reviews", "vs",
                 "compare", "amazon", "walmart", "brands", "top", "cost"],
    "howWords": ["how", "recipe", "recipes", "benefits", "workout", "workouts", "exercises", "diet", "results", "before", "after",
                 "tips", "routine", "method", "meal"],
    "cmpWords": ["vs", "versus", "difference", "compare", "comparison", "instead", "or", "better"],
    "regionSuffix": r"(?!x)x",   # 미국 지명은 접미사로 가려지지 않는다 · picks.internal.catchall.regions 로만
    "scope": {"headMax": 0.45, "tokenMax": 0.70, "calibrated": False},
}

_ALL = {"kr": _KR, "jp": _JP, "us": _US}


def get(gl):
    """시장 설정 한 벌. 모르는 값이면 kr (method-v5.11 까지의 동작)."""
    return _ALL.get(str(gl or "kr").lower(), _KR)


def word_in(piece, words, substr):
    """조각이 사전어를 담는가. substr=False 면 단어 단위 (복수형 's' 는 같은 말로 본다)."""
    if substr:
        return any(w in piece for w in words if len(w) >= 2)
    base = piece[:-1] if piece.endswith("s") and len(piece) > 3 else piece
    return piece in words or base in words


def text_has(text, words, substr):
    """검색어 한 줄이 사전어를 담는가 (check 의 구매·방법 결합 비율 · M5-0 비교 언급)."""
    if substr:
        return any(w in text for w in words)
    return any(word_in(p, words, False) for p in text.split(" ") if p)


def compile_rx(m):
    return [(k, re.compile(p)) for k, p in m["rx"]]
