#!/usr/bin/env python3
"""sc.py · Search Context v2 (현재 시점 하나 · 경로 맵 중심 · 페이지 안에서 경로 분석)

서브커맨드
  kwparams   경로에서 고유 키워드를 뽑아 keyword_info 파라미터를 만든다
  plan       경로 트리·통계와 마케팅 분석용 SERP 대상(E1=시드, E2…=주요 1단계 분기)을 만든다
  serp-trim  SERP 원본 응답을 근거 데이터로 줄인다
  brief      마케팅 분석 입력(brief.md)을 만든다
  render     마케팅 분석 JSON을 검증하고 리포트 HTML을 만든다

숫자(경로 수·검색량)는 코드가 계산하고, LLM은 해석과 마케팅 액션만 쓴다.
페이지 안의 경로 분석은 render --host 로 갈린다.
  claude  · Claude.ai에 게시된 페이지에서 사용자의 Claude(sample)와 ListeningMind 커넥터(serp)로 돌고, 결과는 페이지 저장소(db)에 남는다.
  chatgpt · 페이지가 LLM을 부를 수 없으므로 경로 데이터를 담은 요청문을 복사해 ChatGPT 대화창에 붙여 넣게 한다(저장 기능 없음).
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

# 빌드가 skill.yaml 의 version 으로 치환한다 · 사람이 두 곳에 적지 않는다
SKILL_VERSION = "__SKILL_VERSION__"
MAP_DEPTH = 4
MAP_KEEP = (3, 3, 3, 3)   # 단계마다 상위 3개만, 나머지는 「+N개 더」
BRANCH_SERP = 5          # 시드 다음 주요 분기 중 SERP를 볼 개수
BRIEF_PATHS = 40
SHOW_DEFAULT = 300        # 처음 보여 주고 분석하는 경로 수 · Step 0에서 사용자가 고른 PATHS(100·200·300, 기본 300)
SHOW_STEPS = (100, 200, 300)


# ───────── 읽기 도우미 ─────────

def unwrap(p):
    if isinstance(p, list) and p and all(isinstance(b, dict) and b.get("type") == "text" and "text" in b for b in p):
        try:
            return json.loads("".join(str(b.get("text") or "") for b in p))
        except json.JSONDecodeError:
            return p
    return p


def load_json(path):
    return unwrap(json.loads(Path(path).read_text(encoding="utf-8")))


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def load_paths(path):
    d = load_json(path)
    if isinstance(d, dict):
        if isinstance(d.get("data"), list):
            d = d["data"]
        elif isinstance(d.get("result"), dict):
            d = d["result"].get("paths") or []
        else:
            sys.exit(f"❌ path_finder 응답에 경로가 없습니다 · {d.get('result')} {d.get('reason', '')}")
    seen, out = set(), []
    for p in d or []:
        if isinstance(p, list):
            q = [k.strip() for k in p if isinstance(k, str) and k.strip()]
            key = " > ".join(q)
            if len(q) >= 2 and key not in seen:
                seen.add(key)
                out.append(q)
    return out


def load_volumes(path):
    if not path or not Path(path).exists():
        return {}
    d = load_json(path)
    rows = d.get("data") if isinstance(d, dict) else d
    vol = {}
    for r in rows or []:
        if isinstance(r, dict) and r.get("keyword"):
            v = (r.get("ads_metrics") or {}).get("volume_avg", r.get("volume_avg", 0))
            try:
                vol[r["keyword"]] = int(round(float(v or 0)))
            except (TypeError, ValueError):
                vol[r["keyword"]] = 0
    return vol


def fmt(n):
    return f"{int(n):,}" if isinstance(n, (int, float)) else "–"


# ───────── kwparams ─────────

def cmd_kwparams(a):
    seen, kws = set(), []
    for p in load_paths(a.paths):
        for k in p:
            if k not in seen:
                seen.add(k)
                kws.append(k)
    write_json(a.out, {"keywords": kws[:1000], "gl": a.gl, "data_type": "ads_metrics"})
    print(f"✓ keyword_info 파라미터 · 키워드 {min(len(kws), 1000)}개 → {a.out}")


# ───────── plan ─────────

def build_trie(seqs):
    root = {"c": []}

    def grow(node, items, d):
        if d >= MAP_DEPTH:
            return
        groups = {}
        for i, q in items:
            if len(q) > d:
                groups.setdefault(q[d], []).append((i, q))
        for kw, its in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            ch = {"k": kw, "n": len(its)}
            node["c"].append(ch)
            if d + 1 < MAP_DEPTH:
                ch["c"] = []
                grow(ch, its, d + 1)
                if not ch["c"]:
                    del ch["c"]
    grow(root, list(enumerate(seqs)), 0)
    return root


def cmd_plan(a):
    paths = load_paths(a.paths)
    vol = load_volumes(a.nodes)
    seed = a.seed
    all_through = [p for p in paths if seed in p]
    if not all_through:
        # 띄어쓰기·대소문자만 다른 표기면 경로 데이터의 표기로 맞춘다 (예: 캠핑의자 → 캠핑 의자)
        norm = lambda k: re.sub(r"\s+", "", k).lower()
        alt = Counter(k for p in paths for k in p if norm(k) == norm(seed))
        if alt:
            seed = alt.most_common(1)[0][0]
            all_through = [p for p in paths if seed in p]
            print(f"⚠ 경로 데이터의 시드 표기는 「{seed}」입니다 · 이 표기로 분석합니다 (입력 「{a.seed}」)")
    if not all_through:
        sys.exit(f"❌ 「{seed}」를 지나는 경로가 없습니다.")
    show = max(1, min(a.show, len(all_through)))
    through = all_through[:show]   # PATHS(기본 300) · 요약·마케팅 분석·처음 맵은 이 범위
    left = [list(reversed(p[: p.index(seed)])) for p in through]
    right = [p[p.index(seed) + 1:] for p in through]
    nxt = Counter(r[0] for r in right if r)
    prv = Counter(l[0] for l in left if l)
    branches = [k for k, _ in nxt.most_common(BRANCH_SERP)]
    kws = sorted({k for p in through for k in p})
    kws_all = sorted({k for p in all_through for k in p})
    plan = {
        "seed": seed, "gl": a.gl, "date": a.date, "lang": a.lang,
        "seedVolume": vol.get(seed, 0), "pathCount": len(through), "keywordCount": len(kws),
        "next": [[k, n] for k, n in nxt.most_common(15)], "prev": [[k, n] for k, n in prv.most_common(10)],
        "paths": through, "allPaths": all_through, "show": show, "total": len(all_through),
        "tree": {"L": build_trie(left), "R": build_trie(right)},
        "volumes": {k: vol.get(k, 0) for k in kws_all},
        "evidence": [{"code": f"E{i+1}", "keyword": k, "volume": vol.get(k, 0)} for i, k in enumerate([seed] + branches)],
    }
    write_json(a.out, plan)
    print(f"✓ 「{seed}」 · 경로 {len(through)}개 사용 (받은 경로 {len(all_through)}개 중) · 키워드 {len(kws)}개 → {a.out}")
    print("SERP를 불러올 키워드 (파일 이름 serp_<코드>.json):")
    for e in plan["evidence"]:
        print(f"  {e['code']}\t{e['keyword']}")


# ───────── serp-trim ─────────

def _trim_list(lst):
    return [{"snippet": str(i.get("snippet") or ""), "list": _trim_list(i["list"]) if i.get("list") else None}
            for i in (lst or [])[:12] if isinstance(i, dict)]


def trim_serp(pl):
    if isinstance(pl, list):
        pl = {"result": "OK", "data": pl}
    if not isinstance(pl, dict):
        return {"ok": False, "reason": "응답 형식을 읽지 못함"}
    if pl.get("result") not in (None, "OK", "SUCCESS"):
        return {"ok": False, "reason": str(pl.get("reason") or pl.get("result"))}
    data = pl.get("data") if isinstance(pl.get("data"), list) else []
    ab = next((b for b in data if isinstance(b, dict) and b.get("type") == "ai_overview"), None)
    aio, refs = None, []
    if ab:
        aio = []
        for b in (ab.get("text_blocks") or [])[:20]:
            if b.get("type") == "list" and b.get("list"):
                aio.append({"type": "list", "list": _trim_list(b["list"])})
            elif b.get("snippet"):
                aio.append({"type": "p", "text": str(b["snippet"])})
        refs = [{"title": str(r.get("title") or ""), "source": str(r.get("source") or ""), "url": str(r.get("url") or "")}
                for r in (ab.get("references") or [])[:12] if (r.get("title") or r.get("source"))][:10]
    org = sorted([b for b in data if isinstance(b, dict) and b.get("type") == "organic_results"],
                 key=lambda b: b.get("position") or 99)[:3]
    top = [{"position": b.get("position"), "site": str(b.get("site_name") or ""), "title": str(b.get("title") or ""),
            "url": str(b.get("url") or ""), "snippet": str(b.get("snippet") or "")} for b in org]
    return {"ok": True, "at": pl.get("collected_at"), "aio": aio, "refs": refs, "top": top}


def aio_text(blocks):
    out = []

    def walk(lst, d):
        for i in lst or []:
            out.append("  " * d + "- " + i["snippet"])
            walk(i.get("list"), d + 1)
    for b in blocks or []:
        if b["type"] == "list":
            walk(b["list"], 0)
        else:
            out.append(b["text"])
    return "\n".join(out)


def cmd_serp_trim(a):
    plan = load_json(a.plan)
    ev = []
    for e in plan["evidence"]:
        f = Path(a.serp_dir) / f"serp_{e['code']}.json"
        if not f.exists():
            ev.append({**e, "ok": False, "reason": "SERP 파일 없음"})
            continue
        try:
            ev.append({**e, **trim_serp(load_json(f))})
        except (OSError, json.JSONDecodeError) as err:
            ev.append({**e, "ok": False, "reason": f"읽기 실패 · {err}"})
    write_json(a.out, ev)
    print(f"✓ SERP 근거 {sum(1 for x in ev if x.get('ok'))}/{len(ev)}개 → {a.out}")


# ───────── brief ─────────

def cmd_brief(a):
    plan = load_json(a.plan)
    ev = load_json(a.evidence) if a.evidence and Path(a.evidence).exists() else []
    vol = plan["volumes"]
    L = [f"# Search Context 입력 · 시드 「{plan['seed']}」 (시장 {plan['gl']}, 현재 시점)",
         f"「{plan['seed']}」를 지나는 경로 {plan['pathCount']}개, 등장 키워드 {plan['keywordCount']}개.", ""]
    L.append("## 바로 다음 검색 (분기별 경로 수 · 월 검색량)")
    L.append("; ".join(f"{k} ({n}경로, {fmt(vol.get(k))})" for k, n in plan["next"]))
    if plan["prev"]:
        L.append("## 바로 앞 검색")
        L.append("; ".join(f"{k} ({n}경로)" for k, n in plan["prev"]))
    L.append("")
    L.append(f"## 대표 경로 (검색량 합 상위 {BRIEF_PATHS}개)")
    ranked = sorted(plan["paths"], key=lambda p: -sum(vol.get(k, 0) for k in p))[:BRIEF_PATHS]
    for p in ranked:
        L.append(" → ".join(p))
    L.append("")
    L.append("## SERP 근거 (E) · 시드와 주요 분기")
    for x in ev:
        if not x.get("ok"):
            L.append(f"{x['code']} 「{x['keyword']}」 · SERP 없음 ({x.get('reason')})")
            continue
        L.append(f"{x['code']} 「{x['keyword']}」 (월 검색량 {fmt(x.get('volume'))}, 수집 {str(x.get('at') or '')[:10]})")
        L.append(f"  {x['code']}-AI AI 개요: " + (aio_text(x["aio"]).replace("\n", " ")[:1200] if x.get("aio") else "없음"))
        for o in x.get("top") or []:
            L.append(f"  {x['code']}-{o['position']} [{o['site']}] {o['title']} — {o['snippet']}")
    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print(f"✓ 분석 입력 → {a.out}")


# ───────── render ─────────

TAG_RX = re.compile(r"<(?!/?strong>)[^>]*>")


def clean(t, n=500):
    return TAG_RX.sub("", str(t or "")).strip()[:n]


LABELS = {
    "kr": {"title": "Search Context", "hTitle": "검색 맥락 분석", "hPurpose": "배경과 목적", "hIntro": "시드 키워드를 지나는 검색 경로를 모아 요약·마케팅 할 일·경로 맵을 만들고, 페이지 안에서 경로를 골라 검색 결과 근거로 검색 목적을 분석합니다.", "hDate": "수집", "market": "시장", "vol": "월 검색량", "paths": "경로", "kws": "키워드", "summary": "요약",
           "actions": "마케팅 관점에서 할 일", "why": "근거", "how": "실행", "map": "경로 맵",
           "mapHint": "시드를 가운데 두고 왼쪽은 그 전에, 오른쪽은 그 뒤에 검색한 것입니다. 키워드를 누르면 시드부터 그 키워드까지의 경로가 선택되고, 맵 아래 「선택한 경로」에서 그 경로의 검색 목적을 분석할 수 있습니다. 처음에는 전체가 맞춤으로 보이고, 휠로 확대·축소합니다.",
           "nTip": "맵·질문에 쓰는 경로 수. 받은 순서대로 앞에서부터", "find": "키워드 찾기", "listOpen": "목록", "sel": "선택한 경로", "selHint": "맵에서 키워드를 눌러 경로를 고르세요.",
           "saved": "저장된 분석", "noSaved": "아직 저장된 분석이 없습니다.", "evidence": "근거 SERP (시드와 주요 분기)",
           "fit": "맞춤", "popOn": "호버 카드", "popTip": "끄면 마우스를 올려도 카드와 강조가 뜨지 않고, 선택한 경로만 또렷하게 보입니다", "more": "개 더", "less": "− 접기", "passing": "이 지점을 지나는 경로", "analyze": "경로 분석", "reanalyze": "다시 분석", "open": "보기", "del": "삭제",
           "aio": "AI 개요", "top3": "검색 결과 1~3위", "noaio": "AI 개요 없음", "foot": "경로는 리스닝마인드 패스파인더 현재 시점 표본입니다. SERP는 저장된 Google 스냅샷이며 수집일이 키워드마다 다를 수 있습니다. 해석은 위 데이터만 근거로 Claude가 작성했습니다."},
    "us": {"title": "Search Context", "hTitle": "Search Context Analysis", "hPurpose": "Background and purpose", "hIntro": "Collects the search paths that pass through a seed keyword, builds a summary, marketing actions and a path map, and analyses search intent from SERP evidence for a path you pick inside the page.", "hDate": "Collected", "market": "Market", "vol": "Monthly volume", "paths": "paths", "kws": "keywords", "summary": "Summary",
           "actions": "Marketing to-dos", "why": "Why", "how": "How", "map": "Path map",
           "mapHint": "The seed sits in the middle: searches before it on the left, after it on the right. Click a keyword to select the path from the seed to it, then analyze its search purpose in “Selected path” below. The map opens fitted; scroll to zoom.",
           "nTip": "Number of paths used by the map and chat, in the order received", "find": "Find a keyword", "listOpen": "List", "sel": "Selected path", "selHint": "Click a keyword on the map to pick a path.",
           "saved": "Saved analyses", "noSaved": "No saved analyses yet.", "evidence": "Evidence SERPs (seed and main branches)",
           "fit": "Fit", "popOn": "Hover cards", "popTip": "When off, hovering shows no cards or highlights and only the selected path stands out", "more": " more", "less": "− collapse", "passing": "paths through this point", "analyze": "Analyze path", "reanalyze": "Re-analyze", "open": "Open", "del": "Delete",
           "aio": "AI Overview", "top3": "Top 3 results", "noaio": "No AI Overview", "foot": "Paths are a current ListeningMind PathFinder sample. SERPs are stored Google snapshots; collection dates can differ. Interpretation by Claude from the data above only."},
    "jp": {"title": "Search Context", "hTitle": "検索コンテキスト分析", "hPurpose": "背景と目的", "hIntro": "シードキーワードを通る検索経路を集めて要約・マーケティングの打ち手・経路マップを作り、ページ内で経路を選んで検索結果の根拠から検索目的を分析します。", "hDate": "収集", "market": "市場", "vol": "月間検索数", "paths": "経路", "kws": "キーワード", "summary": "要約",
           "actions": "マーケティング観点のやること", "why": "根拠", "how": "実行", "map": "経路マップ",
           "mapHint": "シードを中央に、左はその前、右はその後の検索です。キーワードを押すとシードからそのキーワードまでの経路が選ばれ、マップ下の「選択した経路」で検索目的を分析できます。最初は全体表示で、ホイールで拡大・縮小します。",
           "nTip": "マップと質問で使う経路数（取得順に先頭から）", "find": "キーワード検索", "listOpen": "一覧", "sel": "選択した経路", "selHint": "マップでキーワードを押して経路を選んでください。",
           "saved": "保存した分析", "noSaved": "保存した分析はまだありません。", "evidence": "根拠SERP（シードと主な分岐）",
           "fit": "全体", "popOn": "ホバーカード", "popTip": "オフにするとホバー時のカードと強調を出さず、選択した経路だけを際立たせます", "more": "件", "less": "− 折りたたむ", "passing": "この地点を通る経路", "analyze": "経路分析", "reanalyze": "再分析", "open": "表示", "del": "削除",
           "aio": "AIによる概要", "top3": "検索結果1〜3位", "noaio": "AIによる概要なし", "foot": "経路はListeningMind PathFinderの現在のサンプルです。SERPは保存されたGoogleスナップショットです。解釈は上記データのみを根拠にClaudeが作成しました。"},
}

CSS = """
:root{--bg:#F7F8FA;--panel:#FFFFFF;--fg:#1E2A3A;--muted:#586882;--line:#E3E8F2;--chip:#F7F8FA;--accent:#7F18FF;--hl:#FF247A;--ok:#2e8b57;--part:#8A6600;--bad:#C43D2F;--notice:#7F18FF;--notice-bg:#FEF9FF;--cover-a:rgb(10,5,16);--cover-b:rgb(26,8,48);--cover-c:rgb(13,21,40);--glow-1:rgba(127,24,255,.33);--glow-2:rgba(24,140,255,.18);--radius:12px;--shadow-xs:0 1px 2px rgba(30,42,58,.04);
--sans:"Noto Sans KR","Pretendard","Noto Sans JP",system-ui,-apple-system,"Segoe UI",sans-serif;--mono:ui-monospace,"SF Mono",Menlo,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#14171c;--panel:#1c2027;--fg:#e6e9ee;--muted:#9aa3b2;--line:#2c323c;--chip:#262b34;--accent:#7f9cff;--hl:#ff8a6b;--ok:#5cc28a;--part:#e0a84b;--bad:#ff8a7c;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#14171c;--panel:#1c2027;--fg:#e6e9ee;--muted:#9aa3b2;--line:#2c323c;--chip:#262b34;--accent:#7f9cff;--hl:#ff8a6b;--ok:#5cc28a;--part:#e0a84b;--bad:#ff8a7c;color-scheme:dark}
/* 헤더 카드 · 공용 리포트(_core/styles/report-shell.css)와 같은 모양 */
.dash-card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow-xs);overflow:hidden}
.dash-cover{background:linear-gradient(135deg,var(--cover-a) 0%,var(--cover-b) 50%,var(--cover-c) 100%);padding:22px 28px;position:relative;overflow:hidden}
.dash-cover::before{content:"";position:absolute;top:-50px;right:-30px;width:200px;height:200px;background:radial-gradient(circle,var(--glow-1) 0%,transparent 70%);pointer-events:none}
.dash-cover::after{content:"";position:absolute;bottom:-30px;left:35%;width:160px;height:160px;background:radial-gradient(circle,var(--glow-2) 0%,transparent 70%);pointer-events:none}
.dash-eyebrow{font-size:11px;font-weight:600;color:rgba(255,255,255,.4);letter-spacing:.06em;text-transform:uppercase;margin-bottom:6px;position:relative}
.dash-title{font-size:20px;font-weight:700;color:#fff;line-height:1.35;margin:0 0 8px;position:relative}
.dash-seed{font-size:13px;color:rgba(255,255,255,.55);position:relative}
.dash-meta{font-size:11px;color:rgba(255,255,255,.35);margin-top:12px;position:relative}
.dash-purpose{padding:20px 24px;background:var(--bg);border-top:1px solid var(--line)}
.dash-purpose b{display:block;font-size:11px;font-weight:700;color:var(--fg);letter-spacing:.08em;margin-bottom:4px}
.dash-purpose p{font-size:14px;line-height:1.7;margin:0}

:root{box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.6 var(--sans)}
.wrap{max-width:1280px;margin:0 auto;padding:24px 18px 48px;display:flex;flex-direction:column;gap:14px}
h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 10px}h3{font-size:13px;margin:0 0 6px}
.muted{color:var(--muted)}.mono{font-family:var(--mono);font-variant-numeric:tabular-nums}
.box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:16px 18px}
.kpis{display:flex;flex-wrap:wrap;gap:8px}.kpi{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:6px 12px}
.kpi small{display:block;color:var(--muted);font-size:11.5px}.kpi b{font-size:15px}
.acts{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-top:10px}
.act{border:1px solid var(--line);border-radius:8px;padding:12px;background:var(--bg);display:flex;flex-direction:column;gap:6px;font-size:13px}
.act b.t{font-size:14px}.act .lab{font:600 11px var(--sans);color:var(--muted)}
.chip{display:inline-block;border:1px solid var(--accent);color:var(--accent);background:var(--panel);border-radius:12px;padding:0 8px;font-size:12px;margin:2px 4px 0 0;cursor:pointer}
.chip:hover{background:var(--accent);color:var(--panel)}
.no{font:600 11px var(--mono);color:var(--panel);background:var(--accent);border-radius:4px;padding:0 5px;margin-right:6px}
.mapgrid{display:grid;grid-template-columns:1fr;gap:12px;align-items:start}
.find{display:flex;gap:6px;align-items:center;margin:0 0 8px;flex-wrap:wrap}
.find input{flex:1;min-width:180px;font:13px var(--sans);background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
.btn{border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:6px;font:600 12.5px var(--sans);padding:5px 10px;cursor:pointer}
.btn:hover{border-color:var(--accent)}.btn.pri{background:var(--accent);border-color:var(--accent);color:var(--panel)}.btn:disabled{opacity:.5;cursor:default}
.flist{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:4px;max-height:170px;overflow:auto;margin:0 0 8px}
.flist[hidden]{display:none}
.fi{display:flex;justify-content:space-between;gap:6px;text-align:left;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:3px 8px;font:12.5px var(--sans);cursor:pointer;min-width:0}
.fi:hover{border-color:var(--accent)}.fi .k{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.fi .v{font:500 11px var(--mono);opacity:.7}
.panel{border:1px solid var(--line);border-radius:8px;background:var(--bg);display:flex;flex-direction:column}
.phead{display:flex;justify-content:space-between;align-items:center;padding:6px 10px;border-bottom:1px solid var(--line);font-size:13px;gap:8px}
.zoom{display:inline-flex;gap:4px}.zoom button{border:1px solid var(--line);background:var(--panel);color:var(--fg);border-radius:6px;font:600 13px var(--sans);min-width:30px;height:28px;padding:0 8px;cursor:pointer}
.stage{height:420px;cursor:grab;touch-action:none;user-select:none}.stage.grabbing{cursor:grabbing}.stage svg{width:100%;height:100%;display:block}
.pm text{font:12px var(--sans);fill:var(--fg)}
.pm .lk{fill:none;stroke:var(--accent);stroke-opacity:.4}
.pm .nd{cursor:pointer}.pm .nd circle{fill:var(--panel);stroke:var(--accent);stroke-width:1.5}
.pm .nd.more text{fill:var(--accent);font-weight:700;text-decoration:underline}.pm .nd.more circle{fill:var(--accent)}
.pm .nd.focus circle{fill:var(--accent)}.pm .nd.focus text{font-weight:700;font-size:13px}
.pm .nd:hover text{fill:var(--hl)}
.pm.hov .lk{stroke-opacity:.1}.pm.hov .nd{opacity:.3}.pm.hov .lk.hv{stroke:var(--hl);stroke-opacity:.9}.pm.hov .nd.hv{opacity:1}.pm.hov .nd.hv text{fill:var(--hl);font-weight:700}
.pop{position:fixed;z-index:50;background:var(--panel);color:var(--fg);border:1px solid var(--line);border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.18);padding:10px 12px;font-size:13px;max-width:320px;max-height:min(60vh,420px);overflow:auto;display:flex;flex-direction:column;gap:6px}
.pop[hidden]{display:none}.pop .px{position:absolute;top:4px;right:6px;border:0;background:transparent;color:var(--muted);font-size:16px;line-height:1;cursor:pointer;padding:2px 4px}.pop .px:hover{color:var(--fg)}.pop{padding-right:26px}
.seg2{display:inline-flex;background:var(--chip);border-radius:8px;padding:2px;gap:2px;margin-left:8px;vertical-align:middle}
.seg2 button{border:0;background:transparent;color:var(--muted);font:600 12px var(--sans);padding:3px 9px;border-radius:6px;cursor:pointer}
.seg2 button[aria-pressed="true"]{background:var(--panel);color:var(--fg);box-shadow:0 1px 2px rgba(0,0,0,.12)}
.zoom #poptog{font-size:12px}.zoom #poptog[aria-pressed="false"]{color:var(--muted);text-decoration:line-through}.pop .ph{font-weight:700}.pop .pm2{color:var(--muted);font-size:12px}
.pop .hk{display:flex;justify-content:space-between;gap:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg);border-radius:6px;padding:3px 8px;font:12.5px var(--sans);cursor:pointer;text-align:left}
.pop .hk:hover{border-color:var(--accent)}.pop .hk span:last-child{font:500 11px var(--mono);opacity:.7}
.pop .pb{display:flex;gap:6px;flex-wrap:wrap}
.ho{display:flex;flex-direction:column;gap:6px}.ho textarea{width:100%;box-sizing:border-box;min-height:120px;font:12px/1.45 var(--mono);color:var(--fg);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;resize:vertical}.ho .hb{display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.pop .crumb span.cur{background:transparent;color:var(--fg);border:1.5px solid var(--fg);font-weight:700}
.pm .lk.sel{stroke:var(--hl);stroke-opacity:1}.pm.hov .lk.sel{stroke-opacity:1;stroke-width:4px}
.pm.selmode .lk{stroke-opacity:.07}.pm.selmode .nd{opacity:.22}.pm.selmode .lk.sel{stroke-opacity:1}.pm.selmode .nd.sel,.pm.selmode .nd.focus{opacity:1}.pm.selmode .nd:not(.sel):hover text{fill:var(--fg)}.pm .nd.sel circle{stroke:var(--hl);stroke-width:3;fill:var(--hl)}.pm .nd.sel text{fill:var(--hl);font-weight:700}
.pm .nd.saved circle{stroke-width:3}
.side{display:flex;flex-direction:column;gap:10px}
.chat{padding:12px 14px;display:flex;flex-direction:column;gap:10px}.chat-h{display:flex;flex-wrap:wrap;gap:4px 12px;align-items:baseline}.chat-h h2{margin:0}
.selbar{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);font-size:13px}
.selbar .lab,.anah .lab{font:600 11px var(--sans);color:var(--muted)}.selbar .bb{display:flex;gap:6px;margin-left:auto}
.thread{display:flex;flex-direction:column;gap:10px;max-height:min(70vh,640px);overflow:auto;padding:2px}
.thread .empty{color:var(--muted);font-size:13px;padding:10px 0}
.mu{align-self:flex-end;max-width:80%;background:var(--accent);color:var(--panel);border-radius:12px 12px 2px 12px;padding:7px 12px;font-size:13px;display:flex;flex-direction:column;gap:4px}
.mu .crumb span{background:rgba(255,255,255,.18);color:inherit;border-color:transparent}.mu .crumb span.cur{background:var(--panel);color:var(--accent)}.mu .crumb span.seed{color:inherit;background:transparent;border-color:rgba(255,255,255,.55)}.mu .crumb i{color:inherit;opacity:.7}
.ma{align-self:flex-start;max-width:92%;background:var(--bg);border:1px solid var(--line);border-radius:12px 12px 12px 2px;padding:9px 12px;font-size:13px}
.ma .tx{white-space:pre-wrap;line-height:1.65}.ma .chip{margin:0 2px}
.ma.ana{max-width:100%;width:100%;border-left:4px solid var(--accent)}.anah{display:flex;flex-wrap:wrap;gap:4px 8px;align-items:center;margin-bottom:4px}
.sug{display:flex;flex-wrap:wrap;gap:6px}.sgb{border:1px dashed var(--line);background:var(--panel);color:var(--fg);border-radius:14px;padding:3px 10px;font:12.5px var(--sans);cursor:pointer}.sgb:hover{border-color:var(--accent)}
.cin{display:flex;gap:8px;align-items:flex-end}.cin textarea{flex:1;min-height:42px;max-height:160px;resize:vertical;font:13px var(--sans);background:var(--bg);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:8px 10px}
.crumb{display:flex;flex-wrap:wrap;gap:3px 4px;align-items:center;font-size:12.5px}
.crumb span{background:var(--chip);border-radius:4px;padding:1px 6px;border:1px solid transparent}.crumb span.seed{background:transparent;border-color:var(--line);color:var(--muted)}.crumb span.cur{background:var(--accent);color:var(--panel);font-weight:700}
.crumb i{color:var(--muted);font-style:normal}
.note{font-size:12.5px;padding:8px 10px;border-radius:6px;background:var(--chip)}
.note.err{color:var(--bad)}
.res .purpose{font-size:15px;font-weight:700;margin:6px 0}
.steps{display:flex;flex-direction:column;gap:6px;margin-top:8px}
.ins{margin-top:10px;padding:10px 12px;border-radius:8px;background:var(--chip);border-left:3px solid var(--hl)}.ins h3{margin:0 0 4px}.ins ul{margin:0;padding-left:18px;font-size:13px}.ins li{margin:0 0 4px}
.evd{margin-top:12px;border-top:1px dashed var(--line);padding-top:8px}
.st{border-left:3px solid var(--accent);padding:2px 0 2px 10px;font-size:13px}
.st b{font-size:13px}.st .r{font:600 11px var(--sans);color:var(--accent);margin-left:6px}.st .s{color:var(--muted);font-size:12.5px}
.tag{font:600 11px var(--sans);border-radius:4px;padding:1px 6px;background:var(--chip)}
.t-met{color:var(--ok)}.t-part{color:var(--part)}.t-not{color:var(--bad)}
.sk{height:10px;border-radius:4px;background:linear-gradient(90deg,var(--chip),var(--line),var(--chip));background-size:200% 100%;animation:skm 1.2s linear infinite;margin:6px 0}
@keyframes skm{from{background-position:200% 0}to{background-position:-200% 0}}
details summary{cursor:pointer;font-weight:600;font-size:13px}
.ev{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(0,1fr);gap:12px;margin:8px 0 12px}@media (max-width:820px){.ev{grid-template-columns:1fr}}
.aio{background:var(--chip);border-radius:6px;padding:8px 10px;font-size:12.5px}.aio p{margin:0 0 6px}.aio ul{margin:0 0 6px;padding-left:18px}
.org div{font-size:12.5px;margin-bottom:6px}.org small{color:var(--muted)}a{color:var(--accent)}
.svl{display:flex;flex-direction:column;gap:10px}
.svc{border:1px solid var(--line);border-radius:10px;background:var(--panel);overflow:hidden;transition:border-color .15s,box-shadow .15s}
.svc[open]{border-color:var(--accent);box-shadow:0 4px 16px rgba(0,0,0,.08)}
.svc>summary{list-style:none;display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:4px 12px;align-items:center;padding:10px 14px;cursor:pointer}
.svc>summary::-webkit-details-marker{display:none}
.svc[open]>summary{background:var(--chip);border-bottom:1px solid var(--line)}
.svc .num{font:700 12px var(--mono);color:var(--panel);background:var(--accent);border-radius:6px;padding:2px 7px;align-self:start;margin-top:2px}
.svc .hd{display:flex;flex-direction:column;gap:3px;min-width:0}.svc .hd b{font-size:14px;line-height:1.4}
.svc .hd .crumb{font-size:12px}.svc .meta{display:flex;gap:8px;align-items:center;color:var(--muted);font-size:11.5px}
.svc .tg{font:600 12px var(--sans);color:var(--accent);white-space:nowrap}.svc .tg::after{content:" ▾"}.svc[open] .tg::after{content:" ▴"}
.svc .tg .c{display:none}.svc[open] .tg .o{display:none}.svc[open] .tg .c{display:inline}
.svc .bd{padding:4px 14px 14px;border-left:4px solid var(--accent);margin:12px 14px 14px;background:var(--bg);border-radius:0 8px 8px 0}
.svc .bd .purpose{display:none}
.svc .acts2{display:flex;gap:6px;justify-content:flex-end;padding:0 14px 12px}
.notice{border:1px solid var(--line);border-left:4px solid var(--notice);background:var(--notice-bg);border-radius:8px;padding:12px 14px;margin:0}
.notice>strong{display:block;margin-bottom:4px}
.banner{border:1px solid var(--part);color:var(--fg);background:var(--panel);border-radius:8px;padding:10px 12px;font-size:13px}
.banner[hidden]{display:none}
"""

JS = r"""
(function(){
var D=JSON.parse(document.getElementById('sc-data').textContent),T=D.t,SEED=D.seed,DEPTH=D.depth,KEEP=D.keep;
// 받은 경로(순서 그대로) 중 앞에서 N개로 맵을 만든다 · 기본 100개, 필요하면 200·300개로 늘림
function trie(seqs){var root={c:[]};(function grow(node,items,d){if(d>=DEPTH)return;var g={},order=[];
  items.forEach(function(q){if(q.length>d){var k=q[d];if(!g[k]){g[k]=[];order.push(k)}g[k].push(q)}});
  order.sort(function(a,b){return g[b].length-g[a].length||(a<b?-1:a>b?1:0)});
  order.forEach(function(k){var ch={k:k,n:g[k].length};node.c.push(ch);if(d+1<DEPTH){ch.c=[];grow(ch,g[k],d+1);if(!ch.c.length)delete ch.c}})})(root,seqs,0);return root}
function build(N){var ps=D.allPaths.slice(0,N);D.paths=ps;D.pathCount=ps.length;
  D.tree={L:trie(ps.map(function(p){return p.slice(0,p.indexOf(SEED)).reverse()})),R:trie(ps.map(function(p){return p.slice(p.indexOf(SEED)+1)}))}}
var NSHOW=D.show;try{var sv=+localStorage.getItem('sc-n-'+SEED);if(sv>0)NSHOW=sv}catch(_){}
NSHOW=Math.min(NSHOW,D.allPaths.length);build(NSHOW);
var RH=24,DX=160,PAD=16,LM=130,st={exp:{}},sel=null,svg=document.querySelector('svg.pm'),z={k:1,x:0,y:0};
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function hid(s){var h=0x811c9dc5,h2=0x811c9dc5;for(var i=0;i<s.length;i++){var c=s.charCodeAt(i);h^=c;h=Math.imul(h,16777619)>>>0;h2^=c+7;h2=Math.imul(h2,16777619)>>>0}return h.toString(16)+h2.toString(16)}
function pkey(p){return p.join(' > ')}
var GPT=D.host==='chatgpt';
var cap={};function use(n){if(GPT||!(window.claude&&window.claude.use))return Promise.resolve(null);return cap[n]||(cap[n]=window.claude.use(n).catch(function(){return null}))}
var banner=document.getElementById('banner');
if(!GPT&&!(window.claude&&window.claude.use)){banner.hidden=false;banner.textContent=T.noRuntime}
// ChatGPT 모드: 페이지가 LLM을 직접 부를 수 없으므로, 경로 데이터를 담은 요청문을 만들어 복사하고 ChatGPT 대화창에 붙여 넣게 한다
function copyText(t,ta){function fb(){try{if(ta){ta.focus();ta.select()}return document.execCommand('copy')}catch(_){return false}}
  if(navigator.clipboard&&navigator.clipboard.writeText)return navigator.clipboard.writeText(t).then(function(){return true},function(){return fb()});return Promise.resolve(fb())}
function hoHtml(m,i){return '<div class="ho"><div class="note">'+esc(m.copied?T.gptCopied:T.gptCopyFail)+'</div><textarea readonly data-ho="'+i+'">'+esc(m.handoff)+'</textarea><div class="hb"><button class="btn" data-a="recopy" data-i="'+i+'">'+esc(T.gptCopy)+'</button></div></div>'}
function handoff(m){push(m);copyText(m.handoff).then(function(ok){m.copied=!!ok;drawThread()})}
// ---------- 맵 ----------
function vis(node,id,d){var cs=node.c||[],o={n:node,id:id,d:d,kids:[]};if(d>=DEPTH||!cs.length)return o;
  var keep=KEEP[Math.min(d,KEEP.length-1)],k=st.exp[id]?cs.length:Math.min(cs.length,keep);
  for(var i=0;i<k;i++)o.kids.push(vis(cs[i],id+'>'+cs[i].k,d+1));
  if(cs.length>k){var n=0;cs.slice(k).forEach(function(c){n+=c.n});o.kids.push({act:'more',parent:id,cnt:cs.length-k,n:n,d:d+1,kids:[]})}
  else if(st.exp[id]&&cs.length>keep)o.kids.push({act:'less',parent:id,n:0,d:d+1,kids:[]});return o}
function lay(t,row){if(!t.kids.length){t.y=row.v++}else{t.kids.forEach(function(c){lay(c,row)});t.y=(t.kids[0].y+t.kids[t.kids.length-1].y)/2}}
function idToPath(id){var parts=id.split('>'),side=parts.shift();if(side==='ROOT')return [SEED];return side==='L'?parts.slice().reverse().concat([SEED]):[SEED].concat(parts)}
var SAVED={};
function render(){var L=vis(D.tree.L,'L',0),R=vis(D.tree.R,'R',0),rl={v:0},rr={v:0};lay(L,rl);lay(R,rr);
  var rows=Math.max(rl.v,rr.v,1),H=rows*RH+PAD*2,cx=DEPTH*DX+LM,W=cx*2,cy=H/2,oL=(rows-rl.v)*RH/2,oR=(rows-rr.v)*RH/2,tot=Math.max(1,D.pathCount);
  var links=[],nodes=[],selIds={};if(sel){var ss=sel.id.split('>');for(var i=1;i<=ss.length;i++)selIds[ss.slice(0,i).join('>')]=1}
  function P(t,sg,off){return t.d===0?[cx,cy]:[cx+sg*t.d*DX,PAD+off+t.y*RH+RH/2]}
  function walk(t,sg,off){var p0=P(t,sg,off);t.kids.forEach(function(c){var p1=P(c,sg,off),w=c.act==='less'?1:1+7*(c.act?c.n:c.n.n)/tot,mx=(p0[0]+p1[0])/2,on=!c.act&&selIds[c.id];
    links.push('<path class="lk'+(on?' sel':'')+'"'+(c.act?'':' data-id="'+esc(c.id)+'"')+' d="M'+p0[0]+','+p0[1].toFixed(1)+'C'+mx+','+p0[1].toFixed(1)+' '+mx+','+p1[1].toFixed(1)+' '+p1[0]+','+p1[1].toFixed(1)+'" stroke-width="'+w.toFixed(1)+'"/>');
    var lab=c.act==='more'?'+'+c.cnt+T.more:c.act==='less'?T.less:c.n.k,sh=lab.length>15?lab.slice(0,14)+'\u2026':lab,anc=sg>0?'start':'end',tx=p1[0]+(sg>0?8:-8);
    var sv=!c.act&&SAVED[pkey(idToPath(c.id))];
    var at=c.act?' class="nd more" data-act="'+c.act+'" data-parent="'+esc(c.parent)+'"':' class="nd'+(on?' sel':'')+(sv?' saved':'')+'" data-id="'+esc(c.id)+'"';
    nodes.push('<g'+at+' data-x="'+p1[0]+'" data-y="'+p1[1].toFixed(1)+'"><title>'+esc(lab)+(c.act==='less'?'':' \u00b7 '+(c.act?c.n:c.n.n))+'</title><circle cx="'+p1[0]+'" cy="'+p1[1].toFixed(1)+'" r="4"/><text x="'+tx+'" y="'+(p1[1]+4).toFixed(1)+'" text-anchor="'+anc+'">'+esc(sh)+'</text></g>');
    walk(c,sg,off)})}
  walk(L,-1,oL);walk(R,1,oR);
  nodes.push('<g class="nd focus" data-id="ROOT" data-x="'+cx+'" data-y="'+cy+'"><circle cx="'+cx+'" cy="'+cy+'" r="7"/><text x="'+cx+'" y="'+(cy-12)+'" text-anchor="middle">'+esc(SEED)+'</text></g>');
  svg.setAttribute('viewBox','0 0 '+W+' '+H);svg.setAttribute('data-cx',cx);svg.setAttribute('data-cy',cy);
  var vp=svg.querySelector('.vp');vp.innerHTML=links.join('')+nodes.join('');
  // 실제로 그려진 범위(라벨 포함)에 맞춰 viewBox를 잡는다 → 「맞춤」이 빈 여백 없이 꽉 차게
  if(sel&&typeof hlKw==='function')hlKw(selKw());
  try{var bb=vp.getBBox(),m=14;if(bb.width>0)svg.setAttribute('viewBox',(bb.x-m)+' '+(bb.y-m)+' '+(bb.width+2*m)+' '+(bb.height+2*m))}catch(_){}}
// 처음 한 번 · 그림 비율에 맞춰 맵 높이를 정한다 (너무 낮거나 높지 않게)
function fitHeight(){var stg=svg.parentNode,b=svg.viewBox.baseVal;if(!b||!b.width)return;var w=stg.clientWidth||800,h=w*b.height/b.width;
  stg.style.height=Math.round(Math.max(320,Math.min(h,innerHeight*0.75)))+'px'}
var g=svg.querySelector('.vp');function apply(){g.setAttribute('transform','translate('+z.x+','+z.y+') scale('+z.k+')')}
function pt(e){var p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;return p.matrixTransform(svg.getScreenCTM().inverse())}
function zoomAt(px,py,f){var nk=Math.min(8,Math.max(0.3,z.k*f));z.x=px-(px-z.x)*nk/z.k;z.y=py-(py-z.y)*nk/z.k;z.k=nk;apply()}
function start(){var sc=svg.getScreenCTM(),b=svg.viewBox.baseVal;if(!sc||!sc.a||sc.a>=0.8){z={k:1,x:0,y:0};apply();return}
  var k=Math.min(8,0.85/sc.a),cx=+svg.getAttribute('data-cx'),cy=+svg.getAttribute('data-cy'),mx=b.x+b.width/2,my=b.y+b.height/2;z={k:k,x:mx-cx*k,y:my-cy*k};apply()}
function keepAnchor(anchor,fn){var sel0='.nd[data-id="'+(window.CSS&&CSS.escape?CSS.escape(anchor):anchor)+'"]',a0=svg.querySelector(sel0),s0=svg.getScreenCTM(),P=null;
  if(a0&&s0){var q=svg.createSVGPoint();q.x=+a0.getAttribute('data-x')*z.k+z.x;q.y=+a0.getAttribute('data-y')*z.k+z.y;P=q.matrixTransform(s0)}
  var eff=s0?s0.a*z.k:z.k;fn();var s1=svg.getScreenCTM(),a1=svg.querySelector(sel0);
  if(P&&s1&&a1){z.k=eff/s1.a;var w=P.matrixTransform(s1.inverse());z.x=w.x-(+a1.getAttribute('data-x'))*z.k;z.y=w.y-(+a1.getAttribute('data-y'))*z.k}apply()}
render();fitHeight();z={k:1,x:0,y:0};apply();
var nseg=document.getElementById('nseg');
function drawSeg(){var tot=D.allPaths.length,opts=D.steps.filter(function(n){return n<tot});opts.push(tot);opts=opts.filter(function(n,i){return opts.indexOf(n)===i});nseg.hidden=opts.length<2;
  nseg.innerHTML=opts.map(function(n){return '<button type="button" data-n="'+n+'" aria-pressed="'+(n===D.pathCount)+'" title="'+esc(T.nTip)+'">'+esc(T.paths)+' '+n+'</button>'}).join('');
  var kp=document.getElementById('kpi-paths');if(kp)kp.textContent=D.pathCount}
nseg.addEventListener('click',function(e){var b=e.target.closest('[data-n]');if(!b)return;var n=+b.getAttribute('data-n');if(n===D.pathCount)return;
  build(n);try{localStorage.setItem('sc-n-'+SEED,String(n))}catch(_){}st.exp={};if(sel&&!nodeOf(sel.id))unselect();else if(cur){var nn=nodeOf(cur.id);cur.n=nn?nn.n:0;drawBar()}
  render();fitHeight();z={k:1,x:0,y:0};apply();drawSeg()});
drawSeg();
svg.addEventListener('wheel',function(e){e.preventDefault();var p=pt(e);zoomAt(p.x,p.y,Math.exp(-e.deltaY*0.0015))},{passive:false});
var dr=null,moved=false;
svg.addEventListener('pointerdown',function(e){if(e.button!==0)return;moved=false;dr={p:pt(e),cx:e.clientX,cy:e.clientY,x:z.x,y:z.y,m:false}});
svg.addEventListener('pointermove',function(e){if(!dr)return;if(!dr.m&&Math.abs(e.clientX-dr.cx)+Math.abs(e.clientY-dr.cy)<8)return;
  if(!dr.m){dr.m=true;try{svg.setPointerCapture(e.pointerId)}catch(_){}svg.parentNode.classList.add('grabbing')}var p=pt(e);z.x=dr.x+(p.x-dr.p.x);z.y=dr.y+(p.y-dr.p.y);apply()});
function end(){if(dr){moved=dr.m;svg.parentNode.classList.remove('grabbing')}dr=null}
svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);
// ---- 호버: 키워드를 포함한 경로 강조 · 더보기 숨은 키워드 · 경로 분석 카드 ----
var pop=document.getElementById('pop'),hideT=null,popFor=null,popOn=true,ptog=document.getElementById('poptog');
try{popOn=localStorage.getItem('sc-popOn')!=='0'}catch(_){}
function selMode(){svg.classList.toggle('selmode',!popOn&&!!sel)}
function setPop(v){popOn=v;ptog.setAttribute('aria-pressed',String(v));if(!v){pop.hidden=true;popFor=null;unhl()}selMode();try{localStorage.setItem('sc-popOn',v?'1':'0')}catch(_){}}
setPop(popOn);ptog.addEventListener('click',function(){setPop(!popOn)});
document.addEventListener('keydown',function(e){if(e.key==='Escape'&&!pop.hidden){pop.hidden=true;popFor=null;unhl()}});
function hlKw(k){svg.classList.add('hov');var ids=[].map.call(svg.querySelectorAll('.nd[data-id]'),function(n){return n.getAttribute('data-id')});
  var hit={};ids.forEach(function(id){var parts=id.split('>');if(parts[parts.length-1]===k||(id==='ROOT'&&k===SEED)){
    var a=parts[0];hit[a]=1;for(var i=1;i<parts.length;i++){a+='>'+parts[i];hit[a]=1}
    ids.forEach(function(o){if(o.indexOf(id+'>')===0||id==='ROOT')hit[o]=1})}});hit.ROOT=1;
  svg.querySelectorAll('.hv').forEach(function(x){x.classList.remove('hv')});
  svg.querySelectorAll('[data-id]').forEach(function(x){var id=x.getAttribute('data-id');if(hit[id]||(id==='L'||id==='R'))x.classList.add('hv')})}
function selKw(){return sel?(sel.id==='ROOT'?SEED:sel.id.split('>').pop()):null}
function unhl(){svg.classList.remove('hov');svg.querySelectorAll('.hv').forEach(function(x){x.classList.remove('hv')});if(sel)hlKw(selKw())}
function place(el){var r=el.getBoundingClientRect(),w=pop.offsetWidth,h=pop.offsetHeight,x=r.right+10,y=r.top-8;
  if(x+w>innerWidth-8)x=Math.max(8,r.left-w-10);if(y+h>innerHeight-8)y=Math.max(8,innerHeight-h-8);pop.style.left=x+'px';pop.style.top=y+'px'}
function showPop(html,el,key){if(!popOn)return;clearTimeout(hideT);pop.innerHTML='<button class="px" data-px="1" aria-label="close" title="Esc">\u00d7</button>'+html;pop.hidden=false;popFor=key;place(el)}
function laterHide(){clearTimeout(hideT);hideT=setTimeout(function(){pop.hidden=true;popFor=null;unhl()},popOn?260:0)}
pop.addEventListener('mouseenter',function(){clearTimeout(hideT)});pop.addEventListener('mouseleave',laterHide);
svg.addEventListener('mouseover',function(e){if(dr&&dr.m||!popOn)return;var t=e.target.closest('.nd');if(!t)return;
  var act=t.getAttribute('data-act');
  if(act==='more'){quietId=null;var par=t.getAttribute('data-parent'),n=nodeOf(par.indexOf('>')<0?par:par),cs=(n&&n.c)||[],keep=KEEP[Math.min(par.split('>').length-1,KEEP.length-1)];
    var hidden=cs.slice(keep);if(popFor==='m:'+par){clearTimeout(hideT);return}
    showPop('<div class="ph">'+esc(T.hidden)+' '+hidden.length+'</div><div class="pm2">'+esc(T.hiddenHint)+'</div>'+hidden.map(function(c){return '<button class="hk" data-par="'+esc(par)+'" data-k="'+esc(c.k)+'"><span>'+esc(c.k)+'</span><span>'+c.n+'</span></button>'}).join(''),t,'m:'+par);return}
  var id=t.getAttribute('data-id');if(!id)return;if(id===quietId)return;quietId=null;var k=id==='ROOT'?SEED:id.split('>').pop();hlKw(k);if(id==='ROOT'){clearTimeout(hideT);return}
  if(popFor==='n:'+id){clearTimeout(hideT);return}var nn=nodeOf(id),p=idToPath(id);
  showPop('<div class="ph">'+esc(k)+'</div><div class="pm2">'+esc(T.passing)+' '+(nn?nn.n:0)+' / '+D.pathCount+'</div>'+crumb(p)+'<div class="pb"><button class="btn pri" data-pa="go" data-id="'+esc(id)+'">'+esc(T.analyzeThis)+'</button><button class="btn" data-pa="sel" data-id="'+esc(id)+'">'+esc(T.selectOnly)+'</button></div>',t,'n:'+id)});
svg.addEventListener('mouseleave',function(){quietId=null});
svg.addEventListener('mouseout',function(e){var t=e.target.closest('.nd');if(!t)return;if(e.relatedTarget&&t.contains(e.relatedTarget))return;laterHide()});
pop.addEventListener('click',function(e){if(e.target.closest('[data-px]')){pop.hidden=true;popFor=null;unhl();return}var b=e.target.closest('[data-pa]'),h=e.target.closest('.hk');
  if(b){var id=b.getAttribute('data-id');pop.hidden=true;popFor=null;unhl();choose(id);if(b.getAttribute('data-pa')==='go'&&cur&&!cur.busy)analyze(cur);return}
  if(h){var par=h.getAttribute('data-par'),k=h.getAttribute('data-k'),anc=(par==='L'||par==='R')?'ROOT':par;pop.hidden=true;popFor=null;unhl();
    keepAnchor(anc,function(){st.exp[par]=1;render()});choose(par+'>'+k)}});
svg.addEventListener('click',function(e){if(moved){moved=false;return}var t=e.target.closest('.nd');if(!t){if(sel&&!busyAna())unselect();return}var act=t.getAttribute('data-act');
  if(act){var par=t.getAttribute('data-parent'),anc=(par==='L'||par==='R')?'ROOT':par;keepAnchor(anc,function(){if(act==='more')st.exp[par]=1;else delete st.exp[par];render()});return}
  var id=t.getAttribute('data-id');if(id==='ROOT')return;choose(id)});
document.querySelector('.zoom').addEventListener('click',function(e){var b=e.target.closest('[data-z]');if(!b)return;var c=b.getAttribute('data-z'),vb=svg.viewBox.baseVal;
  if(c==='fit'){z={k:1,x:0,y:0};apply()}else if(c==='start'){start()}else zoomAt(vb.x+vb.width/2,vb.y+vb.height/2,c==='in'?1.35:1/1.35)});
// 노드 찾기 / 펼치기
function findId(k){var best=null;['R','L'].forEach(function(h){(function walk(n,id,d,anc){(n.c||[]).forEach(function(c,i){var cid=id+'>'+c.k,a2=anc.concat([[id,i,d]]);
  if(c.k===k&&(!best||d<best.d))best={id:cid,anc:a2,d:d};walk(c,cid,d+1,a2)})})(D.tree[h],h,0,[])});return best}
function reveal(b){b.anc.forEach(function(a){if(a[1]>=KEEP[Math.min(a[2],KEEP.length-1)])st.exp[a[0]]=1})}
function revealId(id){var parts=id.split('>'),side=parts.shift(),n=D.tree[side],pid=side;for(var i=0;i<parts.length&&n;i++){var cs=n.c||[],j=-1;
  for(var q=0;q<cs.length;q++)if(cs[q].k===parts[i]){j=q;break}if(j<0)return false;if(j>=KEEP[Math.min(i,KEEP.length-1)])st.exp[pid]=1;n=cs[j];pid=pid+'>'+parts[i]}return true}
function nodeOf(id){var parts=id.split('>'),side=parts.shift(),n=D.tree[side];for(var i=0;i<parts.length&&n;i++){n=(n.c||[]).filter(function(c){return c.k===parts[i]})[0]}return n}
// ---------- 선택 · 분석 ----------
var cur=null,MSG=[],bar=document.getElementById('selbar'),thread=document.getElementById('thread'),sugEl=document.getElementById('sug'),qEl=document.getElementById('q'),asking=false;
// 클릭한 키워드(시드 → 키워드 경로의 끝, 앞 검색 쪽이면 맨 앞)를 파란색으로, 시드는 테두리로만
function crumb(p,k){if(k==null)k=p.length<2?p[0]:(p[0]===SEED?p[p.length-1]:p[0]);
  return '<div class="crumb">'+p.map(function(x,i){var cl=(x===k&&(i===0||i===p.length-1))?'cur':(x===SEED?'seed':'');return '<span'+(cl?' class="'+cl+'"':'')+'>'+esc(x)+'</span>'}).join('<i>\u203a</i>')+'</div>'}
var quietId=null;
function choose(id){sel={id:id};quietId=id;if(pop){clearTimeout(hideT);pop.hidden=true;popFor=null}keepAnchor('ROOT',render);if(typeof selMode==='function')selMode();var p=idToPath(id),n=nodeOf(id);cur={path:p,id:id,n:n?n.n:0,res:SAVED[pkey(p)]||null};drawBar();drawSug();
  if(!cur.res)loadSaved(p)}
function unselect(){sel=null;cur=null;keepAnchor('ROOT',render);if(typeof selMode==='function')selMode();unhl();drawBar();drawSug()}
function loadSaved(p){use('db').then(function(db){if(!db)return;return db.doc('pathAna/'+hid(pkey(p))).get().then(function(sn){var d=sn&&sn.exists&&sn.data();
  if(d&&d.key===pkey(p)&&d.r){SAVED[d.key]=d.r;if(cur&&pkey(cur.path)===d.key){cur.res=d.r;cur.at=d.savedAt;drawBar()}}})}).catch(function(){})}
// ---------- 질문·분석 채팅 ----------
function drawBar(){if(!cur){bar.innerHTML='<span class="muted">'+esc(T.selHint)+'</span>';return}
  bar.innerHTML='<span class="lab">'+esc(T.sel)+'</span>'+crumb(cur.path)+'<span class="muted mono" style="font-size:12px">'+esc(T.passing)+' '+cur.n+' / '+D.pathCount+'</span>'
    +'<span class="bb"><button class="btn pri" data-a="go"'+(busyAna()?' disabled':'')+'>'+esc(cur.res?T.reanalyze:T.analyze)+'</button>'
    +(cur.res?'<button class="btn" data-a="showsaved">'+esc(T.viewSaved)+'</button>':'')+'<button class="btn" data-a="unsel">'+esc(T.unsel)+'</button></span>'}
function busyAna(){return MSG.some(function(m){return m.role==='ana'&&m.busy})}
function drawSug(){var s=cur?[T.sgAnalyze,T.sgBeforeAfter.replace('{k}',cur.path[cur.path[0]===SEED?cur.path.length-1:0]),T.sgCompare]:[T.sgFlow,T.sgOpp,T.sgSeg];
  sugEl.innerHTML=s.map(function(x,i){return '<button class="sgb" data-sg="'+i+'">'+esc(x)+'</button>'}).join('');sugEl.__s=s}
function linkKw(t){return esc(t).replace(/「([^」]{1,60})」/g,function(m,k){var kk=k.replace(/&amp;/g,'&');return D.vol[kk]!=null||kk===SEED?'<span class="chip" data-kw2="'+esc(kk)+'">'+esc(kk)+'</span>':m})}
function drawThread(){if(!MSG.length){thread.innerHTML='<div class="empty">'+esc(T.chatEmpty)+'</div>';return}
  thread.innerHTML=MSG.map(function(m,i){
    if(m.role==='u')return '<div class="mu">'+(m.path?crumb(m.path):'')+'<div>'+esc(m.text)+'</div></div>';
    if(m.handoff)return '<div class="ma'+(m.role==='ana'?' ana':'')+'">'+(m.role==='ana'?'<div class="anah"><span class="lab">'+esc(T.anaTitle)+'</span>'+crumb(m.path)+'</div>':'')+hoHtml(m,i)+'</div>';
    if(m.role==='a')return '<div class="ma">'+(m.err?'<div class="note err">'+esc(m.err)+(m.perm?' <button class="btn" data-a="perm">'+esc(T.permBtn)+'</button>':'')+'</div>':(m.text?'<div class="tx">'+linkKw(m.text)+'</div>':'<div class="sk" style="width:60%"></div><div class="sk"></div>'))+'</div>';
    // 경로 분석 메시지
    var h='<div class="ma ana"><div class="anah"><span class="lab">'+esc(m.saved?T.savedAna:T.anaTitle)+'</span>'+crumb(m.path)+'</div>';
    if(m.err)h+='<div class="note err">'+esc(m.err)+(m.perm?' <button class="btn" data-a="perm">'+esc(T.permBtn)+'</button>':'')+'</div>';
    else if(m.busy)h+='<div class="note">'+esc(m.stage||'')+'</div><div class="sk" style="width:70%"></div><div class="sk"></div>';
    else if(m.res)h+=resHtml(m.res,m.at);
    return h+'</div>'}).join('');thread.scrollTop=thread.scrollHeight}
function push(m){MSG.push(m);drawThread();saveChat();return m}
function saveChat(){var keep=MSG.filter(function(m){return !m.busy&&!m.err&&(m.role==='u'||m.role==='a'&&m.text||m.role==='ana'&&m.res)}).slice(-30).map(function(m){
    return m.role==='ana'?{role:'ana',path:m.path,key:pkey(m.path),at:m.at||0,saved:!!m.saved}:{role:m.role,text:m.text,path:m.path||null}});
  use('db').then(function(db){if(db)return db.doc('data/users/me/chat/'+hid(SEED)).set({seed:SEED,items:keep,at:Date.now()})}).catch(function(){})}
function loadChat(){use('db').then(function(db){if(!db)return;return db.doc('data/users/me/chat/'+hid(SEED)).get().then(function(sn){var d=sn&&sn.exists&&sn.data();
  if(d&&d.seed===SEED&&Array.isArray(d.items)&&!MSG.length){MSG=d.items.map(function(x){return x.role==='ana'?{role:'ana',path:x.path,res:SAVED[x.key]||null,at:x.at,saved:x.saved,pending:!SAVED[x.key]}:x});drawThread()}})}).catch(function(){})}
function resHtml(r,at){var vc={'충족':'met','met':'met','充足':'met','부분 충족':'part','partly met':'part','一部充足':'part'}[r.verdict&&r.verdict.met]||'not';
  var h='<div class="res"><p class="purpose">'+esc(r.purpose)+'</p><div style="font-size:13px">'+esc(r.story)+'</div>';
  if(r.insights&&r.insights.length)h+='<div class="ins"><h3>'+esc(T.insights)+'</h3><ul>'+r.insights.map(function(a){return '<li>'+esc(a)+'</li>'}).join('')+'</ul></div>';
  if(r.actions&&r.actions.length)h+='<h3 style="margin-top:10px">'+esc(T.actions)+'</h3><ul style="margin:0;padding-left:18px;font-size:13px">'+r.actions.map(function(a){return '<li>'+esc(a)+'</li>'}).join('')+'</ul>';
  if(r.verdict&&r.verdict.met)h+='<p style="font-size:13px;margin:10px 0 0"><span class="tag t-'+vc+'">'+esc(r.verdict.met)+'</span> '+esc(r.verdict.why)+'</p>';
  if((r.reading&&r.reading.length)||r.ev){h+='<details class="evd"><summary>'+esc(T.basis)+'</summary>';
    if(r.reading&&r.reading.length)h+='<div class="steps">'+r.reading.map(function(x){return '<div class="st"><b>'+esc(x.keyword)+'</b><span class="r">'+esc(x.role)+'</span><div>'+esc(x.meaning)+'</div><div class="s">'+esc(x.serp)+'</div></div>'}).join('')+'</div>';
    if(r.ev)h+='<details style="margin-top:8px"><summary>'+esc(T.evidence2)+'</summary>'+r.ev.map(evHtml).join('')+'</details>';
    h+='</details>'}
  if(at)h+='<div class="muted" style="font-size:11.5px;margin-top:8px">'+esc(T.savedAt)+' '+new Date(at).toLocaleString()+'</div>';
  return h+'</div>'}
function evHtml(x){var h='<div style="margin-top:8px"><b style="font-size:12.5px">'+esc(x.k)+'</b> <span class="muted" style="font-size:11.5px">'+esc((x.at||'').slice(0,10))+'</span>';
  if(x.err)return h+' <span class="muted">'+esc(x.err)+'</span></div>';
  h+='<div class="aio">'+(x.aio?esc(x.aio).replace(/\n/g,'<br>'):esc(T.noaio))+'</div><div class="org">'+(x.top||[]).map(function(o){return '<div><small>'+o.position+' \u00b7 '+esc(o.site)+'</small> <a href="'+esc(/^https?:/.test(o.url)?o.url:'#')+'" target="_blank" rel="noopener">'+esc(o.title)+'</a></div>'}).join('')+'</div></div>';return h}
document.getElementById('chat').addEventListener('click',function(e){var a=e.target.closest('[data-a]'),sg=e.target.closest('[data-sg]'),kw=e.target.closest('[data-kw2]');
  if(kw){pick(kw.getAttribute('data-kw2'));return}
  if(sg){var t=sugEl.__s[+sg.getAttribute('data-sg')];if(cur&&t===T.sgAnalyze){if(!busyAna())analyze(cur)}else ask(t);return}
  if(!a)return;var w=a.getAttribute('data-a');
  if(w==='go'&&cur&&!busyAna())analyze(cur);
  else if(w==='unsel')unselect();
  else if(w==='recopy'){var mm=MSG[+a.getAttribute('data-i')],ta=thread.querySelector('textarea[data-ho="'+a.getAttribute('data-i')+'"]');if(mm)copyText(mm.handoff,ta).then(function(ok){mm.copied=!!ok;drawThread()})}
  else if(w==='showsaved'&&cur&&cur.res)push({role:'ana',path:cur.path,res:cur.res,at:cur.at,saved:true});
  else if(w==='perm')use('permissions').then(function(pm){if(pm&&pm.manage)return pm.manage()}).catch(function(){alert(T.permMenu)})});
document.getElementById('send').addEventListener('click',function(){ask(qEl.value)});
qEl.addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();ask(qEl.value)}});
function chatContext(){var L=['시드: '+SEED+' · 경로 '+D.pathCount+'개'],N=D.tree.R.c||[],P=D.tree.L.c||[];
  L.push('바로 다음 검색: '+N.map(function(c){return c.k+'('+c.n+')'}).slice(0,15).join(', '));
  if(P.length)L.push('바로 앞 검색: '+P.map(function(c){return c.k+'('+c.n+')'}).slice(0,10).join(', '));
  N.slice(0,5).forEach(function(c){if(c.c)L.push(c.k+' 다음: '+c.c.map(function(x){return x.k+'('+x.n+')'}).slice(0,8).join(', '))});
  var paths=D.paths;if(cur){var kk=cur.path[cur.path[0]===SEED?cur.path.length-1:0];L.push('선택한 경로: '+cur.path.join(' → ')+' (이 지점을 지나는 경로 '+cur.n+'개)');
    paths=D.paths.filter(function(p){return p.indexOf(kk)>=0});L.push('「'+kk+'」를 포함한 경로 '+paths.length+'개 중 일부:');
    if(cur.res)L.push('이 경로의 저장된 분석 · 목적: '+cur.res.purpose+' / 인사이트: '+(cur.res.insights||[]).join(' / '))}
  else L.push('대표 경로:');
  paths.slice(0,45).forEach(function(p){L.push('- '+p.join(' → '))});
  if(D.summary)L.push('리포트 요약: '+D.summary);if(D.acts&&D.acts.length)L.push('리포트의 마케팅 할 일: '+D.acts.join(' / '));
  return L.join('\n')}
