import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Resume } from '../../../../domain/types';

const post = vi.hoisted(() => vi.fn());
vi.mock('../../../../data/http', () => ({ http: { post, get: vi.fn() } }));

const { CoachAsk } = await import('../CoachAsk');

Element.prototype.scrollTo ??= function scrollTo() {};
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const blank = { subtitle: '', body: '' };
const resume = {
  id: 'r1',
  title: '백엔드 이력서',
  content: {
    basicInfo: { name: '문성호', phone: '', email: '', birthDate: '', githubUrl: '', blogUrl: '' },
    coreCompetencies: { text: '' },
    experience: [],
    education: [],
    techStack: [{ id: 't1', name: 'Python', level: '' }],
    certifications: [],
    awards: [],
    trainingExperience: [],
    otherActivities: [],
    projects: [{ id: 'p1', name: '주문 API', role: '', techStack: '', startDate: '', endDate: '', description: '' }],
    selfIntroduction: {
      intro: blank,
      motivation: blank,
      challenge: blank,
      growth: blank,
      strengthsWeaknesses: blank,
      aspiration: blank,
    },
  },
} as unknown as Resume;

const job = (id: string, title: string) => ({
  job_id: id,
  company: '㈜마켓파일럿',
  title,
  source_url: 'https://example.com',
  region: '서울 금천구',
  career: '신입',
  employment_type: '정규직',
  deadline: '2026-10-10T23:59:00+09:00',
  tech_stack: ['Python', 'FastAPI'],
});

let root: Root;
let host: HTMLDivElement;
const onOpenDetail = vi.fn();

beforeEach(() => {
  post.mockReset();
  onOpenDetail.mockReset();
  host = document.createElement('div');
  document.body.append(host);
  root = createRoot(host);
  act(() => root.render(<CoachAsk resume={resume} hidden={false} onBack={() => {}} onOpenDetail={onOpenDetail} />));
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const button = (name: string) =>
  [...host.querySelectorAll('button')].find((b) => b.textContent?.trim() === name || b.getAttribute('aria-label') === name);

async function click(name: string) {
  const target = button(name);
  if (target === undefined) throw new Error(`단추 없음: ${name}`);
  await act(async () => {
    target.click();
  });
}

describe('코치에게 묻기', () => {
  it('처음에는 안내와 제안 셋이 나오고, 제안을 누르면 서버에 묻는다', async () => {
    expect(host.textContent).toContain('채용에 대해 물어보세요');
    post.mockResolvedValueOnce({
      data: {
        mode: '검색',
        reply: '**백엔드** · 서울 공고 284건을 찾았어요.',
        filters: { regions: ['서울'] },
        jobs: [job('J1', '백엔드 엔지니어'), job('J2', 'API 개발자')],
        suggestions: ['정규직만'],
      },
    });
    await click('서울 백엔드 신입');

    expect(post).toHaveBeenCalledWith('/jobs/chat', expect.objectContaining({ message: '서울 백엔드 신입', resumeId: null, lastJobIds: [] }));
    expect(host.querySelector('.coach-ask__text strong')?.textContent).toBe('백엔드');
    expect(host.querySelectorAll('.coach-ask__card')).toHaveLength(2);
    expect(host.textContent).toContain('마감 2026-10-10');
    // 지나간 답의 제안은 누를 수 없다 — 첫 안내의 제안은 사라지고 새 답의 제안만 남는다
    expect(button('요즘 많이 요구하는 기술이 뭐야?')).toBeUndefined();
    expect(button('정규직만')).toBeDefined();
  });

  it('보여 준 목록 · 조건을 다음 말에 실어 보내고, 목록을 봤으면 이력서도 함께 알린다', async () => {
    post.mockResolvedValueOnce({
      data: { mode: '검색', reply: '찾았어요', filters: { regions: ['서울'] }, jobs: [job('J1', 'A'), job('J2', 'B')], suggestions: ['정규직만'] },
    });
    await click('서울 백엔드 신입');
    post.mockResolvedValueOnce({ data: { mode: '비교', reply: '비교했어요', filters: { regions: ['서울'] }, jobs: [job('J2', 'B')], suggestions: [] } });
    await click('정규직만');

    expect(post).toHaveBeenLastCalledWith(
      '/jobs/chat',
      expect.objectContaining({
        filters: { regions: ['서울'] },
        lastJobIds: ['J1', 'J2'],
        lastAnswerJobIds: ['J1', 'J2'],
        seenJobIds: ['J1', 'J2'],
        resumeId: 'r1',
      }),
    );
  });

  it('「이 공고 물어보기」를 누르면 그 공고를 놓고 묻고, 띠의 ✕로 그만둔다', async () => {
    post.mockResolvedValueOnce({ data: { mode: '검색', reply: '찾았어요', filters: {}, jobs: [job('J1', '백엔드 엔지니어')], suggestions: [] } });
    await click('서울 백엔드 신입');
    await click('이 공고 물어보기');

    expect(host.querySelector('.coach-ask__about')?.textContent).toContain('"백엔드 엔지니어"에 대해 묻는 중');
    post.mockResolvedValueOnce({ data: { mode: '공고', reply: '신입도 됩니다', filters: {}, jobs: [], suggestions: [] } });
    await click('신입도 지원할 수 있어?');
    expect(post).toHaveBeenLastCalledWith('/jobs/chat', expect.objectContaining({ jobId: 'J1', resumeId: 'r1' }));

    await click('그만 묻기');
    expect(host.querySelector('.coach-ask__about')).toBeNull();
  });

  it('추천으로 답하면 그 자리에서 이력서 추천을 돌려 세 건을 보이고, 근거 전체 보기로 넘어간다', async () => {
    post.mockResolvedValueOnce({ data: { mode: '추천', resume_scope: '프로젝트', reply: '골라 볼게요', filters: {}, jobs: [], suggestions: [] } });
    const pick = (id: string) => ({ job_id: id, title: `공고 ${id}`, company: '회사', reasons: [{ claim: `${id} 근거` }], conditions: { region: '서울', career: '신입' } });
    post.mockResolvedValueOnce({ data: { recommendations: [pick('A'), pick('B'), pick('C'), pick('D')] } });
    await click('서울 백엔드 신입');

    expect(post).toHaveBeenLastCalledWith('/jobs/recommend', { resumeId: 'r1', topK: 10, scope: '프로젝트' });
    expect(host.textContent).toContain('프로젝트 경험을 읽고 4건을 골랐어요.');
    expect(host.querySelectorAll('.coach-ask__card')).toHaveLength(3);
    expect(host.textContent).toContain('A 근거');

    await click('근거 전체 보기 →');
    expect(onOpenDetail).toHaveBeenCalled();
  });

  it('서버가 거절하면 그 말을 코치 답으로 보인다', async () => {
    post.mockRejectedValueOnce({ response: { data: { detail: '공고 서버에 연결하지 못했습니다.' } } });
    await click('서울 백엔드 신입');
    expect(host.textContent).toContain('공고 서버에 연결하지 못했습니다.');
  });
});
