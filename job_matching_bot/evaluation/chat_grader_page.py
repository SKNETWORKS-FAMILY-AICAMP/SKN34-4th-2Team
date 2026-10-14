"""챗봇 답 문장을 사람이 매기는 페이지.

## 여기서 매기는 것만 사람이 필요하다

의도·조건·번호 가리키기·응답 시간은 정답이 있어 `chat_eval --run`이 자동으로
대조한다. 사람이 매길 것은 **자동으로는 못 보는 둘**이다.

1. **근거** — 답이 실제 공고·통계에서 나왔는가, 아니면 어디서나 들을 수 있는
   일반론인가. 우리 데이터를 안 보고도 쓸 수 있는 답이면 이 서비스일 이유가 없다.
2. **지어냄** — 공고에 없는 마감일·연봉·복지를 만들어 냈는가. 이게 하나라도 있으면
   나머지 답도 못 믿는다.

## 한 화면에서 끝낸다

추천 채점 페이지와 같은 방식이다. 물음과 답, 그리고 답의 근거가 된 공고를 나란히
놓고 그 자리에서 매긴다. 문서와 표를 오가지 않는다.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _run_date(stamp: str) -> date | None:
    """`20260911-153508` 에서 잰 날을 꺼낸다. 마감까지 며칠인지 세는 기준이다."""
    try:
        return datetime.strptime(stamp.split("-")[0], "%Y%m%d").date()
    except ValueError:
        return None


def _deadline_label(value: str | None, base: date | None) -> tuple[str, bool]:
    """(보여 줄 말, 이미 지났나).

    답이 "7일 내 마감"이라고 말했으면 채점하는 사람이 그 자리에서 세어 볼 수 있어야
    한다. 날짜만 적어 두면 오늘이 며칠인지부터 떠올려야 해서 아무도 안 센다.
    """
    if not value:
        return "마감일 미기재", False
    try:
        when = datetime.fromisoformat(value).date()
    except ValueError:
        return value, False
    shown = when.strftime("%m.%d")
    if base is None:
        return f"마감 {shown}", False
    days = (when - base).days
    if days < 0:
        return f"마감 {shown} (지남)", True
    if days == 0:
        return f"마감 {shown} (오늘)", False
    return f"마감 {shown} (D-{days})", False

_STYLE = """
:root{--bg:#f6f7f9;--card:#fff;--line:#e5e7eb;--ink:#111827;--dim:#6b7280;
--blue:#0055ff;--green:#16a34a;--red:#dc2626;--warn:#b45309}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.6 Pretendard,"Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif}
header{position:sticky;top:0;z-index:5;background:var(--card);
border-bottom:1px solid var(--line);padding:10px 20px;display:flex;
align-items:center;gap:14px;flex-wrap:wrap}
h1{font-size:15px;margin:0;font-weight:700}
.bar{flex:1;min-width:160px;height:6px;background:var(--line);border-radius:3px;overflow:hidden}
.bar>i{display:block;height:100%;background:var(--green);width:0;transition:width .2s}
.count{font-variant-numeric:tabular-nums;color:var(--dim);font-size:13px}
main{max-width:960px;margin:0 auto;padding:20px}
.who{color:var(--dim);font-size:13px;margin-bottom:6px}
.turn{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:14px 16px;margin-bottom:10px}
.turn.prev{opacity:.55}
.me{font-weight:700;margin-bottom:8px}
.me span{color:var(--dim);font-weight:400;font-size:12px;margin-left:8px}
.bot{white-space:pre-wrap}
.mode{display:inline-block;font-size:11px;color:var(--dim);border:1px solid var(--line);
border-radius:4px;padding:1px 6px;margin-left:6px}
.jobs{margin-top:10px;border-top:1px dashed var(--line);padding-top:8px;
font-size:13px;color:var(--dim)}
.jobs ul{list-style:none;margin:6px 0 0;padding:0}
.jobs li{padding:5px 0;border-top:1px solid var(--bg)}
.jobs li:first-child{border-top:0}
.jobs a{color:var(--ink);font-weight:600;text-decoration:none}
.jobs a:hover{color:var(--blue);text-decoration:underline}
.meta{font-size:12px;color:var(--dim);margin-top:1px}
.due{color:var(--green);font-weight:600}
.past{color:var(--red);font-weight:600}
.ask{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px;margin-top:16px}
.q{font-size:13px;color:var(--dim);margin:2px 0 8px}
.q b{color:var(--ink)}
.note{display:block;margin-top:3px;font-size:12px;line-height:1.5;opacity:.85}
.tip{background:#fffbeb;border:1px solid #fde68a;color:#78350f;border-radius:8px;
padding:8px 11px;margin-bottom:12px;font-size:12px;line-height:1.55}
:root:not([data-theme="light"]) .tip{background:#3a2f12;border-color:#78591a;color:#fde68a}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px}
button{font:inherit;cursor:pointer;border-radius:8px;padding:9px 15px;
border:1px solid var(--line);background:#fff;color:var(--ink)}
button:hover{border-color:var(--blue)}
button.on{color:#fff;border-color:transparent}
button.yes.on{background:var(--green)}button.mid.on{background:var(--warn)}
button.no.on{background:var(--red)}
kbd{font:12px ui-monospace,monospace;background:var(--bg);border:1px solid var(--line);
border-bottom-width:2px;border-radius:4px;padding:1px 5px;margin-left:6px;color:var(--dim)}
textarea{width:100%;margin-top:6px;padding:8px 10px;border:1px solid var(--line);
border-radius:8px;font:inherit;resize:vertical}
nav{display:flex;gap:10px;margin-top:18px;align-items:center}
.hint{color:var(--dim);font-size:12px}
.done{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:24px;text-align:center;margin-top:18px}
.big{background:var(--blue);color:#fff;border-color:transparent;padding:12px 22px;font-weight:600}
.where{font-size:12px;color:var(--dim);line-height:1.7;margin-bottom:0}
code{background:var(--bg);border:1px solid var(--line);border-radius:4px;padding:1px 5px;
font:12px ui-monospace,monospace}
"""

_SCRIPT = r"""
const ITEMS = JSON.parse(document.getElementById('items').textContent);
const KEY = 'chat-eval-' + document.body.dataset.stamp;
let marks = {};
try { marks = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { marks = {}; }
let at = 0;

const esc = (s) => String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} };

function mark(field, value) {
  const it = ITEMS[at];
  marks[it.번호] = Object.assign({근거:'', 지어냄:'', 메모:''}, marks[it.번호], {[field]: value});
  save();
  const m = marks[it.번호];
  if (m.근거 && m.지어냄) {
    if (at < ITEMS.length - 1) { at += 1; }
  }
  draw();
}

function jobHtml(j) {
  const name = esc(j.company) + ' · ' + esc(j.title);
  const head = j.url
    ? '<a href="' + esc(j.url) + '" target="_blank" rel="noopener">' + name + '</a>'
    : name;
  const bits = [esc(j.meta), '<span class="' + (j.past ? 'past' : 'due') + '">'
    + esc(j.deadline) + '</span>'];
  if (j.stack) { bits.push(esc(j.stack)); }
  return '<li>' + head + '<div class="meta">'
    + bits.filter(Boolean).join(' · ') + '</div></li>';
}

function turnHtml(t, isLast) {
  const jobs = (t.jobs || []).map(jobHtml).join('');
  const head = '답에 붙은 공고 ' + t.jobs.length + '건'
    + (t.total ? ' · 조건에 맞는 전체 ' + t.total + '건' : '');
  return '<div class="turn' + (isLast ? '' : ' prev') + '">'
    + '<div class="me">' + esc(t.message)
    + '<span>' + t.elapsed.toFixed(1) + '초</span></div>'
    + '<div class="bot">' + esc(t.reply) + '</div>'
    + '<span class="mode">' + esc(t.mode) + '</span>'
    + (jobs ? '<div class="jobs">' + head + '<ul>' + jobs + '</ul></div>' : '')
    + '</div>';
}

function draw() {
  const it = ITEMS[at];
  const m = marks[it.번호] || {};
  const graded = Object.values(marks).filter(x => x.근거 && x.지어냄).length;
  document.querySelector('.bar>i').style.width = (graded / ITEMS.length * 100) + '%';
  document.querySelector('.count').textContent = graded + ' / ' + ITEMS.length + ' 매김';
  const on = (f, v) => (m[f] === v ? ' on' : '');
  document.querySelector('main').innerHTML = `
    <div class="who">${esc(it.번호)}번 · ${esc(it.id)} — ${esc(it.note)}</div>
    ${it.turns.map((t, i) => turnHtml(t, i === it.turns.length - 1)).join('')}
    <div class="ask">
      ${it.turns[it.turns.length - 1].jobs.length ? '' :
        '<div class="tip">이 답에는 공고가 붙지 않았습니다. 공고나 숫자를 하나도 말하지 않았다면 두 물음 모두 채점할 것이 없습니다 — <b>해당 없음</b>과 <b>지어낸 것 없음</b>입니다.</div>'}
      <div class="q">마지막 답이 <b>우리 데이터</b>에서 나왔나요?
        <span class="note">공고나 통계로 답했어야 하는데 어디서나 들을 수 있는 말만 했으면 <b>일반론</b>. 인사·위로·범위 밖 거절처럼 애초에 공고로 답할 물음이 아니었으면 <b>해당 없음</b>.</span></div>
      <div class="btns">
        <button class="yes${on('근거','근거 있음')}" onclick="mark('근거','근거 있음')">근거 있음<kbd>1</kbd></button>
        <button class="mid${on('근거','일반론')}" onclick="mark('근거','일반론')">일반론<kbd>2</kbd></button>
        <button class="no${on('근거','해당 없음')}" onclick="mark('근거','해당 없음')">해당 없음<kbd>3</kbd></button>
      </div>
      <div class="q">공고에 <b>없는 것</b>을 지어냈나요?
        <span class="note">마감일·연봉·복지·합격 가능성을 지어낸 것이 특히 그렇습니다. 공고 이야기를 안 한 답은 지어낼 것도 없으니 <b>없음</b>입니다.</span></div>
      <div class="btns">
        <button class="yes${on('지어냄','없음')}" onclick="mark('지어냄','없음')">지어낸 것 없음<kbd>A</kbd></button>
        <button class="no${on('지어냄','있음')}" onclick="mark('지어냄','있음')">지어냄 있음<kbd>S</kbd></button>
      </div>
      <textarea rows="2" placeholder="메모 (선택)" oninput="memo(this.value)">${esc(m.메모 || '')}</textarea>
    </div>
    <nav>
      <button onclick="go(-1)">← 이전</button>
      <button onclick="go(1)">다음 →</button>
      <span class="hint">1/2/3 으로 근거, A/S 로 지어냄. 둘 다 고르면 자동으로 다음</span>
    </nav>
    ${graded === ITEMS.length ? `
      <div class="done">
        <p>${ITEMS.length}건 전부 매겼습니다.</p>
        <button class="big" onclick="download()">채점표 CSV 내려받기</button>
        <p class="where">받은 파일을 <code>job_matching_bot/fixtures/labels/chat-${document.body.dataset.stamp}.csv</code>
        로 옮긴 뒤<br><code>python -m job_matching_bot.evaluation.chat_eval --score</code></p>
      </div>` : ''}
  `;
}

function memo(v) {
  const it = ITEMS[at];
  marks[it.번호] = Object.assign({근거:'', 지어냄:''}, marks[it.번호], {메모: v});
  save();
}
function go(d) { at = Math.min(ITEMS.length - 1, Math.max(0, at + d)); draw(); }

function csv() {
  const cell = (v) => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const head = ['번호', 'id', '물음', '근거', '지어냄', '메모'];
  const lines = [head.join(',')];
  for (const it of ITEMS) {
    const m = marks[it.번호] || {};
    const last = it.turns[it.turns.length - 1];
    lines.push([it.번호, it.id, last.message, m.근거 || '', m.지어냄 || '', m.메모 || '']
      .map(cell).join(','));
  }
  return '﻿' + lines.join('\n');
}

function download() {
  const blob = new Blob([csv()], {type: 'text/csv;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'chat-' + document.body.dataset.stamp + '.csv';
  a.click();
}

document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TEXTAREA') return;
  const byKey = {'1':['근거','근거 있음'], '2':['근거','일반론'], '3':['근거','해당 없음'],
                 'a':['지어냄','없음'], 's':['지어냄','있음'],
                 'A':['지어냄','없음'], 'S':['지어냄','있음']};
  if (byKey[e.key]) { mark(...byKey[e.key]); return; }
  if (e.key === 'ArrowLeft') go(-1);
  if (e.key === 'ArrowRight') go(1);
});

draw();
"""


def build_page(results: list[dict[str, Any]], stamp: str) -> str:
    """채점 페이지 HTML. 바깥에서 받아오는 것 없이 파일 하나로 열린다."""
    base = _run_date(stamp)

    def job_of(raw: dict) -> dict:
        # 답이 내세운 조건(지역·경력·고용형태·마감)을 전부 적는다. 하나라도 빠지면
        # 그 조건을 말한 답은 채점할 수 없다 — 실제로 "7일 내 마감"이라고 답해 놓고
        # 마감일을 안 보여 줘서 맞는지 볼 길이 없었다.
        label, past = _deadline_label(raw.get("deadline"), base)
        meta = [raw.get(key, "") for key in ("region", "career", "employment_type")]
        return {
            "company": raw.get("company", ""),
            "title": raw.get("title", ""),
            "url": raw.get("source_url", ""),
            "meta": " · ".join(v for v in meta if v),
            "deadline": label,
            "past": past,
            "stack": ", ".join(raw.get("tech_stack") or []),
        }

    payload = []
    for number, case in enumerate(results, 1):
        payload.append({
            "번호": number,
            "id": case["id"],
            "note": case.get("note", ""),
            "turns": [
                {
                    "message": turn["message"],
                    "reply": (turn["got"].get("reply") or "").strip(),
                    "mode": turn["got"].get("mode", ""),
                    "total": turn["got"].get("total"),
                    "elapsed": round(float(turn["elapsed"]), 2),
                    "jobs": [job_of(j) for j in (turn["got"].get("jobs") or [])],
                }
                for turn in case["turns"]
            ],
        })
    # `</script>`가 답 안에 있으면 블록이 일찍 닫힌다. 그 한 자리만 막는다.
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (
        '<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>챗봇 채점 · {stamp}</title><style>{_STYLE}</style></head>"
        f'<body data-stamp="{stamp}">'
        "<header><h1>챗봇 답 채점</h1>"
        '<div class="bar"><i></i></div><div class="count"></div></header>'
        "<main></main>"
        f'<script id="items" type="application/json">{data}</script>'
        f"<script>{_SCRIPT}</script></body></html>"
    )


def write_page(path: Path, results: list[dict[str, Any]]) -> Path:
    path.write_text(build_page(results, path.stem), encoding="utf-8")
    return path
