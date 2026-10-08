import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { jobApplyPath, resumeEditPath, RoutePaths } from '../../app/routePaths';
import { http } from '../../data/http';
import { applyBootstrap, updateResume, useMyResumes } from '../../data/repository';
import { nextId } from '../../data/store';
import type { Resume, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/MoreMenu';
import { Badge, Button, Card, Select, TabPage, TextInput } from '../../ui/components';
import { formatDate } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { JobPostingDialog } from '../jobs/JobPostingDialog';
import { careerLabel, type Posting } from '../jobs/JobPostingScreen';
import { closedReason } from '../jobs/postingStatus';
import { ReviewApiError, reviewApi, type Json } from '../resume/review/reviewApi';
import { DeleteResumeDialog } from '../resume/DeleteResumeDialog';
import { applyCopyTitle, isApplyCopy, isTailored, reviewWorkCopy } from '../resume/resumeGroups';
import {
  addEvidencedSkills,
  alignToPosting,
  postingSkills,
  skillCoverage,
  type PostingRequirement,
  type SkillCoverage,
} from './alignDraft';
import { defaultQuestions } from './companyQuestions';
import { CoachAsk } from '../resume/ask/CoachAsk';
import { ApplySiteButton } from './ApplySiteButton';
import { FeaturedPostings } from './FeaturedPostings';
import { QuestionAnswers } from './QuestionAnswers';
import { QuestionsStep, type QuestionChoice } from './QuestionsStep';
import './jobApply.css';

/**
 * 공고 맞춤 지원 — 공고를 먼저 정하고, 그 공고 요건에 맞춘 이력서를 만들어 첨삭한다.
 *
 * 이력서 관리는 「이력서 → 공고 추천 → 맞춤 첨삭」 순서다. 여기는 거꾸로 간다.
 * 1. 공고 링크를 붙여 넣어 수집해 둔 공고를 찾는다(`/posting-link`)
 * 2. 첨삭 서버가 정리한 요건(필수 · 우대 · 주요 업무)과, 바탕 이력서에 그 기술이 있는지 보여 준다
 * 3. 회사 자기소개서 문항을 정한다 — 붙여넣기 · 자주 나오는 문항 · 기본 6문항(QuestionsStep.tsx)
 * 4. 바탕 이력서의 공고용 사본을 뜨고(첨삭과 같은 사본 — `/resume-review/tailored`) 요건 순으로 늘어놓는다.
 *    회사 문항은 사본의 content.companyQuestions 에 담는다
 * 5. 문항별 답변 첨삭 — 공고 요건을 이력서에서 찾아 근거로 답을 쓴다(QuestionAnswers.tsx). 이력서 관리의 AI 첨삭과는 다른 흐름
 *
 * 초안은 순서만 바꾼다. 문장은 첨삭이 공고 원문을 근거로 고친다(alignDraft.ts).
 */

type Requirements =
  | { state: 'loading' }
  | { state: 'ready'; rows: PostingRequirement[] }
  /** retry: 다시 해서 나아질 실패(연결 · 서버 오류)인가. 이미지뿐인 공고 · 마감 공고처럼 서버가 정한 답이면 안내만 */
  | { state: 'failed'; message: string; retry: boolean };

interface Draft {
  resumeId: string;
  tailoredId: string;
  /** 편집기 · 목록에서 쓰는 id — 「원본/tailored/사본」 */
  editId: string;
  session: Json;
  /** 이미 만든 사본을 다시 연 것 — 순서를 다시 바꾸지 않았다 */
  reused: boolean;
  addedSkills: string[];
  matchedSkills: number;
  projectsReordered: boolean;
  /** 사본에 담은 회사 문항 수. 기본 6문항이면 0 */
  questionCount: number;
}

const SITE_LABEL: Record<string, string> = { SARAMIN_POC: '사람인', JOBKOREA_POC: '잡코리아' };

const GROUP_LABEL: Record<string, string> = { must: '필수', preferred: '우대', task: '주요 업무' };

const PLACE_LABEL: Record<SkillCoverage['place'], string> = {
  techStack: '기술스택에 있음',
  text: '본문에만 있음',
  missing: '이력서에 없음',
};

function errorDetail(err: unknown, fallback: string): string {
  if (err instanceof Error && err.name !== 'AxiosError' && err.message !== '') return err.message;
  const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
  return typeof detail === 'string' && detail !== '' ? detail : fallback;
}

function requirementRows(data: Json): PostingRequirement[] {
  const list = Array.isArray(data.requirements) ? (data.requirements as Json[]) : [];
  return list.map((r) => ({
    id: String(r.id ?? ''),
    group: String(r.group ?? ''),
    label: String(r.label ?? ''),
    postingQuote: String(r.posting_quote ?? ''),
  }));
}

/** 서버 사본의 본문 — 옛 이력서는 칸이 빠져 있을 수 있어 정렬하는 두 칸만 배열로 맞춘다 */
function draftContent(raw: unknown): ResumeContent {
  const content = (raw !== null && typeof raw === 'object' ? raw : {}) as ResumeContent;
  return {
    ...content,
    techStack: Array.isArray(content.techStack) ? content.techStack : [],
    projects: Array.isArray(content.projects) ? content.projects : [],
  };
}

export function JobApplyScreen() {
  const user = useCurrentUser();
  const resumes = useMyResumes(user.uid).data ?? [];
  const navigate = useNavigate();

  // 바탕이 될 수 있는 이력서 — 공고 맞춤본 · 첨삭 작업본은 뺀다(기본 이력서 고르기와 같은 규칙)
  const sources = resumes.filter((r) => !isTailored(r) && !r.sourceTailoredResumeId);
  const defaultSource = sources.find((r) => r.isBaseResume) ?? sources[0];

  const [link, setLink] = useState('');
  const [finding, setFinding] = useState(false);
  const [findError, setFindError] = useState<string | null>(null);
  const [posting, setPosting] = useState<Posting | null>(null);
  const [requirements, setRequirements] = useState<Requirements>({ state: 'loading' });
  const [pickedSource, setPickedSource] = useState<string>('');
  const [fillEvidenced, setFillEvidenced] = useState(true);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  /** 회사 자소서 문항 — null 이면 아직 안 정했다 */
  const [questions, setQuestions] = useState<QuestionChoice | null>(null);
  const [viewing, setViewing] = useState(false);
  /** 1단계 — 링크를 붙여 넣거나, 코치에게 물어 찾는다 */
  const [findBy, setFindBy] = useState<'link' | 'coach'>('link');
  // 만든 공고용 이력서는 주소(?resume=…)에 남긴다. 편집기에 갔다 와도, 목록에서 다시 열어도 문항 답변으로 돌아온다.
  // 코치 대화 · 추천에서 고른 공고는 ?job=… 로 들어온다(1단계를 건너뛴다)
  const [params, setParams] = useSearchParams();
  const openId = params.get('resume') ?? '';
  const openJob = params.get('job') ?? '';
  const restoredId = useRef('');
  const openedJob = useRef('');

  const source = sources.find((r) => r.id === pickedSource) ?? defaultSource;
  const skills = useMemo(
    () =>
      posting === null
        ? { required: [], preferred: [] }
        : postingSkills(
            { required: posting.required_skills ?? [], preferred: posting.preferred_skills ?? [] },
            requirements.state === 'ready' ? requirements.rows : [],
          ),
    [posting, requirements],
  );
  const coverage = source === undefined ? [] : skillCoverage(source.content, skills);
  const evidenced = coverage.filter((c) => c.place === 'text');

  const loadRequirements = (jobId: string) => {
    setRequirements({ state: 'loading' });
    reviewApi
      .requirements(jobId)
      .then((data) => setRequirements({ state: 'ready', rows: requirementRows(data) }))
      .catch((err: unknown) =>
        setRequirements({
          state: 'failed',
          message: errorDetail(err, '공고 요건을 정리하지 못했어요.'),
          retry: !(err instanceof ReviewApiError && [404, 409, 422].includes(err.statusCode)),
        }),
      );
  };

  const find = (e: FormEvent) => {
    e.preventDefault();
    void lookup(link.trim());
  };

  const leaveResume = () => {
    restoredId.current = '';
    openedJob.current = '';
    if (openId !== '' || openJob !== '') setParams({}, { replace: true });
  };

  /** 공고 번호로 공고를 읽는다. 저장소 상태가 틀릴 수 있어(REMOVED · 늘어난 마감일) 링크로 불러올 때처럼 페이지를 열어 확인한다 */
  const readPosting = async (jobId: string): Promise<Posting> => {
    const { data } = await http.get<Posting>(`/postings/${encodeURIComponent(jobId)}`);
    if (data.status === 'OPEN' || !data.source_url.startsWith('http')) return data;
    return (await http.get<Posting>('/posting-link', { params: { url: data.source_url } })).data;
  };

  /** 코치 대화 · 추천에서 고른 공고로 연다 — 링크를 붙여 넣은 것과 같은 자리(2단계)에서 시작한다 */
  const openPosting = async (jobId: string) => {
    setFinding(true);
    setFindError(null);
    try {
      const data = await readPosting(jobId);
      setPosting(data);
      setLink(data.source_url);
      setDraft(null);
      setQuestions(null);
      setCreateError(null);
      if (data.status === 'OPEN') loadRequirements(data.job_id);
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      setFindError(status === 404 ? '공고를 찾을 수 없어요. 수집 목록에서 빠진 공고일 수 있어요.' : errorDetail(err, '공고를 불러오지 못했어요.'));
    } finally {
      setFinding(false);
    }
  };

  useEffect(() => {
    if (openJob === '' || openId !== '' || openedJob.current === openJob) return;
    openedJob.current = openJob;
    void openPosting(openJob);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openJob, openId]);

  /** 주소의 공고용 이력서로 이어 간다 — 연결된 공고를 다시 읽고, 문항이 담겨 있으면 문항 답변(5단계)을 연다 */
  const restore = async (resume: Resume) => {
    const copy = reviewWorkCopy(resume);
    if (copy === undefined || !resume.linkedJobId) {
      setFindError('공고 맞춤 지원에서 이어 갈 수 없는 이력서예요. 이력서 관리에서 열어 주세요.');
      return;
    }
    setFinding(true);
    setFindError(null);
    try {
      const data = await readPosting(resume.linkedJobId);
      setPosting(data);
      setLink(data.source_url);
      setPickedSource(copy.base);
      setCreateError(null);
      if (data.status === 'OPEN') loadRequirements(data.job_id);
      const saved = resume.content.companyQuestions ?? [];
      setQuestions(saved.length > 0 ? saved : null);
      setDraft(
        saved.length > 0
          ? {
              resumeId: copy.base, tailoredId: copy.tailored, editId: resume.id, session: {}, reused: true,
              addedSkills: [], matchedSkills: 0, projectsReordered: false, questionCount: saved.length,
            }
          : null,
      );
    } catch (err) {
      setFindError(errorDetail(err, '공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'));
    } finally {
      setFinding(false);
    }
  };

  useEffect(() => {
    if (openId === '' || restoredId.current === openId) return;
    // 이력서 목록(bootstrap)이 아직 없으면 올 때까지 기다린다
    const resume = resumes.find((r) => r.id === openId);
    if (resume === undefined) return;
    restoredId.current = openId;
    void restore(resume);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openId, resumes]);

  const lookup = async (url: string) => {
    if (finding || url === '') return;
    setFinding(true);
    setFindError(null);
    try {
      const { data } = await http.get<Posting>('/posting-link', { params: { url } });
      leaveResume();
      setLink(url);
      setPosting(data);
      setDraft(null);
      setQuestions(null);
      setCreateError(null);
      // 닫힌 공고는 첨삭 서버도 요건 정리를 막는다(409). 부르지 않고 까닭만 보여 준다
      if (data.status === 'OPEN') loadRequirements(data.job_id);
    } catch (err) {
      setFindError(errorDetail(err, '공고를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.'));
    } finally {
      setFinding(false);
    }
  };

  const reset = () => {
    leaveResume();
    setPosting(null);
    setDraft(null);
    setQuestions(null);
    setLink('');
    setFindError(null);
    setCreateError(null);
  };

  const create = async () => {
    if (creating || posting === null || source === undefined || questions === null) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await reviewApi.createTailored(source.id, posting.job_id, 'apply');
      const tailoredId = String(created.tailored_resume_id ?? '');
      if (tailoredId === '') throw new Error('자소서를 만들지 못했어요. 다시 시도해 주세요.');
      const editId = `${source.id}/tailored/${tailoredId}`;
      const session = (created.review_session ?? {}) as Json;
      // 같은 공고로 이미 만든 사본이면 서버가 그것을 돌려준다. 사용자가 고친 순서를 덮지 않도록 다시 늘어놓지 않는다
      const reused = resumes.some((r) => r.id === editId) || Object.keys(session).length > 0;
      // 기본 6문항도 문항 목록으로 담는다 — 이 탭의 첨삭(문항 답변)이 같은 흐름으로 돈다
      const companyQuestions =
        questions === 'default'
          ? defaultQuestions(draftContent(created.content).selfIntroduction, () => nextId('cq'))
          : questions;
      let next: Draft = {
        resumeId: source.id, tailoredId, editId, session, reused,
        addedSkills: [], matchedSkills: 0, projectsReordered: false, questionCount: 0,
      };
      if (reused) {
        // 이미 만든 사본에는 문항만 채운다. 첨삭 대화가 있으면 본문이 바뀌어 대화가 끊기므로 건드리지 않는다
        const before = draftContent(created.content);
        const has = before.companyQuestions?.length ?? 0;
        if (has === 0 && companyQuestions.length > 0 && Object.keys(session).length === 0) {
          await updateResume(editId, { content: { ...before, companyQuestions } });
          next = { ...next, questionCount: companyQuestions.length };
        } else {
          next = { ...next, questionCount: has };
        }
      } else {
        const before = draftContent(created.content);
        const filled = fillEvidenced
          ? addEvidencedSkills(before, skillCoverage(before, skills), () => nextId('t'))
          : { content: before, added: [] };
        const aligned = alignToPosting(filled.content, skills);
        const changed =
          filled.added.length > 0 ||
          aligned.projectsReordered ||
          aligned.content.techStack.some((t, i) => t !== before.techStack[i]) ||
          companyQuestions.length > 0;
        const content = companyQuestions.length > 0 ? { ...aligned.content, companyQuestions } : aligned.content;
        // 첨삭 창이 사본을 다시 읽기 전에 저장을 끝내 둔다
        if (changed) await updateResume(editId, { content });
        next = {
          ...next,
          addedSkills: filled.added,
          matchedSkills: aligned.matchedSkills,
          projectsReordered: aligned.projectsReordered,
          questionCount: companyQuestions.length,
        };
      }
      await applyBootstrap();
      setDraft(next);
      restoredId.current = next.editId;
      setParams({ resume: next.editId }, { replace: true });
    } catch (err) {
      setCreateError(errorDetail(err, '자소서를 만들지 못했어요. 다시 시도해 주세요.'));
    } finally {
      setCreating(false);
    }
  };

  const closed = posting !== null && posting.status !== 'OPEN';
  // 같은 공고가 사람인 · 잡코리아에 함께 올라온 경우(수집기가 group_key 로 묶는다). 한쪽만 조기 마감되기도 한다
  const openCopy = posting?.links?.find((l) => l.job_id !== posting.job_id && l.status === 'OPEN' && l.source_url.startsWith('http'));
  const imageOnly = posting !== null && (posting.body_is_image || posting.description.trim() === '');
  const blocked = closed || imageOnly || requirements.state === 'failed';
  // 이 공고로 이 탭에서 이미 만든 자소서
  const madeForPosting = posting === null ? [] : resumes.filter((r) => r.linkedJobId === posting.job_id && isApplyCopy(r));

  return (
    <TabPage title="공고 맞춤 지원" description="지원할 공고를 먼저 정하고, 그 공고 요건에 맞춘 이력서를 만들어 첨삭합니다.">
      <Stepper
        done={[posting !== null, requirements.state === 'ready' && posting !== null, questions !== null, draft !== null, false]}
      />
      <Card className="apply-step">
        <StepHead no={1} title="공고 설정" done={posting !== null} />
        {posting === null && (
          <div className="apply-tabs" role="tablist" aria-label="공고 찾는 방법">
            <button type="button" role="tab" aria-selected={findBy === 'link'} className={`apply-tab${findBy === 'link' ? ' is-on' : ''}`} onClick={() => setFindBy('link')}>
              <Icon name="link" size={18} />
              링크 붙여넣기
            </button>
            <button type="button" role="tab" aria-selected={findBy === 'coach'} className={`apply-tab${findBy === 'coach' ? ' is-on' : ''}`} onClick={() => setFindBy('coach')}>
              <Icon name="forum" size={18} />
              코치에게 묻기
            </button>
          </div>
        )}
        {/* 대화는 공고를 고른 뒤에도 숨겨 둘 뿐 남긴다 — 「다른 공고」로 돌아오면 이어서 고른다 */}
        {findBy === 'coach' &&
          (source === undefined ? (
            posting === null && <p className="hint">바탕 이력서가 있어야 코치에게 물을 수 있어요. 이력서 관리에서 먼저 작성해 주세요.</p>
          ) : (
            <div className="apply-coach" hidden={posting !== null}>
              <CoachAsk
                resume={source}
                hidden={posting !== null}
                pickLabel="이 공고 고르기"
                onPickJob={(jobId) => setParams({ job: jobId })}
              />
            </div>
          ))}
        {posting === null ? (
          findBy === 'link' && (
          <form className="apply-link" onSubmit={find}>
            <TextInput
              value={link}
              onChange={(e) => setLink(e.target.value)}
              placeholder="https://www.saramin.co.kr/zf_user/jobs/view?rec_idx=…"
              aria-label="공고 링크"
              autoFocus
            />
            <Button type="submit" disabled={finding || link.trim() === ''}>
              {finding ? '찾는 중…' : '공고 불러오기'}
            </Button>
          </form>
          )
        ) : (
          <PostingSummary posting={posting} onOpen={() => setViewing(true)} onChange={reset} />
        )}
        {posting === null && findBy === 'link' && (
          <p className="hint">사람인 · 잡코리아 공고 상세 페이지 주소를 붙여 넣으세요. 우리가 수집해 둔 공고만 불러올 수 있어요.</p>
        )}
        {/* 코치 대화 · 주요 기업 카드에서 고른 공고(?job=…)를 불러오는 동안 */}
        {posting === null && openJob !== '' && finding && <p className="hint">고른 공고를 불러오고 있어요…</p>}
        {findError !== null && <p className="apply-error">{findError}</p>}
      </Card>

      {/* 대기업 · 인기 기업 · 외국계 공고. 고르면 코치 대화에서 고른 공고와 같이 2단계로 간다 */}
      {posting === null && <FeaturedPostings busy={finding} onPick={(jobId) => setParams({ job: jobId })} />}

      {/* 이 탭에서 만든 자소서만. 이력서 관리의 공고 맞춤 이력서는 거기서 본다 */}
      {posting === null && <MadeList resumes={resumes.filter(isApplyCopy)} />}

      {posting !== null && (
        <Card className="apply-step">
          <StepHead no={2} title="공고가 요구하는 것" done={requirements.state === 'ready'} />
          {closed && (
            <div className="apply-warn">
              <span>{closedReason(posting.status, posting.deadline)} 맞춤 첨삭은 열려 있는 공고만 할 수 있어요.</span>
              {openCopy !== undefined && (
                <Button size="sm" variant="outline" disabled={finding} onClick={() => void lookup(openCopy.source_url)}>
                  <Icon name="swap_horiz" size={16} />
                  {SITE_LABEL[openCopy.source] ?? '다른 사이트'}에 열려 있는 같은 공고로 불러오기
                </Button>
              )}
            </div>
          )}
          {!closed && imageOnly && (
            <p className="apply-warn">상세 내용이 이미지로만 올라온 공고라 요건을 읽을 수 없어요. 텍스트 공고를 골라 주세요.</p>
          )}
          {!closed && <RequirementList requirements={requirements} onRetry={() => loadRequirements(posting.job_id)} />}

          {source === undefined ? (
            <p className="hint">
              바탕이 될 이력서가 없어요. <Link to={RoutePaths.resume}>이력서 관리</Link>에서 기본 이력서를 먼저 작성해 주세요.
            </p>
          ) : (
            <div className="apply-coverage">
              <div className="apply-coverage__head">
                <span className="apply-label">바탕 이력서와 비교</span>
                <Select value={source.id} onChange={(e) => setPickedSource(e.target.value)} aria-label="바탕 이력서" disabled={draft !== null}>
                  {sources.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title}
                      {r.isBaseResume ? ' (기본)' : ''}
                    </option>
                  ))}
                </Select>
              </div>
              {coverage.length === 0 ? (
                <p className="hint">
                  {requirements.state === 'loading' ? '요건을 정리하면 기술을 비교해요.' : '이 공고에서는 비교할 기술 이름을 찾지 못했어요.'}
                </p>
              ) : (
                <ul className="apply-skills">
                  {coverage.map((c) => (
                    <li key={`${c.group}-${c.skill}`} className={`apply-skill apply-skill--${c.place}`} title={PLACE_LABEL[c.place]}>
                      <Icon name={c.place === 'techStack' ? 'check_circle' : c.place === 'text' ? 'adjust' : 'radio_button_unchecked'} size={15} />
                      {c.skill}
                      {c.group === 'required' && <span className="apply-skill__must">필수</span>}
                    </li>
                  ))}
                </ul>
              )}
              {coverage.some((c) => c.place === 'missing') && (
                <p className="hint">
                  이력서에 없는 기술은 지어 넣지 않아요. 써 본 경험이 있으면 첨삭의 「경험 보완」 단계에서 답해 주세요.
                </p>
              )}
            </div>
          )}
        </Card>
      )}

      {posting !== null && (
        <Card className="apply-step">
          <StepHead no={3} title="회사 자기소개서 문항" done={questions !== null} />
          <QuestionsStep value={questions} locked={draft !== null} onChange={setQuestions} posting={posting} />
        </Card>
      )}

      {posting !== null && source !== undefined && questions !== null && (
        <Card className="apply-step">
          <StepHead no={4} title="이 공고용 자소서" done={draft !== null} />
          {draft === null ? (
            <>
              <ul className="apply-plan">
                <li>「{source.title}」을 복사해 이 공고용 자소서를 만들어요. 바탕 이력서는 그대로예요.</li>
                <li>기술스택은 공고 필수 → 우대 순으로, 프로젝트는 공고 기술과 많이 겹치는 순으로 늘어놓아요.</li>
                <li>
                  {questions === 'default'
                    ? '자기소개서는 기본 6문항을 그대로 써요.'
                    : `자기소개서 문항 ${questions.length}개를 이 이력서에 담아요.`}
                </li>
                <li>문장은 바꾸지 않아요. 문장은 다음 단계 AI 첨삭이 공고 원문을 근거로 고쳐요.</li>
              </ul>
              {evidenced.length > 0 && (
                <label className="apply-check">
                  <input type="checkbox" checked={fillEvidenced} onChange={(e) => setFillEvidenced(e.target.checked)} />
                  본문에만 있는 공고 기술 {evidenced.length}개({evidenced.map((c) => c.skill).join(', ')})를 기술스택에도 넣기
                </label>
              )}
              {madeForPosting.length > 0 && (
                <p className="hint">이 공고로 만든 자소서가 이미 있어요. 같은 바탕 이력서면 그 자소서를 이어서 열어요.</p>
              )}
              <div className="apply-actions">
                <Button onClick={() => void create()} disabled={creating || blocked || requirements.state === 'loading'}>
                  <Icon name="note_add" size={18} />
                  {creating ? '만드는 중…' : '자소서 만들기'}
                </Button>
              </div>
              {createError !== null && <p className="apply-error">{createError}</p>}
            </>
          ) : (
            <DraftDone draft={draft} onEdit={() => navigate(resumeEditPath(draft.editId))} />
          )}
        </Card>
      )}

      {viewing && posting !== null && <JobPostingDialog jobId={posting.job_id} onClose={() => setViewing(false)} />}
    </TabPage>
  );
}

