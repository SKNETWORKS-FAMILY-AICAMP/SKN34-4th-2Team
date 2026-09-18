import { useEffect, useState } from 'react';

import type { Resume } from '../../domain/types';
import { JobRecommendationLoading } from './JobRecommendationLoading';

/**
 * 공고 추천 — 단계가 하나씩 켜지다 마지막에 로봇이 손을 놓는다.
 *
 * 한 번 받아 둔 추천은 이력서별로 남겨 둔다. 다른 패널을 보다 돌아와도 목록이
 * 그대로 있고, 다시 받고 싶을 때만 「다시 추천」을 누른다.
 */
interface JobPick {
  title: string;
  company: string;
  why: string;
}

const jobCache = new Map<string, JobPick[]>();

const STEP_IDS = ['resume', 'search', 'filter', 'judge'] as const;

function pickJobs(resume: Resume): JobPick[] {
  const skills = resume.content.techStack.map((t) => t.name);
  const hit = (name: string) => skills.filter((s) => name.includes(s)).length;
  return [
    {
      title: '데이터 분석가',
      company: '커머스 스타트업 · 서울',
      why: `내 기술 ${skills.length}개 중 ${Math.max(1, hit('Python SQL Pandas Tableau'))}개 일치`,
    },
    {
      title: '주니어 데이터 엔지니어',
      company: '핀테크 · 판교',
      why: 'SQL·Airflow 경험이 맞아요',
    },
    {
      title: '데이터 파이프라인 엔지니어',
      company: '모빌리티 · 성남',
      why: '프로젝트의 배치 스케줄링 경험을 봤어요',
    },
  ];
}

export function JobRecommendationRun({ resume }: { resume: Resume }) {
  const cached = jobCache.get(resume.id);
  const [jobs, setJobs] = useState<JobPick[] | null>(cached ?? null);
  const [step, setStep] = useState(0);
  const [results, setResults] = useState<Record<string, string>>({});

  useEffect(() => {
    if (jobs !== null) return;
    const lines = [
      `기술 ${resume.content.techStack.length}개 · 프로젝트 ${resume.content.projects.length}개를 읽었어요`,
      '조건에 맞는 공고 18건을 찾았어요',
      '지원 자격까지 맞는 공고 7건을 남겼어요',
      '이력서와 겹치는 근거가 많은 순으로 정렬했어요',
    ];
    const timers = STEP_IDS.map((id, i) =>
      window.setTimeout(() => {
        setResults((r) => ({ ...r, [id]: lines[i] }));
        setStep(i + 1);
      }, 1200 * (i + 1)),
    );
    // 마지막 단계 뒤 로봇이 떨어지는 시간(1.3초)만큼 두고 목록으로 넘어간다.
    timers.push(
      window.setTimeout(() => {
        const picked = pickJobs(resume);
        jobCache.set(resume.id, picked);
        setJobs(picked);
      }, 1200 * STEP_IDS.length + 1300),
    );
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [jobs, resume]);

  // 추천이 끝나면 로딩은 사라지고 목록만 남는다.
  if (jobs !== null) {
    return (
      <div className="coach-run">
        <div className="coach-jobs__head">
          <strong>맞춤 공고 {jobs.length}건</strong>
          <span className="spacer" />
          <button
            type="button"
            className="btn btn--text btn--sm"
            onClick={() => {
              jobCache.delete(resume.id);
              setResults({});
              setStep(0);
              setJobs(null);
            }}
          >
            다시 추천
          </button>
        </div>
        <div className="coach-jobs">
          {jobs.map((job) => (
            <div key={job.title} className="coach-job">
              <strong>{job.title}</strong>
              <span className="hint">{job.company}</span>
              <span className="coach-job__why">{job.why}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const done = step >= STEP_IDS.length;
  return (
    <div className="coach-run">
      <JobRecommendationLoading
        current={done ? null : STEP_IDS[step]}
        results={results}
        completed={done}
      />
    </div>
  );
}

