import { describe, expect, it } from 'vitest';

import type { AssessmentQuestion, CurriculumRow, PracticeSet, StudyNote } from '../../../domain/types';
import { buildReviewLinks, parseLessonDate, relatedProblemIndexes } from '../reviewLinks';

const q = (id: string, sourceDay?: number, sourceTopic?: string): AssessmentQuestion =>
  ({ id, order: 0, type: 'multipleChoice', prompt: id, points: 5, choices: [], acceptedAnswers: [], origin: 'ai', sourceDay, sourceTopic }) as unknown as AssessmentQuestion;

const rows: CurriculumRow[] = [
  { dayIndex: 15, dateLabel: '2026년 9월 15일', subject: '멀티모달', topic: 'RAG', detail: '영상 RAG', order: 0 },
  { dayIndex: 11, dateLabel: '2026-09-11', subject: '멀티모달', topic: 'CNN', detail: 'CNN · ViT', order: 1 },
  { dayIndex: 3, dateLabel: '3일차', subject: '기초', topic: 'Python', detail: '함수', order: 2 },
];
const set = (id: string, lessonDate: string, title: string, topics: string[]): PracticeSet => ({
  id, cohortId: 'c', sourceTitle: '', lessonDate, dayLabel: '', title, files: [], model: '',
  problems: topics.map((topic) => ({ kind: 'concept', topic, prompt: topic, sourceFiles: [], explanation: '', choices: [], answerIndex: 0, starterCode: '', expectedStdout: '', blankAnswers: [], referenceSolution: '', hiddenTests: '', packages: [] })),
});
const sets = [set('s15', '2026-09-15', '영상 RAG', ['프레임 번호 추출', 'OpenCV 색상 순서']), set('s11', '2026-09-11', 'CNN · ViT · CLIP', ['합성곱 출력 크기'])];
const notes: StudyNote[] = [
  { id: 'n1', sourceId: 'src', status: 'done', scopeKey: 'date:2026-09-15', reportMarkdown: '', reviewMarkdown: '', files: [] },
  { id: 'n2', sourceId: 'src', status: 'done', scopeKey: 'python/day01', reportMarkdown: '', reviewMarkdown: '', files: [] },
];

describe('수업일자 읽기', () => {
  it('여러 형식을 읽는다', () => {
    expect(parseLessonDate('2026년 9월 15일')).toBe('2026-09-15');
    expect(parseLessonDate('2026-09-11')).toBe('2026-09-11');
    expect(parseLessonDate('2026.9.5')).toBe('2026-09-05');
    expect(parseLessonDate('9/15', 2026)).toBe('2026-09-15');
  });
  it('일차만 있으면 날짜가 아니다', () => {
    expect(parseLessonDate('3일차')).toBeNull();
    expect(parseLessonDate('9/15')).toBeNull();
  });
});

describe('오답 → 복습 연결', () => {
  it('근거 일수로 묶어 그날 세트와 노트를 잇는다', () => {
    const links = buildReviewLinks({ wrong: [q('a', 15, '프레임 번호'), q('b', 15, 'OpenCV'), q('c', 11, 'CNN')], rows, sets, notes });
    expect(links.map((l) => l.day)).toEqual([15, 11]);
    expect(links[0]).toMatchObject({ date: '2026-09-15', label: '멀티모달 · 영상 RAG' });
    expect(links[0].set?.id).toBe('s15');
    expect(links[0].notes.map((n) => n.id)).toEqual(['n1']);
    expect(links[0].questions).toHaveLength(2);
    expect(links[1].set?.id).toBe('s11');
  });

  it('날짜가 없는 커리큘럼은 주제로 세트를 찾는다', () => {
    const [link] = buildReviewLinks({ wrong: [q('a', 3, '합성곱 출력 크기')], rows, sets, notes });
    expect(link.date).toBe('2026-09-11');
    expect(link.set?.id).toBe('s11');
    expect(link.notes).toEqual([]);
  });

  it('근거 일수가 없는 문항은 따로 묶는다', () => {
    const [link] = buildReviewLinks({ wrong: [q('a')], rows, sets, notes });
    expect(link).toMatchObject({ day: null, date: null, set: null, label: '근거 수업 없음' });
  });

  it('문항과 같은 주제의 복습 문제를 고른다', () => {
    const [link] = buildReviewLinks({ wrong: [q('a', 15, '프레임 번호')], rows, sets, notes });
    expect(relatedProblemIndexes(link, link.questions[0])).toEqual([0]);
    expect(relatedProblemIndexes(link, q('z', 15, '없는 주제'))).toEqual([]);
  });
});
