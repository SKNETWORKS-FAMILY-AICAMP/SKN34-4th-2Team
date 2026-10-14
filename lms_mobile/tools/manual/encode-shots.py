#!/usr/bin/env python3
"""
캡처한 PNG 를 JPEG 로 줄여 src/manual/shots.ts 로 만든다 — content.ts 의 SHOT_BY_BLOCK 에 쓰인 것만 넣는다.

  python3 tools/manual/encode-shots.py <캡처 폴더(shots)>

필요: pip install pillow
"""
import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image

MOBILE = Path(__file__).resolve().parent.parent.parent


def main() -> None:
    shots = Path(sys.argv[1] if len(sys.argv) > 1 else 'shots')
    content = (MOBILE / 'src' / 'manual' / 'content.ts').read_text(encoding='utf-8')
    keys = sorted(set(re.findall(r"'((?:st|in|ad)-[a-z0-9-]+)'", content.split('SHOT_BY_BLOCK')[1])))
    lines = [
        '/**',
        ' * 설명서 화면 캡처 — 데모 데이터(가짜 학생 · 기수)로 앱을 띄워 찍은 화면을 JPEG 로 줄여 넣었다.',
        ' * tools/manual 의 캡처 스크립트가 만든다. 손으로 고치지 않는다.',
        ' */',
        'export const SHOTS: Record<string, string> = {',
    ]
    for key in keys:
        image = Image.open(shots / f'{key}.png').convert('RGB')
        width = 1300 if key.endswith('-pad') else 468
        image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, 'JPEG', quality=72, optimize=True, progressive=True)
        lines.append(f"  '{key}': 'data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}',")
    lines.append('};\n')
    (MOBILE / 'src' / 'manual' / 'shots.ts').write_text('\n'.join(lines), encoding='utf-8')
    print(f'{len(keys)}장 → src/manual/shots.ts')


if __name__ == '__main__':
    main()
