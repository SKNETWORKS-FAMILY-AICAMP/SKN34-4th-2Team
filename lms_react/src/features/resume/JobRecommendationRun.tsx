import { useEffect, useState } from 'react';

import { http } from '../../data/http';
import type { Resume } from '../../domain/types';
import { JobRecommendationLoading } from './JobRecommendationLoading';

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
    })),
    searchQuery: String(data.search_query ?? ''),
    notice: String(data.notice ?? ''),
    warnings: Array.isArray(data.warnings) ? (data.warnings as string[]) : [],
  };
}

export function JobRecommendationRun({ resume }: { resume: Resume }) {
  const cached = jobCache.get(resume.id);
  const [result, setResult] = useState<JobResult | null>(cached ?? null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [results, setResults] = useState<Record<string, string>>({});

  useEffect(() => {
    if (result !== null || error !== null) return;
    let alive = true;

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
  }, [error, result, resume]);

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

  // 추천이 끝나면 로딩은 사라지고 목록만 남는다.
  if (result !== null) {
    return (
      <div className="coach-run">
        <div className="coach-jobs__head">
          <strong>맞춤 공고 {result.jobs.length}건</strong>
          <span className="spacer" />
          <button type="button" className="btn btn--text btn--sm" onClick={again}>
            다시 추천
          </button>
        </div>
        {result.jobs.length === 0 ? (
          <p className="hint">조건에 맞는 공고를 찾지 못했어요. 희망 조건을 넓혀 보세요.</p>
        ) : (
          <div className="coach-jobs">
            {result.jobs.map((job) => (
              <div key={job.jobId} className="coach-job">
                <div className="coach-job__head">
                  <strong>{job.title}</strong>
                  <span className={`coach-job__fit coach-job__fit--${job.fit === '높음' ? 'high' : job.fit === '보통' ? 'mid' : 'low'}`}>
                    {job.fit}
                  </span>
                </div>
                <span className="hint">
                  {[job.company, job.conditions.region, job.conditions.employmentType]
                    .filter((v) => v !== null && v !== undefined && v !== '')
                    .join(' · ')}
                </span>
                {job.reasons.slice(0, 2).map((reason) => (
                  <span key={reason.claim} className="coach-job__why">
                    {reason.claim}
                  </span>
                ))}
                {job.filterStatus === 'CHECK_REQUIRED' && (
                  <span className="coach-job__check">
                    확인 필요: {job.unknownConditions.join(' · ') || '지원 자격을 공고에서 확인하세요'}
                  </span>
                )}
                {job.sourceUrl !== '' && (
                  <a className="coach-job__link" href={job.sourceUrl} target="_blank" rel="noreferrer">
                    공고 보기
                  </a>
                )}
              </div>
            ))}
          </div>
        )}
        {result.notice !== '' && <p className="hint coach-jobs__notice">{result.notice}</p>}
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
