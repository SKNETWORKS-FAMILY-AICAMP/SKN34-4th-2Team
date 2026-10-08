"""Render saved real-model results for local browser inspection; no network."""
import argparse
from html import escape
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('reports', nargs='+')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    blocks = []
    for filename in args.reports:
        report = json.loads(Path(filename).read_text(encoding='utf-8'))
        blocks.append('<h2>' + escape(Path(filename).stem) + '</h2>')
        usage = report['usage']
        blocks.append(f'<p>{escape(report["model"])} · {usage["calls"]} calls · {usage["latency_ms"]/1000:.1f}s</p>')
        for row in report['results']:
            original = row['experience']['current_text']
            status = row['validation']['status']
            candidate = (row.get('candidate') or {}).get('suggested_text', '')
            final = candidate if status == 'READY' else original
            blocks.append('<article><h3>' + escape(row['experience']['title']) +
                f' <small>{escape(status)}</small></h3><div class="pair"><section><h4>원문</h4><p>' +
                escape(original) + '</p></section><section><h4>사용자에게 제안하는 결과</h4><p>' +
                escape(final) + '</p></section></div>')
            if status != 'READY':
                blocks.append('<p class="note">적용 가능한 수정안이 아닙니다. 원문을 유지합니다.</p>')
            blocks.append('<details><summary>검증 기록 · 생성 후보</summary><pre>' +
                escape(json.dumps({'validation': row['validation'], 'candidate': candidate,
                    'questions': row.get('gap_questions', [])}, ensure_ascii=False, indent=2)) + '</pre></details></article>')
        if report.get('http_response'):
            blocks.append('<p>실제 B HTTP route + adapter + 실제 LLM. 저장소는 메모리이며 Django·브라우저 E2E 실행은 아닙니다.</p>')
    criteria = '<h2>확인 기준</h2><ul><li>B-1: 초기 이해 → 실무 기여 → 장기 방향이 남아 있는가?</li><li>B-2: 지원 이유가 중심이고 경험은 근거로 쓰이는가?</li><li>B-3: 구현·테스트를 담당·주도·성과로 확대하지 않는가?</li><li>원문보다 낫지 않으면 원문 유지가 표시되는가?</li></ul>'
    page = '''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Resume Review 실제 모델 비교</title><style>
body{font:16px/1.8 system-ui,sans-serif;background:#f5f7fb;color:#172333;max-width:1200px;margin:32px auto;padding:0 24px}
h1,h2,h3{line-height:1.35}h2{margin-top:48px}article{background:white;border:1px solid #dce2ed;border-radius:12px;padding:24px;margin:20px 0}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:32px}p{white-space:pre-wrap}small,.note{color:#52647c}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}summary{cursor:pointer}@media(max-width:760px){.pair{grid-template-columns:1fr}}
</style><h1>Resume Review — 실제 모델 결과 비교</h1><p>저장된 평가 결과입니다. 이 화면은 제품 UI가 아닌 읽기 전용 비교 보고서이며, 승인·저장 기능이나 외부 연결은 없습니다.</p>'''
    output = Path(args.output)
    output.write_text(page + criteria + ''.join(blocks) + '</html>', encoding='utf-8')
    print(output.resolve())


if __name__ == '__main__':
    main()
