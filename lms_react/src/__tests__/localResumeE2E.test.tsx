import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, expect, it, vi } from 'vitest';
import { LocalResumeE2E, PlannerPreview } from '../features/jobApply/LocalResumeE2E';

afterEach(() => { vi.unstubAllGlobals(); sessionStorage.clear(); history.replaceState(null, '', '/'); });

it('keeps real resume selection empty and defaults to Mock without live calls', async () => {
  sessionStorage.setItem('local-resume-e2e-token','local-only');
  const fetchMock=vi.fn(async (_url:string) => ({ok:true,json:async()=>({resumes:[],jobs:[],real_resumes:[],real_jobs:[],ai_mode:'mock'})}));
  vi.stubGlobal('fetch',fetchMock);
  const host=document.createElement('div'); const root=createRoot(host);
  try {
    await act(async()=>root.render(<LocalResumeE2E/>));
    const mode=host.querySelector('select[aria-label="데이터 모드"]') as HTMLSelectElement;
    await act(async()=>{mode.value='real';mode.dispatchEvent(new Event('change',{bubbles:true}));});
    expect(host.textContent).toContain('로컬 복제 데이터 · 원본 수정 없음');
    expect(host.textContent).toContain('아직 가져온 이력서가 없습니다');
    expect((host.querySelector('select[aria-label="AI 실행"]') as HTMLSelectElement).value).toBe('mock');
    expect(fetchMock.mock.calls.every(c=>!String(c[0]).endsWith('/write'))).toBe(true);
  } finally { await act(async()=>root.unmount()); }
});

it('renders Writer readiness naturally and generates only READY with request identity', async () => {
  sessionStorage.setItem('local-resume-e2e-token','local-only'); history.replaceState(null,'','/?application=app1');
  const workspace={id:'app1',base_resume_id:1,tailored_resume_id:2,questions:[
    {id:'q1',raw_text:'기술 경험',analysis:{asks_for:[{key:'technical_contribution'}]},source_type:'recruit_role'},
    {id:'q2',raw_text:'성과',analysis:{asks_for:[{key:'result'}]},source_type:'recruit_role'},
    {id:'q3',raw_text:'기여',analysis:{},source_type:'recruit_role'}], experiences:[],bindings:[],counts:{},ai_mode:'mock',semantic_status:'mock',
    requirement_profile_linked:true,planner:{plan:{assignments:[]},duplicate_story_warnings:[],next_question:null}};
  const gates={questions:[{question_id:'q1',status:'READY'}, {question_id:'q2',status:'NEEDS_INPUT',missing_information:[{key:'result'}]},
    {question_id:'q3',status:'BLOCKED',issues:['wrong-owner ev-secret']}],materials:[]};
  const fetchMock=vi.fn(async (url:string,_options?:RequestInit)=>({ok:true,json:async()=>url.endsWith('/catalog')?{jobs:[],resumes:[],ai_mode:'mock'}:
    url.endsWith('/writer-readiness')?gates:url.endsWith('/write')?{final_text:'확인된 API 기여 문장입니다.',result:{status:'READY',readiness:gates.questions[0]},telemetry:{llm_calls:0}}:workspace}));
  vi.stubGlobal('fetch',fetchMock);
  const host=document.createElement('div');const root=createRoot(host);
  try {
    await act(async()=>root.render(<LocalResumeE2E/>));
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,0));});
    const buttons=[...host.querySelectorAll('button')].filter(b=>b.textContent==='자기소개서 생성');
    expect(buttons).toHaveLength(3);expect(buttons[0].disabled).toBe(false);expect(buttons[1].disabled).toBe(true);expect(buttons[2].disabled).toBe(true);
    expect(host.textContent).toContain('실제로 어떤 결과가 있었나요');expect(host.textContent).not.toContain('wrong-owner');
    await act(async()=>{buttons[0].click();buttons[0].click();});
    expect(host.textContent).toContain('확인된 API 기여 문장입니다.');
    const calls=fetchMock.mock.calls.filter(c=>c[0].endsWith('/write'));expect(calls).toHaveLength(1);
    expect(JSON.parse(String(calls[0][1]?.body))).toMatchObject({ai_mode:'mock',question_id:'q1',request_id:expect.any(String)});
    expect(host.textContent).not.toContain('ev-secret');
  } finally {await act(async()=>root.unmount());}
});