function ask(text){var q=String(text||'').trim();if(!q||asking)return;
  if(GPT){qEl.value='';push({role:'u',text:q,path:cur?cur.path:null});var hist0=MSG.filter(function(x){return x.role==='u'}).slice(-6,-1).map(function(x){return '질문: '+x.text}).join('\n');
    handoff({role:'a',handoff:T.chatPrompt.replace('{ctx}',function(){return chatContext()}).replace('{hist}',function(){return hist0||'없음'}).replace('{q}',function(){return q}).replace('{lang}',function(){return T.langName})});return}
  qEl.value='';asking=true;
  push({role:'u',text:q,path:cur?cur.path:null});var m=push({role:'a',text:'',busy:true});
  use('sample').then(function(sample){if(!sample){m.busy=false;m.err=T.noSample;m.perm=true;asking=false;drawThread();return}
    var hist=MSG.filter(function(x){return (x.role==='u'||x.role==='a'&&x.text)&&x!==m}).slice(-7,-1).map(function(x){return (x.role==='u'?'질문: ':'답: ')+x.text}).join('\n');
    var prompt=T.chatPrompt.replace('{ctx}',function(){return chatContext()}).replace('{hist}',function(){return hist||'없음'}).replace('{q}',function(){return q}).replace('{lang}',function(){return T.langName});
    return sample(prompt,{onText:function(o){m.text=o.text;var el=thread.lastElementChild;if(el)el.innerHTML='<div class="tx">'+linkKw(o.text)+'</div>';thread.scrollTop=thread.scrollHeight}}).then(function(r){
      m.text=(r&&r.text)||m.text;m.busy=false;asking=false;drawThread();saveChat()})})
  .catch(function(e){m.busy=false;asking=false;m.err={not_granted:T.noSample,rate_limited:T.rate}[e&&e.code]||T.failed;m.perm=e&&e.code==='not_granted';if(e&&e.text)m.text=e.text;drawThread()})}
