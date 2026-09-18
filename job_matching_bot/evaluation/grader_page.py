"""채점을 한 화면에서 끝내는 페이지를 만든다.

## 왜 만들었나

원래는 `읽기.md`를 보며 판단하고 `채점표.csv`의 같은 번호 줄에 옮겨 적는 방식이었다.
30줄을 매기려면 문서와 표를 서른 번 오가야 하고, 번호를 한 칸 밀려 적으면 그 뒤가
전부 어긋난다. 실제로 9월 7일에 두 번 만들어 두고 한 줄도 안 채워졌다.

여기서는 공고 요건과 이력서를 나란히 놓고 그 자리에서 매긴다. 키 하나로 끝나고,
다 매기면 `--score`가 그대로 읽는 CSV를 내려받는다.

## 지키는 것

- **모델 판단은 접어 둔다.** 먼저 보면 그대로 따라간다. 원래 문서의 규칙 그대로다.
- **중간에 꺼도 된다.** 매긴 값은 브라우저에 남는다. 실행별로 따로 저장한다.
- **인터넷이 필요 없다.** 파일 하나로 열린다. 외부에서 받아오는 것이 없다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
main{max-width:1100px;margin:0 auto;padding:20px}
.who{color:var(--dim);font-size:13px;margin-bottom:4px}
h2{font-size:19px;margin:0 0 6px}
.cond{color:var(--dim);font-size:13px;margin-bottom:16px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:820px){.cols{grid-template-columns:1fr}}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.box h3{font-size:12px;margin:0 0 10px;color:var(--dim);font-weight:700;letter-spacing:.02em}
.box ul{margin:0;padding-left:18px}.box li{margin-bottom:4px}
.tags{font-size:13px;line-height:1.8}
.tags b{color:var(--blue);font-weight:600}
.ask{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px;margin-top:16px}
.btns{display:flex;gap:10px;flex-wrap:wrap}
button{font:inherit;cursor:pointer;border-radius:8px;padding:10px 16px;
border:1px solid var(--line);background:#fff;color:var(--ink)}
button:hover{border-color:var(--blue)}
button.on{color:#fff;border-color:transparent}
button.yes.on{background:var(--green)}button.mid.on{background:var(--warn)}
button.no.on{background:var(--red)}
kbd{font:12px ui-monospace,monospace;background:var(--bg);border:1px solid var(--line);
border-bottom-width:2px;border-radius:4px;padding:1px 5px;margin-left:6px;color:var(--dim)}
textarea{width:100%;margin-top:10px;padding:8px 10px;border:1px solid var(--line);
border-radius:8px;font:inherit;resize:vertical}
details{margin-top:14px;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:12px 16px}
summary{cursor:pointer;font-size:13px;color:var(--dim)}
.q{font-size:13px;color:var(--dim);margin:2px 0 8px 14px}
nav{display:flex;gap:10px;margin-top:18px;align-items:center}
.done{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:24px;text-align:center}
.done p{color:var(--dim);font-size:14px}
.big{background:var(--blue);color:#fff;border-color:transparent;padding:12px 22px;font-weight:600}
.hint{color:var(--dim);font-size:12px;margin-top:10px}
"""

