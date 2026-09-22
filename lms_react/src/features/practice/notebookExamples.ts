import type { CellType } from './notebookModel';

/** 불러오기 예시 — 34기 멀티모달 수업(2026-09)의 코드에서 브라우저로 돌 수 있는 부분만 옮겼다. */
export const EXAMPLES: { id: string; label: string; source: string; type: CellType; code: string }[] = [
  {
    id: 'frame-no',
    label: '프레임 번호 뽑기',
    source: '9/15 · 03_video_rag_image_caption',
    type: 'code',
    code: `import re

# 프레임 파일명에서 숫자 프레임 번호를 정수로 추출하는 함수
def extract_frame_no(frame_file):
    match = re.search(r'_frame(\\d+)\\.jpg', frame_file)
    return int(match.group(1))

extract_frame_no('alpinist_frame00300.jpg')`,
  },
  {
    id: 'table',
    label: 'DataFrame 표',
    source: '9/15 · 03_video_rag_image_caption 의 captions_df',
    type: 'code',
    code: `import pandas as pd

# 프레임별 캡션 — 수업의 captions_df 를 작게 흉내 냈다
captions = pd.DataFrame({
    'video': ['skiing', 'skiing', 'alpinist', 'alpinist'],
    'frame_no': [30, 60, 0, 300],
    'caption': ['a skier going down', 'snow slope', 'a climber on rock', 'mountain top'],
})
captions`,
  },
  {
    id: 'plot',
    label: '그래프 그리기',
    source: 'matplotlib · plt.show() 없이도 그려진다',
    type: 'code',
    code: `import matplotlib.pyplot as plt

# 영상별로 추출한 프레임 수 — 브라우저에 한글 글꼴이 없어 그래프 글자는 영어로 쓴다
videos = ['skiing', 'alpinist', 'basketball']
frames = [42, 35, 58]

plt.figure(figsize=(5, 3))
plt.bar(videos, frames, color='#0284c7')
plt.title('Frames per video')
plt.ylabel('frames')
plt.show()`,
  },
  {
    id: 'memo',
    label: '마크다운 메모',
    source: '설명을 적는 셀 · 두 번 눌러 편집',
    type: 'markdown',
    code: `## 오늘 정리
- \`re.search\`는 **처음 맞는 곳** 하나만 찾는다
- 괄호 \`( )\`로 감싼 부분이 \`group(1)\`

> 모르겠는 건 [파이썬 re 문서](https://docs.python.org/ko/3/library/re.html)에서 찾아보기`,
  },
  {
    id: 'input',
    label: 'input() 써 보기',
    source: '위 「입력값」 칸에 한 줄씩 적는다',
    type: 'code',
    code: `name = input()
count = int(input())
for i in range(count):
    print(f'{name} {i + 1}번째 프레임')`,
  },
  {
    id: 'loop',
    label: '끝나지 않는 반복문',
    source: '중단 버튼 · 시간 제한 확인용',
    type: 'code',
    code: `n = 0
while n < 3:
    print('n =', n)
    # n += 1 이 빠졌다 — 「중단」을 누르거나 10초 뒤 자동으로 멈춘다`,
  },
];

export const FIRST_CELLS: { type: CellType; source: string }[] = [
  {
    type: 'markdown',
    source: `## 9/15 영상 RAG 복습
프레임 파일명에서 번호를 뽑고, 캡션을 표로 모아 본다. 셀을 고르고 **Shift+Enter**로 실행한다.`,
  },
  { type: 'code', source: EXAMPLES[0].code },
  {
    type: 'code',
    source: `# 앞 셀에서 만든 함수를 그대로 쓴다 — 셀끼리 변수가 이어진다
frames = ['skiing_frame00030.jpg', 'skiing_frame00060.jpg', 'skiing_frame00090.jpg']
[extract_frame_no(f) for f in frames]`,
  },
];
