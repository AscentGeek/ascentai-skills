#!/usr/bin/env python3
"""st_build.py · 시즌·트렌드 분석의 숫자를 모두 만든다 (코드). 문장은 만들지 않는다.

  python3 st_build.py --config config.json --list kw_list.json --kw lm_keyword_info_*.json \
      --out-dir "$WORKDIR" [--now 10]

입력
  config.json   · 분석자가 정한 시드·관련성 필터(rel/exc)·테마 규칙 (references/config.md)
  kw_list.json  · st_prepare.py 출력 (검색어 출처 rel/clu)
  --kw          · keyword_info 응답 파일들

출력
  data.json     · 렌더러 입력 (숫자 전부)
  facts.md      · 문장 쓸 때 쓰는 숫자 목록 (narrative 는 여기 있는 숫자만 쓴다)
  off.txt       · 관련성 필터로 뺀 검색어 (4년 검색량 큰 순) — 필터 검토용
  untagged.txt  · 어느 테마에도 안 들어간 검색어 (최근 12개월 큰 순) — 테마 규칙 검토용

규칙(고정)
  · 검색량 = 네이버 + 구글 월 검색량. 기간 = 데이터가 있는 마지막 달까지 48개월.
  · 최근 12개월 = 마지막 12개월, 직전 12개월 = 그 앞 12개월. 최근 3개월 전년비 = 마지막 3개월 vs 1년 전 같은 3개월.
  · 계절 지수 = 해마다(12개월 묶음) 월값 ÷ 그 해 월평균, 같은 달끼리 4년 중앙값.
  · 단계: 피크 = 평균 위 부분의 상위 30%(1 + 0.7×(최대−1) 이상) · 비수기 = 0.9 미만 · 비수기 직전 1–2개월 이탈 ·
    비수기→피크 사이 상승 · 비수기가 끝나기 직전 1–2개월 준비 · 그 외 유지/반등 · 최대/최소 < 1.4 이면 연중.
  · 신규 = 앞 24개월에 검색량이 없다가 그 뒤 처음 나타났고 최근 12개월 600 이상, 직전보다 늘어남.
    급등 = 최근 12개월이 직전의 2배 이상이고 1,200 이상. 연도(2025·25년 등)가 붙은 검색어는 신호에서 뺀다.
  · 테마 = config 순서대로 첫 번째로 맞는 테마 하나에만 들어간다.
exit · 0 성공 / 1 입력 오류 / 3 기간 부족
"""
import argparse
import collections
import json
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import st_common as C  # noqa: E402

YR = re.compile(r"(20[12]\d|2[3-9]\s?[년年])")  # i18n-ok · 연도 표기 (kr 25년 · jp 25年)
THR_MONTH = 1.4


