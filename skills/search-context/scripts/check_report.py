#!/usr/bin/env python3
"""check_report.py · v2 리포트에 필수 기능이 빠지지 않았는지 정적으로 확인한다.

  python3 scripts/check_report.py "{WORKDIR}/report.html"

기능 목록은 references/report-features.md 와 같게 유지한다. 하나라도 빠지면 exit 1.
"""
import json
import re
import sys
from pathlib import Path

CHECKS = [
    ("요약", '<h2>요약</h2>', '<h2>Summary</h2>', '<h2>要約</h2>'),
    ("마케팅 액션(M1…)", '<span class="no">M1</span>'),
    ("경로 맵 · 단일 맵", 'svg class="pm"', 'id="sc-data"'),
    ("경로 수 기본 100 · 늘리기", 'id="nseg"', '"allPaths":', "build(n)"),
    ("경로 맵 · 확대/축소/맞춤/포커스", 'data-z="in"', 'data-z="out"', 'data-z="fit"', 'data-z="start"'),
    ("경로 맵 · 펼치기/접기", "act==='more'"),
    ("키워드 찾기", 'id="fq"', 'id="flist"'),
    ("질문·경로 분석 채팅 (선택 경로 바 · 대화 · 추천 질문 · 입력)", 'id="chat"', 'id="selbar"', 'id="thread"', 'id="sug"', 'id="q"', ".crumb span.cur"),
    ("채팅 답변 (사용자 Claude · 경로 데이터 근거 · 키워드 칩)", "chatContext()", "data-kw2"),
    ("채팅 기록 저장 (보는 사람별)", "data/users/me/chat/"),
    ("페이지 안 경로 분석 (Claude · ListeningMind serp)", "use('sample')", "callTool(D.lm,'serp'"),
    ("연결 요청 (Claude/커넥터 없음 · 권한 설정)", "noSample", "noMcp", "permissions"),
    ("분석 저장·다시 보기", "pathAna/", 'id="savedlist"'),
    ("상위 3개 + 더보기", "(3, 3, 3, 3)" if False else '"keep": [3, 3, 3, 3]'),
    ("더보기 호버 · 숨은 키워드 모달", 'id="pop"', "T.hidden"),
    ("키워드 호버 · 포함 경로 강조 · 이 경로 분석", "hlKw(", 'data-pa="go"'),
    ("처음 맞춤 · 그림 범위에 맞춘 viewBox", "getBBox()", "fitHeight()"),
    ("선택하면 키워드 포함 경로 전체 고정 강조 · 모달 닫힘", "hlKw(selKw())", "quietId"),
    ("호버 카드 끄기/켜기 · 닫기 · 끄면 선택 경로만 보기", 'id="poptog"', "data-px", "selmode"),
    ("경로 분석 인사이트", "T.insights", '"insights":'),
    ("근거(단계별 SERP 분석·SERP 원문)는 펼치기", 'class="evd"', "T.basis"),
    ("저장된 분석에 분석 내용과 근거", "T.detail", "resHtml(d.r,d.savedAt)"),
    ("저장된 분석 카드 · 번호 · 하나만 펼침", 'details class="svc"', 'details.svc[open]'),
    ("빈 공간 클릭 · 선택 해제", "if(!t){if(sel&&!busyAna())unselect();return}"),
    ("호버 카드 Target 키워드 · 버튼과 구분", ".pop .crumb span.cur{"),
]

# Claude 런타임에서만 쓰는 기능 · ChatGPT용 리포트에서는 확인하지 않는다
CLAUDE_ONLY = {"채팅 기록 저장 (보는 사람별)", "페이지 안 경로 분석 (Claude · ListeningMind serp)",
               "연결 요청 (Claude/커넥터 없음 · 권한 설정)", "분석 저장·다시 보기",
               "저장된 분석에 분석 내용과 근거", "저장된 분석 카드 · 번호 · 하나만 펼침"}
GPT_CHECKS = [
    ("ChatGPT · 질문·경로 분석 요청문 복사", "handoff({role:'a'", "handoff({role:'ana'", "copyText(", "recopy"),
]

def main():
    if len(sys.argv) < 2:
        print(__doc__); return 2
    html = Path(sys.argv[1]).read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="sc-data">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1).replace("<\\/", "</")) if m else {}
    host = data.get("host", "claude")
    print(f"· 대상 도구 {host}")
    checks = CHECKS if host == "claude" else [c for c in CHECKS if c[0] not in CLAUDE_ONLY] + GPT_CHECKS
    miss = []
    if host == "chatgpt":
        # 보이는 문구에 Claude 연결 안내가 남으면 안 된다
        texts = json.dumps(data.get("t", {}), ensure_ascii=False)
        body = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S)
        ok = "Claude" not in texts and "Claude" not in re.sub(r"lm-search-context v[0-9.]+", "", body)
        print(("✓ " if ok else "✗ ") + "ChatGPT · 보이는 문구에 Claude 안내 없음")
        if not ok:
            miss.append("ChatGPT · 보이는 문구에 Claude 안내 없음")
    for name, *need in checks:
        ok = any(n in html for n in need) if name == "요약" else all(n in html for n in need)
        print(("✓ " if ok else "✗ ") + name)
        if not ok:
            miss.append(name)
    if miss:
        print(f"❌ 빠진 기능 {len(miss)}개 · 렌더러(sc.py)를 확인하세요. 리포트를 넘기지 마세요.")
        return 1
    print("✓ 필수 기능 모두 확인")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
