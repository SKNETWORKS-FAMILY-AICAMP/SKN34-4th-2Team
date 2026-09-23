import { beforeEach, describe, expect, it, vi } from 'vitest';

import { changedRevisionSpans } from '../reviewDiff';
import type { Json } from '../reviewApi';

const api = vi.hoisted(() => ({
  context: vi.fn(),
  createTailored: vi.fn(),
  tailored: vi.fn(),
  saveSession: vi.fn(),
  promote: vi.fn(),
  review: vi.fn(),
  apply: vi.fn(),
  undo: vi.fn(),
}));

vi.mock('../reviewApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../reviewApi')>()),
  reviewApi: api,
}));

const { ReviewSession } = await import('../reviewSession');

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

function makeSession(extra: Partial<ConstructorParameters<typeof ReviewSession>[0]> = {}) {
  const closed: (string | undefined)[] = [];
  const session = new ReviewSession({
    resumeId: 'r1',
    jobId: 'JOB-1',
    jobCompany: '㈜회사',
    jobTitle: 'AI 개발자',
    tailoredResumeId: '',
    initialReviewSession: {},
    generalReview: false,
    onChanged: () => {},
    onClose: (result) => closed.push(result),
    confirmComplete: async () => true,
    onStatus: () => {},
    onFocusPreview: () => {},
    onRefocusAnswer: () => {},
    ...extra,
  });
  session.attach();
  return { session, closed };
}

const sentence = (i: number, editType: string, extra: Json = {}): Json => ({
  field_path: `projects[${i}].description`,
  original_quote: `원문 ${i}`,
  suggested_revision: `고친 문장 ${i}`,
  edit_type: editType,
  reason: `이유 ${i}`,
  ...extra,
});

const firstReview: Json = {
  review_id: 'rev-1',
  input_hash: 'h1',
  summary: '공고와 비교했습니다. 프로젝트 근거가 있습니다. 수치는 없습니다. 네 번째 문장.',
  job_source: { company: '㈜회사', title: 'AI 개발자', snapshot_hash: 'job-h' },
  sentence_reviews: [sentence(0, 'clarity'), sentence(1, 'tone'), sentence(2, 'content'), sentence(3, 'content', { original_quote: '[회사명] 지원' })],
  questions: [
    { question_id: 'q1', field_path: 'projects[0].description', topic: 'result', question: '성과가 있나요?', stage: 3 },
    { question_id: 'q2', field_path: 'projects[1].description', topic: 'action', question: '무엇을 했나요?', stage: 3 },
  ],
  requirement_map: [{ id: 'req-1', group: 'must', label: 'Python', status: 'met' }],
  star_checks: [{ field_path: 'projects[0].description', present: ['action'] }],
};

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.createTailored.mockResolvedValue({ tailored_resume_id: 'tailored_1', content: { basicInfo: { name: '학생' } }, review_session: {} });
  api.context.mockResolvedValue({ content: { basicInfo: { name: '학생' } }, input_hash: 'h1', job_source: { snapshot_hash: 'job-h' } });
  api.saveSession.mockResolvedValue({ saved: true });
  api.review.mockResolvedValue(firstReview);
});