def phases(ix):
    ix = [max(v, 0.01) for v in ix]
    mx, mn = max(ix), min(ix)
    if mx / mn < 1.4:
        return ["연중"] * 12
    thr = 1 + 0.7 * (mx - 1)
    P = [None] * 12
    for i, v in enumerate(ix):
        if v >= thr:
            P[i] = "피크"
        elif v < 0.9:
            P[i] = "비수기"

    def scan(i, step):
        j = i
        for d in range(1, 13):
            j = (j + step) % 12
            if P[j] in ("피크", "비수기"):
                return P[j], d
        return None, 99
    for i in range(12):
        if P[i]:
            continue
        f, fd = scan(i, 1)
        b, _ = scan(i, -1)
        loc = ix[i] >= ix[(i - 1) % 12] and ix[i] >= ix[(i + 1) % 12] and ix[i] >= 1.1
        if f == "비수기" and loc:
            P[i] = "반등"
        elif f == "비수기" and fd <= 2:
            P[i] = "이탈"
        elif b == "비수기" and f == "피크":
            P[i] = "상승"
        else:
            P[i] = "유지"
    for i in range(12):
        if P[i] == "비수기" and P[(i + 1) % 12] in ("상승", "피크"):
            run, j = 0, i
            while P[j] == "비수기" and run < 12:
                run += 1
                j = (j - 1) % 12
            for t in range(min(2, run - 1) if run > 1 else 0):
                P[(i - t) % 12] = "준비"
    return P


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--list")
    p.add_argument("--kw", nargs="+", required=True)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--now", type=int, help="지금 달(1–12). 없으면 데이터 마지막 달의 다음 달")
    a = p.parse_args()

    cfg = json.loads(Path(a.config).read_text(encoding="utf-8"))
    seed = cfg["seed"]
    # 시장(gl)과 리포트 언어(lang)는 독립이다 · lang 은 facts.md 숫자 단위(만 · 万 · K)와 렌더 언어를 정한다
    gl = cfg.get("gl") or "kr"
    lang = cfg.get("lang") or "kr"
    C.set_lang(lang)
    src = json.loads(Path(a.list).read_text(encoding="utf-8")).get("src", {}) if a.list else {}
    srcn = {C.norm_kw(k): v for k, v in src.items()}

    recs, seen = [], set()
    for f in a.kw:
        for r in C.keyword_records(C.load_json(f)):
            k = C.norm_kw(r["keyword"])
            if k in seen:
                continue
            seen.add(k)
            recs.append(r)
    if not recs:
        print("❌ keyword_info 결과가 비었습니다", file=sys.stderr)
        return 1
    allm = sorted({m for r in recs for m in r["months"]})
    if len(allm) < 48:
        print(f"❌ 월 데이터가 {len(allm)}개월뿐입니다 · 48개월이 필요합니다", file=sys.stderr)
        return 3
    M = allm[-48:]
    MO = [int(m[5:]) for m in M[:12]]
    NOW = a.now or (int(M[-1][5:]) % 12 + 1)

    REL = re.compile(cfg["rel"], re.I) if cfg.get("rel") else None
    EXC = re.compile(cfg["exc"], re.I) if cfg.get("exc") else None
    KW, OFF = [], []
    for r in recs:
        d = {m: (n or 0) + (g or 0) for m, n, g in zip(r["months"], r["nv"], r["gg"])}
        s = [d.get(m, 0) for m in M]
        if sum(s) <= 0:
            continue
        k = r["keyword"]
        ok = (REL.search(k) if REL else True) and not (EXC.search(k) if EXC else False)
        rec = dict(kw=k, src=srcn.get(C.norm_kw(k), "rel"), s=s)
        (KW if ok else OFF).append(rec)
    # 공통 하한 — 4년 합계가 이보다 작은 검색어는 모든 탭에서 뺀다(숫자가 튀는 아주 작은 검색어)
    MIN_TOTAL = int(cfg.get("min_total", 1000))
    LOW = [k for k in KW if sum(k["s"]) < MIN_TOTAL]
    KW = [k for k in KW if sum(k["s"]) >= MIN_TOTAL]
    if not KW:
        print("❌ 관련성 필터 뒤 남은 검색어가 없습니다 · config 의 rel/exc 를 확인하세요", file=sys.stderr)
        return 1

    E = lambda s: [sum(s[i * 12:(i + 1) * 12]) for i in range(4)]
    for k in KW:
        s = k["s"]
        f = next(i for i, v in enumerate(s) if v > 0)
        e = E(s)
        y3, y3p = sum(s[45:48]), sum(s[33:36])
        k.update(e=e, first=f, yoy3=(y3 / y3p - 1) if y3p > 0 else None)
        cls = None
        if f >= 24 and e[3] >= 600 and e[3] > e[2]:
            cls = "new"
        elif e[2] > 0 and e[3] >= 1200 and e[3] / e[2] >= 2:
            cls = "surge"
        if cls and YR.search(k["kw"]):
            cls = None
        k["cls"] = cls

    tot = [sum(k["s"][i] for k in KW) for i in range(48)]
    eras = E(tot)
    MKT = eras[3] / eras[2] - 1 if eras[2] else 0
    M3 = sum(tot[45:48]) / sum(tot[33:36]) - 1 if sum(tot[33:36]) else 0

    TH = [(t[0], t[1], re.compile(t[2], re.I)) for t in cfg.get("themes", [])]

    def tag(kw):
        for tid, _, c in TH:
            if c.search(kw):
                return tid
        return None
    for k in KW:
        k["t"] = tag(k["kw"])

    def yidx(s):
        out = []
        for e in range(4):
            y = s[e * 12:(e + 1) * 12]
            mu = sum(y) / 12
            out.append([v / mu for v in y] if mu > 0 else None)
        return out

    def cidx(s):
        idx = collections.defaultdict(list)
        for y in yidx(s):
            if y is None:
                continue
            for i, v in enumerate(y):
                idx[MO[i]].append(v)
        return [round(st.median(idx[m]), 3) if idx[m] else 0 for m in range(1, 13)]

    def year_peaks(s):
        return [MO[y.index(max(y))] for y in yidx(s) if y]

    def mv(s):
        o = [0] * 12
        for i in range(36, 48):
            o[int(M[i][5:]) - 1] = s[i]
        return o

    circ = lambda x, y: min((x - y) % 12, (y - x) % 12)

    # ── 테마 ──
    groups = [("_all", "전체 (기준)", KW)]
    for tid, name, _ in TH:
        mem = [k for k in KW if k["t"] == tid]
        if mem:
            groups.append((tid, name, mem))
    themes, rows, skw, tkw = [], [], {}, {}
    for gid, name, mem in groups:
        s = [sum(k["s"][i] for k in mem) for i in range(48)]
        e = E(s)
        ci = cidx(s)
        pk = ci.index(max(ci)) + 1
        yp = year_peaks(s)
        row = dict(id=gid, name=name, idx=ci, ph=phases(ci), peak=pk, e4=e[3])
        if gid != "_all":
            y3, y3p = sum(s[45:48]), sum(s[33:36])
            t = dict(id=gid, name=name, n=len(mem), e3=e[2], e4=e[3],
                     yoy12=round(e[3] / e[2] - 1, 4) if e[2] else None,
                     yoy3=round(y3 / y3p - 1, 4) if y3p else None,
                     nsig=sum(1 for k in mem if k["cls"]), peak=pk, s=s[24:48])
            themes.append(t)
            row["yoy12"] = t["yoy12"]
        rows.append(row)
        # 테마별 상위 검색어(콘솔 요약용)
        T4 = sum(s) or 1

        def kwrow(k):
            c2 = cidx(k["s"])
            p2 = c2.index(max(c2)) + 1
            ys = year_peaks(k["s"])
            return dict(k=k["kw"], v=sum(k["s"][36:]), share=round(sum(k["s"]) / T4, 4), idx=[round(x, 2) for x in c2],
                        ph=phases(c2), peak=p2, hit=sum(x == p2 for x in ys), ny=len(ys), yp=ys, off=p2 != pk, mv=mv(k["s"]))
        big = sorted(mem, key=lambda k: -sum(k["s"]))
        top = [kwrow(k) for k in big[:10]]
        odd = []
        for k in big[10:]:
            if sum(k["s"][36:]) < 3000:
                continue
            r = kwrow(k)
            if r["ny"] < 2 or circ(r["peak"], pk) < 2:
                continue
            if r["hit"] < (3 if r["ny"] >= 4 else r["ny"]) or max(r["idx"]) < 1.4:
                continue
            odd.append(r)
        skw[gid] = dict(n=len(mem), peak=pk, hit=sum(x == pk for x in yp), ny=len(yp), yp=yp, mv=mv(s),
                        topshare=round(sum(r["share"] for r in top), 4), top=top, odd=odd[:3])
        if gid != "_all":
            L = [dict(k=k["kw"], e3=k["e"][2], e4=k["e"][3], ea=[round(x) for x in k["e"]], c=k["cls"], f=M[k["first"]], t=gid, s=k["s"][24:48],
                      y3=None if k["yoy3"] is None else round(k["yoy3"], 3)) for k in mem]
            tkw[gid] = dict(up=sorted([r for r in L if r["e4"] > r["e3"]], key=lambda r: -(r["e4"] - r["e3"])),
                            dn=sorted([r for r in L if r["e4"] < r["e3"]], key=lambda r: r["e4"] - r["e3"]))

    base = rows[0]
    for r in rows[1:]:
        m = r["peak"] - 1
        r["off"] = bool(max(r["idx"]) - base["idx"][m] >= 0.15 and circ(r["peak"], base["peak"]) >= 2)
    PR = {"준비": 0, "상승": 1, "피크": 2, "반등": 3, "유지": 4, "이탈": 5, "비수기": 6, "연중": 7}
    rows[1:] = sorted(rows[1:], key=lambda r: (PR[r["ph"][NOW - 1]], (r["peak"] - NOW) % 12, -r["e4"]))

    # ── 월별 시즌 키워드 (붙은 두 달 · 4년 중 3년 · 지수 1.4) ──
    mon = collections.defaultdict(list)
    for k in KW:
        s = k["s"]
        if sum(s[24:]) < 500:          # 월별 시즌 키워드 대상: 최근 2년 합계 500 이상(월평균 약 20)
            continue
        pk = year_peaks(s)
        ny = len(pk)
        if ny < 2:
            continue
        ci = cidx(s)
        need = 3 if ny >= 4 else ny
        best = None
        for a0 in range(1, 13):
            w = (a0, a0 % 12 + 1)
            n = sum(x in w for x in pk)
            if n < need:
                continue
            m = max(w, key=lambda x: ci[x - 1])
            if ci[m - 1] < THR_MONTH:
                continue
            hit = sorted({x for x in pk if x in w}, key=lambda x: (x - a0) % 12)
            span = f"{hit[0]}–{hit[-1]}월" if len(hit) > 1 else f"{hit[0]}월"
            cand = (n, ci[m - 1], m, span, list(w))
            if best is None or cand[:2] > best[:2]:
                best = cand
        if best:
            n, ix, m, span, w = best
            vals = [s[i] for i in range(48) if int(M[i][5:]) == m and s[i] > 0]
            mon[m].append(dict(k=k["kw"], n=n, ny=ny, new=ny < 4, span=span, ix=round(ix, 2),
                               vol=round(st.mean(vals)) if vals else 0, w=w, t=k["t"], s=s,
                               ci=[round(x, 2) for x in ci]))
    skip = {C.norm_kw(x) for x in (cfg.get("skip_month") or [seed])}
    months = {m: [x for x in sorted(v, key=lambda x: -x["vol"]) if C.norm_kw(x["k"]) not in skip] for m, v in mon.items()}

    def sigrow(k):
        return dict(k=k["kw"], c=k["cls"], src=k["src"], f=M[k["first"]], e3=k["e"][2], e4=k["e"][3],
                    y3=None if k["yoy3"] is None else round(k["yoy3"], 3), t=k["t"], sp=k["s"][24:48])
    new = [sigrow(k) for k in sorted([k for k in KW if k["cls"] == "new"], key=lambda k: -k["e"][3])]
    surge = [sigrow(k) for k in sorted([k for k in KW if k["cls"] == "surge"], key=lambda k: -(k["e"][3] - k["e"][2]))]

    untag = sorted([k for k in KW if not k["t"]], key=lambda k: -k["e"][3])
    e4all = eras[3] or 1

    # 시드 단독 — 시드·rel 표기를 지우면 아무것도 안 남는 검색어(후드티 · 후디). 미분류가 정상이라 검토 기준에서 뺀다
    def seed_only(kw):
        rest = kw.lower().replace(seed.lower(), " ")
        if REL:
            rest = REL.sub(" ", rest)
        return not rest.strip()
    core = [k for k in untag if not seed_only(k["kw"])]
    clu = [k for k in KW if k["src"] == "clu"]
    meta = dict(seed=seed, gl=gl, lang=lang, collected=cfg.get("collected", ""), now=NOW, months=M, queried=len(src) or len(recs),
                returned=len(recs), kept=len(KW), off=len(OFF), low=len(LOW), min_total=MIN_TOTAL, ki_files=len(a.kw),
                n_rel=sum(1 for v in src.values() if v == "rel"), n_clu=sum(1 for v in src.values() if v == "clu"),
                clu_kept=len(clu), clu_sig=sum(1 for k in clu if k["cls"]),
                untagged=len(untag), untagged_share=round(sum(k["e"][3] for k in untag) / e4all, 4),
                untagged_core=len(core), untagged_core_share=round(sum(k["e"][3] for k in core) / e4all, 4))
    _sn = C.norm_kw(seed)
    seed_s = next((k["s"] for k in KW + LOW + OFF if C.norm_kw(k["kw"]) == _sn), None)   # 탭 1 연도별 월 검색량
    # 미분류 검색어 — 테마별 표·캘린더에는 안 나오지만 주요 트렌드 후보(탭 2)와 상승·하락(탭 3)은 전체에서 고른다
    untk = [dict(k=k["kw"], e3=k["e"][2], e4=k["e"][3], ea=[round(x) for x in k["e"]], c=k["cls"], f=M[k["first"]], t=None, s=k["s"][24:48],
                 y3=None if k["yoy3"] is None else round(k["yoy3"], 3)) for k in untag if k["e"][3] != k["e"][2]]
    D = dict(meta=meta, tot=tot, seed_s=seed_s, untk=untk, eras=eras, mkt=round(MKT, 4), mkt3=round(M3, 4), rows=rows, themes=themes,
             months={str(m): v for m, v in months.items()}, skw=skw, tkw=tkw, new=new, surge=surge)
    out = Path(a.out_dir)
    (out / "data.json").write_text(json.dumps(D, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out / "off.txt").write_text("\n".join(f"{k['kw']}\t{sum(k['s']):,}" for k in sorted(OFF, key=lambda k: -sum(k["s"]))), encoding="utf-8")
    (out / "untagged.txt").write_text("\n".join(f"{k['kw']}\t{k['e'][3]:,}" for k in untag), encoding="utf-8")
    (out / "facts.md").write_text(facts(D), encoding="utf-8")

    print(f"월 {M[0]} ~ {M[-1]} · 지금 {NOW}월 · 조회 {meta['returned']} → 관련 {len(KW) + len(LOW)} / 제외 {len(OFF)} · 4년 합계 {MIN_TOTAL:,} 미만 {len(LOW)} → 분석 {len(KW)}")
    print(f"최근 12개월 {C.pct(MKT)} · 최근 3개월 전년비 {C.pct(M3)} · 신규 {len(new)} · 급등 {len(surge)}")
    n_core = len(core) / (len(KW) or 1)
    print(f"테마 {len(themes)}개 · 미분류 {len(untag)}개 (최근 12개월 검색량의 {meta['untagged_share']*100:.1f}%)"
          f" · 시드 단독 {len(untag) - len(core)}개 제외하면 {len(core)}개 (검색어의 {n_core*100:.1f}% · 검색량의 {meta['untagged_core_share']*100:.1f}%)")
    if meta["untagged_core_share"] > 0.1 or n_core > 0.2:
        print("⚠️ 시드 단독을 뺀 미분류가 검색량 10% 또는 검색어 20%를 넘습니다 · 아래 미분류 전체를 보고 테마 규칙을 보강하세요")
    for t in themes:
        print(f"  {t['id']:10s} {t['name'][:12]:12s} n{t['n']:4d} 12m {C.pct(t['yoy12'] or 0)} 정점 {t['peak']}월")
    print(f"미분류 전체 {len(core)}개 (시드 단독 제외 · 최근 12개월 큰 순):", ", ".join(f"{k['kw']}({k['e'][3]:,})" for k in core))
    return 0


def trend_pool(pool, min_volume=5000, top_n=None):
    """market-flow-report 의 _trend_pool 을 두 기간(직전 12개월 e3 · 최근 12개월 e4)에 맞춘 것."""
    out = {"new": [], "growing": [], "falling": []}
    for r in pool:
        a, b = r["e3"], r["e4"]
        if max(a, b) < min_volume:
            continue
        if a <= max(a, b) * 0.02 and b > 0:
            out["new"].append(r)
        elif a > 0 and b / a >= 1.5:
            out["growing"].append(r)
        elif a > 0 and b / a <= 0.5:
            out["falling"].append(r)
    for k in out:
        out[k] = sorted(out[k], key=lambda r: -max(r["e3"], r["e4"]))[:top_n]  # top_n=None 이면 전체
    return out


def facts(D):
    """narrative 를 쓸 때 쓰는 숫자. 여기 없는 숫자는 문장에 쓰지 않는다."""
    fm, kv, pct = C.fmt, C.kv, C.pct
    m = D["meta"]
    L = [f"# facts · {m['seed']}", "",
         f"- 기간 {m['months'][0]} ~ {m['months'][-1]} · 지금 {m['now']}월 · 분석 검색어 {m['kept']:,}개 (관련 없음 {m['off']:,} · 4년 합계 {m['min_total']:,} 미만 {m['low']:,} 제외)",
         f"- 최근 12개월 {fm(D['eras'][3])}({kv(D['eras'][3])}) · 직전 12개월 {fm(D['eras'][2])}({kv(D['eras'][2])}) · 변화 {pct(D['mkt'])} · 최근 3개월 전년비 {pct(D['mkt3'])}",
         ]
    L += ["", "## 월별 시즌 키워드 (그 달 평균 검색량)"]
    for mm in range(1, 13):
        v = D["months"].get(str(mm), [])
        if v:
            L.append(f"- {mm}월: " + " · ".join(f"{x['k']} {fm(x['vol'])} ({x['span']})" for x in v[:6]) + (f" 외 {len(v)-6}개" if len(v) > 6 else ""))
        else:
            L.append(f"- {mm}월: 없음")
    TN = {x["id"]: x["name"] for x in D["themes"]}
    cal = {}
    for mm in range(1, 13):
        for x in D["months"].get(str(mm), []):
            if x.get("t"):
                cal.setdefault(x["t"], {}).setdefault(mm, []).append(x["k"])
    L += ["", "## 테마별 시즌 캘린더 (시즌 키워드 1개 이상 테마 · 키워드 많은 순)"]
    for tid, d in sorted(cal.items(), key=lambda z: -sum(len(v) for v in z[1].values())):
        n = sum(len(v) for v in d.values())
        L.append(f"- {TN.get(tid, tid)} ({n}개): " + " / ".join(
            f"{mm}월 " + "·".join(v[:4]) + (f" 외 {len(v)-4}개" if len(v) > 4 else "") for mm, v in sorted(d.items())))
    nt = sum(1 for v in D["months"].values() for x in v if not x.get("t"))
    if nt:
        L.append(f"- 테마 없는 시즌 키워드 {nt}개 (캘린더에는 안 보이고 월별 카드에만 보임)")
    # 직전 1년에서 최근 1년으로 — st_render.py 2탭 ① 주요 트렌드(years_trends) 근거
    _pool, _seen = [], set()
    for v in list(D["tkw"].values()) + [dict(up=D.get("untk", []), dn=[])]:   # 테마 + 미분류 = 전체
        for r in v["up"] + v["dn"]:
            if r["k"] not in _seen:
                _seen.add(r["k"])
                _pool.append(r)
    _TN = {x["id"]: x["name"] for x in D["themes"]}
    mm = D["meta"]["months"]
    L += ["", f"## 최근 1년 주요 트렌드 재료 (직전 12개월 {mm[24][:7]}–{mm[35][:7]} · 최근 12개월 {mm[36][:7]}–{mm[47][:7]})",
          f"- 전체 {fm(D['eras'][2])}({kv(D['eras'][2])}) → {fm(D['eras'][3])}({kv(D['eras'][3])}) · 변화 {pct(D['mkt'])}"]
    # 트렌드 재료 — market-flow-report trendPool 규칙을 두 기간에 맞춤 (surge 는 구간이 둘이라 없음) · 전체
    #   new: 직전 1년이 사실상 0(두 기간 큰 쪽의 2% 이하) · growing: 최근 1년 ÷ 직전 1년 ≥ 1.5배 · falling: ≤ 0.5배 · 큰 쪽 5,000 이상
    _tp = trend_pool(_pool)
    for lab, key in (("new · 직전 1년에 사실상 없던 검색어", "new"), ("growing · 최근 1년이 직전 1년의 1.5배 이상", "growing"), ("falling · 최근 1년이 직전 1년의 절반 이하", "falling")):
        L.append(f"### 트렌드 재료 · {lab} ({len(_tp[key])}개 · years_trends.memberKeywords 는 같은 갈래 안에서만)")
        L += [f"- {r['k']} [{_TN.get(r['t'], '테마 없음')}] {fm(r['e3'])} → {fm(r['e4'])}" for r in _tp[key]] or ["- 없음"]
    # 확인할 것 — 서로 다른 검색어가 같은 달에 한꺼번에 튄 달(수집 쪽 영향일 수 있음 · limit_note 근거)
    #   검색어마다 24개월 중앙값의 4배 이상인 달을 '튄 달'로 보고(중앙값 50 이상만), 한 달에 20개 이상이 함께 튀었고
    #   그중 80% 이상이 한 테마인 달을 적는다(서로 다른 장소·제품이 같은 달에 한꺼번에 튀는 것은 실제 관심보다 수집 쪽 영향일 수 있다)
    _spk = collections.defaultdict(list)
    for r in _pool:
        s = r["s"]
        med = sorted(s)[12]
        if med < 50:
            continue
        for j, v in enumerate(s):
            if v >= 4 * med:
                _spk[j].append(r)
    _bad = sorted((j, L_) for j, L_ in _spk.items()
                  if len(L_) >= 20 and collections.Counter(r["t"] for r in L_).most_common(1)[0][1] >= 0.8 * len(L_))
    L += ["", "## 확인할 것 · 한 테마의 검색어가 같은 달에 함께 튄 달 (24개월 중앙값의 4배 이상 · 한 달 20개 이상 · 80% 이상 한 테마)"]
    if not _bad:
        L.append("- 없음")
    for j, L_ in _bad:
        _c = collections.Counter(_TN.get(r["t"], "") for r in L_)
        L.append(f"- {mm[24 + j][:7]}: {len(L_)}개 — " + " · ".join(f"{k} {v}" for k, v in _c.most_common(4))
                 + " — 예: " + " / ".join(r["k"] for r in sorted(L_, key=lambda r: -r["s"][j])[:6]))
    # 테마별 트렌드 — st_render.py 2탭 ②와 같은 순서 · 주요 트렌드 반례 확인용
    L += ["", "## 테마별 트렌드 (최근 12개월 vs 직전 12개월 · 테마마다 늘어난 · 줄어든 검색어 — 반대 예 확인용)"]
    for th in sorted(D["themes"], key=lambda x: -x["e4"]):
        U, Dn = D["tkw"][th["id"]]["up"], D["tkw"][th["id"]]["dn"]
        L.append(f"### {th['id']}: {th['name']} — 검색어 {th['n']}개")
        for lab, lst in (("늘어난", U), ("줄어든", Dn)):
            L.append(f"- {lab} {len(lst)}개 중 상위 20: " + (" / ".join(
                f"{x['k']} {fm(x['e3'])} → {fm(x['e4'])} ({'+' if x['e4'] >= x['e3'] else '−'}{kv(abs(x['e4']-x['e3']))})" + (f" 신규 {x['f'][:7].replace('-', '.')}" if x["c"] == "new" else "")
                for x in lst[:20]) or "없음"))
    # 트렌드 (QoQ 순 · QoQ+YoY) — st_render.py 3탭과 같은 규칙
    TN = {x["id"]: x["name"] for x in D["themes"]}
    pool, seen = [], set()
    for v in list(D["tkw"].values()) + [dict(up=D.get("untk", []), dn=[])]:   # 테마 + 미분류 = 전체
        for r in v["up"] + v["dn"]:
            if r["k"] not in seen:
                seen.add(r["k"])
                pool.append(r)

    def q3(r):
        s = r["s"]
        return sum(s[9:12]), sum(s[18:21]), sum(s[21:24])

    def dirn(r, both):
        y0, q0, q1 = q3(r)
        if q0 < 10 or (both and y0 < 10):
            return None
        qq = q1 / q0 - 1
        yy = q1 / y0 - 1 if y0 else 0
        if qq > 0 and (not both or yy > 0):
            return "up"
        if qq < 0 and (not both or yy < 0):
            return "dn"
        return None

    upq = [r for r in pool if dirn(r, False) == "up"]
    dnq = [r for r in pool if dirn(r, False) == "dn"]
    up = [r for r in pool if dirn(r, True) == "up"]
    dn = [r for r in pool if dirn(r, True) == "dn"]
    pc = lambda a, b: f"{(a/b-1)*100:+.0f}%" if b else "—"

    def line(r):
        y0, q0, q1 = q3(r)
        return (f"{r['k']} ({TN.get(r['t'], '테마 없음')}) 최근 3개월 {fm(q1)} · QoQ {'+' if q1 >= q0 else '−'}{fm(abs(q1-q0))} ({pc(q1, q0)}) · "
                f"YoY {'+' if q1 >= y0 else '−'}{fm(abs(q1-y0))} ({pc(q1, y0)})")
    m = D["meta"]["months"]
    L += ["", f"## 트렌드 · 최근 3개월 {m[45][:7]}–{m[47][5:7]}",
          "- QoQ 순 = 직전 3개월보다 늘어난(줄어든) 검색어 · QoQ+YoY = 작년 같은 3개월보다도 늘어난(줄어든) 검색어 · 둘 다 QoQ 증감량 순"]
    gq = lambda r: q3(r)[2] - q3(r)[1]
    for lab, lst, key in (("상승 · QoQ 순", upq, lambda r: -gq(r)), ("상승 · QoQ+YoY", up, lambda r: -gq(r)),
                          ("하락 · QoQ 순", dnq, gq), ("하락 · QoQ+YoY", dn, gq)):
        L.append(f"### {lab} ({len(lst)}개 중 상위 20)")
        L += [f"- {line(r)}" for r in sorted(lst, key=key)[:20]]
    L += ["", "## 신규·급등"]
    for lab, lst in (("신규", D["new"]), ("급등", D["surge"])):
        L.append(f"- {lab} {len(lst)}개: " + " / ".join(f"{r['k']} {fm(r['e3'])} → {fm(r['e4'])} ({r['f'][:7].replace('-', '.')})" for r in lst[:15]))
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
