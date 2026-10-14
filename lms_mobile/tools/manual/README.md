# 모바일 설명서(PDF) 만들기

앱 설정 → 도움말 → 「PDF 매뉴얼 보기」는 `src/manual/` 세 파일로 역할별 설명서를 기기에서 PDF 로 만든다.

| 파일 | 내용 |
|---|---|
| `src/manual/content.ts` | 장 · 꼭지 글, 꼭지별 캡처 연결(`SHOT_BY_BLOCK`) |
| `src/manual/html.ts` | PDF 모양(표지 · 차례 · 본문) |
| `src/manual/shots.ts` | 화면 캡처(JPEG, 자동 생성) |

글만 고칠 때는 `content.ts` 만 고치면 된다. 화면이 바뀌어 캡처를 다시 찍을 때만 아래 순서를 따른다.

## 캡처 다시 찍기

캡처는 실제 서버가 아니라 웹 데모 데이터(`lms_react/src/data/seed.ts`, 가짜 학생 · 기수)로 앱을 브라우저에 띄워 찍는다.
개인정보가 들어가지 않는다.

```bash
# 1. 데모 앱 만들기 (lms_mobile 을 임시 폴더에 복사해 고친 뒤 웹으로 내보냄 — 원본은 그대로)
python3 tools/manual/prepare-demo.py /tmp/lms-demo

# 2. 띄우기
node tools/manual/serve.mjs /tmp/lms-demo/app/dist-web 8090 &

# 3. 찍기 (폰 390×844 · 태블릿 1194×834, 2배율) → ./shots/*.png
CHROME=/path/to/chrome node tools/manual/capture.mjs            # 전체
CHROME=/path/to/chrome node tools/manual/capture.mjs student    # 역할 하나만

# 4. shots.ts 만들기
python3 tools/manual/encode-shots.py shots

# 5. (선택) PC 에서 PDF 미리보기
CHROME=/path/to/chrome node tools/manual/preview-pdf.mjs manual-preview
```

필요한 것: Node 20+, Python 3 + Pillow, `playwright-core`, `esbuild`, 크롬(또는 크로미움).
새 화면을 넣으려면 `capture.mjs` 에 찍는 줄을 더하고 `content.ts` 의 `SHOT_BY_BLOCK` 에 꼭지 제목과 이름을 이어 준다.
