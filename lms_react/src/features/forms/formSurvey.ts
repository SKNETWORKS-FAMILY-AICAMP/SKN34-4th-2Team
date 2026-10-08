import type { FormAnswer, FormQuestion, FormQuestionType, FormResponse, FormTask, User } from '../../domain/types';
import { toCsv, type ExportTable } from '../export/tableExport';

/** 서버(lms/form_surveys.py)와 같은 한도 */
export const MAX_QUESTIONS = 50;
export const SHORT_MAX = 300;
export const LONG_MAX = 5000;

export const QuestionTypes: FormQuestionType[] = ['short', 'long', 'single', 'multi', 'scale', 'date'];

export const QuestionTypeLabels: Record<FormQuestionType, string> = {
  short: '단답',
  long: '장문',
  single: '객관식(하나)',
  multi: '체크박스(여러 개)',
  scale: '점수(척도)',
  date: '날짜',
};

export const QuestionTypeIcons: Record<FormQuestionType, string> = {
  short: 'short_text',
  long: 'notes',
  single: 'radio_button_checked',
  multi: 'check_box',
  scale: 'linear_scale',
  date: 'event',
};

export type Answers = Record<string, FormAnswer>;

export function newQuestionId(): string {
  return Math.random().toString(16).slice(2, 10).padEnd(8, '0');
}

export function newQuestion(type: FormQuestionType = 'short'): FormQuestion {
  const base: FormQuestion = { id: newQuestionId(), type, title: '', required: false };
  if (type === 'single' || type === 'multi') return { ...base, options: ['', ''] };
  if (type === 'scale') return { ...base, scaleMax: 5 };
  return base;
}

/** 종류를 바꿀 때 — 보기 · 척도처럼 새 종류에 필요한 것만 채운다 */
export function changeType(q: FormQuestion, type: FormQuestionType): FormQuestion {
  const { options, scaleMax, minLabel, maxLabel, ...rest } = q;
  const next: FormQuestion = { ...rest, type };
  if (type === 'single' || type === 'multi') next.options = options && options.length >= 2 ? options : ['', ''];
  if (type === 'scale') Object.assign(next, { scaleMax: scaleMax ?? 5, minLabel, maxLabel });
  return next;
}

/** 저장 전에 질문 목록을 검사한다. 문제가 없으면 null */
export function questionsError(questions: FormQuestion[]): string | null {
  if (questions.length === 0) return '질문을 하나 이상 넣어 주세요.';
  if (questions.length > MAX_QUESTIONS) return `질문은 ${MAX_QUESTIONS}개까지 넣을 수 있습니다.`;
  for (const [i, q] of questions.entries()) {
    if (q.title.trim() === '') return `${i + 1}번 질문 내용을 입력해 주세요.`;
    if (q.type === 'single' || q.type === 'multi') {
      const filled = new Set((q.options ?? []).map((o) => o.trim()).filter((o) => o !== ''));
      if (filled.size < 2) return `${i + 1}번 질문에 보기를 두 개 이상 넣어 주세요.`;
    }
  }
  return null;
}

/** 서버로 보낼 모양 — 빈 보기 · 앞뒤 공백을 뺀다 */
export function tidyQuestions(questions: FormQuestion[]): FormQuestion[] {
  return questions.map((q) => {
    const out: FormQuestion = { ...q, title: q.title.trim() };
    const description = q.description?.trim();
    if (description) out.description = description;
    else delete out.description;
    if (q.options) out.options = [...new Set(q.options.map((o) => o.trim()).filter((o) => o !== ''))];
    return out;
  });
}

export function isBlank(value: FormAnswer | undefined): boolean {
  return value === undefined || (typeof value === 'string' && value.trim() === '') || (Array.isArray(value) && value.length === 0);
}

