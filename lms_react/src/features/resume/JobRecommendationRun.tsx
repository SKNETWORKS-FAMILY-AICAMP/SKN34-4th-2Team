import { useEffect, useState, type MouseEvent } from 'react';

import { http } from '../../data/http';
import { Icon } from '../../ui/Icon';
import type { Resume } from '../../domain/types';
import { JobPostingDialog } from '../jobs/JobPostingDialog';
import { careerLabel, jobPostingPath } from '../jobs/JobPostingScreen';
import { JobRecommendationLoading } from './JobRecommendationLoading';
import { useReviewDock } from './review/ReviewDock';
import { reviewApi } from './review/reviewApi';

/**
 * 공고 추천 — 단계가 하나씩 켜지다 마지막에 로봇이 손을 놓는다.
 *
 * 추천은 서버(`/api/jobs/recommend` → job_matching_bot)가 한다. 이력서 평문은 화면이 만들지 않는다.
 * 서버가 DB 에서 읽어 만든다 — 남의 이력서로 받거나 화면이 보낸 글이 DB 와 달라지는 것을 막는다.
 *
 * 추천은 15초쯤 걸린다. 그동안 단계 카드를 순서대로 켜 두되, **끝났다고 먼저 말하지 않는다.**
 * 마지막 단계는 답이 올 때까지 켜 둔 채로 기다린다.
 *
 * 한 번 받아 둔 추천은 이력서별로 남겨 둔다. 다른 패널을 보다 돌아와도 목록이
 * 그대로 있고, 다시 받고 싶을 때만 「다시 추천」을 누른다.
 */
interface Reason {
  claim: string;
  resumeQuote: string;
  jobQuote: string;
}

interface JobPick {
  jobId: string;
  title: string;
  company: string;
  sourceUrl: string;
  fit: string;
  reasons: Reason[];
  concerns: string[];
  conditions: { region?: string; employmentType?: string | null; career?: string; education?: string; deadline?: string | null };
  filterStatus: string;
  unknownConditions: string[];
  /** 상세 공고가 이미지뿐이면 원문 근거로 첨삭할 수 없다 */
  bodyIsImage: boolean;
}

interface JobResult {
  jobs: JobPick[];
  searchQuery: string;
  notice: string;
  warnings: string[];
}

const jobCache = new Map<string, JobResult>();
/**
 * 지금 받고 있는 추천 — 이력서별로 하나만 둔다.
 *
 * 추천 한 번은 30초쯤 걸리고 LLM 을 부른다. React 는 개발 모드에서 효과를 두 번 실행하므로
 * 그냥 두면 같은 추천을 두 번 부른다. 이미 가고 있는 요청이 있으면 그 약속을 같이 기다린다.
 */
const pending = new Map<string, Promise<JobResult>>();

function requestJobs(resumeId: string): Promise<JobResult> {
  const going = pending.get(resumeId);
  if (going !== undefined) return going;
  const promise = http
    .post<Record<string, unknown>>('/jobs/recommend', { resumeId, topK: 10 })
    .then(({ data }) => {
      const next = toResult(data);
      jobCache.set(resumeId, next);
      return next;
    })
    .finally(() => pending.delete(resumeId));
  pending.set(resumeId, promise);
  return promise;
}

/**
 * 맞춤 이력서에 연결된 공고 하나 — 원본 _showLinkedJob. 새로 점수를 매긴 추천이 아니라서
 * 근거 · 적합도는 없고, 서버 공고 카드로 보여 「재첨삭」을 단다. 수집해 둔 공고 표에서 바로 읽는다.
 */
