import { useEffect, useRef, useState } from 'react';
import { Badge, Button, Card, Select, TabPage } from '../../ui/components';
import './localResumeE2E.css';

const ROOT = '/api/local/resume-e2e';
// Display aliases for the fictional local fixture; stored values and API IDs stay unchanged.
const DISPLAY_TITLES: Record<string, string> = {
  '가상 E2E 데이터 기업': '데이터 서비스 기업 (예시)',
  'Data Analyst / AI Service': 'AI 서비스 데이터 분석 직무',
  '가상 학생 기본 이력서': '데이터 분석가 지원 이력서',
  'KKBOX churn analysis': 'KKBOX 고객 이탈 분석',
};
const displayTitle = (text: string) => DISPLAY_TITLES[text] ?? text;
type Fact = { id: string; normalized_fact: string; assertion_state: string };
type Gap = { key: string; category: string; target_experience_id: string | null; reason: string; question_proposal: string };
type Assignment = { question_id: string; primary_experience_ids: string[]; story_focus: string; core_evidence_ids: string[]; supporting_evidence_ids: string[]; result_evidence_ids: string[]; missing_information: Gap[] };
type Workspace = {
  id: string; base_resume_id: number; tailored_resume_id: number | null;
  questions: { id: string; raw_text: string; analysis: { asks_for?: { key: string }[] }; source_type: string }[];
  experiences: { id: string; title: string; evidence: Fact[] }[];
  bindings: { resume_id: number; experience_id: string; item_key: string }[];
  counts: Record<string, number>; ai_mode: string; semantic_status: string;
  data_mode?: 'mock' | 'real'; requirement_profile_linked?: boolean;
  resume_items?: { item_key: string; section: string; title: string; initialized: boolean }[];
  registration?: { resume_imported: boolean; experience_initialized: boolean; experience_count: number; evidence_extracted: number };
  planner: { plan: { assignments: Assignment[] }; duplicate_story_warnings: string[][]; next_question: Gap | null } | null;
};
type Job = { id: string; title: string; company: string; job_id?: string; snapshot_hash?: string; resume_id?: number };
type Catalog = { resumes: { id: number; title: string }[]; jobs: Job[]; real_resumes?: { id: number; title: string; registration?: Workspace['registration'] }[]; real_jobs?: Job[]; ai_mode: string };
type Gate = { question_id: string; status: 'READY' | 'NEEDS_INPUT' | 'BLOCKED'; missing_information?: { question_proposal?: string; reason?: string; key?: string }[] };
type WriterResult = { final_text: string; result: { status: string; readiness: Gate }; telemetry?: unknown };

