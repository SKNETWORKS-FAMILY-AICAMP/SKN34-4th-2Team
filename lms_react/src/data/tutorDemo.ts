import type { TutorMode, TutorQuestion, TutorReply, TutorTurn } from './repository';

/**
 * 데모(MODE=test) 튜터 — 서버 없이 힌트 단계 · 잡담 거르기 · 정답 잠금이 어떻게 보이는지만 흉내 낸다.
 * 대화는 이 탭이 열려 있는 동안만 기억한다.
 */

const threads = new Map<string, TutorTurn[]>();
// 서버(study_notes/practice/tutor.py)와 같다. JS 의 \W 는 한글도 잡으니 기호는 \p{P}\p{S} 로
const TRIVIAL = /^[\s\p{P}\p{S}_ㅋㅎㅠㅜㅡㄷ]*$|^(안녕|안녕하세요|하이|hi|hello|ㅎㅇ|ㅇㅇ|ok|네|응|테스트|test)[\s\p{P}\p{S}]*$/iu;

function keyOf(mode: TutorMode, setId?: string, index?: number) {
  return mode === 'problem' ? `set:${setId}:${index ?? 0}` : 'cell';
}

function levelOf(turns: TutorTurn[]) {
  return Math.max(0, ...turns.map((t) => t.hintLevel ?? 0));
}

/** 처음으로 뭔가 하는 줄 — def · 빈 줄 · 주석은 건너뛴다 */
function bodyLine(code: string) {
  const lines = code.split('\n');
  const i = lines.findIndex((l) => l.trim() && !l.trim().startsWith('#') && !l.trim().startsWith('def '));
  return i < 0 ? [] : [i + 1];
}

function answer(body: TutorQuestion, level: number | null): Omit<TutorReply, 'hintLevel' | 'llm'> & { llm: boolean } {
  const question = (body.question ?? '').trim();
  if (body.action === 'answer') {
    return {
      kind: 'locked',
      reply: '모범답안은 2번 채점해 본 뒤 문제 아래 「모범답안 보기」에서 열려요. 힌트를 한 단계 더 받아 볼까요?',
      lines: [],
      llm: false,
    };
  }
  if (question.length < 2 || TRIVIAL.test(question)) {
    return {
      kind: 'offtopic',
      reply: '막힌 곳을 한 문장으로 물어봐 주세요. 예: 「왜 이 줄에서 오류가 나요?」',
      lines: [],
      llm: false,
    };
  }
  const lines = bodyLine(body.code);
  if (body.mode === 'problem') {
    const reply =
      level === 1
        ? '채점 메시지가 어떤 값을 기대했는지 먼저 보세요. 지금 코드는 그 값을 어떤 순서로 만들고 있나요?'
        : level === 2
          ? `${lines[0] ?? 1}번째 줄을 보세요. 여기서 고르는(또는 더하는) 방법이 문제에서 원하는 것과 같은지 떠올려 보세요.`
          : `${lines[0] ?? 1}번째 줄의 모양은 거의 맞아요. ___ 자리에 들어갈 함수 하나만 바꿔 보세요.`;
    return { kind: 'hint', reply, lines: level === 1 ? [] : lines, llm: true };
  }
  const error = /(\w+Error)/.exec(body.run)?.[1];
  const reply = error
    ? `${error}가 났어요. ${lines[0] ?? 1}번째 줄에서 쓰는 이름 · 값이 그 줄보다 먼저 만들어졌는지 확인해 보세요. (데모 답변)`
    : '이 셀은 위에서부터 한 줄씩 값을 만들고, 마지막 줄의 값을 보여 줘요. 궁금한 줄을 짚어 물어보면 더 자세히 알려 줄게요. (데모 답변)';
  return { kind: 'explain', reply, lines, llm: true };
}

export async function demoTutorAsk(body: TutorQuestion): Promise<TutorReply> {
  const key = keyOf(body.mode, body.setId, body.index);
  const turns = threads.get(key) ?? [];
  const current = levelOf(turns);
  const level = body.mode === 'problem' ? (body.action === 'more' ? Math.min(3, current + 1) : Math.max(1, current)) : null;
  const question =
    body.question?.trim() || (body.action === 'more' ? '힌트 더 주세요' : body.action === 'answer' ? '정답 알려 주세요' : '');
  const a = answer({ ...body, question }, level);
  await new Promise((r) => setTimeout(r, 500));
  const at = new Date().toISOString();
  threads.set(key, [
    ...turns,
    {
      role: 'user',
      text: question,
      kind: null,
      hintLevel: level,
      lines: [],
      at,
    },
    {
      role: 'assistant',
      text: a.reply,
      kind: a.kind,
      hintLevel: level,
      lines: a.lines,
      at,
    },
  ]);
  return { ...a, hintLevel: level };
}

export async function demoTutorThread(mode: TutorMode, setId?: string, index?: number) {
  const turns = threads.get(keyOf(mode, setId, index)) ?? [];
  return { turns, hintLevel: levelOf(turns) };
}