function requestLinkedJob(jobId: string): Promise<JobResult> {
  return http.get<Record<string, unknown>>(`/postings/${encodeURIComponent(jobId)}`).then(({ data }) => ({
    jobs: [
      {
        jobId: String(data.job_id ?? jobId),
        title: String(data.title ?? ''),
        company: String(data.company ?? ''),
        sourceUrl: String(data.source_url ?? ''),
        fit: '',
        reasons: [],
        concerns: [],
        conditions: {
          region: String(data.region ?? ''),
          employmentType: (data.employment_type ?? null) as string | null,
          career: careerLabel(String(data.career_type ?? ''), data.min_career_years as number | null),
          education: String(data.education ?? ''),
          deadline: (data.deadline ?? null) as string | null,
        },
        filterStatus: 'PASS',
        unknownConditions: [],
        bodyIsImage: Boolean(data.body_is_image),
      },
    ],
    searchQuery: '',
    notice: '이 맞춤 이력서와 연결된 공고입니다.',
    warnings: [],
  }));
}

const STEP_IDS = ['resume', 'search', 'filter', 'judge'] as const;

/** 서버 응답(snake_case)을 화면 모양으로 */
function toResult(data: Record<string, unknown>): JobResult {
  const list = Array.isArray(data.recommendations) ? (data.recommendations as Record<string, unknown>[]) : [];
  return {
    jobs: list.map((r) => ({
      jobId: String(r.job_id ?? ''),
      title: String(r.title ?? ''),
      company: String(r.company ?? ''),
      sourceUrl: String(r.source_url ?? ''),
      fit: String(r.fit ?? ''),
      reasons: (Array.isArray(r.reasons) ? (r.reasons as Record<string, unknown>[]) : []).map((x) => ({
        claim: String(x.claim ?? ''),
        resumeQuote: String(x.resume_quote ?? ''),
        jobQuote: String(x.job_quote ?? ''),
      })),
      concerns: Array.isArray(r.concerns) ? (r.concerns as string[]) : [],
      conditions: {
        region: String((r.conditions as Record<string, unknown>)?.region ?? ''),
        employmentType: ((r.conditions as Record<string, unknown>)?.employment_type ?? null) as string | null,
        career: String((r.conditions as Record<string, unknown>)?.career ?? ''),
        education: String((r.conditions as Record<string, unknown>)?.education ?? ''),
        deadline: ((r.conditions as Record<string, unknown>)?.deadline ?? null) as string | null,
      },
      filterStatus: String(r.filter_status ?? 'PASS'),
      unknownConditions: Array.isArray(r.unknown_conditions) ? (r.unknown_conditions as string[]) : [],
      bodyIsImage: Boolean(r.body_is_image),
    })),
    searchQuery: String(data.search_query ?? ''),
    notice: String(data.notice ?? ''),
    warnings: Array.isArray(data.warnings) ? (data.warnings as string[]) : [],
  };
}

/**
 * 공고 카드 하나 — ai_job_coach_panel.dart 의 _RecommendationCard.
 *
 * 원본을 그대로 따른다:
 * - 왼쪽에 번호 동그라미, 제목을 누르면 공고가 열린다
 * - **적합도(높음/보통/낮음)는 내지 않는다.** 사람 정답으로 검증된 적이 없어 순서에만 쓴다.
 *   그 자리는 근거 문장이 대신한다(원본 주석 그대로)
 * - 한 줄 요약은 근무지 · 고용형태 · 경력. 지원할지 정할 때 먼저 보는 것들이다
 * - 마감은 표 안이 아니라 밖에 둔다. 펼치지 않아도 보여야 한다
 * - 근거는 접어 둔다. 「추천 근거 보기」를 눌러야 이력서 ↔ 공고 인용이 나온다
 */
/** 마감은 날짜까지만 — 원본 _deadlineDate. 시각·시간대는 지원 여부를 정하는 데 쓰이지 않는다 */
function deadlineDate(value: string): string {
  return /^\d{4}-\d{2}-\d{2}/.exec(value)?.[0] ?? value;
}