export async function localE2ERequest(path: string, token: string, body?: unknown) {
  const response = await fetch(ROOT + path, { method: body === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok || data.ok === false) throw new Error(data.detail || '로컬 API 오류');
  return data;
}

export function PlannerPreview({ workspace }: { workspace: Workspace }) {
  const title = (id: string) => displayTitle(workspace.experiences.find(e => e.id === id)?.title || '연결된 경험을 확인할 수 없습니다.');
  const facts = workspace.experiences.flatMap(e => e.evidence);
  const fact = (id: string) => {
    const found = facts.find(f => f.id === id);
    if (!found) return '연결된 내용을 확인할 수 없습니다.';
    return ['resume_stated', 'user_asserted'].includes(found.assertion_state) ? found.normalized_fact : null;
  };
  return <>
    {workspace.questions.map((q, index) => {
      const a = workspace.planner?.plan.assignments.find(x => x.question_id === q.id);
      return <Card key={q.id} title={`문항 ${index + 1}`}>
        <p className="local-resume-e2e__question">{q.raw_text}</p>
        {!a && <p className="local-resume-e2e__muted">{q.analysis.asks_for?.length ? '문항 분석이 완료됐습니다. 작성 방향을 분석해 보세요.' : '문항을 분석하면 활용할 경험과 작성 방향을 확인할 수 있어요.'}</p>}
        {a && <><section><h3>활용할 경험</h3><div className="local-resume-e2e__tags">{a.primary_experience_ids.map(id => <Badge key={id}>{title(id)}</Badge>)}</div></section>
          <section className="local-resume-e2e__focus"><h3>이 문항에서 강조할 포인트</h3><p>{a.story_focus}</p></section>
          {([
            ['core_evidence_ids', '강조할 내용'],
            ['supporting_evidence_ids', '함께 활용할 내용'],
            ['result_evidence_ids', '확인된 결과'],
          ] as const).map(([key, label]) => {
            const visible = a[key].map(id => ({ id, text: fact(id) })).filter(f => f.text);
            return visible.length > 0 && <section key={key}><h3>{label}</h3><ul>{visible.map(f => <li key={f.id}>{f.text}</li>)}</ul></section>;
          })}
          {a.missing_information.length > 0 && <section className="local-resume-e2e__gaps"><h3>추가로 필요한 정보</h3>
            {a.missing_information.map((g, i) => <div key={i} className="local-resume-e2e__gap">
              {g.target_experience_id && <Badge>{title(g.target_experience_id)}</Badge>}
              <p>{g.question_proposal || g.reason}</p>
              {g.question_proposal && g.reason && <p className="local-resume-e2e__muted">{g.reason}</p>}
            </div>)}
          </section>}
        </>}
      </Card>;
    })}
    {!!workspace.planner?.duplicate_story_warnings.length && <Card title="경험 활용을 확인해 주세요">
      {workspace.planner.duplicate_story_warnings.map((ids, i) => <p key={i}>{ids.map(id => {
        const index = workspace.questions.findIndex(q => q.id === id);
        return index < 0 ? '연결된 문항' : `문항 ${index + 1}`;
      }).join(' · ')}에서 같은 경험을 활용하고 있습니다. 강조할 기여를 구분해 보세요.</p>)}
    </Card>}
  </>;
}

export function LocalResumeE2E() {
  const [token, setToken] = useState(() => sessionStorage.getItem('local-resume-e2e-token') || '');
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [role, setRole] = useState('');
  const [resume, setResume] = useState('');
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [status, setStatus] = useState('미리보기를 시작해 주세요.');
  const [busy, setBusy] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState('지원 준비 내용을 불러오고 있습니다…');
  const [error, setError] = useState('');
  const [debugError, setDebugError] = useState('');
  const [debugOpen, setDebugOpen] = useState(false);
  const [dataMode, setDataMode] = useState<'mock' | 'real'>('mock');
  const [aiMode, setAiMode] = useState<'mock' | 'live'>('mock');
  const [gates, setGates] = useState<Gate[]>([]);
  const [readinessAudit, setReadinessAudit] = useState<unknown>(null);
  const [answers, setAnswers] = useState<Record<string, WriterResult>>({});
  const inFlight = useRef(false);
  const requestIds = useRef<Record<string, string>>({});
  const jobs = dataMode === 'real' ? catalog?.real_jobs || [] : catalog?.jobs || [];
  const resumes = dataMode === 'real' ? catalog?.real_resumes || [] : catalog?.resumes || [];
  const executionBody = (key: string) => ({ ai_mode: aiMode, request_id: requestIds.current[key] ||= crypto.randomUUID() });
  const approveLive = () => aiMode === 'mock' || window.confirm('Live AI 실행: 선택한 이력서 경험·답변·공고 context가 외부 LLM API로 전송되고 비용이 발생합니다. 실행할까요?');
  const refreshReadiness = async (w: Workspace) => {
    if (!w.planner) { setGates([]); setReadinessAudit(null); return; }
    const audit = await localE2ERequest(`/applications/${w.id}/writer-readiness`, token);
    setGates(audit.questions); setReadinessAudit(audit);
  };
  const reportError = (e: unknown) => {
    setError('지원 준비 정보를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
    setDebugError(e instanceof Error ? e.message : '알 수 없는 처리 오류');
  };
  const run = async (fn: () => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError(''); setDebugError('');
    try { await fn(); } catch (e) { reportError(e); }
    finally { inFlight.current = false; setBusy(false); }
  };
  useEffect(() => {
    if (!token) return;
    let active = true;
    void (async () => {
      try {
        const c: Catalog = await localE2ERequest('/catalog', token);
        if (!active) return;
        setCatalog(c); setStatus('공고와 기본 이력서를 선택하세요.');
        const id = new URLSearchParams(location.search).get('application');
        if (id) {
          const w: Workspace = await localE2ERequest('/applications/' + id, token);
          if (active) {
            setWorkspace(w); setResume(String(w.base_resume_id)); setStatus('이전에 준비하던 내용을 불러왔습니다.');
            setDataMode(w.data_mode || 'mock');
            await refreshReadiness(w);
            const saved = sessionStorage.getItem(`local-resume-e2e-role:${w.id}`);
            if (saved && [...c.jobs, ...c.real_jobs || []].some(j => j.id === saved)) setRole(saved);
          }
        }
      } catch (e) { if (active) reportError(e); }
    })();
    return () => { active = false; };
  }, [token]);
  const step = (suffix: string, label: string) => run(async () => {
    if (!workspace) return;
    if (['analyze','plan'].includes(suffix) && !approveLive()) return;
    setLoadingMessage(suffix === 'analyze' ? '문항을 분석하고 있습니다…' : suffix === 'plan' ? '활용할 경험과 작성 방향을 정리하고 있습니다…' : '지원 준비 내용을 불러오고 있습니다…');
    const w = await localE2ERequest(`/applications/${workspace.id}/${suffix}`, token,
      ['analyze','plan'].includes(suffix) ? executionBody(`${workspace.id}:${suffix}:${aiMode}`) : {});
    setWorkspace(w); setStatus(label);
    setAnswers({}); await refreshReadiness(w);
  });
  const selectedJob = jobs.find(j => j.id === role);
  const selectedResume = resumes.find(r => r.id === (workspace?.base_resume_id ?? Number(resume)));
  return <TabPage className="local-resume-e2e" title="공고 맞춤 지원 준비" description="내 경험을 바탕으로 문항별 작성 방향을 살펴보세요." actions={<Badge>개발 미리보기</Badge>}>
    <Card title="지원할 공고와 이력서">
      <label>데이터 모드<Select aria-label="데이터 모드" disabled={busy} value={dataMode} onChange={e => {
        setDataMode(e.target.value as 'mock' | 'real'); setWorkspace(null); setRole(''); setResume(''); setGates([]); setAnswers({}); setReadinessAudit(null);
        history.replaceState(null, '', location.pathname);
      }}><option value="mock">예시 데이터</option><option value="real">실제 데이터 기반 로컬 테스트</option></Select></label>
      <p className="local-resume-e2e__muted">{dataMode === 'real' ? '로컬 복제 데이터 · 원본 수정 없음' : '예시 자료로 지원 준비 과정을 확인하는 미리보기입니다.'}</p>
      <label>AI 실행<Select aria-label="AI 실행" disabled={busy} value={aiMode} onChange={e => setAiMode(e.target.value as 'mock' | 'live')}><option value="mock">Mock — 기록된 응답 검증</option><option value="live">Live — 실제 AI 호출</option></Select></label>
      {aiMode === 'live' && <p role="note">Live 선택됨: 외부 API 전송·비용 발생. 실행 버튼마다 확인합니다.</p>}
      {!token && <Button disabled={busy} onClick={() => run(async () => {
        const auth = await localE2ERequest('/login', '', { email: 'resume-e2e@example.test', password: 'LocalE2E-only!' });
        sessionStorage.setItem('local-resume-e2e-token', auth.access); setToken(auth.access);
      })}>미리보기 시작하기</Button>}
      {catalog && <>
        {dataMode === 'real' && !resumes.length && <p>아직 가져온 이력서가 없습니다. 작성한 이력서를 명시적 로컬 import 명령으로 가져와 주세요.</p>}
        <label>공고 선택<Select aria-label="공고 선택" value={role} onChange={e => setRole(e.target.value)}><option value="">선택하세요</option>{jobs.filter(j => !j.resume_id || !resume || j.resume_id === Number(resume)).map(j => <option key={j.id + ':' + j.resume_id} value={j.id}>{displayTitle(j.company)} · {displayTitle(j.title)}</option>)}</Select></label>
        <label>기본 이력서 선택<Select aria-label="기본 이력서 선택" value={resume} onChange={e => { setResume(e.target.value); if (dataMode === 'real') setRole(''); }}><option value="">선택하세요</option>{resumes.map(r => <option key={r.id} value={r.id}>{displayTitle(r.title)}</option>)}</Select></label>
        <Button disabled={busy || !role || !resume} onClick={() => run(async () => {
          const w = await localE2ERequest('/applications/open-or-create', token,
            { role_id: role, base_resume_id: Number(resume), data_mode: dataMode, idempotency_key: `local-e2e:${role}:${resume}`, entry_source: 'job_first' });
          sessionStorage.setItem(`local-resume-e2e-role:${w.id}`, role);
          setWorkspace(w); history.replaceState(null, '', `${location.pathname}?application=${w.id}`); setStatus('지원 준비 내용을 불러왔습니다.');
        })}>{workspace ? '지원 준비 계속하기' : '이 공고에 맞게 준비하기'}</Button>
      </>}
      <p role="status">{busy ? loadingMessage : status}</p>{error && <p role="alert">{error}</p>}
    </Card>
    {workspace && <>
      <Card title="문항별 지원 준비">
        <div className="local-resume-e2e__selection">
          <div><h3>지원 공고</h3><p>{selectedJob ? `${displayTitle(selectedJob.company)} · ${displayTitle(selectedJob.title)}` : '위에서 지원 공고를 선택해 주세요.'}</p></div>
          <div><h3>선택한 이력서</h3><p>{selectedResume ? displayTitle(selectedResume.title) : '이력서 정보를 확인해 주세요.'}</p><Badge tone={workspace.tailored_resume_id ? 'success' : 'neutral'}>{workspace.tailored_resume_id ? '맞춤 이력서 준비 완료' : '맞춤 이력서 준비 전'}</Badge></div>
        </div>
        <div className="local-resume-e2e__actions">
          <Button variant="outline" disabled={busy} onClick={() => step('tailored-resume', '맞춤 이력서를 준비했습니다.')}>맞춤 이력서 준비</Button>
          <Button variant="outline" disabled={busy} onClick={() => step('questions', '지원 문항을 불러왔습니다.')}>문항 가져오기</Button>
          <Button variant="outline" disabled={busy || !workspace.questions.length} onClick={() => step('analyze', '문항 분석이 완료됐습니다.')}>문항 분석</Button>
          <Button disabled={busy || !workspace.questions.every(q => q.analysis.asks_for?.length) || !workspace.questions.length} onClick={() => step('plan', '작성 방향 분석이 완료됐습니다. 내용을 검토해 주세요.')}>작성 방향 분석</Button>
        </div>
        {!workspace.questions.length && <p className="local-resume-e2e__muted">공고의 문항을 가져와 지원 준비를 시작하세요.</p>}
      </Card>
      <PlannerPreview workspace={workspace} />
      {workspace.data_mode === 'real' && <Card title="이력서 경험 분석">
        <p>등록은 원문 저장에서 끝납니다. 첫 Review에서 기존 v2 엔진이 경험을 연결하고 사실 추출·문장 작성·검증을 수행합니다.</p>
        {(workspace.resume_items || []).map(e => <section key={e.item_key}><h3>{e.title}</h3><p>{e.initialized ? '이 경험의 Review가 시작되었습니다.' : '원문 등록 완료 · 아직 분석하지 않았습니다.'}</p>
          <Button disabled={busy || aiMode !== 'live'} onClick={() => run(async () => {
            if (!approveLive()) return;
            setLoadingMessage('기존 첨삭봇이 선택한 경험의 원문을 분석하고 있습니다…');
            const w: Workspace = await localE2ERequest(`/applications/${workspace.id}/extract-evidence`, token,
              { ...executionBody(`${workspace.id}:review:${e.item_key}:live`), item_key: e.item_key });
            setWorkspace(w); setAnswers({}); setGates([]); setStatus('경험 분석이 완료됐습니다. 문항과 작성 방향을 다시 분석해 주세요.');
          })}>이 경험 Review 시작</Button>
        </section>)}
        {aiMode === 'mock' && <p>원문만 등록한 실제 이력서는 Live를 명시적으로 선택해야 봇이 분석합니다. Mock으로 근거를 임의 생성하지 않습니다.</p>}
      </Card>}
      {workspace.planner && <Card title="자기소개서 생성">
        <p>{workspace.requirement_profile_linked ? '공고 요구사항 profile 연결됨' : '연결된 공고 요구사항 분석이 없습니다.'}</p>
        <p>현재 실행: {aiMode === 'live' ? 'Live (외부 API)' : 'Mock (기록 재생 — 품질 판정 아님)'}</p>
        {workspace.questions.map((q, index) => {
          const gate = gates.find(g => g.question_id === q.id); const answer = answers[q.id];
          return <section key={q.id}><h3>문항 {index + 1}</h3>
            {gate?.status === 'NEEDS_INPUT' && <p>추가 정보가 필요합니다. {gate.missing_information?.map(g => g.question_proposal || (g.key === 'result' ? '이 행동 이후 실제로 어떤 결과가 있었나요?' : '질문에 답하는 데 필요한 내용을 추가해 주세요.')).join(' ')}</p>}
            {(gate?.status === 'BLOCKED' || answer?.result.status === 'BLOCKED') && <p role="alert">현재 정보로는 안전하게 첨삭을 진행할 수 없습니다. 다시 분석해 주세요.</p>}
            <Button disabled={busy || gate?.status !== 'READY' || !!answer} onClick={() => run(async () => {
              if (!approveLive()) return;
              setLoadingMessage('선택한 근거로 자기소개서를 작성하고 검증하고 있습니다…');
              const result: WriterResult = await localE2ERequest(`/applications/${workspace.id}/write`, token,
                { ...executionBody(`${workspace.id}:write:${q.id}:${aiMode}`), question_id: q.id });
              setAnswers(old => ({ ...old, [q.id]: result }));
            })}>자기소개서 생성</Button>
            {answer?.final_text && <><h3>생성된 자기소개서</h3><p>{answer.final_text}</p></>}
          </section>;
        })}
      </Card>}
    </>}
    <details className="local-resume-e2e__debug" onToggle={e => setDebugOpen(e.currentTarget.open)}>
      <summary>개발자 정보 보기</summary>
      {debugOpen && <pre>{JSON.stringify({ api_root: ROOT, data_mode: dataMode, ai_mode: aiMode,
        registration: workspace?.registration || catalog?.real_resumes?.find(r => r.id === Number(resume))?.registration || null,
        selection: { role_context_id: role || null, resume_id: resume || null }, workspace, readiness: readinessAudit, writer_results: answers, error: debugError || null }, null, 2)}</pre>}
    </details>
  </TabPage>;
}