_SCRIPT = r"""
const ITEMS = JSON.parse(document.getElementById('items').textContent);
const KEY = 'eval-labels-' + document.body.dataset.stamp;
let marks = {};
try { marks = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { marks = {}; }
let at = 0;

const esc = (s) => String(s ?? '').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(marks)); } catch (e) {} };
const list = (xs, empty) => xs && xs.length
  ? '<ul>' + xs.map(x => '<li>' + esc(x) + '</li>').join('') + '</ul>'
  : '<p class="q">' + empty + '</p>';

function mark(verdict, grade) {
  const it = ITEMS[at];
  marks[it.번호] = { verdict, grade, memo: (marks[it.번호] || {}).memo || '' };
  save();
  if (at < ITEMS.length - 1) { at += 1; draw(); } else { draw(); }
}

function draw() {
  const it = ITEMS[at];
  const m = marks[it.번호] || {};
  const graded = Object.keys(marks).length;
  document.querySelector('.bar>i').style.width = (graded / ITEMS.length * 100) + '%';
  document.querySelector('.count').textContent = graded + ' / ' + ITEMS.length + ' 매김';
  const on = (v, g) => (m.verdict === v && (g === undefined || m.grade === g)) ? ' on' : '';
  document.querySelector('main').innerHTML = `
    <div class="who">${esc(it.번호)}번 · ${esc(it.이력서)} · 모델 순위 ${esc(it.순위)}위</div>
    <h2>${esc(it.회사)} — ${esc(it.공고)}</h2>
    <div class="cond">공고 요구 · ${esc(it.조건)}${it.공고링크 ? ' · <a href="' + esc(it.공고링크) + '" target="_blank" rel="noopener">공고 원문</a>' : ''}</div>
    <div class="cols">
      <div class="box"><h3>공고가 요구하는 것</h3>
        ${it.공고_기술 ? '<p class="tags">기술 ' + esc(it.공고_기술) + '</p>' : ''}
        ${it.공고_자격증 ? '<p class="tags">자격증 ' + esc(it.공고_자격증) + '</p>' : ''}
        ${it.공고_전공 ? '<p class="tags">전공 ' + esc(it.공고_전공) + '</p>' : ''}
        ${it.공고_우대자격증 ? '<p class="tags">자격증 (우대) ' + esc(it.공고_우대자격증) + '</p>' : ''}
        ${it.공고_우대전공 ? '<p class="tags">전공 (우대) ' + esc(it.공고_우대전공) + '</p>' : ''}
        <h3 style="margin-top:12px">자격요건</h3>
        ${list(it.자격요건, '공고에 자격요건 구간이 없습니다')}
        ${it.우대사항 && it.우대사항.length ? '<h3 style="margin-top:12px">우대사항</h3>' + list(it.우대사항, '') : ''}
      </div>
      <div class="box"><h3>이력서에 있는 것 · ${esc(it.이력서)}</h3>
        <div class="cond" style="margin-bottom:10px">${esc(it.이력서_조건)}</div>
        <p class="tags">기술 ${it.이력서_기술 ? esc(it.이력서_기술) : '(없음)'}</p>
        <p class="tags">자격증 ${it.이력서_자격증 ? esc(it.이력서_자격증) : '(없음)'}</p>
        <p class="tags">전공 ${it.이력서_전공 ? esc(it.이력서_전공) : '(없음)'}</p>
        <details><summary>이력서 전문 보기</summary>
          <pre style="white-space:pre-wrap;font:13px/1.7 inherit">${esc(it.이력서_전문)}</pre>
        </details>
      </div>
    </div>
    <div class="ask">
      <div class="btns">
        <button class="yes${on('예','높음')}" onclick="mark('예','높음')">추천 · 높음<kbd>1</kbd></button>
        <button class="mid${on('예','보통')}" onclick="mark('예','보통')">추천 · 보통<kbd>2</kbd></button>
        <button class="no${on('아니오')}" onclick="mark('아니오','')">추천 안 함<kbd>3</kbd></button>
      </div>
      <div class="q">높음 = 직무가 같고 주된 기술이 겹친다 · 보통 = 직무는 같은데 주된 기술이 다르다</div>
      <textarea rows="2" placeholder="메모 (선택)" oninput="memo(this.value)">${esc(m.memo || '')}</textarea>
    </div>
    <details><summary>모델의 판단 보기 — 먼저 스스로 정한 뒤 펼치세요</summary>
      <p class="q" style="margin-left:0">모델 등급: <b>${esc(it.모델_등급)}</b></p>
      ${it.근거.length ? it.근거.map(r =>
        '<p style="margin:6px 0 2px">· ' + esc(r.claim || '') + '</p>' +
        '<p class="q">이력서 "' + esc(r.resume_quote || '') + '"</p>' +
        '<p class="q">공고 "' + esc(r.job_quote || '') + '"</p>').join('')
        : '<p class="q" style="margin-left:0">근거 없음</p>'}
      ${it.우려.length ? '<p class="q" style="margin-left:0">확인되지 않은 요건</p>' +
        it.우려.map(c => '<p class="q">· ' + esc(c) + '</p>').join('') : ''}
    </details>
    <nav>
      <button onclick="go(-1)">← 이전</button>
      <button onclick="go(1)">다음 →</button>
      <span class="hint">키보드: 1 / 2 / 3 으로 매기고 자동으로 다음. ← → 로 이동</span>
    </nav>
    ${graded === ITEMS.length ? `
      <div class="done" style="margin-top:18px">
        <p>${ITEMS.length}건 전부 매겼습니다.</p>
        <button class="big" onclick="download()">채점표 CSV 내려받기</button>
        <p class="hint">받은 파일을 <code>job_matching_bot/fixtures/eval_labels.csv</code> 로 옮기고
        <code>python -m job_matching_bot.evaluation.recommend_eval --score</code> 를 실행하세요.</p>
      </div>` : ''}
  `;
}

function memo(v) {
  const it = ITEMS[at];
  marks[it.번호] = Object.assign({ verdict: '', grade: '' }, marks[it.번호], { memo: v });
  save();
}
function go(d) {
  at = Math.min(ITEMS.length - 1, Math.max(0, at + d));
  draw();
}
function csv() {
  const cell = (v) => {
    const s = String(v ?? '');
    return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const head = ['번호', '이력서', '회사', '공고', '사람_추천여부', '사람_등급', '메모'];
  const rows = ITEMS.map(it => {
    const m = marks[it.번호] || {};
    return [it.번호, it.이력서, it.회사, it.공고.slice(0, 40),
            m.verdict || '', m.grade || '', m.memo || ''].map(cell).join(',');
  });
  return '﻿' + head.join(',') + '\n' + rows.join('\n') + '\n';
}
function download() {
  const blob = new Blob([csv()], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'eval_labels.csv';
  a.click();
  URL.revokeObjectURL(a.href);
}
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'TEXTAREA') return;
  if (e.key === '1') mark('예', '높음');
  else if (e.key === '2') mark('예', '보통');
  else if (e.key === '3') mark('아니오', '');
  else if (e.key === 'ArrowLeft') go(-1);
  else if (e.key === 'ArrowRight') go(1);
});
draw();
"""


