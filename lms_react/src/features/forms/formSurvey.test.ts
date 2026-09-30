import { beforeEach, describe, expect, it } from 'vitest';

import { deleteFormTask, saveFormTask, submitFormResponse } from '../../data/repository';
import { DemoAccounts, seedUsers } from '../../data/seed';
import { getDb, resetDb } from '../../data/store';
import type { FormQuestion, FormResponse, FormTask } from '../../domain/types';
import {
  answersError,
  changeType,
  formatAnswer,
  newQuestion,
  questionsError,
  responsesToCsv,
  summarize,
  tidyQuestions,
} from './formSurvey';

const student = seedUsers.find((u) => u.uid === DemoAccounts.studentUid)!;

const questions: FormQuestion[] = [
  { id: 'name', type: 'short', title: '이름', required: true },
  { id: 'track', type: 'single', title: '분야', required: true, options: ['AI', '웹'] },
  { id: 'tools', type: 'multi', title: '도구', required: false, options: ['git', 'docker'] },
  { id: 'score', type: 'scale', title: '만족도', required: false, scaleMax: 5 },
];

const task: FormTask = {
  id: 'survey-x',
  title: '테스트 설문',
  description: '',
  mode: 'builtin',
  formUrl: '',
  questions,
  dueAt: new Date(Date.now() + 86400000),
  published: true,
  responseCount: 0,
};

const response = (userId: string, answers: FormResponse['answers']): FormResponse => ({
  id: userId,
  userId,
  userEmail: '',
  userDisplayName: userId,
  taskId: task.id,
  source: 'builtin',
  answers,
  submittedAt: new Date('2026-09-30T03:00:00Z'),
});

beforeEach(() => {
  resetDb();
});

describe('설문 만들기 규칙', () => {
  it('빈 질문 · 보기 부족을 막는다', () => {
    expect(questionsError([])).toContain('하나 이상');
    expect(questionsError([{ ...newQuestion('short'), title: ' ' }])).toBe('1번 질문 내용을 입력해 주세요.');
    expect(questionsError([{ ...newQuestion('single'), title: '분야', options: ['AI', ' ', 'AI'] }])).toContain('보기를 두 개');
    expect(questionsError(questions)).toBeNull();
  });

  it('종류를 바꾸면 필요한 칸만 남기고, 저장 전에 빈 보기를 뺀다', () => {
    const scale = changeType({ ...questions[1] }, 'scale');
    expect(scale.options).toBeUndefined();
    expect(scale.scaleMax).toBe(5);
    expect(changeType(scale, 'multi').options).toEqual(['', '']);
    const [tidy] = tidyQuestions([{ ...questions[1], title: ' 분야 ', options: ['AI', '', ' AI ', '웹'], description: ' ' }]);
    expect(tidy).toEqual({ id: 'track', type: 'single', title: '분야', required: true, options: ['AI', '웹'] });
  });
});

describe('학생 답 규칙', () => {
  it('필수 누락을 질문 id 와 함께 알려 준다', () => {
    expect(answersError(questions, { name: '홍길동' })).toEqual({ id: 'track', message: '「분야」에 답해 주세요.' });
    expect(answersError(questions, { name: '홍길동', track: 'AI', tools: [] })).toBeNull();
  });

  it('답을 읽기 좋게 바꾼다', () => {
    expect(formatAnswer(questions[2], ['git', 'docker'])).toBe('git, docker');
    expect(formatAnswer(questions[3], 4)).toBe('4 / 5');
    expect(formatAnswer(questions[0], undefined)).toBe('');
  });
});

describe('결과 집계', () => {
  const rows = [
    response('a', { name: '가', track: 'AI', tools: ['git', 'docker'], score: 5 }),
    response('b', { name: '나', track: 'AI', tools: ['git'], score: 3 }),
    response('c', { name: '다', track: '웹' }),
  ];

  it('객관식 · 체크박스는 보기마다 센다', () => {
    expect(summarize(questions[1], rows)).toEqual({
      kind: 'choice',
      answered: 3,
      tallies: [
        { label: 'AI', count: 2 },
        { label: '웹', count: 1 },
      ],
    });
    const tools = summarize(questions[2], rows);
    expect(tools.answered).toBe(2);
    expect(tools.kind === 'choice' && tools.tallies.map((t) => t.count)).toEqual([2, 1]);
  });

  it('척도는 점수별 수와 평균을 낸다', () => {
    const score = summarize(questions[3], rows);
    expect(score.kind === 'scale' && score.average).toBe(4);
    expect(score.kind === 'scale' && score.tallies.map((t) => t.count)).toEqual([0, 0, 1, 0, 1]);
  });

  it('CSV 는 미제출자까지 한 줄씩, 질문이 열이 된다', () => {
    const csv = responsesToCsv(task, [rows[0]], [student]);
    const [header, line] = csv.replace('\uFEFF', '').split('\r\n');
    expect(header).toBe('이름,이메일,제출,제출 시각,이름,분야,도구,만족도');
    expect(line.startsWith(`${student.displayName},`)).toBe(true);
    expect(line).toContain('미제출');
  });
});

describe('설문 흐름(테스트 모드)', () => {
  it('만들고 · 학생이 내고 · 다시 내면 응답 하나만 남는다', async () => {
    const id = await saveFormTask({ ...task, id: '' });
    const saved = getDb().formTasks.find((t) => t.id === id)!;
    expect(saved.mode).toBe('builtin');

    await submitFormResponse(saved, { name: '홍길동', track: 'AI' }, student);
    await submitFormResponse(saved, { name: '홍길동', track: '웹' }, student);
    const mine = getDb().formResponses.filter((r) => r.taskId === id && r.userId === student.uid);
    expect(mine).toHaveLength(1);
    expect(mine[0].answers).toEqual({ name: '홍길동', track: '웹' });
    expect(mine[0].source).toBe('builtin');
    expect(getDb().formTasks.find((t) => t.id === id)?.responseCount).toBe(1);

    await deleteFormTask(id);
    expect(getDb().formTasks.some((t) => t.id === id)).toBe(false);
    expect(getDb().formResponses.some((r) => r.taskId === id)).toBe(false);
  });
});