describe('공고 맞춤 첨삭 흐름 — job_resume_review_dialog.dart', () => {
  it('첫 첨삭: 사본을 뜨고, 공고 hash 를 실어 부르고, 요약 · 문장 다듬기 묶음부터 보여 준다', async () => {
    const { session } = makeSession();
    await session.review();

    expect(api.createTailored).toHaveBeenCalledWith('r1', 'JOB-1');
    const request = api.review.mock.calls[0][1] as Json;
    expect(request).toMatchObject({
      review_mode: 'job',
      tailored_resume_id: 'tailored_1',
      selected_job_id: 'JOB-1',
      expected_input_hash: 'h1',
      expected_job_hash: 'job-h',
    });
    // 요약은 세 문장까지 글머리표로
    expect(session.messages[0]).toEqual({
      type: 'assistant',
      text: '검토 요약\n\n• 공고와 비교했습니다.\n\n• 프로젝트 근거가 있습니다.\n\n• 수치는 없습니다.',
    });
    // 표현만 고친 두 개는 한 카드로, 질문은 수정안을 정한 뒤로 미룬다
    expect(session.messages[1]).toMatchObject({ type: 'identity', payload: { _kind: 'polish', _indices: [0, 1] } });
    expect(session.messages).toHaveLength(2);
    expect(session.pendingQuestion).toMatchObject({ question_id: 'q1' });
    expect(session.view().currentStage).toBe(1);
    expect(api.saveSession).toHaveBeenCalled();
  });

  it('건너뛰면 다음 수정안, 회사명 · 직무명 확인, 그다음 질문 순서로 나온다', async () => {
    const { session } = makeSession();
    await session.review();

    session.skipSuggestion([0, 1]);
    expect(session.messages.at(-1)).toMatchObject({ type: 'suggestion', payload: { _index: 2 } });
    session.skipSuggestion([2]);
    expect(session.messages.at(-1)).toMatchObject({
      type: 'identity',
      payload: { _indices: [3], _company: '㈜회사', _title: 'AI 개발자' },
    });
    session.skipSuggestion([3]);
    expect(session.messages.at(-1)).toMatchObject({ type: 'question', payload: { question_id: 'q1' } });
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q1' });
    expect(session.view().remainingQuestionCount).toBe(2);
  });

  it('반영하면 표시가 바뀌고 되돌리기가 생기며, 되돌리면 다시 풀린다', async () => {
    const { session } = makeSession();
    await session.review();
    api.apply.mockResolvedValue({ operation_id: 'op-1', input_hash: 'h2' });
    api.undo.mockResolvedValue({ input_hash: 'h1' });

    await session.applySuggestion([0, 1]);
    expect(api.apply.mock.calls[0][1]).toMatchObject({
      review_id: 'rev-1',
      expected_input_hash: 'h1',
      selected_indices: [0, 1],
      tailored_resume_id: 'tailored_1',
    });
    const bundle = session.messages[1];
    expect(bundle.type === 'identity' && bundle.payload).toMatchObject({ _applied: true, _undo_available: true });
    expect(session.result?.input_hash).toBe('h2');
    expect(session.changed).toBe(true);

    await session.undoSuggestion((bundle as { payload: Json }).payload);
    expect(api.undo.mock.calls[0][1]).toMatchObject({ application_id: 'op-1', expected_input_hash: 'h2' });
    expect(bundle.type === 'identity' && bundle.payload).toMatchObject({ _applied: false, _undone: true });
  });

  it('「없음」은 기다리지 않고 다음 질문을 띄우고, 기록은 뒤에서 보낸다', async () => {
    const { session } = makeSession();
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [] });
    await session.review();
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q1' });

    api.review.mockResolvedValueOnce({
      ...firstReview,
      review_id: 'rev-2',
      sentence_reviews: [],
      questions: [{ question_id: 'q2b', field_path: 'projects[1].description', topic: 'action', question: '무엇을 했나요?', stage: 3 }],
      telemetry: { model_skipped: 'none_answer' },
    });
    session.submitNoneAnswer(session.view().activeQuestion!);
    // 바로 다음 질문
    expect(session.messages.slice(-3).map((m) => m.type)).toEqual(['user', 'assistant', 'question']);
    await flush();
    await flush();
    const noneCall = api.review.mock.calls[1][1] as Json;
    expect(noneCall).toMatchObject({ previous_review_id: 'rev-1', answers: [{ question_id: 'q1', answer: '없음' }] });
    // 서버가 새로 매긴 질문 번호를 떠 있는 질문이 받는다
    expect(session.view().activeQuestion).toMatchObject({ question_id: 'q2b' });
  });

  it('질문을 다 마치면 누락 점검을 한 번 하고 완료 안내를 띄운다', async () => {
    const { session } = makeSession();
    api.review.mockResolvedValueOnce({ ...firstReview, sentence_reviews: [], questions: [] });
    api.review.mockResolvedValueOnce({ ...firstReview, review_id: 'rev-gap', sentence_reviews: [], questions: [] });
    await session.review();
    session.afterRender();
    await flush();
    await flush();
    const gap = api.review.mock.calls[1][1] as Json;
    expect(gap).toMatchObject({ review_phase: 'gap_audit', previous_review_id: 'rev-1' });
    expect(session.messages.at(-1)).toEqual({
      type: 'assistant',
      text: '누락 점검까지 완료했습니다. 추가로 확인할 중요한 항목이 없습니다.',
    });
    expect(session.view().reviewCompleted).toBe(true);
    expect(session.sessionCompleted).toBe(true);
  });

  it('첨삭 완료는 대화를 저장하고 사본을 편집기로 옮겨 그 id 로 닫는다', async () => {
    const { session, closed } = makeSession();
    api.promote.mockResolvedValue('matched_1');
    await session.review();
    await session.completeReview();
    expect(api.promote).toHaveBeenCalledWith('r1', 'tailored_1');
    expect(closed).toEqual(['matched_1']);
    const saved = api.saveSession.mock.calls.at(-1)![2] as Json;
    expect(saved).toMatchObject({ version: 1, job_id: 'JOB-1', manually_completed: true, completed: true });
  });

  it('저장된 대화로 다시 열면 이어 간다 — 다른 공고의 대화는 버린다', () => {
    const saved: Json = {
      version: 1,
      resume_id: 'r1',
      job_id: 'JOB-1',
      result: { review_id: 'rev-1', input_hash: 'h1' },
      messages: [{ type: 'assistant', text: '검토 요약' }],
      question_queue: [],
      pending_question: null,
    };
    const { session } = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: saved });
    expect(session.messages).toEqual([{ type: 'assistant', text: '검토 요약' }]);
    const other = makeSession({ tailoredResumeId: 'tailored_1', initialReviewSession: { ...saved, job_id: 'JOB-2' } });
    expect(other.session.messages).toEqual([]);
  });

  it('일반 첨삭은 사본을 만들지 않고 대화도 저장하지 않는다', async () => {
    const { session } = makeSession({ generalReview: true });
    await session.review();
    expect(api.createTailored).not.toHaveBeenCalled();
    expect(api.review.mock.calls[0][1]).toMatchObject({ review_mode: 'general' });
    expect(api.review.mock.calls[0][1]).not.toHaveProperty('selected_job_id');
    expect(api.saveSession).not.toHaveBeenCalled();
  });
});

describe('수정안에서 바뀐 글자만 굵게', () => {
  it('앞뒤가 같으면 가운데 바뀐 부분만', () => {
    expect(changedRevisionSpans('데이터를 분석했습니다', '데이터를 정제해 분석했습니다')).toEqual([
      { text: '데이터를 ', changed: false },
      { text: '정제해 ', changed: true },
      { text: '분석했습니다', changed: false },
    ]);
  });
  it('원문이 비면 전부 새 글자, 같으면 그대로', () => {
    expect(changedRevisionSpans('', '새 문장')).toEqual([{ text: '새 문장', changed: true }]);
    expect(changedRevisionSpans('같음', '같음')).toEqual([{ text: '같음', changed: false }]);
  });
});