def _applicant_terms(persona: dict[str, Any]) -> str:
    """지원자 쪽 조건 한 줄. 공고의 `학력무관 · 경력무관` 과 맞대어 보라고 둔다.

    이게 없으면 공고가 대졸을 요구하는지는 보이는데 이 사람이 대졸인지가 안 보인다.
    """
    regions = ", ".join(persona.get("preferred_regions") or []) or "지역 무관"
    types = ", ".join(persona.get("preferred_employment_types") or []) or "형태 무관"
    return (
        f"{regions} · {types} · {persona.get('education_level', '미기재')}"
        f" · 연차 {persona.get('career_years', 0)}"
    )


def build_page(items: list[dict[str, Any]], personas: dict[str, Any], stamp: str) -> str:
    """채점 페이지 HTML. 바깥에서 받아오는 것 없이 파일 하나로 열린다."""
    payload = [
        {
            **{
                key: item[key]
                for key in (
                    "번호", "이력서", "순위", "회사", "공고", "공고링크",
                    "모델_등급", "근거", "우려", "공고_기술", "자격요건",
                    "우대사항", "조건", "공고_자격증", "공고_전공",
                    "공고_우대자격증", "공고_우대전공",
                    "이력서_기술", "이력서_자격증", "이력서_전공",
                )
            },
            "이력서_전문": (personas.get(item["이력서"], {}).get("resume_text") or "").strip(),
            "이력서_조건": _applicant_terms(personas.get(item["이력서"], {})),
        }
        for item in items
    ]
    # `</script>`가 글 안에 있으면 블록이 일찍 닫힌다. 그 한 자리만 막는다.
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    return (
        "<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>추천 채점 · {stamp}</title><style>{_STYLE}</style></head>"
        f"<body data-stamp=\"{stamp}\">"
        "<header><h1>추천 채점</h1><div class=\"bar\"><i></i></div>"
        "<span class=\"count\"></span></header><main></main>"
        f"<script id=\"items\" type=\"application/json\">{data}</script>"
        f"<script>{_SCRIPT}</script></body></html>\n"
    )


def write_page(path: Path, items: list[dict[str, Any]], personas: dict[str, Any]) -> Path:
    path.write_text(build_page(items, personas, path.stem), encoding="utf-8")
    return path
