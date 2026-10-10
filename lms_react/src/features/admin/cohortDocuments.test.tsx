import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { AdminCohortFormScreen } from './AdminPeopleScreens';

const mocks = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn(), upload: vi.fn(), read: vi.fn(), preview: vi.fn(), cohorts: [] as unknown[] }));
vi.mock('../../data/repository', async (original) => ({
  ...await original<typeof import('../../data/repository')>(),
  useCohorts: () => mocks.cohorts, createCohort: mocks.create, updateCohort: mocks.update,
  uploadCohortDocument: mocks.upload, getCohortDocuments: mocks.read,
  getCohortDeletionPreview: mocks.preview,
}));
let cleanup: () => void;
afterEach(() => { cleanup?.(); mocks.cohorts = []; vi.resetAllMocks(); });

const emptyDocuments = {cohortId:'cohort_test',documents:{curriculum:null,policy:null}};

it('warns when a stored policy has no calculation criteria', async () => {
  mocks.cohorts = [{cohortId:'cohort_test',name:'테스트 기수',status:'planned',studentCount:0}];
  mocks.read.mockResolvedValue(emptyDocuments);
  mocks.update.mockResolvedValue(undefined);
  mocks.upload.mockResolvedValue({calculationStatus:'unverified',calculationIssues:{allowance:'missing'}});
  const host = document.createElement('div'); document.body.appendChild(host);
  const root = createRoot(host);
  cleanup = () => { act(() => root.unmount()); host.remove(); };
  await act(async () => root.render(<MemoryRouter initialEntries={['/admin/cohorts/cohort_test/edit']}>
    <Routes><Route path="/admin/cohorts/:cohortId/edit" element={<AdminCohortFormScreen />} /></Routes>
  </MemoryRouter>));
  await act(async () => {
    const input = host.querySelector('input[aria-label="기수별 정책 문서"]')!;
    Object.defineProperty(input,'files',{value:[new File(['test'],'test.docx')]});
    input.dispatchEvent(new Event('change',{bubbles:true}));
  });
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '변경사항 저장')!.click());
  expect(host.textContent).toContain('장려금 기준 확인이 필요합니다');
  expect(host.textContent).toContain('해당 개인 계산은 보류됩니다');
  expect(mocks.upload).toHaveBeenCalledTimes(1);
  expect(mocks.create).not.toHaveBeenCalled();
});

it('shows matching archived and active cohorts by stable identity and blocks new creation', async () => {
  mocks.cohorts = [
    {cohortId:'cohort-old-40',name:'SK 40기',termNumber:40,status:'closed',studentCount:0},
    {cohortId:'cohort-other-40',name:'다른 이름',termNumber:40,status:'active',studentCount:0},
  ];
  mocks.preview.mockImplementation(async (code: string) => ({state: code === 'cohort-other-40' ? 'failed' : 'not_started'}));
  mocks.read.mockResolvedValue(emptyDocuments);
  const host = document.createElement('div'); document.body.appendChild(host);
  const root = createRoot(host);
  cleanup = () => { act(() => root.unmount()); host.remove(); };
  await act(async () => root.render(<MemoryRouter initialEntries={['/admin/cohorts/create']}>
    <Routes><Route path="/admin/cohorts/create" element={<AdminCohortFormScreen />} />
      <Route path="/admin/cohorts/:cohortId/edit" element={<AdminCohortFormScreen />} /></Routes>
  </MemoryRouter>));
  const name = host.querySelector('input')!;
  const term = host.querySelector('input[type="number"]')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(name, ' SK   40기 ');
    name.dispatchEvent(new Event('input', {bubbles:true}));
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(term, '40');
    term.dispatchEvent(new Event('input', {bubbles:true}));
  });
  expect(host.textContent).toContain('이미 등록된 기수가 있습니다');
  expect(host.textContent).toContain('SK 40기');
  expect(host.textContent).toContain('다른 이름');
  expect(host.textContent).toContain('삭제 처리 중 · 수정 불가');
  expect([...host.querySelectorAll('button')].filter(button => button.textContent === '기존 기수 수정')).toHaveLength(1);
  await act(async () => [...host.querySelectorAll('button')].find(button => button.textContent === '기존 기수 수정')!.click());
  expect(mocks.read).toHaveBeenCalledWith('cohort-old-40');
  expect(mocks.create).not.toHaveBeenCalled();
});

