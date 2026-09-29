import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({ extractQuestions: vi.fn(), extractQuestionsFromLink: vi.fn() }));

vi.mock('../../resume/review/reviewApi', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../resume/review/reviewApi')>()),
  reviewApi: api,
}));

const { CaptureUpload } = await import('../CaptureUpload');

let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  // jsdom 에는 미리보기 주소가 없다
  URL.createObjectURL = vi.fn(() => `blob:${Math.random()}`);
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
  vi.clearAllMocks();
});

const flush = () => act(async () => {
  await new Promise((resolve) => setTimeout(resolve, 0));
});

function choose(files: File[]) {
  const input = host.querySelector('input[type=file]') as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: files, configurable: true });
  act(() => {
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

const readButton = () => [...host.querySelectorAll('button')].find((b) => b.textContent?.includes('문항 읽기')) as HTMLButtonElement;

describe('캡처 올리기', () => {
  it('고른 캡처를 보내고, 읽은 문항을 확인 목록으로 넘긴다', async () => {
    api.extractQuestions.mockResolvedValue({
      questions: [{ question: '지원 동기를 쓰시오.', limit: 700 }, { question: '협업 경험을 쓰시오.', limit: null }],
      dropped: 1,
    });
    const onParsed = vi.fn();
    act(() => root.render(<CaptureUpload onParsed={onParsed} />));
    expect(readButton().disabled).toBe(true);

    choose([new File(['a'], 'q.png', { type: 'image/png' })]);
    await flush();
    expect(host.querySelectorAll('.apply-thumbs img')).toHaveLength(1);

    act(() => readButton().click());
    await flush();
    expect(api.extractQuestions).toHaveBeenCalledWith([expect.any(File)]);
    const [questions, dropped] = onParsed.mock.calls[0];
    expect(questions.map((q: { question: string; limit: number | null }) => [q.question, q.limit])).toEqual([
      ['지원 동기를 쓰시오.', 700],
      ['협업 경험을 쓰시오.', null],
    ]);
    expect(dropped).toBe(1);
  });

  it('지원서 양식 PDF 는 한 개로 받아 그대로 보낸다', async () => {
    api.extractQuestions.mockResolvedValue({ questions: [], dropped: 0 });
    act(() => root.render(<CaptureUpload onParsed={vi.fn()} />));
    choose([new File(['a'], 'q.png', { type: 'image/png' })]);
    await flush();
    const pdf = new File(['%PDF'], '지원서양식.pdf', { type: 'application/pdf' });
    choose([pdf]);
    await flush();
    // 캡처를 PDF 로 바꾼다 — 섞어 보내지 않는다
    expect(host.querySelectorAll('.apply-thumbs img')).toHaveLength(0);
    expect(host.querySelector('.apply-thumbs__pdf')?.textContent).toContain('지원서양식.pdf');
    act(() => readButton().click());
    await flush();
    expect(api.extractQuestions).toHaveBeenCalledWith([pdf]);
  });

  it('Word 파일은 받지 않고 PDF 로 저장하라고 알려 준다', async () => {
    act(() => root.render(<CaptureUpload onParsed={vi.fn()} />));
    choose([new File(['PK'], 'form.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })]);
    await flush();
    expect(host.querySelectorAll('.apply-thumbs li')).toHaveLength(0);
    expect(host.textContent).toContain('PDF 로 저장해 올려 주세요');
    expect(readButton().disabled).toBe(true);
  });

  it('공고 첨부파일 링크로도 읽는다', async () => {
    api.extractQuestionsFromLink.mockResolvedValue({ questions: [{ question: '직무역량 강화 노력을 기술하시오.', limit: null }] });
    const onParsed = vi.fn();
    act(() => root.render(<CaptureUpload onParsed={onParsed} />));
    const input = host.querySelector('input[type=url]') as HTMLInputElement;
    const url = 'https://dym-upload.saramin.co.kr/upload/attach5.pdf';
    act(() => {
      const setValue = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setValue?.call(input, url);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    act(() => (host.querySelector('.apply-attach-link') as HTMLFormElement).requestSubmit());
    await flush();
    expect(api.extractQuestionsFromLink).toHaveBeenCalledWith(url);
    expect(onParsed.mock.calls[0][0][0].question).toBe('직무역량 강화 노력을 기술하시오.');
    expect(api.extractQuestions).not.toHaveBeenCalled();
  });

  it('세 장까지만 받는다', async () => {
    act(() => root.render(<CaptureUpload onParsed={vi.fn()} />));
    choose([1, 2, 3, 4].map((n) => new File(['a'], `${n}.png`, { type: 'image/png' })));
    await flush();
    expect(host.querySelectorAll('.apply-thumbs img')).toHaveLength(3);
    expect(host.textContent).toContain('3장까지');
  });
});