var MCPMSG=T.mcp;
function serpOne(k,db,mcp){var key='serp/'+hid(k);if(D.pre&&D.pre[k])return Promise.resolve(D.pre[k]);
  return (db?db.doc(key).get().then(function(sn){var d=sn&&sn.exists&&sn.data();return d&&d.k===k?d:null}).catch(function(){return null}):Promise.resolve(null)).then(function(hit){
    if(hit)return hit;if(!mcp)return {k:k,err:T.noMcp};
    return mcp.callTool(D.lm,'serp',{gl:D.gl,keyword:k,num:10}).then(function(r){var pl=r&&r.payload;if(typeof pl==='string'){try{pl=JSON.parse(pl)}catch(_){}}
      if(!pl||typeof pl!=='object')return {k:k,err:T.badSerp};if(pl.result&&pl.result!=='OK')return {k:k,err:pl.reason||T.badSerp};
      var data=pl.data||[],ab=data.filter(function(b){return b.type==='ai_overview'})[0],aio='';
      if(ab){(ab.text_blocks||[]).forEach(function(b){if(b.type==='list'){(function w(l,d){(l||[]).forEach(function(i){aio+='  '.repeat(d)+'- '+(i.snippet||'')+'\n';w(i.list,d+1)})})(b.list,0)}else if(b.snippet)aio+=b.snippet+'\n'})}
      var top=data.filter(function(b){return b.type==='organic_results'}).sort(function(a,b){return (a.position||99)-(b.position||99)}).slice(0,3).map(function(b){return {position:b.position,site:b.site_name||'',title:b.title||'',url:b.url||'',snippet:b.snippet||''}});
      var v={k:k,at:pl.collected_at||'',aio:aio.slice(0,2400),top:top};if(db)db.doc(key).set(v).catch(function(){});return v},
      function(err){var c=err&&err.code;return {k:k,err:MCPMSG[c]||(err&&err.message)||T.badSerp,code:c}})})}
