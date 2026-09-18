import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { resumeEditPath } from '../../app/routePaths';
import { createResume, deleteResume, useMyResumes } from '../../data/repository';
import { ResumeSectionKeys, ResumeSectionLabels, ResumeStatusLabels } from '../../domain/constants';
import type { Resume, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/MoreMenu';
import { Badge, Button, Card, EmptyState } from '../../ui/components';
import { formatDate, formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * 이력서 — features/resume/presentation/resume_screen.dart, resume_edit_screen.dart
 *
 * 섹션은 11개다. 기본 이력서 하나가 AI 첨삭·공고 추천의 바탕이 되고, 나머지는
 * 「다른 이력서」로 표에 모인다.
 */
const SECTIONS = ResumeSectionKeys.map((key) => ({ key, label: ResumeSectionLabels[key] }));

const emptyContent: ResumeContent = {
  basicInfo: { name: '', phone: '', email: '', birthDate: '', githubUrl: '', blogUrl: '' },
  coreCompetencies: { text: '' },
  experience: [],
  education: [],
  techStack: [],
  certifications: [],
  awards: [],
  trainingExperience: [],
  otherActivities: [],
  projects: [],
  selfIntroduction: {
    intro: { subtitle: '', body: '' },
    motivation: { subtitle: '', body: '' },
    challenge: { subtitle: '', body: '' },
    growth: { subtitle: '', body: '' },
    strengthsWeaknesses: { subtitle: '', body: '' },
    aspiration: { subtitle: '', body: '' },
  },
};

function filledCount(resume: Resume): number {
  return SECTIONS.filter((s) => resume.sections[s.key] === true).length;
}

/** 이력서 관리 — 기본 이력서 카드 + 다른 이력서 표 */
export function ResumeScreen() {
  const user = useCurrentUser();
  const resumes = useMyResumes(user.uid);
  const navigate = useNavigate();
  const [tab, setTab] = useState<'all' | 'draft' | 'feedbackRequested' | 'approved'>('all');

  const base = resumes.find((r) => r.isBaseResume) ?? resumes[0];
  const others = resumes.filter((r) => r.id !== base?.id);
  const count = (status: string) => resumes.filter((r) => r.status === status).length;

  const shown =
    tab === 'all' ? others : others.filter((r) => r.status === tab);

  const create = () => {
    const id = createResume({
      userId: user.uid,
      userDisplayName: user.displayName,
      title: '새 이력서',
      status: 'draft',
      sections: {},
      content: {
        ...emptyContent,
        basicInfo: { ...emptyContent.basicInfo, name: user.displayName, email: user.email },
      },
      isBaseResume: resumes.length === 0,
      feedbackCount: 0,
      lastSeenFeedbackCount: 0,
      readFeedbackIds: [],
      revisionCount: 0,
    });
    navigate(resumeEditPath(id));
  };

  return (
    <div className="screen__inner">
      <header className="page-head">
        <div>
          <h1 className="page-head__title">이력서 관리</h1>
          <p className="page-head__desc">기본 이력서로 AI 첨삭과 공고 추천을 받습니다.</p>
        </div>
      </header>

      {/* 숫자 배지의 색은 뜻이다 — 작성 중은 주황, 피드백 요청은 늘 파랑, 승인은 초록. */}
      <div className="resume-tabs">
        {(
          [
            ['all', '전체', resumes.length, 'neutral'],
            ['draft', '작성 중', count('draft'), 'warning'],
            ['feedbackRequested', '피드백 요청', count('feedbackRequested'), 'info'],
            ['approved', '승인', count('approved'), 'success'],
          ] as const
        ).map(([id, label, n, tone]) => (
          <button
            key={id}
            type="button"
            data-tone={tone}
            className={`resume-tab${tab === id ? ' resume-tab--on' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
            <span className="resume-tab__count">{n}</span>
          </button>
        ))}
      </div>

      {base === undefined ? (
        <Card>
          <EmptyState message="작성한 이력서가 없습니다" action={<Button onClick={create}>이력서 만들기</Button>} />
        </Card>
      ) : (
        <BaseResumeCard resume={base} onCreate={create} />
      )}

      <section className="panel panel--flush">
        <h2 className="resume-others__title">다른 이력서</h2>
        {shown.length === 0 ? (
          <p className="hint" style={{ padding: '0 18px 18px' }}>
            아직 다른 이력서가 없습니다.
          </p>
        ) : (
          <table className="table resume-others__table">
            <thead>
              <tr>
                <th>제목</th>
                <th style={{ width: 130 }}>상태</th>
                <th style={{ width: 160 }}>채운 섹션</th>
                <th style={{ width: 120 }}>피드백</th>
                <th style={{ width: 120 }}>수정일</th>
                <th style={{ width: 60 }} />
              </tr>
            </thead>
            <tbody>
              {shown.map((resume) => (
                <tr key={resume.id}>
                  <td>
                    <Link className="resume-others__link" to={resumeEditPath(resume.id)}>
                      {resume.title}
                    </Link>
                  </td>
                  <td>
                    <Badge tone={resume.status === 'approved' ? 'success' : 'primary'}>
                      {ResumeStatusLabels[resume.status]}
                    </Badge>
                  </td>
                  <td>
                    <span className="resume-progress">
                      <span className="resume-progress__bar">
                        <i style={{ width: `${(filledCount(resume) / SECTIONS.length) * 100}%` }} />
                      </span>
                      <strong>{filledCount(resume)}</strong>
                      <span className="hint">/{SECTIONS.length}</span>
                    </span>
                  </td>
                  <td className="hint">
                    {resume.feedbackCount === 0 ? '피드백 없음' : `${resume.feedbackCount}건`}
                  </td>
                  <td className="hint">{formatDate(resume.updatedAt)}</td>
                  <td>
                    <MoreMenu
                      items={[
                        {
                          key: 'open',
                          label: '열기',
                          onSelect: () => navigate(resumeEditPath(resume.id)),
                        },
                        {
                          key: 'delete',
                          label: '삭제',
                          danger: true,
                          onSelect: () => deleteResume(resume.id),
                        },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function BaseResumeCard({ resume, onCreate }: { resume: Resume; onCreate(): void }) {
  const filled = filledCount(resume);
  const missing = SECTIONS.filter((s) => resume.sections[s.key] !== true);

  return (
    <section className="panel base-resume">
      <div className="base-resume__head">
        <span className="base-resume__tag">
          <Icon name="bookmark" size={15} />
          기본 이력서
        </span>
        <span className="hint">· AI 첨삭과 공고 추천에 쓰입니다</span>
        <span className="spacer" />
        <Link className="btn btn--filled btn--md" to={resumeEditPath(resume.id)}>
          이어서 작성
        </Link>
        <MoreMenu
          items={[{ key: 'change', label: '기본 이력서 변경', onSelect: onCreate }]}
        />
      </div>

      <div className="base-resume__title-row">
        <strong className="base-resume__title">{resume.title}</strong>
        <Badge tone={resume.status === 'approved' ? 'success' : 'warning'}>
          {ResumeStatusLabels[resume.status]}
        </Badge>
      </div>

      <p className="hint">
        마지막 수정 <strong>{formatDateTime(resume.updatedAt)}</strong> ·{' '}
        {resume.feedbackCount === 0 ? '피드백 없음' : `피드백 ${resume.feedbackCount}건`}
      </p>

      <div className="base-resume__progress">
        <span className="seg-bar">
          {SECTIONS.map((s) => (
            <i key={s.key} className={resume.sections[s.key] === true ? 'seg-bar__on' : undefined} />
          ))}
        </span>
        <strong>{filled}</strong>
        <span className="hint">/ {SECTIONS.length} 섹션 채움</span>
      </div>

      {missing.length > 0 && (
        <div className="base-resume__missing">
          <span className="hint">남은 섹션</span>
          {missing.slice(0, 3).map((s) => (
            <Link key={s.key} className="missing-chip" to={resumeEditPath(resume.id, { section: s.key })}>
              <Icon name="add" size={15} />
              {s.label}
            </Link>
          ))}
        </div>
      )}

      <p className="base-resume__foot">공고를 선택해 맞춤 첨삭을 시작하면 회사별 이력서가 여기에 저장됩니다.</p>
    </section>
  );
}