const STEPS = ['공고 설정', '요건 확인', '자소서 문항', '자소서 만들기', 'AI 첨삭'];

/** 맨 위 단계 줄 — 끝난 단계는 체크, 처음으로 안 끝난 단계가 지금 단계 */
function Stepper({ done }: { done: boolean[] }) {
  const current = done.findIndex((d) => !d);
  return (
    <ol className="apply-stepper">
      {STEPS.map((label, i) => (
        <li key={label} className={done[i] ? 'is-done' : i === current ? 'is-current' : undefined} aria-current={i === current ? 'step' : undefined}>
          <span className="apply-step__no">{done[i] ? <Icon name="check" size={16} /> : i + 1}</span>
          {label}
        </li>
      ))}
    </ol>
  );
}

function StepHead({ no, title, done }: { no: number; title: string; done: boolean }) {
  return (
    <header className="apply-step__head">
      <span className={`apply-step__no${done ? ' is-done' : ''}`}>{done ? <Icon name="check" size={16} /> : no}</span>
      <h2>{title}</h2>
    </header>
  );
}

function PostingSummary({ posting, onOpen, onChange }: { posting: Posting; onOpen(): void; onChange(): void }) {
  /** 회사 채용 사이트를 연 뒤의 안내 — 요약 줄 아래에 */
  const [siteNote, setSiteNote] = useState('');
  const facts = [
    posting.region,
    posting.employment_type,
    careerLabel(posting.career_type, posting.min_career_years),
    posting.deadline ? `~ ${posting.deadline.slice(0, 10)}` : '',
  ].filter((v) => v !== '' && v !== null);
  return (
    <>
      <div className="apply-posting">
        <div className="apply-posting__text">
          <span className="apply-posting__company">{posting.company}</span>
          <strong className="apply-posting__title">{posting.title}</strong>
          <span className="hint">{facts.join(' · ')}</span>
        </div>
        <div className="apply-posting__actions">
          {/* 공채는 요건 · 문항이 회사 채용 사이트에 있다. 일반 공고는 못 찾으면 원문을 연다 */}
          {posting.source_url.startsWith('http') && (
            <ApplySiteButton jobId={posting.job_id} fallbackUrl={posting.source_url} onNote={setSiteNote} />
          )}
          <Button variant="outline" size="sm" onClick={onOpen}>
            <Icon name="description" size={16} />
            원문 보기
          </Button>
          <Button variant="text" size="sm" onClick={onChange}>
            다른 공고
          </Button>
        </div>
      </div>
      {siteNote !== '' && <p className="hint apply-site-note">{siteNote}</p>}
    </>
  );
}