function analyze(c){if(GPT){push({role:'u',text:T.sgAnalyze,path:c.path});handoff({role:'ana',path:c.path.slice(),handoff:T.prompt.replace('{path}',function(){return c.path.join(' → ')}).replace('{lang}',function(){return T.langName})});return}
  var cm=push({role:'u',text:T.sgAnalyze,path:c.path});c=push({role:'ana',path:c.path.slice(),busy:true,stage:T.stSerp});var drawSel=function(){drawThread();drawBar()};drawSel();
  Promise.all([use('db'),use('mcp'),use('sample')]).then(function(r){var db=r[0],mcp=r[1],sample=r[2];
    if(!sample){c.busy=false;c.err=T.noSample;c.perm=true;drawSel();return}
    if(!mcp){c.busy=false;c.err=T.noMcp;c.perm=true;drawSel();return}
    var ks=c.path.filter(function(k,i){return c.path.indexOf(k)===i});
    var out=[],i=0;function next(){if(i>=ks.length)return Promise.resolve();var k=ks[i++];c.stage=T.stSerp+' ('+i+'/'+ks.length+') '+k;drawSel();return serpOne(k,db,mcp).then(function(v){out.push(v);return next()})}
    return next().then(function(){var bad=out.filter(function(x){return x.code==='server_not_connected'||x.code==='needs_reauth'||x.code==='not_in_manifest'||x.code==='blocked_by_policy'})[0];
      if(bad){c.busy=false;c.err=bad.err;c.perm=bad.code==='not_in_manifest';drawSel();return}
      if(!out.some(function(x){return !x.err})){c.busy=false;c.err=out[0]&&out[0].err||T.badSerp;drawSel();return}
      c.stage=T.stLlm;drawSel();
      var ev=out.map(function(x,j){var code='E'+(j+1);if(x.err)return code+' 「'+x.k+'」 SERP 없음';return code+' 「'+x.k+'」 (수집 '+(x.at||'').slice(0,10)+')\n'+code+'-AI AI 개요: '+(x.aio?x.aio.replace(/\n/g,' ').slice(0,1400):'없음')+'\n'+x.top.map(function(o){return code+'-'+o.position+' ['+o.site+'] '+o.title+' — '+o.snippet}).join('\n')}).join('\n\n');
      var prompt=T.prompt.replace('{path}',function(){return c.path.join(' → ')}).replace('{ev}',function(){return ev}).replace('{lang}',function(){return T.langName});
      return sample.json(prompt).then(function(res){if(!res||!res.purpose)throw {code:'invalid'};
        var clean={purpose:String(res.purpose).slice(0,300),story:String(res.story||'').slice(0,900),
          reading:(res.reading||[]).filter(function(x){return c.path.indexOf(x.keyword)>=0}).slice(0,10).map(function(x){return {keyword:x.keyword,role:String(x.role||'').slice(0,20),meaning:String(x.meaning||'').slice(0,400),serp:String(x.serp||'').slice(0,400)}}),
          verdict:{met:String((res.verdict||{}).met||''),why:String((res.verdict||{}).why||'').slice(0,500)},
          insights:(res.insights||[]).slice(0,3).map(function(a){return String(a).slice(0,400)}),
          actions:(res.actions||[]).slice(0,3).map(function(a){return String(a).slice(0,300)}),ev:out};
        var key=pkey(c.path),at=Date.now();SAVED[key]=clean;c.res=clean;c.at=at;c.busy=false;if(cur&&pkey(cur.path)===key){cur.res=clean;cur.at=at}drawSel();saveChat();keepAnchor('ROOT',render);
        if(db)db.doc('pathAna/'+hid(key)).set({key:key,path:c.path,r:clean,savedAt:at}).then(loadList).catch(function(){})})})
  }).catch(function(e){c.busy=false;c.err={not_granted:T.noSample,rate_limited:T.rate}[e&&e.code]||T.failed;c.perm=e&&e.code==='not_granted';drawSel()})}