it('keeps a created cohort when attachment fails and retries without duplicate creation', async () => {
  mocks.create.mockResolvedValue(undefined);
  mocks.update.mockResolvedValue(undefined);
  let rejectUpload!: (error: Error) => void;
  mocks.upload.mockImplementationOnce(() => new Promise((_, reject) => { rejectUpload = reject; })).mockResolvedValue(undefined);
  mocks.read.mockResolvedValue(emptyDocuments);
  const host = document.createElement('div'); document.body.appendChild(host);
  const root = createRoot(host);
  cleanup = () => { act(() => root.unmount()); host.remove(); };
  await act(async () => root.render(<MemoryRouter><AdminCohortFormScreen /></MemoryRouter>));
  expect(host.querySelector('input[aria-label="기수별 정책 문서"]')?.getAttribute('accept')).toBe('.pdf,.docx');
  const name = host.querySelector('input')!;
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(name, '테스트 기수');
    name.dispatchEvent(new Event('input', { bubbles: true }));
    name.dispatchEvent(new Event('change', { bubbles: true }));
    const input = host.querySelector('input[aria-label="커리큘럼 PDF"]')!;
    Object.defineProperty(input, 'files', { value: [new File(['%PDF-1.7'], 'course.pdf', { type: 'application/pdf' })] });
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
  const click = async (label: string) => act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === label)!.click());
  await click('교육 자료 등록');
  await click('등록 내용 확인');
  expect(mocks.create).not.toHaveBeenCalled();
  expect(mocks.upload).not.toHaveBeenCalled();
  await click('이전');
  expect((host.querySelector('input[aria-label="커리큘럼 PDF"]') as HTMLInputElement).files?.[0].name).toBe('course.pdf');
  await click('등록 내용 확인');
  await click('기수 생성');
  expect(mocks.create).toHaveBeenCalledTimes(1);
  const progress = host.querySelector('.cohort-save-progress')!;
  expect(progress.textContent).toContain('커리큘럼 저장·검색 준비 중');
  expect(progress.textContent).toContain('course.pdf');
  expect(progress.closest('[hidden]')).toBeNull();
  expect(progress.querySelector('progress')?.hasAttribute('value')).toBe(false);
  expect(host.querySelector('.cohort-form__footer button:disabled')).not.toBeNull();
  await act(async () => rejectUpload(new Error('upload failed')));
  expect(host.querySelector('.cohort-save-progress')).toBeNull();
  expect(host.textContent).toContain('기수 정보는 저장됐습니다');
  expect(host.querySelector('[aria-current="step"]')?.textContent).toContain('교육 자료');
  await click('등록 내용 확인');
  await click('다시 저장');
  expect(mocks.create).toHaveBeenCalledTimes(1);
  expect(mocks.update).toHaveBeenCalledWith(mocks.create.mock.calls[0][0].cohortId, expect.anything());
  expect(mocks.upload).toHaveBeenCalledTimes(2);
});

it('shows stored per-cohort documents separately from a selected replacement and preserves a successful file after partial failure', async () => {
  mocks.cohorts = [{cohortId:'cohort_test',name:'테스트 기수',description:'',status:'planned',studentCount:0}];
  const stored = {cohortId:'cohort_test',documents:{
    curriculum:{kind:'curriculum',filename:'old-course.pdf',updatedAt:'2026-10-08T01:00:00Z',ragStatus:'ready'},
    policy:{kind:'policy',filename:'old-policy.docx',updatedAt:null,ragStatus:'registered'},
  }};
  mocks.read.mockResolvedValue(stored);
  mocks.update.mockResolvedValue(undefined);
  mocks.upload.mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error('policy failed'));
  const host = document.createElement('div'); document.body.appendChild(host);
  const root = createRoot(host);
  cleanup = () => { act(() => root.unmount()); host.remove(); mocks.cohorts = []; };
  await act(async () => root.render(<MemoryRouter initialEntries={['/admin/cohorts/cohort_test/edit']}>
    <Routes><Route path="/admin/cohorts/:cohortId/edit" element={<AdminCohortFormScreen />} /></Routes>
  </MemoryRouter>));
  expect(mocks.read).toHaveBeenCalledWith('cohort_test');
  expect((host.querySelector('.cohort-form__documents') as HTMLFieldSetElement).hidden).toBe(true);
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '교육 자료')!.click());
  expect((host.querySelector('.cohort-form__documents') as HTMLFieldSetElement).hidden).toBe(false);
  expect(host.textContent).toContain('현재 등록 · old-course.pdf');
  expect(host.textContent).toContain('등록됨 · 검색 반영 미확인');
  const input = host.querySelector('input[aria-label="커리큘럼 PDF"]') as HTMLInputElement;
  const policy = host.querySelector('input[aria-label="기수별 정책 문서"]') as HTMLInputElement;
  await act(async () => {
    Object.defineProperty(input,'files',{value:[new File(['%PDF-1.7'],'new-course.pdf',{type:'application/pdf'})]});
    input.dispatchEvent(new Event('change',{bubbles:true}));
    Object.defineProperty(policy,'files',{value:[new File(['%PDF-1.7'],'new-policy.pdf',{type:'application/pdf'})]});
    policy.dispatchEvent(new Event('change',{bubbles:true}));
  });
  expect(input.isSameNode(host.querySelector('input[aria-label="커리큘럼 PDF"]'))).toBe(true);
  expect(host.textContent).toContain('교체 예정 · new-course.pdf');
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '기본 정보')!.click());
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '교육 자료')!.click());
  expect(input.isSameNode(host.querySelector('input[aria-label="커리큘럼 PDF"]'))).toBe(true);
  expect(input.files?.[0].name).toBe('new-course.pdf');
  mocks.read.mockResolvedValue({...stored,documents:{...stored.documents,curriculum:{...stored.documents.curriculum,filename:'new-course.pdf'}}});
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '변경사항 저장')!.click());
  expect(mocks.upload).toHaveBeenCalledTimes(2);
  expect(host.textContent).toContain('현재 등록 · new-course.pdf');
  expect(host.textContent).toContain('현재 등록 · old-policy.docx');
  expect(host.textContent).toContain('교체 예정 · new-policy.pdf');
  expect(host.textContent).toContain('실패한 항목만 다시 저장');
});