function RequirementList({ requirements, onRetry }: { requirements: Requirements; onRetry(): void }) {
  if (requirements.state === 'loading') {
    return <p className="hint apply-loading">공고 원문에서 필수 · 우대 요건을 정리하고 있어요… (처음 여는 공고는 몇 초 걸려요)</p>;
  }
  if (requirements.state === 'failed' && !requirements.retry) {
    return (
      <p className="apply-note">
        <Icon name="info" size={18} />
        <span>{requirements.message}</span>
      </p>
    );
  }
  if (requirements.state === 'failed') {
    return (
      <div className="apply-error-row">
        <p className="apply-error">{requirements.message}</p>
        <Button variant="text" size="sm" onClick={onRetry}>
          다시 시도
        </Button>
      </div>
    );
  }
  if (requirements.rows.length === 0) {
    return <p className="hint">공고 원문에서 요건을 뽑지 못했어요. 원문 보기로 직접 확인해 주세요.</p>;
  }
  const groups = ['must', 'preferred', 'task'].map((g) => ({ g, rows: requirements.rows.filter((r) => r.group === g) }));
  return (
    <div className="apply-reqs">
      {groups
        .filter((x) => x.rows.length > 0)
        .map(({ g, rows }) => (
          <section key={g} className="apply-reqs__group">
            <span className={`apply-label apply-label--${g}`}>{GROUP_LABEL[g] ?? g}</span>
            <ul>
              {rows.map((r) => (
                <li key={r.id}>
                  <strong>{r.label}</strong>
                  <q>{r.postingQuote}</q>
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}

function DraftDone({ draft, onEdit }: { draft: Draft; onEdit(): void }) {
  return (
    <div className="apply-done">
      {draft.reused ? (
        <p>이 공고로 만든 자소서가 이미 있어서 그 자소서를 열었어요. 고쳐 둔 내용이 그대로 남아 있어요.</p>
      ) : (
        <ul className="apply-plan apply-plan--done">
          {draft.addedSkills.length > 0 && <li>본문에 있던 {draft.addedSkills.join(', ')}을(를) 기술스택에 넣었어요.</li>}
          <li>
            {draft.matchedSkills + draft.addedSkills.length > 0
              ? `공고 기술 ${draft.matchedSkills + draft.addedSkills.length}개를 기술스택 앞쪽으로 옮겼어요.`
              : '기술스택에 공고 기술이 없어 순서를 그대로 뒀어요.'}
          </li>
          <li>{draft.projectsReordered ? '프로젝트를 공고 기술과 많이 겹치는 순으로 정렬했어요.' : '프로젝트 순서는 그대로예요.'}</li>
          {draft.questionCount > 0 && <li>자기소개서 문항 {draft.questionCount}개를 담았어요.</li>}
        </ul>
      )}
      <div className="apply-actions">
        <Button variant="outline" onClick={onEdit}>
          <Icon name="edit" size={18} />
          편집기에서 열기
        </Button>
      </div>

      <div className="apply-qa">
        <div className="apply-qa__head">
          <h3>문항별 답변 첨삭</h3>
          <span className="hint">
            공고 요건을 이력서에서 찾아 근거로 답을 써요. 문장마다 근거가 붙고, 근거가 모자라면 질문으로 물어요.
          </span>
        </div>
        <QuestionAnswers resumeId={draft.resumeId} tailoredId={draft.tailoredId} editId={draft.editId} />
      </div>
    </div>
  );
}

/** 공고로 만든 이력서 — 링크를 붙여 넣기 전 화면. 누르면 이 탭에서 이어서 작업한다 */
function MadeList({ resumes }: { resumes: Resume[] }) {
  const [deleting, setDeleting] = useState<Resume | null>(null);
  if (resumes.length === 0) return null;
  const sorted = [...resumes].sort((a, b) => (b.updatedAt?.getTime() ?? 0) - (a.updatedAt?.getTime() ?? 0));
  return (
    <Card className="apply-made" title="내 자소서">
      <ul>
        {sorted.map((r) => {
          // 공고용 사본은 이 탭에서 이어 간다(문항 답변). 이력서 관리의 첨삭을 마쳐 옮긴 이력서는 편집기로 연다
          const here = reviewWorkCopy(r) !== undefined;
          return (
            <li key={r.id} className="apply-made__row">
              <Link className="apply-made__item" to={here ? jobApplyPath(r.id) : resumeEditPath(r.id)}>
                <Icon name="work" size={16} />
                <span className="apply-made__title">{applyCopyTitle(r.title)}</span>
                {!here && <Badge tone="neutral">첨삭 완료본 · 편집기로 열기</Badge>}
                {here && (r.content.companyQuestions?.length ?? 0) > 0 && (
                  <Badge tone="info">문항 {r.content.companyQuestions?.length}개</Badge>
                )}
                <span className="hint">{formatDate(r.updatedAt)}</span>
              </Link>
              {r.status !== 'approved' && (
                <MoreMenu
                  label={`${applyCopyTitle(r.title)} 더보기`}
                  items={[{ key: 'delete', label: '삭제', danger: true, onSelect: () => setDeleting(r) }]}
                />
              )}
            </li>
          );
        })}
      </ul>
      {deleting !== null && (
        <DeleteResumeDialog resume={deleting} title={applyCopyTitle(deleting.title)} onClose={() => setDeleting(null)} />
      )}
    </Card>
  );
}