// ---------- 저장된 분석 ----------
var svl=document.getElementById('savedlist');
function loadList(){use('db').then(function(db){if(!db){svl.innerHTML='<p class="muted">'+esc(T.noRuntime)+'</p>';return}
  return db.collection('pathAna').orderBy('savedAt','desc').limit(200).get().then(function(q){var rows=[];q.docs.forEach(function(sn){var d=sn.data();if(d&&d.key&&d.r){SAVED[d.key]=d.r;rows.push(d)}});
    var ch=false;MSG.forEach(function(m){if(m.pending&&SAVED[pkey(m.path)]){m.res=SAVED[pkey(m.path)];m.pending=false;ch=true}});if(ch)drawThread();
    keepAnchor('ROOT',render);if(!rows.length){svl.innerHTML='<p class="muted">'+esc(T.noSaved)+'</p>';return}
    svl.innerHTML=rows.map(function(d,i){return '<details class="svc"><summary><span class="num">'+(i+1)+'</span><span class="hd"><b>'+esc(d.r.purpose)+'</b>'+crumb(d.path)+'</span>'
      +'<span class="meta"><span>'+new Date(d.savedAt).toLocaleDateString()+'</span><span class="tg"><span class="o">'+esc(T.detail)+'</span><span class="c">'+esc(T.close)+'</span></span></span></summary>'
      +'<div class="bd">'+resHtml(d.r,d.savedAt)+'</div><div class="acts2"><button class="btn" data-open="'+esc(d.key)+'">'+esc(T.showMap)+'</button><button class="btn" data-del="'+esc(d.key)+'">'+esc(T.del)+'</button></div></details>'}).join('');
    // 하나를 열면 나머지는 닫아 어디까지가 한 분석인지 분명하게
    svl.querySelectorAll('details.svc').forEach(function(dt){dt.addEventListener('toggle',function(){if(dt.open)svl.querySelectorAll('details.svc[open]').forEach(function(o){if(o!==dt)o.open=false})})})})})
  .catch(function(){svl.innerHTML='<p class="muted">'+esc(T.noSaved)+'</p>'})}
