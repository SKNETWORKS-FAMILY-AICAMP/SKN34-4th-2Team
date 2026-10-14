import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const http = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('../../../../data/http', () => ({ http }));

import { reviewApi, ReviewApiError } from '../reviewApi';

describe('자소서 답 쓰기 — 백그라운드 작업', () => {
  beforeEach(() => {
    http.post.mockReset();
    vi.useFakeTimers();
  });
  afterEach(() => vi.useRealTimers());

  it('같은 작업 번호로 3초마다 물어 끝나면 결과를 돌려준다', async () => {
    const result = { questions: [{ question_id: 'cq1', draft: '답' }], job_closed: false };
    http.post
      .mockResolvedValueOnce({ data: { async_job: { state: 'queued', elapsed_seconds: 0 } } })
      .mockResolvedValueOnce({ data: { async_job: { state: 'running', elapsed_seconds: 3 } } })
      .mockResolvedValueOnce({ data: result });
    const done = reviewApi.questionWorkflow('r1', 'apply_1', [], { stage: 'plan' });
    await vi.runAllTimersAsync();
    await expect(done).resolves.toEqual(result);
    expect(http.post).toHaveBeenCalledTimes(3);
    const attempts = http.post.mock.calls.map((c) => (c[1] as { asyncAttempt: string }).asyncAttempt);
    expect(new Set(attempts).size).toBe(1);
    expect(attempts[0]).toBeTruthy();
    expect((http.post.mock.calls[0][1] as { stage: string }).stage).toBe('plan');
    expect(http.post.mock.calls[0][2]).toEqual({ timeout: 30_000 }); // 확인 요청은 짧다
  });

  it('확인 요청이 잠깐 끊겨도(504 · 연결) 같은 번호로 이어 묻는다', async () => {
    http.post
      .mockResolvedValueOnce({ data: { async_job: { state: 'running', elapsed_seconds: 1 } } })
      .mockRejectedValueOnce({ response: { status: 504, data: {} } })
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ data: { questions: [] } });
    const done = reviewApi.questionWorkflow('r1', 'apply_1', []);
    await vi.runAllTimersAsync();
    await expect(done).resolves.toEqual({ questions: [] });
    expect(http.post).toHaveBeenCalledTimes(4);
  });

  it('서버가 정한 실패(마감 · 문항 없음)는 그대로 알린다', async () => {
    http.post.mockRejectedValueOnce({ response: { status: 422, data: { detail: 'company_question_not_found' } } });
    const done = reviewApi.questionWorkflow('r1', 'apply_1', []);
    const caught = done.catch((err: unknown) => err);
    await vi.runAllTimersAsync();
    const err = await caught;
    expect(err).toBeInstanceOf(ReviewApiError);
    expect((err as ReviewApiError).message).toContain('이 문항을 이력서에서 찾지 못했어요');
    expect(http.post).toHaveBeenCalledTimes(1);
  });
});
