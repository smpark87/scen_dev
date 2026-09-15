"""D13 — 데모 화면 조립.

07 §3 의 구성을 따른다. 이야기 축:
  "기계는 작동한다. 설명력은 나오지 않았다. 왜인지는 특정됐다."

결과를 숨기지도, 없는 성과를 만들지도 않는다. 각 그림 위에 그 화면이 무엇을
증명하고 무엇을 증명하지 않는지 한 줄로 붙인다.

출력: out/demo.html  (단독 파일. 회의에서 그대로 띄운다)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd


def fig_fragment(path: Path) -> str:
    """plotly 가 쓴 전체 HTML 에서 **그리는 부분만** 떼어낸다.

    초판은 iframe srcdoc 에 전체 문서를 통째로 넣었는데, 중첩 iframe 은
    뷰어·미리보기에서 자주 차단되어 화면이 비어 보인다 (2026-08-03 확인).
    plotly.js 를 페이지 상단에 한 번만 싣고, 각 그림은 div + script 로 직접 심는다.
    파일도 작아지고 스크롤·반응형도 정상 동작한다.
    """
    s = path.read_text(encoding="utf-8")
    m = re.search(r"<body>(.*)</body>", s, re.S)
    body = m.group(1) if m else s
    # CDN 로더 태그는 뺀다 — 상단에서 한 번만 싣는다.
    # plotly 는 <script charset="utf-8" src="..."> 처럼 src 앞에 속성을 붙이므로
    # src 위치를 고정하면 안 된다.
    return re.sub(r'<script\b[^>]*\bsrc="[^"]*plotly[^"]*"[^>]*>\s*</script>', "", body)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DATA, DISCLAIMER, FIGS, OUT  # noqa: E402

FIGS_ORDER = [
    ("01_density.html", "① 문서 밀도 — 무엇을 재료로 쓰는가",
     "결핍의 첫 증거. article 소스가 2023년부터만 존재해 그 이전은 평일당 1.8건이다."),
    ("02_embedding_map.html", "② 임베딩 공간 — 의미가 구조를 갖는가",
     "설명이 필요 없는 그림. 다만 이 구조에는 소스·형식 편향이 섞여 있어 그대로 쓰면 안 된다."),
    ("03_semantic_panel.html", "③ 의미 축 — 개수가 아니라 방향",
     "덩어리 20개와 부호 있는 축 9개 모두 데이터가 만들었다. 이름만 사람이 붙였다."),
    ("07_substitutability.html", "③′ 그 축들은 무엇을 담고 있는가 — 정형과의 중복 측정",
     "설명력을 재기 전에 먼저 볼 것. 의미 축이 정형의 다른 표현일 뿐이라면 "
     "기여가 없는 게 당연하다. 가정하지 않고 축마다 측정했다."),
    ("04_decomposition.html", "④ 대칭 설명력 분해 — 핵심 결과",
     "신뢰구간이 기준선을 배제한 것은 정형 2건뿐. 의미 변수는 어느 대상에서도 0을 배제하지 못한다."),
    ("05_event_study.html", "④′ 사건 코호트 — 분석 단위를 바꿔 재시험",
     "날짜가 아니라 사건을 단위로 삼아도 결과는 같다. 다섯 유형 모두 무작위와 구분되지 않는다."),
    ("06_direction.html", "⑤ 한계 — 어떤 방향을 구별하고 어떤 방향을 못 구별하는가",
     "임베딩의 경계선이 우리 실제 데이터에서 그어졌다. 여기가 구조화 추출이 필요한 지점이다."),
]

CSS = """
:root{--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--acc:#4C78A8;--warn:#c0392b;--bg:#fff;--card:#fafafa}
@media(prefers-color-scheme:dark){:root{--fg:#e8e8e8;--mut:#9a9a9a;--line:#333;--bg:#151515;--card:#1e1e1e}}
*{box-sizing:border-box}
body{margin:0;font:15px/1.65 -apple-system,'Segoe UI','Malgun Gothic',sans-serif;color:var(--fg);background:var(--bg)}
.wrap{max-width:1180px;margin:0 auto;padding:28px 20px 80px}
h1{font-size:27px;margin:.2em 0 .1em;letter-spacing:-.01em}
h2{font-size:19px;margin:2.4em 0 .5em;padding-bottom:.35em;border-bottom:2px solid var(--acc)}
h3{font-size:15px;margin:1.6em 0 .4em;color:var(--mut);font-weight:600}
.sub{color:var(--mut);font-size:14px;margin:0 0 18px}
.banner{background:#fff4f1;border:1px solid #f0c4b8;color:#8a2b12;border-radius:8px;
  padding:12px 16px;font-size:13.5px;margin:16px 0 8px}
@media(prefers-color-scheme:dark){.banner{background:#2a1512;border-color:#5a2c20;color:#e8a08a}}
.lede{background:var(--card);border-left:4px solid var(--acc);border-radius:0 8px 8px 0;
  padding:16px 20px;margin:22px 0;font-size:16px}
.lede b{color:var(--acc)}
.note{color:var(--mut);font-size:13.5px;margin:.2em 0 12px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:13px 15px}
.card .k{font-size:11.5px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
.card .v{font-size:21px;font-weight:650;margin-top:3px}
.card .d{font-size:12.5px;color:var(--mut);margin-top:3px}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:12px 0}
th,td{border-bottom:1px solid var(--line);padding:7px 10px;text-align:left}
th{font-weight:600;color:var(--mut);font-size:12.5px}
td.num{text-align:right;font-variant-numeric:tabular-nums}
.ok{color:#1a7f4b;font-weight:600}.no{color:var(--mut)}.bad{color:var(--warn);font-weight:600}
.figwrap{border:1px solid var(--line);border-radius:10px;margin:10px 0 6px;
  background:#fff;padding:6px;overflow-x:auto}
.figwrap .plotly-graph-div{margin:0 auto}
.scroll{overflow-x:auto}
footer{margin-top:60px;padding-top:18px;border-top:1px solid var(--line);color:var(--mut);font-size:12.5px}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:12.5px}
"""


def card(k: str, v: str, d: str = "") -> str:
    return f'<div class="card"><div class="k">{k}</div><div class="v">{v}</div>' \
           f'<div class="d">{d}</div></div>'


def main() -> None:
    dec = pd.read_parquet(DATA / "decomp.parquet")
    ev = json.loads((DATA / "event_study.json").read_text(encoding="utf-8"))
    dr = json.loads((DATA / "direction_test.json").read_text(encoding="utf-8"))
    prep = json.loads((DATA / "prep_summary.json").read_text(encoding="utf-8"))
    anames = json.loads((DATA / "axis_names.json").read_text(encoding="utf-8"))

    # 두 벌을 낸다. plotly.js 본체가 4.9MB 라 인라인하면 파일이 6.8MB 가 되고
    # 미리보기·메신저에서 잘 안 열린다. 용도가 다르므로 분리한다.
    #   demo.html          CDN 로드 · 약 2MB · 공유·미리보기용 (인터넷 필요)
    #   demo-offline.html  전량 인라인 · 약 7MB · 회의장 단독 실행용
    h: list[str] = []
    h.append(f"<style>{CSS}</style><div class='wrap'>")
    h.append("<h1>Semantic Factor 개념 실증 (Demo)</h1>")
    h.append("<p class='sub'>임베딩된 비정형 정보가 통계 변수로 작동하는가 · "
             "2026-08-03 · scen_dev</p>")
    h.append(f"<div class='banner'><b>⚠ {DISCLAIMER}</b> — 이 산출물로 예측력을 "
             "주장하지 않는다. 저장·리그 등 저빈도 계열이 발표 전 시점에 값으로 들어가 "
             "있어 정형 쪽이 구조적으로 유리하다.</div>")
    h.append("<div class='lede'><b>기계는 작동한다. 설명력은 나오지 않았다. "
             "왜인지는 특정됐다.</b><br>"
             "비정형 문서를 통계 변수로 바꾸는 전 과정이 재현 가능하게 돌아간다. "
             "그러나 그 변수들이 Henry Hub 가격을 설명한다는 증거는 "
             "<b>일자 패널과 사건 코호트 두 단위 모두에서</b> 나오지 않았다. "
             "그리고 그 이유가 수치로 특정됐다 — 이것이 이 단계의 실질 산출이다.</div>")

    # 1부
    h.append("<h2>1부 — 기계가 도는가</h2>")
    h.append("<div class='grid'>"
             + card("시장 모집단", f"{prep['market_chunks']:,}",
                    f"청크 / 문서 {prep['market_docs']:,}건")
             + card("소스 편향 제거", f"{prep['eta2_before']['source']:.0%} → "
                    f"{prep['eta2_after']['source']:.1%}", "eta² (소스×언어 중심화)")
             + card("의미 덩어리", "20", "k-means · 문서당 1표 가중")
             + card("부호 있는 축", f"{len(anames['adopted'])}",
                    f"채택 / 폐기 {len(anames['rejected'])} (형식·언어)")
             + "</div>")
    h.append("<h3>축이 실재한다는 외부 검증</h3>")
    h.append("<p class='note'>계절 정보를 아무것도 넣지 않고 뽑은 축 "
             "<code>ax_2_0</code>(선물 코멘터리 안의 기온 방향)을 달력에 대면 "
             "<b>1월 −1.17(한파) · 7월 +1.22(폭염)</b> 의 계절 곡선이 나온다. "
             "축이 우연한 방향이 아니라는 뜻이다.</p>")

    def tbl_decomp() -> str:
        rows = ["<h3>④ 판정표</h3><div class='scroll'><table><tr><th>대상</th><th>지표</th>"
                "<th class='num'>정형 S</th><th class='num'>의미 M</th><th>판정</th></tr>"]
        for _, r in dec.iterrows():
            base = 0.0 if r.kind == "num" else 0.5
            unit = "R²" if r.kind == "num" else "AUC"
            vs = "ok" if r.S_lo > base else "no"
            vm = "ok" if r.M_lo > base else "no"
            best = "정형 유의" if r.S_lo > base else ("의미 유의" if r.M_lo > base else "—")
            rows.append(
                f"<tr><td>{r['name']}</td><td>{unit}</td>"
                f"<td class='num {vs}'>{r.S:+.3f}<br><span style='font-size:11px;color:#888'>"
                f"[{r.S_lo:+.2f},{r.S_hi:+.2f}]</span></td>"
                f"<td class='num {vm}'>{r.M:+.3f}<br><span style='font-size:11px;color:#888'>"
                f"[{r.M_lo:+.2f},{r.M_hi:+.2f}]</span></td><td>{best}</td></tr>")
        rows.append("</table></div><p class='note'>90% 이동블록 부트스트랩 구간. "
                    "가장 근접했던 것은 <b>T7 꼬리에서 의미 AUC 0.583 &gt; 정형 0.512</b> 였으나 "
                    "구간이 0.5를 포함한다 (양성 38건) — 시사적이나 주장 불가.</p>")
        return "".join(rows)

    def tbl_events() -> str:
        er = ["<div class='scroll'><table><tr><th>유형</th><th class='num'>사건</th>"
              "<th class='num'>키워드 밖 확장</th><th class='num'>t−5→0</th>"
              "<th class='num'>t+3</th><th class='num'>양측 p</th></tr>"]
        for e in ev:
            er.append(f"<tr><td>{e['name']}</td><td class='num'>{e['n_events']}</td>"
                      f"<td class='num ok'>{e['n_expanded']/e['n_docs']:.0%}</td>"
                      f"<td class='num'>{e['pre5']:+.2%}</td>"
                      f"<td class='num'>{e['h3']:+.2%}</td>"
                      f"<td class='num'>{e['p_two_sided']:.3f}</td></tr>")
        er.append("</table></div><p class='note'>코호트의 <b>58~92%가 제목 키워드에 "
                  "걸리지 않은 문서</b>다 — 의미로만 찾아냈고, 키워드로는 만들 수 없는 "
                  "코호트다. 다만 <b>사전 표류가 사후 반응보다 크다</b>"
                  "(지정학 t−5→0 +2.02% vs t+3 −2.96%). 기사가 나오는 시점에는 "
                  "이미 가격에 반영돼 있다.</p>")
        return "".join(er)

    def tbl_direction() -> str:
        rows = ["<div class='scroll'><table><tr><th>방향의 종류</th><th>예</th>"
                "<th class='num'>분류 AUC</th><th>판정</th></tr>"]
        verd = [("어휘가 다름", "폭염 ↔ 한파", "ok", "구별한다"),
                ("템플릿 안 단어 차이", "warmed ↔ cooled", "no",
                 "구별하나 비지도 축에서 밀린다"),
                ("비교·부정으로만 갈림", "예상 하회 ↔ 상회", "bad", "구별하지 못한다")]
        for d, (kind, ex, cls, v) in zip(dr, verd):
            rows.append(f"<tr><td>{kind}</td><td>{ex}</td>"
                        f"<td class='num {cls}'>{d['auc']:.3f}</td><td>{v}</td></tr>")
        rows.append("</table></div><p class='note'>세 번째 줄이 <b>구조화 이벤트 추출이 "
                    "필요한 이유</b>다 (03 §5.4 <code>direction</code> 필드). "
                    "합성 예시가 아니라 우리 코퍼스가 그렇게 말한다.</p>")
        return "".join(rows)

    def tbl_subst() -> str:
        sb = json.loads((DATA / "substitutability.json").read_text(encoding="utf-8"))
        rows = ["<div class='scroll'><table><tr><th>의미 축</th>"
                "<th class='num'>R²(축 | 정형)</th><th>판정</th></tr>"]
        for a in sb["axes"]:
            hi = a["r2_given_S"] >= sb["cut"]
            rows.append(
                f"<tr><td>[{a['cluster']}] {a['label']}</td>"
                f"<td class='num {'bad' if hi else 'ok'}'>{a['r2_given_S']:+.3f}</td>"
                f"<td>{'숫자의 다른 표현' if hi else '정형에 없는 정보'}</td></tr>")
        rows.append("</table></div>")
        rows.append(
            "<p class='note'><b>기온 축만 정형이 재현한다(+0.334).</b> HDD/CDD 에 이미 "
            "있으니 당연하다. 그런데 <b>‘생산·공급 전망’은 −0.015 로 대체되지 않는다</b> — "
            "정형에 있는 것은 <b>실현 생산량</b>이고 텍스트에 있는 것은 <b>전망의 수정</b>"
            "(<i>“EIA, 올해 생산량 전망치 하향 조정”</i>)이기 때문이다. "
            "같은 이유로 저장량 축도 −0.039 다. 수준은 숫자에 있으나 <b>전망·해석은 없다</b>.</p>")
        rows.append(
            "<p class='note'>그럼에도 <b>대체가능 축을 빼고 고유 8개로만 다시 분해해도 "
            "증분은 전부 0</b>이다 (T1 +0.001 · T6 +0.000 · W1 −0.017). "
            "따라서 <b>“의미 축이 정형의 재탕이라 기여가 없었다”는 설명은 쓸 수 없다.</b> "
            "9개 중 8개가 숫자에 없는 정보를 담고도 가격 설명에는 기여하지 않는다.</p>")
        rows.append(
            "<p class='note'>설계 결함 하나 — <code>ax_2_2</code>(+0.192)는 음극이 정형"
            "(생산·기온), 양극이 비정형(지정학)이라 <b>양 극의 성격이 다르다.</b> "
            "다음 반복에서는 대비축이 아니라 지정학 강도 자체를 뽑아야 한다.</p>")
        return "".join(rows)

    AFTER = {"07_substitutability.html": tbl_subst,
             "04_decomposition.html": tbl_decomp,
             "05_event_study.html": tbl_events,
             "06_direction.html": tbl_direction}

    for i, (fn, title, note) in enumerate(FIGS_ORDER):
        if i == 4:
            h.append("<h2>2부 — 설명력이 있는가</h2>")
            h.append("<h3>먼저: 채점기 자체를 검증했다</h3>")
            h.append("<p class='note'>“신호가 없다”와 “파이프라인이 신호를 못 잡는다”는 "
                     "다르다. 정답을 아는 합성 대상으로 먼저 시험했다.</p>")
            h.append("<div class='scroll'><table><tr><th>합성 대상</th>"
                     "<th class='num'>정형 R²</th><th class='num'>의미 R²</th></tr>"
                     "<tr><td>순수 잡음 (기대 ≈ 0)</td><td class='num'>−0.01</td>"
                     "<td class='num'>−0.01</td></tr>"
                     "<tr><td>정형 3열 선형결합</td><td class='num ok'>+0.896</td>"
                     "<td class='num'>+0.13</td></tr>"
                     "<tr><td>의미 3열 선형결합</td><td class='num'>−0.18</td>"
                     "<td class='num ok'>+0.740</td></tr></table></div>")
            h.append("<p class='note'><b>양방향으로 대칭이다.</b> 의미 변수에 신호가 "
                     "있으면 이 채점기는 찾아낸다. 아래 결과는 그 위에서 읽는다.</p>")
        if i == 6:
            h.append("<h2>3부 — 어디서 막히는가</h2>")
        h.append(f"<h3>{title}</h3><p class='note'>{note}</p>")
        p = FIGS / fn
        if not p.exists():
            h.append(f"<p class='note bad'>({fn} 없음)</p>")
            continue
        h.append(f"<div class='figwrap'>{fig_fragment(p)}</div>")
        if fn in AFTER:
            h.append(AFTER[fn]())

    # 결핍 정량화
    h.append("<h2>⑥ 왜 안 나왔는가 — 수치로</h2>")
    h.append("<div class='grid'>"
             + card("국면 표본", "5~6",
                    "분석창 2023~2026 전체가 저가·공급과잉 한 종류")
             + card("위기 국면", "0건",
                    "2021 Uri · 2022 우크라이나가 코퍼스에 없음")
             + card("평일 시장 문서", "9.4건", "의미 변수의 일일 재료량")
             + card("기사 타이밍", "사후",
                    "사건 코호트에서 사전 표류 > 사후 반응")
             + "</div>")
    h.append("<div class='lede'>이 데모의 결론은 “안 된다”가 아니라 "
             "<b>“이 세 가지가 갖춰져야 판정이 가능하다”</b> 이다.<br>"
             "① 뉴스 아카이브 조달 (2015~2022 — 국면 표본 5~6 → 15~20)<br>"
             "② as-of 적용 (현재 정형의 우위에 발표 전 값이 섞여 있다)<br>"
             "③ 구조화 이벤트 추출 (<code>direction</code> 필드 — ⑤의 세 번째 줄)</div>")

    h.append("<footer>재현: <code>prep.py → factors.py → panel.py → structured.py → "
             "targets.py → decompose.py → events.py → direction.py → assemble.py</code>"
             "<br>DB 는 읽기 전용 계정(<code>scen_ro</code>)으로만 접근했고 "
             "ngip 운영 데이터는 변경하지 않았다. 실행 중 발견한 함정 목록은 06 §6.2.</footer>")
    h.append("</div>")

    body = "".join(h) + "</body></html>"
    from plotly.offline import get_plotlyjs

    # ⚠️ charset 선언이 없으면 UTF-8 로 저장해도 브라우저가 다른 인코딩으로 읽어
    #    한글이 전부 깨진다. iframe 판에서는 plotly 가 만든 내부 문서에 charset 이
    #    있어 가려져 있었다 (2026-08-03). 완전한 문서로 감싼다.
    HEAD = ("<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Semantic Factor 개념 실증 (Demo) — scen_dev</title>")

    for fn, js in (
        ("demo.html",
         '<script src="https://cdn.plot.ly/plotly-3.1.0.min.js" charset="utf-8"></script>'),
        ("demo-offline.html", f"<script>{get_plotlyjs()}</script>"),
    ):
        p = OUT / fn
        p.write_text(HEAD + js + "</head><body>" + body, encoding="utf-8")
        print(f"{p}  ({p.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