svl.addEventListener('click',function(e){var o=e.target.closest('[data-open]'),dl=e.target.closest('[data-del]');
  if(o){var p=o.getAttribute('data-open').split(' > '),id=p[0]===SEED?'R>'+p.slice(1).join('>'):'L>'+p.slice(0,-1).reverse().join('>');
    if(revealId(id)){choose(id);var r=SAVED[o.getAttribute('data-open')];if(r)push({role:'ana',path:p,res:r,saved:true})}document.getElementById('mapsec').scrollIntoView({behavior:'smooth',block:'start'})}
  if(dl&&confirm(T.delAsk)){var key=dl.getAttribute('data-del');use('db').then(function(db){if(db)return db.doc('pathAna/'+hid(key)).delete()}).then(function(){delete SAVED[key];loadList()}).catch(function(){})}});
loadList();
// ---------- 키워드 찾기 · 마케팅 액션 키워드 ----------
var fq=document.getElementById('fq'),fl=document.getElementById('flist');
function drawFind(){var q=(fq.value||'').replace(/\s+/g,'').toLowerCase();var ks=Object.keys(D.vol).filter(function(k){return !q||k.replace(/\s+/g,'').toLowerCase().indexOf(q)>=0}).sort(function(a,b){return (D.vol[b]||0)-(D.vol[a]||0)});
  fl.innerHTML=ks.slice(0,300).map(function(k){return '<button class="fi" data-k="'+esc(k)+'"><span class="k">'+esc(k)+'</span><span class="v">'+Number(D.vol[k]||0).toLocaleString()+'</span></button>'}).join('')}