/** 학생 답 검사 — 필수 누락 · 글자 수. 문제가 있으면 질문 id 와 문구 */
export function answersError(questions: FormQuestion[], answers: Answers): { id: string; message: string } | null {
  for (const q of questions) {
    const value = answers[q.id];
    if (isBlank(value)) {
      if (q.required) return { id: q.id, message: `「${q.title}」에 답해 주세요.` };
      continue;
    }
    const limit = q.type === 'short' ? SHORT_MAX : q.type === 'long' ? LONG_MAX : 0;
    if (limit > 0 && typeof value === 'string' && value.trim().length > limit) {
      return { id: q.id, message: `「${q.title}」은(는) ${limit}자까지 쓸 수 있습니다.` };
    }
  }
  return null;
}

/** 답 하나를 사람이 읽는 글자로 */
export function formatAnswer(q: FormQuestion, value: FormAnswer | undefined): string {
  if (isBlank(value)) return '';
  if (Array.isArray(value)) return value.join(', ');
  if (q.type === 'scale') return `${value} / ${q.scaleMax ?? 5}`;
  return String(value);
}

export interface ChoiceTally {
  label: string;
  count: number;
}

export type QuestionSummary =
  | { kind: 'choice'; answered: number; tallies: ChoiceTally[] }
  | { kind: 'scale'; answered: number; tallies: ChoiceTally[]; average: number | null }
  | { kind: 'text'; answered: number; texts: { userId: string; text: string }[] };

/** 질문별 결과 — 객관식 · 체크박스 · 척도는 보기마다 몇 명, 글 답은 목록 */
export function summarize(q: FormQuestion, responses: FormResponse[]): QuestionSummary {
  const values = responses
    .map((r) => ({ userId: r.userId, value: r.answers?.[q.id] }))
    .filter((v): v is { userId: string; value: FormAnswer } => !isBlank(v.value));
  if (q.type === 'single' || q.type === 'multi') {
    const tallies = (q.options ?? []).map((label) => ({
      label,
      count: values.filter((v) => (Array.isArray(v.value) ? v.value.includes(label) : v.value === label)).length,
    }));
    return { kind: 'choice', answered: values.length, tallies };
  }
  if (q.type === 'scale') {
    const max = q.scaleMax ?? 5;
    const scores = values.map((v) => Number(v.value)).filter((n) => Number.isFinite(n));
    const tallies = Array.from({ length: max }, (_, i) => ({
      label: String(i + 1),
      count: scores.filter((n) => n === i + 1).length,
    }));
    const average = scores.length === 0 ? null : Math.round((scores.reduce((a, b) => a + b, 0) / scores.length) * 10) / 10;
    return { kind: 'scale', answered: scores.length, tallies, average };
  }
  return { kind: 'text', answered: values.length, texts: values.map((v) => ({ userId: v.userId, text: String(v.value) })) };
}

function stamp(at: Date | undefined): string {
  if (at === undefined) return '';
  return at.toLocaleString('sv-SE', { timeZone: 'Asia/Seoul' }).slice(0, 16);
}

/** 학생마다 한 줄 — 미제출자도 넣는다 */
export function responsesTable(task: FormTask, responses: FormResponse[], students: User[]): ExportTable {
  const questions = task.mode === 'builtin' ? task.questions : [];
  const header = ['이름', '이메일', '제출', '제출 시각', ...questions.map((q) => q.title)];
  const byUser = new Map(responses.filter((r) => r.taskId === task.id).map((r) => [r.userId, r]));
  const rows = [...students]
    .sort((a, b) => a.displayName.localeCompare(b.displayName, 'ko'))
    .map((s) => {
      const r = byUser.get(s.uid);
      return [
        s.displayName,
        s.personalEmail ?? s.email,
        r ? '제출' : '미제출',
        stamp(r?.submittedAt),
        ...questions.map((q) => formatAnswer(q, r?.answers?.[q.id])),
      ];
    });
  return { title: task.title, header, rows };
}

/** 엑셀에서 바로 열리게 BOM 을 붙인다 */
export function responsesToCsv(task: FormTask, responses: FormResponse[], students: User[]): string {
  return toCsv(responsesTable(task, responses, students));
}
