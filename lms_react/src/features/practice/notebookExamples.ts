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
    source: '실행하면 셀 아래에 입력칸이 뜬다',
    type: 'code',
    code: `name = input('이름: ')
count = int(input('몇 장? '))
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
 *
 * 난이도 세 단계로 나누고 **쉬운 것부터** 늘어놓는다. 「연습 문제 풀기」는 아직 노트북에
 * 없는 것 중 맨 앞 것을 넣으므로, 처음 누르면 기초부터 차례로 나온다.
 *
 *   1 기초   변수 · 산술 · 문자열 · 리스트 · if · for — 문법 하나씩
 *   2 중급   함수로 묶기 · 딕셔너리 · 문자열 다듬기 · 컴프리헨션
 *   3 응용   정규식 · numpy · 수업(영상 RAG)에서 실제로 쓴 모양
 */
export type MiniLevel = 1 | 2 | 3;

export const MINI_LEVELS: Record<MiniLevel, string> = { 1: '기초', 2: '중급', 3: '응용' };

export interface MiniProblem {
  id: string;
  level: MiniLevel;
  title: string;
  prompt: string;
  starter: string;
  check: string;
}

export const MINI_PROBLEMS: MiniProblem[] = [
  // ── 1 기초 ──────────────────────────────────────────────
  {
    id: 'add',
    level: 1,
    title: '두 수 더하기',
    prompt: '두 수를 받아 더한 값을 돌려주는 `add(a, b)` 를 만드세요. `return` 으로 값을 돌려줘야 합니다 — `print` 는 화면에 찍기만 할 뿐 돌려주지 않아요.',
    starter: `def add(a, b):
    # 여기에 작성
    pass`,
    check: `# 확인 — 모두 통과하면 「통과!」, 틀리면 AssertionError 가 난다
assert add(1, 2) == 3
assert add(10, -4) == 6
assert add(0.5, 0.25) == 0.75
print('통과!')`,
  },
  {
    id: 'is-even',
    level: 1,
    title: '짝수인지 알아보기',
    prompt: '정수가 짝수면 `True`, 홀수면 `False` 를 돌려주는 `is_even(n)` 을 만드세요. 나머지 연산자 `%` 를 써 보세요.',
    starter: `def is_even(n):
    # 여기에 작성
    pass`,
    check: `assert is_even(4) is True
assert is_even(7) is False
assert is_even(0) is True
print('통과!')`,
  },
  {
    id: 'biggest',
    level: 1,
    title: '가장 큰 값',
    prompt: '숫자 리스트에서 가장 큰 값을 돌려주는 `biggest(nums)` 를 만드세요. `max()` 를 써도 되고, `for` 로 하나씩 견줘도 됩니다.',
    starter: `def biggest(nums):
    # 여기에 작성
    pass`,
    check: `assert biggest([3, 9, 2]) == 9
assert biggest([-5, -1, -9]) == -1
assert biggest([42]) == 42
print('통과!')`,
  },
  {
    id: 'sum-to',
    level: 1,
    title: '1부터 n까지 더하기',
    prompt: '`1 + 2 + … + n` 을 돌려주는 `sum_to(n)` 을 만드세요. `for` 와 `range` 로 직접 더해 보세요.',
    starter: `def sum_to(n):
    total = 0
    # 여기에 작성
    return total`,
    check: `assert sum_to(1) == 1
assert sum_to(5) == 15
assert sum_to(100) == 5050
print('통과!')`,
  },
  {
    id: 'evens',
    level: 1,
    title: '짝수만 고르기',
    prompt: '리스트에서 짝수만 골라 **새 리스트**로 돌려주는 `evens(nums)` 를 만드세요. 순서는 그대로 둡니다.',
    starter: `def evens(nums):
    result = []
    # 여기에 작성
    return result`,
    check: `assert evens([1, 2, 3, 4, 5, 6]) == [2, 4, 6]
assert evens([1, 3, 5]) == []
assert evens([]) == []
print('통과!')`,
  },
  {
    id: 'reverse',
    level: 1,
    title: '문자열 뒤집기',
    prompt: "문자열을 거꾸로 돌려주는 `reverse(s)` 를 만드세요. 예: `'abc'` → `'cba'`. 슬라이스 `[::-1]` 을 써도 됩니다.",
    starter: `def reverse(s):
    # 여기에 작성
    pass`,
    check: `assert reverse('abc') == 'cba'