function pick(k){var b=findId(k);if(!b){return}reveal(b);choose(b.id)}
fq.addEventListener('input',function(){fl.hidden=false;drawFind()});
document.getElementById('ftog').addEventListener('click',function(){fl.hidden=!fl.hidden;if(!fl.hidden)drawFind()});
fl.addEventListener('click',function(e){var b=e.target.closest('.fi');if(b){pick(b.getAttribute('data-k'));fl.hidden=true}});
document.querySelectorAll('[data-kw]').forEach(function(c){c.addEventListener('click',function(){pick(c.getAttribute('data-kw'));document.getElementById('mapsec').scrollIntoView({behavior:'smooth',block:'start'})})});
drawBar();drawSug();drawThread();loadChat();
})();
"""

JS_T = {
    "kr": {"noRuntime": "이 페이지는 Claude.ai에 게시된 상태에서 열어야 경로 분석과 저장이 동작합니다. (맵 보기는 그대로 됩니다)",
           "noSample": "Claude 연결이 필요합니다. 페이지에서 Claude 사용을 허용한 뒤 다시 눌러 주세요.",
           "noMcp": "ListeningMind 커넥터 연결이 필요합니다. claude.ai 설정의 커넥터에서 ListeningMind를 연결한 뒤 다시 눌러 주세요.",
           "badSerp": "SERP를 불러오지 못했습니다.", "rate": "요청이 많아 잠시 멈췄습니다. 조금 뒤 다시 눌러 주세요.", "failed": "분석을 만들지 못했습니다. 다시 눌러 주세요.",
           "stSerp": "SERP 불러오는 중", "stLlm": "Claude가 검색 목적을 분석하는 중", "savedAt": "저장", "evidence2": "SERP 원문 (AI 개요 · 1~3위)", "delAsk": "이 분석을 지울까요?",
           "langName": "한국어", "chat": "질문·경로 분석", "chatHint": "맵에서 경로를 고르거나, 궁금한 것을 바로 물어보세요", "chatPh": "예: 노스페이스 패딩을 찾은 사람들은 다음에 어디로 가나요? (Enter로 보내기)", "send": "보내기",
           "chatEmpty": "맵에서 키워드를 눌러 경로를 고른 뒤 「경로 분석」을 누르거나, 아래에 질문을 입력하세요. 답은 이 페이지의 경로 데이터를 근거로 합니다.",
           "unsel": "선택 해제", "viewSaved": "저장된 분석 보기", "anaTitle": "경로 분석", "savedAna": "저장된 분석",
           "sgAnalyze": "이 경로 분석해줘", "sgBeforeAfter": "「{k}」 앞뒤로 사람들은 무엇을 검색해?", "sgCompare": "이 경로와 비슷한 다른 경로는?",
           "sgFlow": "가장 큰 흐름은 뭐야?", "sgOpp": "마케팅 기회가 큰 경로는?", "sgSeg": "성별·가격 같은 조건이 붙는 경로는?",
           "chatPrompt": "너는 검색 경로 분석가이자 마케터다. 아래는 리스닝마인드 패스파인더에서 뽑은 검색 경로 데이터다. 이 데이터만 근거로 사용자의 질문에 짧고 분명하게 답해라.\n\n[데이터]\n{ctx}\n\n[앞선 대화]\n{hist}\n\n[질문]\n{q}\n\n규칙: 데이터에 없는 사실을 지어내지 마라. 숫자는 데이터에 있는 경로 수만 쓰고, 경로 수는 표본이라 비중으로 해석해라. 키워드는 「」로 감싸 원문 그대로 써라. 3~6문장이나 짧은 줄 목록으로 답하고 마크다운 제목·표·굵게는 쓰지 마라. SERP(검색 결과) 내용이 필요한 질문이면 그 경로를 골라 「경로 분석」을 하라고 권해라. 답변 언어: {lang}.", "permBtn": "권한 설정 열기", "insights": "이 경로에서 보이는 인사이트", "basis": "근거 보기 · 단계별 SERP 분석", "hidden": "숨겨진 키워드", "hiddenHint": "누르면 펼쳐서 선택합니다", "analyzeThis": "이 경로 분석", "selectOnly": "선택", "detail": "분석 내용 보기", "close": "접기", "showMap": "맵에서 보기", "permMenu": "아티팩트 상단의 권한(Permissions) 메뉴에서 Claude와 ListeningMind 사용을 허용해 주세요.",
           "mcp": {"server_not_connected": "ListeningMind 커넥터가 연결돼 있지 않습니다. claude.ai 설정의 커넥터에서 연결해 주세요.",
                   "needs_reauth": "ListeningMind 연결이 만료됐습니다. claude.ai 설정의 커넥터에서 다시 연결해 주세요.",
                   "not_in_manifest": "이 페이지에서 ListeningMind 사용이 허용되지 않았습니다.", "blocked_by_policy": "조직 정책으로 ListeningMind를 쓸 수 없습니다.",
                   "server_unavailable": "ListeningMind 서버가 잠시 응답하지 않습니다.", "selection_required": "ListeningMind 커넥터를 골라 주세요."}},
    "us": {"noRuntime": "Open this page as a published Claude.ai artifact to analyze and save paths. (The map still works.)",
           "noSample": "Claude access is needed. Allow Claude on this page and click again.",
           "noMcp": "The ListeningMind connector is needed. Connect it in claude.ai Settings → Connectors and click again.",
           "badSerp": "Could not load the SERP.", "rate": "Too many requests. Try again shortly.", "failed": "Could not create the analysis. Try again.",
           "stSerp": "Loading SERPs", "stLlm": "Claude is analyzing the search purpose", "savedAt": "Saved", "evidence2": "Raw SERPs (AI Overview · top 3)", "delAsk": "Delete this analysis?",
           "langName": "English", "chat": "Ask · analyze paths", "chatHint": "Pick a path on the map or just ask", "chatPh": "e.g. Where do people go after searching for the North Face padding? (Enter to send)", "send": "Send",
           "chatEmpty": "Pick a keyword on the map and press “Analyze path”, or type a question below. Answers are based on this page's path data.",
           "unsel": "Clear", "viewSaved": "View saved analysis", "anaTitle": "Path analysis", "savedAna": "Saved analysis",
           "sgAnalyze": "Analyze this path", "sgBeforeAfter": "What do people search before and after “{k}”?", "sgCompare": "Which other paths are similar?",
           "sgFlow": "What is the biggest flow?", "sgOpp": "Which paths are the best marketing opportunities?", "sgSeg": "Which paths add conditions like gender or price?",
           "chatPrompt": "You are a search-path analyst and marketer. Below is ListeningMind PathFinder path data. Answer the user's question briefly and clearly using only this data.\n\n[Data]\n{ctx}\n\n[Previous turns]\n{hist}\n\n[Question]\n{q}\n\nRules: do not invent facts. Use only path counts present in the data and read them as shares of a sample. Wrap keywords in 「」 exactly as written. Answer in 3-6 sentences or a short line list, no markdown headings, tables or bold. If the question needs SERP content, suggest picking that path and running “Analyze path”. Answer language: {lang}.", "permBtn": "Open permissions", "insights": "Insights from this path", "basis": "Show evidence · step-by-step SERP analysis", "hidden": "Hidden keywords", "hiddenHint": "Click to expand and select", "analyzeThis": "Analyze this path", "selectOnly": "Select", "detail": "Show analysis", "close": "Collapse", "showMap": "Show on map", "permMenu": "Allow Claude and ListeningMind in the artifact's Permissions menu.",
           "mcp": {"server_not_connected": "ListeningMind is not connected. Connect it in claude.ai Settings → Connectors.",
                   "needs_reauth": "ListeningMind connection expired. Reconnect it in Settings → Connectors.",
                   "not_in_manifest": "This page is not allowed to use ListeningMind.", "blocked_by_policy": "Your organization blocks ListeningMind here.",
                   "server_unavailable": "ListeningMind is temporarily unavailable.", "selection_required": "Choose which ListeningMind connector to use."}},
    "jp": {"noRuntime": "経路分析と保存はClaude.aiで公開されたページで動作します。（マップ表示はそのまま使えます）",
           "noSample": "Claudeの接続が必要です。ページでClaudeの利用を許可してから再度押してください。",
           "noMcp": "ListeningMindコネクタの接続が必要です。claude.aiの設定→コネクタで接続してから再度押してください。",
           "badSerp": "SERPを取得できませんでした。", "rate": "リクエストが多いため一時停止しました。", "failed": "分析を作成できませんでした。",
           "stSerp": "SERP取得中", "stLlm": "Claudeが検索目的を分析中", "savedAt": "保存", "evidence2": "SERP原文（AI概要・1〜3位）", "delAsk": "この分析を削除しますか？",
           "langName": "日本語", "chat": "質問・経路分析", "chatHint": "マップで経路を選ぶか、そのまま質問してください", "chatPh": "例：ノースフェイスのダウンを検索した人は次にどこへ？（Enterで送信）", "send": "送信",
           "chatEmpty": "マップでキーワードを押して「経路分析」を押すか、下に質問を入力してください。回答はこのページの経路データに基づきます。",
           "unsel": "選択解除", "viewSaved": "保存した分析を見る", "anaTitle": "経路分析", "savedAna": "保存した分析",
           "sgAnalyze": "この経路を分析して", "sgBeforeAfter": "「{k}」の前後で何を検索している？", "sgCompare": "この経路に似た経路は？",
           "sgFlow": "一番大きな流れは？", "sgOpp": "マーケティング機会が大きい経路は？", "sgSeg": "性別や価格の条件が付く経路は？",
           "chatPrompt": "あなたは検索経路のアナリスト兼マーケターです。以下はListeningMind PathFinderの経路データです。このデータだけを根拠に、質問に短く明確に答えてください。\n\n[データ]\n{ctx}\n\n[これまでの会話]\n{hist}\n\n[質問]\n{q}\n\nルール：データにない事実を作らない。経路数はデータにあるものだけを使い、サンプルの比率として解釈する。キーワードは「」で原文のまま囲む。3〜6文か短い箇条で答え、見出し・表・太字は使わない。SERPの内容が必要なら、その経路を選んで「経路分析」をするよう勧める。回答言語：{lang}。", "permBtn": "権限設定を開く", "insights": "この経路から見えるインサイト", "basis": "根拠を見る・段階別SERP分析", "hidden": "隠れたキーワード", "hiddenHint": "押すと展開して選択します", "analyzeThis": "この経路を分析", "selectOnly": "選択", "detail": "分析内容を見る", "close": "閉じる", "showMap": "マップで表示", "permMenu": "アーティファクトの権限メニューでClaudeとListeningMindを許可してください。",
           "mcp": {"server_not_connected": "ListeningMindが接続されていません。設定→コネクタで接続してください。", "needs_reauth": "ListeningMindの接続が切れました。再接続してください。",
                   "not_in_manifest": "このページではListeningMindを使えません。", "blocked_by_policy": "組織のポリシーでListeningMindを使えません。",
                   "server_unavailable": "ListeningMindが一時的に応答しません。", "selection_required": "ListeningMindコネクタを選んでください。"}},
}

PROMPT = """너는 검색 행동 분석가이자 마케터다. 한 사람이 Google에서 아래 순서대로 이어서 검색했다(리스닝마인드 패스파인더 경로). 각 키워드에 저장된 Google SERP 스냅샷의 AI 개요와 검색 결과 1~3위를 붙였다.

경로: {path}

{ev}

할 일:
1. 마지막 키워드와 뒤로 갈수록 붙는 조건(브랜드, 상품, 성별, 가격, 행동 등)을 근거로, 경로 전체가 향하는 최종 검색 목적을 한 문장으로 정해라.
2. 그 목적에 비추어 각 검색을 다시 읽어라. 뒤 키워드를 알고 나면 앞 검색이 실제로 무엇을 찾던 것인지 분명해진다. 각 검색의 역할과, 그 SERP가 무엇을 보탰고 무엇이 모자라 다음 검색이 필요했는지 써라.
3. SERP를 모두 합쳐 최종 목적이 해결됐는지 판정해라.
4. 이 경로에서 읽을 수 있는 인사이트를 1~3개 적어라. 단계 요약을 반복하지 말고, 경로 전체를 보아야 드러나는 것을 써라: 소비자가 무엇을 기준으로 비교·결정하는지, 어떤 브랜드·상품이 기준점이나 대안 역할을 하는지, SERP가 어디서 사람을 다른 곳으로 보내는지, 검색 목적과 SERP 사이의 빈틈 등. 각 인사이트에 근거를 붙여라.
5. 이 경로를 근거로 마케터가 할 일을 1~3개 적어라(콘텐츠, SERP 노출, 상품 페이지, 광고 키워드 등 구체적으로).

원칙: 위 SERP와 키워드만 근거로 삼고 없는 사실을 지어내지 마라. SERP 수집일은 실제 검색 시점과 다를 수 있다. 근거는 E1, E2-AI, E3-1 같은 번호로 쓰지 말고 「키워드」 AI 개요, 「키워드」 검색 결과 2위(사이트명)처럼 읽는 사람이 바로 알 수 있는 말로 써라(번호는 위 자료를 정리하려고 붙인 것이며 읽는 사람에게는 보이지 않는다). 근거가 약하면 추정이라고 밝혀라. 숫자로 단정하지 마라. 답변 언어: {lang}. 키워드는 원문 그대로 둔다.

