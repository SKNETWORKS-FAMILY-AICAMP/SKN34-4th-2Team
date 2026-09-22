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

/**
 * 연습 문제 — 세트 없이 연습장에서 바로 풀어 보는 짧은 파이썬 문제.
 * 설명(마크다운) · 풀 자리(코드) · 확인(assert 를 실행해 보는 코드) 세 셀로 들어간다.
 * 채점 기록은 남기지 않는다 — 복습 문제(세트)와 달리 그냥 손 푸는 용도다.
 */
export interface MiniProblem {
  id: string;
  title: string;
  prompt: string;
  starter: string;
  check: string;
}

export const MINI_PROBLEMS: MiniProblem[] = [
  {
    id: 'frame-no',
    title: '프레임 번호 뽑기',
    prompt:
      "`skiing_frame00030.jpg` 같은 파일명에서 `_frame` 뒤의 숫자를 **정수**로 돌려주는 `frame_no(name)` 를 만드세요. " +
      '앞의 0 은 떼어져야 합니다 (`00030` → `30`).',
    starter: `import re

def frame_no(name):
    # 여기에 작성
    pass`,
    check: `# 확인 — 모두 통과하면 아무것도 찍히지 않고, 틀리면 AssertionError 가 난다
assert frame_no('skiing_frame00030.jpg') == 30
assert frame_no('alpinist_frame00300.jpg') == 300
assert frame_no('x_frame0.jpg') == 0
print('통과!')`,
  },
  {
    id: 'every-nth',
    title: '일정 간격으로 고르기',
    prompt:
      '프레임 목록 `frames` 에서 `step` 개마다 하나씩(0번째부터) 고르는 `every_nth(frames, step)` 을 만드세요. ' +
      '예: `every_nth([0,1,2,3,4,5], 3)` → `[0, 3]`',
    starter: `def every_nth(frames, step):
    # 여기에 작성
    pass`,
    check: `assert every_nth([0, 1, 2, 3, 4, 5], 3) == [0, 3]
assert every_nth(list(range(10)), 4) == [0, 4, 8]
assert every_nth([], 2) == []
print('통과!')`,
  },
  {
    id: 'cosine',
    title: '코사인 유사도',
    prompt:
      '두 벡터의 코사인 유사도 `cosine(a, b)` 를 numpy 로 만드세요. 내적을 두 벡터 크기의 곱으로 나눕니다. ' +
      '같은 방향이면 1, 직각이면 0 이어야 합니다.',
    starter: `import numpy as np

def cosine(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    # 여기에 작성
    pass`,
    check: `assert abs(cosine([1, 0], [1, 0]) - 1) < 1e-9
assert abs(cosine([1, 0], [0, 1])) < 1e-9
assert abs(cosine([1, 1], [1, 0]) - 0.7071) < 1e-3
print('통과!')`,
  },
  {
    id: 'count-words',
    title: '단어 세기',
    prompt:
      "문장에서 단어별 개수를 딕셔너리로 돌려주는 `count_words(text)` 를 만드세요. 대소문자는 가리지 않습니다. " +
      "예: `'to be or not to be'` → `{'to': 2, 'be': 2, 'or': 1, 'not': 1}`",
    starter: `def count_words(text):
    # 여기에 작성
    pass`,
    check: `assert count_words('to be or not to be') == {'to': 2, 'be': 2, 'or': 1, 'not': 1}
assert count_words('A a b') == {'a': 2, 'b': 1}
assert count_words('') == {}
print('통과!')`,
  },
  {
    id: 'top-k',
    title: '가장 비슷한 k개',
    prompt:
      '점수 배열 `scores` 에서 값이 큰 순서로 인덱스 `k` 개를 돌려주는 `top_k(scores, k)` 를 만드세요. ' +
      '예: `top_k([0.1, 0.9, 0.5], 2)` → `[1, 2]`',
    starter: `import numpy as np

def top_k(scores, k):
    # 여기에 작성 — np.argsort 를 떠올려 보세요
    pass`,
    check: `assert list(top_k([0.1, 0.9, 0.5], 2)) == [1, 2]
assert list(top_k([3, 1, 2], 3)) == [0, 2, 1]
assert list(top_k([5], 1)) == [0]
print('통과!')`,
  },
];