it('shows the completed DB document after creation and on edit refresh', async () => {
  mocks.cohorts = [];
  mocks.create.mockResolvedValue(undefined);
  mocks.upload.mockResolvedValue(undefined);
  mocks.read.mockImplementation(async (id: string) => ({cohortId:id,documents:{
    curriculum:{kind:'curriculum',filename:'new-course.pdf',updatedAt:'2026-10-08T01:00:00Z',ragStatus:'ready'},
    policy:null,
  }}));
  const host = document.createElement('div'); document.body.appendChild(host);
  let root = createRoot(host);
  cleanup = () => { act(() => root.unmount()); host.remove(); mocks.cohorts = []; };
  await act(async () => root.render(<MemoryRouter initialEntries={['/admin/cohorts/new']}>
    <Routes><Route path="/admin/cohorts/new" element={<AdminCohortFormScreen />} />
      <Route path="/admin/cohorts/:cohortId/edit" element={<AdminCohortFormScreen />} /></Routes>
  </MemoryRouter>));
  const name = host.querySelector('input')!;
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '교육 자료 등록')!.click());
  expect(host.querySelector('[aria-current="step"]')?.textContent).toContain('기본 정보');
  expect(mocks.create).not.toHaveBeenCalled();
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value')!.set!.call(name,'새 기수');
    name.dispatchEvent(new Event('input',{bubbles:true}));
    const input = host.querySelector('input[aria-label="커리큘럼 PDF"]')!;
    Object.defineProperty(input,'files',{value:[new File(['%PDF-1.7'],'new-course.pdf',{type:'application/pdf'})]});
    input.dispatchEvent(new Event('change',{bubbles:true}));
  });
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '교육 자료 등록')!.click());
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '등록 내용 확인')!.click());
  await act(async () => [...host.querySelectorAll('button')].find(b => b.textContent === '기수 생성')!.click());
  expect(host.textContent).toContain('현재 등록 · new-course.pdf');
  expect(host.textContent).toContain('검색 반영 완료');
  expect(host.textContent).toContain('저장 완료 · 문서별 검색 반영 상태');
  const id = mocks.create.mock.calls[0][0].cohortId;
  expect(mocks.read).toHaveBeenCalledWith(id);
  act(() => root.unmount());
  root = createRoot(host);
  mocks.cohorts = [{cohortId:id,name:'새 기수',description:'',status:'planned',studentCount:0}];
  await act(async () => root.render(<MemoryRouter initialEntries={[`/admin/cohorts/${id}/edit`]}>
    <Routes><Route path="/admin/cohorts/:cohortId/edit" element={<AdminCohortFormScreen />} /></Routes>
  </MemoryRouter>));
  expect(host.textContent).toContain('현재 등록 · new-course.pdf');
  expect(host.textContent).toContain('검색 반영 완료');
});