JSON 하나만 출력해라. 다른 글이나 코드 블록 표시는 쓰지 마라.
{"purpose":"최종 검색 목적 한 문장","story":"경로를 하나의 과정으로 읽은 해석 2~3문장","reading":[{"keyword":"경로의 키워드 그대로","role":"역할, 6자 안팎","meaning":"다시 읽은 이 검색의 의미 1문장","serp":"이 SERP가 보탠 것과 모자랐던 것 1문장 (근거는 「키워드」 AI 개요, 「키워드」 검색 결과 N위(사이트명)처럼)"}],"verdict":{"met":"충족, 부분 충족, 미충족 중 하나","why":"1~2문장"},"insights":["경로 전체에서 읽히는 인사이트 1문장 (근거: 「키워드」 AI 개요 또는 검색 결과 N위(사이트명))"],"actions":["마케터가 할 일"]}"""
# ChatGPT 모드 경로 분석 요청문: SERP는 사용자의 ChatGPT가 ListeningMind 커넥터로 직접 조회한다
def gpt_prompt(base, gl, lm):
    p = base.replace("각 키워드에 저장된 Google SERP 스냅샷의 AI 개요와 검색 결과 1~3위를 붙였다.",
                     f"각 키워드의 Google SERP는 {lm} 커넥터의 serp 도구로 직접 조회해라(gl={gl}, num=10). 근거는 「키워드」 AI 개요, 「키워드」 검색 결과 N위(사이트명)처럼 써라. 커넥터를 쓸 수 없으면 SERP를 지어내지 말고 연결이 필요하다고만 답해라.")
    p = p.replace("{ev}\n\n", "")
    i = p.index("\n\nJSON 하나만 출력해라")
    return p[:i] + "\n\n결과는 이 순서로 짧게 써라: 최종 검색 목적(한 문장) → 경로 해석(2~3문장) → 단계별 읽기(키워드마다 역할·의미·SERP 근거 한 줄) → 판정(충족·부분 충족·미충족 중 하나와 이유) → 인사이트(1~3개, 근거 출처) → 마케터가 할 일(1~3개). 마크다운 제목과 표는 쓰지 마라."

GPT_T = {
    "kr": {"analyze": "경로 분석 요청 복사", "reanalyze": "경로 분석 요청 복사", "analyzeThis": "이 경로 분석 요청 복사",
           "chatHint": "질문하거나 경로 분석을 누르면 이 페이지의 경로 데이터를 담은 요청문이 복사됩니다",
           "chatEmpty": "맵에서 키워드를 눌러 경로를 고른 뒤 「경로 분석 요청 복사」를 누르거나, 아래에 질문을 입력하세요. 이 페이지의 경로 데이터를 담은 요청문이 복사되니 ChatGPT 대화창에 붙여 넣으면 답을 받을 수 있습니다.",
           "chatPh": "예: 축구화를 찾은 사람들은 다음에 어디로 가나요? (Enter로 요청문 만들기)", "send": "요청문 만들기",
           "gptCopied": "요청문을 복사했습니다. ChatGPT 대화창에 붙여 넣어 보내세요. 경로 분석은 ChatGPT에 연결된 ListeningMind 커넥터로 SERP를 조회합니다.",
           "gptCopyFail": "자동 복사가 막혔습니다. 아래 요청문을 선택해 복사한 뒤 ChatGPT 대화창에 붙여 넣으세요.", "gptCopy": "다시 복사",
           "mapHint": "시드를 가운데 두고 왼쪽은 그 전에, 오른쪽은 그 뒤에 검색한 것입니다. 키워드를 누르면 시드부터 그 키워드까지의 경로가 선택되고, 맵 아래에서 그 경로의 분석 요청문을 만들 수 있습니다. 처음에는 전체가 맞춤으로 보이고, 휠로 확대·축소합니다.",
           "foot": "경로는 리스닝마인드 패스파인더 현재 시점 표본입니다. SERP는 저장된 Google 스냅샷이며 수집일이 키워드마다 다를 수 있습니다. 요약과 할 일은 위 데이터만 근거로 ChatGPT가 작성했습니다."},
    "us": {"analyze": "Copy path-analysis request", "reanalyze": "Copy path-analysis request", "analyzeThis": "Copy analysis request",
           "chatHint": "Asking or analyzing copies a request containing this page's path data",
           "chatEmpty": "Pick a path on the map and click “Copy path-analysis request”, or type a question below. A request with this page's path data is copied; paste it into your ChatGPT chat to get the answer.",
           "chatPh": "e.g. Where do people go after searching for football boots? (Enter to build the request)", "send": "Build request",
           "gptCopied": "Request copied. Paste it into your ChatGPT chat and send it. Path analysis looks up SERPs through the ListeningMind connector in ChatGPT.",
           "gptCopyFail": "Automatic copy was blocked. Select the request below, copy it and paste it into your ChatGPT chat.", "gptCopy": "Copy again",
           "mapHint": "The seed sits in the middle: searches before it on the left, after it on the right. Click a keyword to select the path from the seed to it, then build an analysis request for it below the map. The map starts fitted; use the wheel to zoom.",
           "foot": "Paths are a current ListeningMind PathFinder sample. SERPs are stored Google snapshots; collection dates can differ by keyword. The summary and actions were written by ChatGPT from the data above only."},
    "jp": {"analyze": "経路分析リクエストをコピー", "reanalyze": "経路分析リクエストをコピー", "analyzeThis": "分析リクエストをコピー",
           "chatHint": "質問や経路分析を押すと、このページの経路データを含むリクエストがコピーされます",
           "chatEmpty": "マップでキーワードを押して経路を選び「経路分析リクエストをコピー」を押すか、下に質問を入力してください。経路データを含むリクエストがコピーされるので、ChatGPTの会話欄に貼り付けると回答が得られます。",
           "chatPh": "例：サッカースパイクを調べた人は次に何を検索しますか？（Enterでリクエスト作成）", "send": "リクエスト作成",
           "gptCopied": "リクエストをコピーしました。ChatGPTの会話欄に貼り付けて送信してください。経路分析はChatGPTに接続したListeningMindコネクタでSERPを取得します。",
           "gptCopyFail": "自動コピーがブロックされました。下のリクエストを選択してコピーし、ChatGPTの会話欄に貼り付けてください。", "gptCopy": "もう一度コピー",
           "mapHint": "シードを中央に、左はその前、右はその後の検索です。キーワードを押すとシードからそのキーワードまでの経路が選ばれ、マップ下で分析リクエストを作れます。最初は全体表示で、ホイールで拡大・縮小します。",
           "foot": "経路はListeningMind PathFinderの現在のサンプルです。SERPは保存されたGoogleスナップショットです。要約とやることは上記データのみを根拠にChatGPTが作成しました。"},
}


def detect_host(v):
    """HTML을 만드는 LLM 도구. 명시가 기본이고, auto는 파일 시스템으로 추정한다."""
    if v in ("claude", "chatgpt"):
        return v
    if Path("/mnt/user-data").exists():
        return "claude"
    if Path("/mnt/data").exists():
        return "chatgpt"
    sys.exit("❌ 실행 중인 LLM 도구를 알 수 없습니다. render에 --host claude 또는 --host chatgpt 를 넘기세요.")


PROMPT_MET = {"kr": None, "us": ("충족, 부분 충족, 미충족 중 하나", "one of: met, partly met, not met"), "jp": ("충족, 부분 충족, 미충족 중 하나", "充足、一部充足、未充足のいずれか")}


def cmd_render(a):
    plan = load_json(a.plan)
    ev = load_json(a.evidence) if a.evidence and Path(a.evidence).exists() else []
    raw = load_json(a.analysis)
    host = detect_host(a.host)
    T = dict(LABELS.get(a.lang, LABELS["kr"]))
    G = GPT_T.get(a.lang, GPT_T["kr"]) if host == "chatgpt" else {}
    for k in ("analyze", "reanalyze", "mapHint", "foot"):
        if k in G:
            T[k] = G[k]
    e = html.escape
    kwset = set(plan["volumes"]) | {plan["seed"]}
    acts = []
    warn = []
    for x in (raw.get("actions") or [])[:6]:
        kws = [k for k in (x.get("keywords") or []) if k in kwset]
        dropped = [k for k in (x.get("keywords") or []) if k not in kwset]
        if dropped:
            warn.append(f"경로에 없는 키워드를 뺐습니다 · {', '.join(dropped)}")
        if x.get("title"):
            acts.append({"title": clean(x["title"], 120), "why": clean(x.get("why"), 400), "how": clean(x.get("how"), 400), "keywords": kws[:6]})
    if not acts:
        sys.exit("❌ 마케팅 액션이 하나도 없습니다. 분석 JSON의 actions를 다시 쓰세요.")
    summary = clean(raw.get("summary"), 700)

    prompt = PROMPT
    if PROMPT_MET.get(a.lang):
        prompt = prompt.replace(*PROMPT_MET[a.lang])
    jt = dict(JS_T.get(a.lang, JS_T["kr"]))
    jt.update({k: T[k] for k in ("more", "less", "selHint", "passing", "analyze", "reanalyze", "open", "del", "noSaved", "actions", "noaio", "sel", "paths", "nTip")})
    jt["prompt"] = gpt_prompt(prompt, plan["gl"], a.lm_server) if host == "chatgpt" else prompt
    for k in ("analyzeThis", "chatHint", "chatEmpty", "chatPh", "send", "gptCopied", "gptCopyFail", "gptCopy"):
        if k in G:
            jt[k] = G[k]
    if host == "chatgpt":
        for k in ("noRuntime", "noSample", "noMcp", "stLlm", "permMenu", "mcp"):
            jt.pop(k, None)
    data = {"seed": plan["seed"], "gl": plan["gl"], "lm": a.lm_server, "host": host, "depth": MAP_DEPTH, "keep": list(MAP_KEEP),
            "pathCount": plan["pathCount"], "vol": plan["volumes"], "t": jt,
            "allPaths": plan.get("allPaths") or plan["paths"], "show": plan.get("show") or plan["pathCount"], "steps": [n for n in SHOW_STEPS],
            "summary": summary, "acts": [x["title"] for x in acts]}
    # 리포트를 만들 때 받은 SERP(E1…)를 페이지에 넣어 둔다 · 페이지 안 경로 분석이 같은 SERP를 다시 사지 않게
    data["pre"] = {x["keyword"]: {"k": x["keyword"], "at": x.get("at") or "", "aio": aio_text(x.get("aio"))[:2400],
                                  "top": [{k: t.get(k) for k in ("position", "site", "title", "url", "snippet")} for t in (x.get("top") or [])]}
                   for x in ev if x.get("ok")}
    dj = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

    def lst(blocks):
        out = []
        for b in blocks or []:
            if b["type"] == "list":
                def li(l):
                    return "<ul>" + "".join(f"<li>{e(i['snippet'])}{li(i['list']) if i.get('list') else ''}</li>" for i in l) + "</ul>"
                out.append(li(b["list"]))
            else:
                out.append(f"<p>{e(b['text'])}</p>")
        return "".join(out)

    H = [f'<!doctype html><html lang="{ {"kr": "ko", "jp": "ja"}.get(a.lang, "en") }"><head><meta charset="utf-8">',
         '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
         f'<title>{e(T["title"])} · {e(plan["seed"])}</title><style>{CSS}</style></head><body><div class="wrap">',
         # 헤더 카드 · 공용 리포트와 같은 모양 (CSS 는 .dash-* 참조).
         # KPI 는 따로 칩으로 두지 않고 메타 줄에 넣는다 — 공용 리포트가 쓰는
         # 방식이고, 나누면 같은 숫자가 화면에 두 번 나온다.
         f'<div class="dash-card"><div class="dash-cover">'
         f'<div class="dash-eyebrow">{e(T["title"])} · {e(T["market"])} {e(plan["gl"])}</div>'
         f'<div class="dash-title">{e(T["hTitle"])}</div>'
         f'<div class="dash-seed">「{e(plan["seed"])}」</div>'
         f'<div class="dash-meta">{e(T["hDate"])}: {e(plan.get("date") or "")} · '
         f'{e(T["paths"])} <span id="kpi-paths">{plan["pathCount"]}</span>/{plan.get("total", plan["pathCount"])} · '
         f'{e(T["kws"])} {plan["keywordCount"]} · {e(T["vol"])} {fmt(plan["seedVolume"])}</div>'
         f'</div><div class="dash-purpose"><b>{e(T["hPurpose"])}</b><p>{e(T["hIntro"])}</p></div></div>',
         '<div class="banner" id="banner" hidden></div>',
         f'<section class="box"><h2>{e(T["summary"])}</h2><p style="margin:0">{e(summary)}</p>',
         f'<h2 style="margin-top:14px">{e(T["actions"])}</h2><div class="acts">']
    for i, x in enumerate(acts):
        chips = "".join(f'<span class="chip" data-kw="{e(k)}">{e(k)}</span>' for k in x["keywords"])
        H.append(f'<div class="act"><b class="t"><span class="no">M{i+1}</span>{e(x["title"])}</b>'
                 f'<span><span class="lab">{e(T["why"])}</span> {e(x["why"])}</span><span><span class="lab">{e(T["how"])}</span> {e(x["how"])}</span><span>{chips}</span></div>')
    H.append('</div></section>')
    H.append(f'<section class="box" id="mapsec"><h2>{e(T["map"])}</h2><p class="muted" style="font-size:12.5px;margin:0 0 8px">{e(T["mapHint"])}</p>'
             f'<div class="mapgrid"><div><div class="find"><input type="search" id="fq" placeholder="{e(T["find"])}" aria-label="{e(T["find"])}" autocomplete="off">'
             f'<button type="button" class="btn" id="ftog">{e(T["listOpen"])}</button></div><div class="flist" id="flist" hidden></div>'
             f'<div class="panel"><div class="phead"><span><b>{e(plan["seed"])}</b> <span class="seg2" id="nseg" role="group" aria-label="{e(T["paths"])}"></span></span>'
             f'<span class="zoom"><button type="button" id="poptog" aria-pressed="true" title="{e(T["popTip"])}">{e(T["popOn"])}</button><button type="button" data-z="in" aria-label="+">＋</button><button type="button" data-z="out" aria-label="−">−</button>'
             f'<button type="button" data-z="fit">{e(T["fit"])}</button><button type="button" data-z="start" aria-label="focus">◎</button></span></div>'
             f'<div class="stage"><svg class="pm" preserveAspectRatio="xMidYMid meet" role="img" aria-label="{e(T["map"])}"><g class="vp"></g></svg></div></div></div>'
             f'<div class="side"><div class="box chat" id="chat"><div class="chat-h"><h2>{e(jt["chat"])}</h2><span class="muted" style="font-size:12px">{e(jt["chatHint"])}</span></div>'
             f'<div class="selbar" id="selbar"></div><div class="thread" id="thread"></div><div class="sug" id="sug"></div>'
             f'<div class="cin"><textarea id="q" rows="2" placeholder="{e(jt["chatPh"])}" aria-label="{e(jt["chat"])}"></textarea><button type="button" class="btn pri" id="send">{e(jt["send"])}</button></div></div></div></div></section>')
    H.append(f'<section class="box"{" hidden" if host == "chatgpt" else ""}><h2>{e(T["saved"])}</h2><div class="svl" id="savedlist"><p class="muted">…</p></div></section>')
    H.append('<div class="pop" id="pop" hidden></div>')

    H.append(f'<p class="muted" style="font-size:12px">{e(T["foot"])} · lm-search-context v{SKILL_VERSION}</p></div>')
    H.append(f'<script type="application/json" id="sc-data">{dj}</script><script>{JS}</script></body></html>')
    Path(a.out).write_text("".join(H), encoding="utf-8")
    print(f"✓ 리포트 → {a.out} · 대상 도구 {host}")
    for w in warn:
        print(f"  ⚠ {w}")


def main():
    p = argparse.ArgumentParser(description="Search Context v2")
    s = p.add_subparsers(dest="cmd", required=True)
    x = s.add_parser("kwparams"); x.add_argument("--paths", required=True); x.add_argument("--gl", required=True); x.add_argument("--out", required=True)
    x = s.add_parser("plan")
    x.add_argument("--paths", required=True); x.add_argument("--nodes"); x.add_argument("--seed", required=True)
    x.add_argument("--gl", required=True); x.add_argument("--lang", default="kr"); x.add_argument("--date", default="")
    x.add_argument("--show", type=int, default=SHOW_DEFAULT, help="요약·분석·처음 맵에 쓸 경로 수 = Step 0의 PATHS (100·200·300, 기본 300)")
    x.add_argument("--out", required=True)
    x = s.add_parser("serp-trim"); x.add_argument("--plan", required=True); x.add_argument("--serp-dir", required=True); x.add_argument("--out", required=True)
    x = s.add_parser("brief"); x.add_argument("--plan", required=True); x.add_argument("--evidence"); x.add_argument("--out", required=True)
    x = s.add_parser("render"); x.add_argument("--plan", required=True); x.add_argument("--evidence"); x.add_argument("--analysis", required=True)
    x.add_argument("--lang", default="kr", choices=["kr", "us", "jp"]); x.add_argument("--out", required=True)
    x.add_argument("--host", default="auto", choices=["auto", "claude", "chatgpt"], help="이 HTML을 만드는 LLM 도구 (페이지 안 분석·질문 방식이 달라짐)")
    x.add_argument("--lm-server", default="ListeningMind", help="ListeningMind 커넥터의 표시 이름 (이 대화의 도구 목록에 보이는 이름)")
    a = p.parse_args()
    {"kwparams": cmd_kwparams, "plan": cmd_plan, "serp-trim": cmd_serp_trim, "brief": cmd_brief, "render": cmd_render}[a.cmd](a)


if __name__ == "__main__":
    main()