it('selects job/resume, opens Application and renders persisted Planner facts/gaps', async () => {
  const applicationId = '2dbe8039-1674-4330-97ae-d343b6cbe402';
  const workspace = { id: applicationId, base_resume_id: 1, tailored_resume_id: 2,
    questions: [{ id: 'q-1', raw_text: '직무 역량', analysis: { asks_for: [{ key: 'technical_contribution' }] }, source_type: 'recruit_role' }],
    experiences: [{ id: 'exp-1', title: 'LMS 프로젝트', evidence: [{ id: 'ev-1', normalized_fact: 'Django API 구현', assertion_state: 'user_asserted' }] }],
    bindings: [], counts: { Experience: 1, Evidence: 1 }, ai_mode: 'mock', semantic_status: 'NO-GO',
    planner: { plan: { assignments: [{ question_id: 'q-1', primary_experience_ids: ['exp-1'], story_focus: '직접 구현한 API',
      core_evidence_ids: ['ev-1'], supporting_evidence_ids: [], result_evidence_ids: [], missing_information: [{ key: 'preparation_effort', category: 'experience_evidence', target_experience_id: 'exp-1', reason: '기존 의미 문제', question_proposal: '어떤 준비를 했나요?' }] }] },
      duplicate_story_warnings: [], next_question: null } };
  const fetchMock = vi.fn(async (url: string) => ({ ok: true, json: async () => url.endsWith('/catalog')
    ? { ai_mode: 'mock', jobs: [{ id: 'role-1', title: 'Data', company: 'Fictional' }], resumes: [{ id: 1, title: '기본 이력서' }] }
    : url.endsWith('/login') ? { ok: true, access: 'fictional-jwt' } : workspace }));
  vi.stubGlobal('fetch', fetchMock);
  const host = document.createElement('div'); document.body.append(host); const root = createRoot(host);
  const flush = async () => { await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); }); };
  const click = async (text: string) => {
    const button = [...host.querySelectorAll('button')].find(b => b.textContent === text)!;
    await act(async () => { button.click(); }); await flush();
  };
  try {
    await act(async () => root.render(<LocalResumeE2E />));
    await click('미리보기 시작하기');
    for (const [label, value] of [['공고 선택', 'role-1'], ['기본 이력서 선택', '1']]) {
      const select = host.querySelector(`select[aria-label="${label}"]`) as HTMLSelectElement;
      await act(async () => { select.value = value; select.dispatchEvent(new Event('change', { bubbles: true })); });
    }
    await click('이 공고에 맞게 준비하기');
    const call = fetchMock.mock.calls.find(c => c[0].endsWith('/open-or-create'));
    expect(call).toBeDefined();
    expect(location.search).toContain(`application=${applicationId}`);
    expect(host.textContent).toContain('Django API 구현');
    expect(host.textContent).toContain('강조할 내용');
    expect(host.textContent).toContain('기존 의미 문제');
    for (const hidden of [applicationId, 'exp-1', 'ev-1', 'core_evidence_ids', 'NO-GO', 'user_asserted', 'technical_contribution', 'preparation_effort']) expect(host.textContent).not.toContain(hidden);
    expect(host.textContent).not.toContain('최종 자기소개서 생성');
    await click('맞춤 이력서 준비');
    await click('문항 가져오기');
    await click('문항 분석');
    await click('작성 방향 분석');
    expect(host.textContent).toContain('작성 방향 분석이 완료됐습니다.');
    const detail = host.querySelector('details')!;
    await act(async () => { detail.open = true; detail.dispatchEvent(new Event('toggle')); });
    expect(host.textContent).toContain(applicationId);
    expect(host.textContent).toContain('core_evidence_ids');
    expect(host.textContent).toContain('NO-GO');
    expect(host.textContent).not.toContain('fictional-jwt');
    await act(async () => { detail.open = false; detail.dispatchEvent(new Event('toggle')); });
    expect(host.textContent).not.toContain('core_evidence_ids');
  } finally { await act(async () => root.unmount()); host.remove(); }
});

it('never falls back to IDs, hides inactive facts, and preserves legitimate user text', async () => {
  const id = '3683fb32-4c35-4b0c-9355-cfd8ac7b3215';
  const workspace = { id, base_resume_id: 1, tailored_resume_id: null, bindings: [], counts: {}, ai_mode: 'mock', semantic_status: 'NO-GO',
    questions: [{ id: 'q', raw_text: '기여 경험', analysis: {}, source_type: 'recruit_role' }],
    experiences: [{ id: 'exp', title: 'API 프로젝트', evidence: [
      { id: 'active', normalized_fact: `요청 추적 식별자 ${id}를 기록했습니다.`, assertion_state: 'user_asserted' },
      { id: 'old', normalized_fact: '잘못된 과거 역할', assertion_state: 'superseded' },
    ] }],
    planner: { plan: { assignments: [{ question_id: 'q', primary_experience_ids: ['missing-exp'], story_focus: 'API 연동', core_evidence_ids: ['missing-fact', 'active', 'old'], supporting_evidence_ids: [], result_evidence_ids: [], missing_information: [] }] }, duplicate_story_warnings: [], next_question: null },
  };
  const host = document.createElement('div'); const root = createRoot(host);
  try {
    await act(async () => root.render(<PlannerPreview workspace={workspace} />));
    expect(host.textContent).toContain('연결된 경험을 확인할 수 없습니다.');
    expect(host.textContent).toContain('연결된 내용을 확인할 수 없습니다.');
    expect(host.textContent).not.toContain('missing-exp');
    expect(host.textContent).not.toContain('missing-fact');
    expect(host.textContent).not.toContain('잘못된 과거 역할');
    expect(host.textContent).toContain(`요청 추적 식별자 ${id}`);
    expect(host.textContent).not.toContain('확인된 결과');
  } finally { await act(async () => root.unmount()); }
});

it('keeps raw API errors in collapsed developer information only', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({ detail: 'internal error 2dbe8039-1674-4330-97ae-d343b6cbe402' }) })));
  const host = document.createElement('div'); const root = createRoot(host);
  try {
    await act(async () => root.render(<LocalResumeE2E />));
    await act(async () => { host.querySelector('button')!.click(); });
    expect(host.textContent).toContain('잠시 후 다시 시도해 주세요.');
    expect(host.textContent).not.toContain('internal error');
    const detail = host.querySelector('details')!;
    await act(async () => { detail.open = true; detail.dispatchEvent(new Event('toggle')); });
    expect(host.textContent).toContain('internal error');
    expect(host.textContent).not.toContain('LocalE2E-only!');
  } finally { await act(async () => root.unmount()); }
});