assert reverse('영상 RAG') == 'GAR 상영'
assert reverse('') == ''
print('통과!')`,
  },
  {
    id: 'ext',
    level: 1,
    title: '파일 확장자 꺼내기',
    prompt: "파일 이름에서 확장자만 돌려주는 `ext(name)` 을 만드세요. 예: `'frame00030.jpg'` → `'jpg'`. 마지막 `.` 뒤를 보면 됩니다.",
    starter: `def ext(name):
    # 여기에 작성 — name.split('.') 이나 name.rsplit('.', 1)
    pass`,
    check: `assert ext('frame00030.jpg') == 'jpg'
assert ext('captions.csv') == 'csv'
assert ext('video.2024.mp4') == 'mp4'
print('통과!')`,
  },

  // ── 2 중급 ──────────────────────────────────────────────
  {
    id: 'every-nth',
    level: 2,
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
    id: 'mmss',
    level: 2,
    title: '초를 분:초로',
    prompt: "초 단위 정수를 `'분:초'` 로 바꾸는 `mmss(seconds)` 를 만드세요. 두 자리로 맞춥니다. 예: `65` → `'01:05'`. `//` 와 `%`, 그리고 f-문자열의 `:02d` 를 떠올려 보세요.",
    starter: `def mmss(seconds):
    # 여기에 작성
    pass`,
    check: `assert mmss(65) == '01:05'
assert mmss(0) == '00:00'
assert mmss(600) == '10:00'
print('통과!')`,
  },
  {
    id: 'clip',
    level: 2,
    title: '긴 캡션 줄이기',
    prompt: "글이 `n` 글자보다 길면 `n` 글자까지만 두고 끝에 `…` 를 붙이는 `clip(text, n)` 을 만드세요. 짧으면 그대로 돌려줍니다.",
    starter: `def clip(text, n):
    # 여기에 작성
    pass`,
    check: `assert clip('스키를 타는 사람이 산을 내려온다', 6) == '스키를 타는…'
assert clip('짧은 글', 10) == '짧은 글'
assert clip('정확히열글자입니다요', 10) == '정확히열글자입니다요'
print('통과!')`,
  },
  {
    id: 'count-words',
    level: 2,
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
    id: 'most-common',
    level: 2,
    title: '가장 흔한 단어',
    prompt: "문장에서 가장 많이 나온 단어를 돌려주는 `most_common(text)` 을 만드세요. 앞에서 만든 「단어 세기」를 다시 쓰거나 `collections.Counter` 를 써도 됩니다. 빈 문장이면 `None`.",
    starter: `from collections import Counter

def most_common(text):
    # 여기에 작성
    pass`,
    check: `assert most_common('to be or not to be to') == 'to'
assert most_common('apple') == 'apple'
assert most_common('') is None
print('통과!')`,
  },

  // ── 3 응용 ──────────────────────────────────────────────
  {
    id: 'frame-no',
    level: 3,
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
    id: 'sort-frames',
    level: 3,
    title: '프레임 이름 번호순 정렬',
    prompt:
      "프레임 파일명을 **번호 순서**로 정렬해 돌려주는 `sort_frames(names)` 를 만드세요. 글자순으로 하면 `frame10` 이 `frame9` 앞에 옵니다. " +
      '`sorted(..., key=...)` 에 앞에서 만든 번호 뽑기를 넣어 보세요.',
    starter: `import re

def sort_frames(names):
    # 여기에 작성
    pass`,
    check: `assert sort_frames(['a_frame10.jpg', 'a_frame9.jpg', 'a_frame100.jpg']) == ['a_frame9.jpg', 'a_frame10.jpg', 'a_frame100.jpg']
assert sort_frames([]) == []
print('통과!')`,
  },
  {
    id: 'cosine',
    level: 3,
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
    id: 'top-k',
    level: 3,
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

/** 노트북에 이미 들어간 연습 문제 제목 — 설명 셀의 머리글로 알아본다 */
export const MINI_HEADING = '### 연습 · ';
