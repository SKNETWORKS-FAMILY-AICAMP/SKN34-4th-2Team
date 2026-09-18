import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { resumeEditPath } from '../../app/routePaths';
import { useResumes } from '../../data/repository';
import { ResumeSectionKeys, ResumeStatusLabels, computeSections } from '../../domain/constants';
import type { Resume } from '../../domain/types';
import { InstructorTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { MoreMenu } from '../../ui/MoreMenu';
import { formatDate } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * 이력서 관리(검토) — features/resume/presentation/resume_screen.dart의 canReview 가지
 *
 * 강사와 관리자가 같은 표를 본다. 작성 중인 이력서는 아직 학생의 것이라 목록에
 * 올라오지 않는다: 피드백을 요청했거나 승인한 것만 보인다. 한 줄의 「검토하기」가
 * 이력서 편집 화면을 검토자 모드로 연다.
 */
type Filter = 'requested' | 'approved' | 'all';

const TAB_LABELS: Record<Filter, string> = {
  requested: '피드백 요청',
  approved: '승인',
  all: '전체',
};

/** 배지 색은 상태의 뜻을 따른다. 강조색을 바꿔도 이 색은 움직이지 않는다. */
const TAB_TONES: Record<Filter, string> = {
  requested: 'info',
  approved: 'success',
  all: 'neutral',
};

export function ReviewerResumesScreen({ canApprove = false }: { canApprove?: boolean }) {
  const user = useCurrentUser();
  const all = useResumes();
  const navigate = useNavigate();
  const statsRef = useTourTarget(InstructorTargets.resumesStats);
  const [filter, setFilter] = useState<Filter>('requested');

  // 검토자에게 보이는 이력서 — resume_model.dart의 isVisibleToReviewer
  const resumes = all
    .filter((r) => r.status === 'feedbackRequested' || r.status === 'approved')
    .slice()
    .sort((a, b) => (b.updatedAt?.getTime() ?? 0) - (a.updatedAt?.getTime() ?? 0));

  const counts: Record<Filter, number> = {
    requested: resumes.filter((r) => r.status === 'feedbackRequested').length,
    approved: resumes.filter((r) => r.status === 'approved').length,
    all: resumes.length,
  };
  const shown =
    filter === 'all'
      ? resumes
      : resumes.filter((r) =>
          filter === 'requested' ? r.status === 'feedbackRequested' : r.status === 'approved',
        );

  const subtitle = canApprove
    ? '상단 바에서 고른 기수의 이력서입니다. 피드백을 요청했거나 승인한 것만 보입니다.'
    : `${user.cohortName === '' ? '담당 기수' : user.cohortName} · 피드백을 요청했거나 승인한 이력서만 보입니다.`;

  return (
    <div className="screen__inner">
      <header className="page-head">
        <div>
          <h1 className="page-head__title">이력서 관리</h1>
          <p className="page-head__desc">{subtitle}</p>
        </div>
      </header>

      <div className="resume-tabs" ref={statsRef}>
        {(['requested', 'approved', 'all'] as const).map((id) => (
          <button
            key={id}
            type="button"
            data-tone={TAB_TONES[id]}
            className={`resume-tab${filter === id ? ' resume-tab--on' : ''}`}
            onClick={() => setFilter(id)}
          >
            {TAB_LABELS[id]}
            <span className="resume-tab__count">{counts[id]}</span>
          </button>
        ))}
      </div>

      {shown.length === 0 ? (
        <p className="resume-empty">
          {resumes.length === 0 ? '피드백을 요청한 이력서가 없습니다' : '이 묶음에 해당하는 이력서가 없습니다'}
        </p>
      ) : (
        <section className="panel panel--flush">
          <table className="table resume-review__table">
            <thead>
              <tr>
                <th style={{ width: 120 }}>학생</th>
                <th>이력서</th>
                <th style={{ width: 130 }}>상태</th>
                <th style={{ width: 120 }}>수정일</th>
                <th style={{ width: 150 }}>채운 섹션</th>
                <th>피드백</th>
                <th style={{ width: 150 }} />
              </tr>
            </thead>
            <tbody>
              {shown.map((resume) => (
                <ReviewRow
                  key={resume.id}
                  resume={resume}
                  onOpen={(section) => navigate(resumeEditPath(resume.id, section))}
                />
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function ReviewRow({
  resume,
  onOpen,
}: {
  resume: Resume;
  onOpen(opts?: { feedback?: boolean }): void;
}) {
  const done = computeSections(resume.content);
  const filled = ResumeSectionKeys.filter((k) => done[k]).length;

  return (
    <tr className="resume-review__row" onClick={() => onOpen()}>
      <td>
        <strong>{resume.userDisplayName ?? resume.userId}</strong>
      </td>
      <td className="resume-review__title">{resume.title}</td>
      <td>
        {/* 상태 색은 뜻이라 강조색을 따라가지 않는다 — 피드백 요청은 늘 파랑이다. */}
        <span
          className={`status-pill status-pill--${resume.status === 'approved' ? 'ok' : 'info'}`}
        >
          {ResumeStatusLabels[resume.status]}
        </span>
      </td>
      <td className="hint">{formatDate(resume.updatedAt)}</td>
      <td>
        <span className="resume-progress">
          <span className="resume-progress__bar">
            <i style={{ width: `${(filled / ResumeSectionKeys.length) * 100}%` }} />
          </span>
          <strong>{filled}</strong>
          <span className="hint">/{ResumeSectionKeys.length}</span>
        </span>
      </td>
      <td className="hint">
        {resume.feedbackCount === 0 ? '아직 남긴 피드백 없음' : `${resume.feedbackCount}건`}
      </td>
      <td className="resume-review__actions">
        <button
          type="button"
          className="btn btn--filled btn--sm"
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
        >
          검토하기
        </button>
        <MoreMenu
          items={[
            { key: 'open', label: '열기', onSelect: () => onOpen() },
            {
              key: 'feedback',
              label: '빠른 피드백 작성',
              onSelect: () => onOpen({ feedback: true }),
            },
          ]}
        />
      </td>
    </tr>
  );
}