function JobCard({
  index,
  job,
  onReview,
  reviewLabel,
  showReasons = true,
  onOpenPosting,
}: {
  index: number;
  job: JobPick;
  onReview?(job: JobPick): void;
  /** 공고 원문을 화면 위 창으로 연다 */
  onOpenPosting?(job: JobPick): void;
  /** 맞춤 이력서에 연결된 공고면 「재첨삭」 */
  reviewLabel?: string;
  /** 연결된 공고는 새로 추천한 것이 아니라 근거가 없다. 공고만 보이고 「추천 근거 보기」를 달지 않는다 */
  showReasons?: boolean;
}) {
  const [open, setOpen] = useState(false);
  // 원본 _reviewButton — 접었을 때는 근거 보기 옆, 펼치면 근거 위 오른쪽에 둔다
  const reviewButton = onReview !== undefined && (
    <button
      type="button"
      className="btn btn--filled btn--sm job-card__review"
      disabled={job.bodyIsImage}
      title={job.bodyIsImage ? '상세 공고가 이미지뿐이라 원문 근거 첨삭을 할 수 없습니다.' : '선택 공고와 이력서를 비교해 첨삭합니다.'}
      onClick={() => onReview(job)}
    >
      <Icon name="auto_fix_high" size={14} />
      {job.bodyIsImage ? '원문 확인 불가' : (reviewLabel ?? '공고 맞춤 첨삭')}
    </button>
  );
  const summary = [job.conditions.region, job.conditions.employmentType, job.conditions.career]
    .filter((v) => v !== null && v !== undefined && v !== '')
    .join(' · ');
  // 채용 사이트로 바로 보내지 않고 수집해 둔 원문을 화면 위 창으로 연다. 첨삭하던 화면을 잃지 않는다.
  // Ctrl · ⌘ · 가운데 버튼으로 누르면 브라우저가 하던 대로 새 탭에 연다
  const link = job.jobId === '' ? '' : jobPostingPath(job.jobId);
  const openInPlace = (e: MouseEvent<HTMLAnchorElement>) => {
    if (onOpenPosting === undefined || e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    onOpenPosting(job);
  };

  return (
    <div className="job-card">
      <div className="job-card__top">
        <span className="job-card__no">{index}</span>
        <div className="job-card__title">
          {link === '' ? (
            <strong>{job.title}</strong>
          ) : (
            <a href={link} target="_blank" rel="noreferrer" onClick={openInPlace}>
              <strong>{job.title}</strong>
            </a>
          )}
          <span className="job-card__company">{job.company}</span>
        </div>
        {link !== '' && (
          <a
            className="job-card__open"
            href={link}
            target="_blank"
            rel="noreferrer"
            aria-label="공고 원문 보기"
            title="공고 원문 보기 (Ctrl+클릭: 새 탭)"
            onClick={openInPlace}
          >
            <Icon name="open_in_new" size={14} />
          </a>
        )}
      </div>

      {summary !== '' && <span className="job-card__summary">{summary}</span>}
      {job.conditions.deadline != null && job.conditions.deadline !== '' && (
        <span className="job-card__deadline">~ {deadlineDate(job.conditions.deadline)}</span>
      )}
      {job.unknownConditions.length > 0 && (
        <span className="job-card__check">확인 필요: {job.unknownConditions.join(', ')}</span>
      )}

      {open && reviewButton !== false && <div className="job-card__review-row">{reviewButton}</div>}

      {open && (
        <div className="job-card__why">
          <span className="job-card__label">공고 조건</span>
          <dl className="job-card__conds">
            <div>
              <dt>근무지역</dt>
              <dd>{job.conditions.region || '미기재'}</dd>
            </div>
            <div>
              <dt>고용형태</dt>
              <dd>{job.conditions.employmentType || '미기재'}</dd>
            </div>
            <div>
              <dt>경력</dt>
              <dd>{job.conditions.career || '미기재'}</dd>
            </div>
            <div>
              <dt>학력</dt>
              <dd>{job.conditions.education || '미기재'}</dd>
            </div>
          </dl>

          {job.reasons.length > 0 && (
            <>
              <span className="job-card__label job-card__label--ok">추천 근거 — 이력서 문장 ↔ 공고 문장</span>
              {job.reasons.map((reason) => (
                <div key={reason.claim} className="job-card__reason">
                  <strong>{reason.claim}</strong>
                  {reason.resumeQuote !== '' && (
                    <span className="job-card__quote job-card__quote--resume">이력서 “{reason.resumeQuote}”</span>
                  )}
                  {reason.jobQuote !== '' && (
                    <span className="job-card__quote job-card__quote--job">공고 “{reason.jobQuote}”</span>
                  )}
                </div>
              ))}
            </>
          )}

          {job.concerns.length > 0 && (
            <>
              <span className="job-card__label job-card__label--warn">
                공고 자격요건 중 이력서에서 확인되지 않는 것
              </span>
              {job.concerns.map((concern) => (
                <span key={concern} className="job-card__concern">
                  {concern}
                </span>
              ))}
            </>
          )}
        </div>
      )}

      <div className="job-card__foot">
        {showReasons ? (
          <button type="button" className="job-card__toggle" onClick={() => setOpen((v) => !v)}>
            {open ? '근거 접기' : '추천 근거 보기'}
            <Icon name={open ? 'expand_less' : 'expand_more'} size={14} />
          </button>
        ) : (
          <span />
        )}
        {!open && reviewButton}
      </div>
    </div>
  );
}

export function JobRecommendationRun({ resume }: { resume: Resume }) {
  const cached = jobCache.get(resume.id);
  const [result, setResult] = useState<JobResult | null>(cached ?? null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [results, setResults] = useState<Record<string, string>>({});
  /** 화면 위 창으로 보고 있는 공고 원문 */
  const [viewing, setViewing] = useState<string | null>(null);
  const { openReview } = useReviewDock();
  // 공고 맞춤 이력서(편집기로 옮긴 사본)는 연결된 공고를 보여 주고 「재첨삭」을 단다 — 원본 _hasLinkedJob
  const linkedJobId = resume.linkedJobId ?? '';
  // 첨삭 작업본(「원본/tailored/사본」)이면 새로 뜨지 않고 그 사본의 대화를 이어서 연다
  const workCopy = /^(?<base>[^/]+)\/tailored\/(?<tailored>[^/]+)$/.exec(resume.id)?.groups;

  const reviewJob = async (job: JobPick) => {
    const options = { generalReview: false, jobId: job.jobId, jobCompany: job.company, jobTitle: job.title };
    if (workCopy === undefined) {
      openReview(`job-review-${resume.id}-${job.jobId}`, { ...options, resumeId: resume.id });
      return;
    }
    // 원본 _restoreSession — 저장된 대화가 있으면 이어 간다. 못 읽어도 창은 열고, 첨삭이 사본을 다시 읽는다
    let session: Record<string, unknown> = {};
    try {
      const saved = await reviewApi.tailored(workCopy.base, workCopy.tailored);
      if (saved.review_session !== null && typeof saved.review_session === 'object') {
        session = saved.review_session as Record<string, unknown>;
      }
    } catch {
      // 대화 없이 연다
    }
    openReview(`job-review-${workCopy.base}-${job.jobId}`, {
      ...options,
      resumeId: workCopy.base,
      tailoredResumeId: workCopy.tailored,
      initialReviewSession: session,
    });
  };

  useEffect(() => {
    if (result !== null || error !== null) return;
    let alive = true;

    // 연결된 공고 하나를 읽어 온다. 새로 추천하는 게 아니라 로봇 단계 로딩은 띄우지 않는다
    if (linkedJobId !== '') {
      void requestLinkedJob(linkedJobId)
        .then((next) => alive && setResult(next))
        .catch((err: unknown) => {
          if (!alive) return;
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
          setError(detail ?? '연결된 맞춤 공고를 불러올 수 없습니다.');
        });
      return () => {
        alive = false;
      };
    }

    // 단계 카드는 기다리는 동안 차례로 켠다. 마지막 단계는 답이 올 때까지 켜 둔다.
    const lines = [
      `기술 ${resume.content.techStack.length}개 · 프로젝트 ${resume.content.projects.length}개를 읽었어요`,
      '조건에 맞는 공고를 찾고 있어요',
      '희망 조건과 지원 자격을 비교하고 있어요',
      '이력서와 공고의 연결점을 확인하고 있어요',
    ];
    const timers = STEP_IDS.slice(0, -1).map((id, i) =>
      window.setTimeout(() => {
        if (!alive) return;
        setResults((r) => ({ ...r, [id]: lines[i] }));
        setStep(i + 1);
      }, 1800 * (i + 1)),
    );

    void requestJobs(resume.id)
      .then((next) => {
        if (!alive) return;
        setResults((r) => ({ ...r, judge: `맞는 공고 ${next.jobs.length}건을 골랐어요` }));
        setStep(STEP_IDS.length);
        setResult(next);
      })
      .catch((err: unknown) => {
        if (!alive) return;
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setError(detail ?? '공고를 추천하지 못했어요. 잠시 후 다시 시도해 주세요.');
      });

    return () => {
      alive = false;
      timers.forEach((t) => window.clearTimeout(t));
    };
  }, [error, result, resume, linkedJobId]);

  const again = () => {
    jobCache.delete(resume.id);
    setResults({});
    setStep(0);
    setError(null);
    setResult(null);
  };

  if (error !== null) {
    return (
      <div className="coach-run">
        <div className="coach-jobs__head">
          <strong>공고를 추천하지 못했어요</strong>
          <span className="spacer" />
          <button type="button" className="btn btn--text btn--sm" onClick={again}>
            다시 시도
          </button>
        </div>
        <p className="hint">{error}</p>
      </div>
    );
  }

  if (linkedJobId !== '' && result === null) {
    return (
      <div className="coach-run">
        <p className="hint">연결된 맞춤 공고를 불러오고 있어요…</p>
      </div>
    );
  }

  const closePosting = () => setViewing(null);

  // 추천이 끝나면 로딩은 사라지고 목록만 남는다.
  if (result !== null) {
    return (
      <div className="coach-run">
        <div className="coach-jobs__head">
          <strong>{linkedJobId !== '' ? '연결된 맞춤 공고' : `맞춤 공고 ${result.jobs.length}건`}</strong>
          <span className="spacer" />
          {linkedJobId === '' && (
            <button type="button" className="btn btn--text btn--sm" onClick={again}>
              다시 추천
            </button>
          )}
        </div>
        {result.jobs.length === 0 ? (
          <p className="hint">
            조건에 맞는 공고를 찾지 못했습니다. 희망 지역·고용형태를 넓히거나 이력서에 기술과 프로젝트를 더 적어 보세요.
          </p>
        ) : (
          <div className="coach-jobs">
            {result.jobs.map((job, index) => (
              <JobCard
                key={job.jobId}
                index={index + 1}
                job={job}
                onReview={(job) => void reviewJob(job)}
                reviewLabel={linkedJobId !== '' ? '재첨삭' : undefined}
                showReasons={linkedJobId === ''}
                onOpenPosting={(job) => setViewing(job.jobId)}
              />
            ))}
          </div>
        )}
        {result.notice !== '' && <p className="hint coach-jobs__notice">{result.notice}</p>}
        {viewing !== null && <JobPostingDialog jobId={viewing} onClose={closePosting} />}
      </div>
    );
  }

  return (
    <div className="coach-run">
      <JobRecommendationLoading
        current={STEP_IDS[Math.min(step, STEP_IDS.length - 1)]}
        results={results}
        completed={false}
      />
    </div>
  );
}
