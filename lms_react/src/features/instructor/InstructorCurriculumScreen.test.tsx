import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, expect, it, vi } from 'vitest';

const { save } = vi.hoisted(() => ({ save: vi.fn() }));
vi.mock('../../data/repository', () => ({ replaceCurriculumSheet: save, useCurriculumSheets: () => [] }));
vi.mock('../../data/store', () => ({ nextId: () => 'test-sheet' }));
vi.mock('../../tour/useTourTarget', () => ({ useTourTarget: () => null }));
vi.mock('../auth/session', () => ({ useCurrentUser: () => ({ uid:'test',cohortName:'테스트',displayName:'테스트' }) }));
const { InstructorCurriculumScreen } = await import('./InstructorCurriculumScreen');
let root: ReturnType<typeof createRoot>;
let host: HTMLDivElement;
afterEach(() => { act(() => root.unmount()); host.remove(); vi.clearAllMocks(); });
function button(text: string) {
  return [...document.querySelectorAll('button')].find(b => b.textContent?.trim() === text)!;
}
function setup() {
  host=document.createElement('div');document.body.appendChild(host);root=createRoot(host);
  act(() => root.render(<InstructorCurriculumScreen />));
  act(() => button('CSV 등록').click());
  const input=document.querySelector('textarea')!;
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value')!.set!.call(input,'111,2026년 11월 11일 수요일,프로젝트,주제,내용');
    input.dispatchEvent(new Event('input',{bubbles:true}));
  });
  return input;
}
it('keeps input and dialog on server rejection and blocks duplicate submits while pending', async () => {
  let reject!: (reason: unknown) => void;
  save.mockImplementation(() => new Promise((_,fail) => { reject=fail; }));
  const input=setup();
  act(() => button('등록').click());
  expect(save).toHaveBeenCalledTimes(1);
  const saving=[...document.querySelectorAll('button')].find(b => /등록 중|저장 중|등록/.test(b.textContent || '') && b.disabled);
  expect(saving).toBeTruthy();
  await act(async () => { reject({ isAxiosError:true, response:{data:{detail:'111일차 날짜가 101일차와 중복됩니다.'}} }); });
  expect(document.querySelector('textarea')).toBe(input);
  expect(input.value).toContain('2026년 11월 11일');
  expect(document.body.textContent).toContain('111일차 날짜가 101일차와 중복됩니다.');
});
it('closes dialog only after successful save', async () => {
  let resolve!: () => void;
  save.mockImplementation(() => new Promise<void>(done => { resolve=done; }));
  setup();act(() => button('등록').click());
  expect(document.querySelector('textarea')).not.toBeNull();
  await act(async () => { resolve(); });
  expect(document.querySelector('textarea')).toBeNull();
});
