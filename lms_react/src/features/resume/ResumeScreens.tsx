import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { resumeEditPath } from '../../app/routePaths';
import { createResume, deleteResume, setBaseResume, useMyResumes } from '../../data/repository';
import { ResumeSectionKeys, ResumeSectionLabels, ResumeStatusLabels } from '../../domain/constants';
import type { Resume, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/MoreMenu';
import { Badge, Button, Card, Dialog, EmptyState, ErrorState, Skeleton } from '../../ui/components';
import { formatDate, formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { groupResumes, isTailored, type ResumeRow } from './resumeGroups';

/**
 * 이력서 — features/resume/presentation/resume_screen.dart, resume_edit_screen.dart
 *
 * 섹션은 11개다. 기본 이력서 하나가 AI 첨삭·공고 추천의 바탕이 되고, 나머지는
 * 「다른 이력서」로 표에 모인다. 공고 맞춤 이력서는 만든 원본 밑에 묶는다(resumeGroups.ts).
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
  const query = useMyResumes(user.uid);
  const navigate = useNavigate();
  const [tab, setTab] = useState<'all' | 'draft' | 'feedbackRequested' | 'approved'>('all');
  const [choosingBase, setChoosingBase] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(false);

  // 훅은 모두 위에서 부른 뒤에 갈라진다 — 렌더마다 호출 순서가 같아야 하므로.
  // 지금은 메모리라 loading이 항상 false지만, 서버를 붙이면 여기가 실제로 걸린다.
  if (query.loading) {
    return (
      <div className="screen__inner">
        <Skeleton rows={4} />
      </div>
    );
  }
  if (query.error !== null) {
    return (
      <div className="screen__inner">
        <ErrorState message="이력서를 불러오지 못했습니다" onRetry={() => window.location.reload()} />
      </div>
    );
  }

  const resumes = query.data ?? [];
  const base = resumes.find((r) => r.isBaseResume) ?? resumes.find((r) => !isTailored(r)) ?? resumes[0];
  const count = (status: string) => resumes.filter((r) => r.status === status).length;

  // 「전체」에서는 맞춤 이력서를 원본 밑에 묶는다. 상태 탭은 상태로 고르는 곳이라 한 줄씩 그대로 둔다.
  const grouped = groupResumes(resumes, base);
  const shown: ResumeRow[] =
    tab === 'all'
      ? grouped.rows
      : resumes.filter((r) => r.id !== base?.id && r.status === tab).map((r) => ({ resume: r, children: [] }));

  const create = async (asBase = false) => {
    if (creating) return;
    setCreating(true);
    setCreateError(false);
    try {
      const id = await createResume({
        userId: user.uid,
        userDisplayName: user.displayName,
        title: asBase ? '기본 이력서' : '새 이력서',
        status: 'draft',
        sections: {},
        content: {
          ...emptyContent,
          basicInfo: { ...emptyContent.basicInfo, name: user.displayName, email: user.email },
        },
        isBaseResume: asBase || resumes.length === 0,
        feedbackCount: 0,
        lastSeenFeedbackCount: 0,
        readFeedbackIds: [],
        revisionCount: 0,
      });
      // 새 기본 이력서면 옛 기본은 내린다(한 사람에 하나)
      if (asBase) setBaseResume(user.uid, id);
      navigate(resumeEditPath(id));
    } catch {
      setCreateError(true);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="screen__inner">
      <header className="page-head">
        <div>
          <h1 className="page-head__title">이력서 관리</h1>
          <p className="page-head__desc">기본 이력서로 AI 첨삭과 공고 추천을 받습니다.</p>
        </div>
      </header>
      {createError && <ErrorState message="이력서를 만들지 못했습니다. 다시 시도해 주세요." onRetry={() => void create()} />}

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
          <EmptyState message="작성한 이력서가 없습니다" action={<Button onClick={() => void create()} disabled={creating}>이력서 만들기</Button>} />
        </Card>
      ) : (
        <BaseResumeCard resume={base} tailored={tab === 'all' ? grouped.baseTailored : []} onChangeBase={() => setChoosingBase(true)} />
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
              {shown.map((row) => (
                <ResumeTableRows key={row.resume.id} row={row} />
              ))}
            </tbody>
          </table>
        )}
      </section>

      {choosingBase && (
        <BaseResumePicker
          resumes={resumes}
          currentId={base?.id}
          onClose={() => setChoosingBase(false)}
          onPick={(id) => {
            setChoosingBase(false);
            setBaseResume(user.uid, id);
          }}
          onCreate={() => {
            setChoosingBase(false);
            void create(true);
          }}
        />
      )}
    </div>
  );
}

/**
 * 기본 이력서 바꾸기 — Flutter _registerBaseResume.
 * 공고별 첨삭은 기본 이력서를 복사해 진행하므로, 공고 맞춤 이력서는 기본이 될 수 없다(후보에서 뺀다).
 */
function BaseResumePicker({
  resumes,
  currentId,
  onClose,
  onPick,
  onCreate,
}: {
  resumes: Resume[];
  currentId: string | undefined;
  onClose(): void;
  onPick(id: string): void;
  onCreate(): void;
}) {
  const candidates = resumes.filter((r) => !isTailored(r) && !r.sourceTailoredResumeId);
  return (
    <Dialog title="기본 이력서 등록" onClose={onClose}>
      <p className="hint">공고별 첨삭은 여기서 고른 기본 이력서를 복사해 진행합니다.</p>
      <ul className="base-picker">
        {candidates.map((r) => (
          <li key={r.id}>
            <button type="button" className="base-picker__item" disabled={r.id === currentId} onClick={() => onPick(r.id)}>
              <span className="base-picker__title">{r.title}</span>
              <span className="hint">
                {filledCount(r)}/{SECTIONS.length} 항목 작성{r.id === currentId ? ' · 지금 기본 이력서' : ''}
              </span>
            </button>
          </li>
        ))}
        <li>
          <button type="button" className="base-picker__item base-picker__item--new" onClick={onCreate}>
            <Icon name="add" size={18} />
            새 기본 이력서 작성
          </button>
        </li>
      </ul>
    </Dialog>
  );
}

function BaseResumeCard({ resume, tailored, onChangeBase }: { resume: Resume; tailored: Resume[]; onChangeBase(): void }) {
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
          items={[{ key: 'change', label: '기본 이력서 변경', onSelect: onChangeBase }]}
        />
      </div>

      <div className="base-resume__title-row">
        <strong className="base-resume__title">{resume.title}</strong>
        <StatusBadge resume={resume} />
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

      {tailored.length > 0 ? (
        <TailoredList resumes={tailored} />
      ) : (
        <p className="base-resume__foot">공고를 선택해 맞춤 첨삭을 시작하면 회사별 이력서가 여기에 저장됩니다.</p>
      )}
    </section>
  );
}

/** 기본 이력서 카드 밑 — 이 이력서로 만든 공고 맞춤 이력서. 많으면 접어 둔다 */
function TailoredList({ resumes }: { resumes: Resume[] }) {
  const [open, setOpen] = useState(resumes.length <= 3);
  return (
    <div className="tailored">
      <button type="button" className="tailored__head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <Icon name="work" size={16} />
        공고 맞춤 이력서 <strong>{resumes.length}</strong>
        <span className="spacer" />
        <Icon name={open ? 'expand_less' : 'expand_more'} size={18} />
      </button>
      {open && (
        <ul className="tailored__list">
          {resumes.map((r) => (
            <li key={r.id}>
              <Link className="tailored__item" to={resumeEditPath(r.id)}>
                <span className="tailored__title">{r.title}</span>
                <StatusBadge resume={r} />
                <span className="hint">{formatDate(r.updatedAt)}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StatusBadge({ resume }: { resume: Resume }) {
  const tone = resume.status === 'approved' ? 'success' : resume.status === 'draft' ? 'warning' : 'info';
  return <Badge tone={tone}>{ResumeStatusLabels[resume.status]}</Badge>;
}

/**
 * 「다른 이력서」 표의 한 줄 — Flutter _StudentTable 그대로.
 * 맞춤 이력서가 딸린 줄은 제목 뒤 「맞춤 n ⌄」 알약이 붙고, 줄을 누르면 바로 밑에 좁은 줄로 펼친다(열기는 ⋯ 메뉴).
 * 딸린 것이 없으면 줄을 누르면 연다. 승인된 이력서 · 기본 이력서는 지우지 않는다.
 */
function ResumeTableRows({ row }: { row: ResumeRow }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const { resume, children } = row;
  const hasCopies = children.length > 0;
  const openResume = (r: Resume) => navigate(resumeEditPath(r.id));
  const menu = (r: Resume) => (
    <MoreMenu
      items={[
        { key: 'open', label: '열기', onSelect: () => openResume(r) },
        ...(r.status === 'approved' || r.isBaseResume
          ? []
          : [{ key: 'delete', label: '삭제', danger: true, onSelect: () => deleteResume(r.id) }]),
      ]}
    />
  );
  const cells = (r: Resume) => (
    <>
      <td>
        <StatusBadge resume={r} />
      </td>
      <td>
        <span className="resume-progress">
          <span className="resume-progress__bar">
            <i style={{ width: `${(filledCount(r) / SECTIONS.length) * 100}%` }} />
          </span>
          <strong>{filledCount(r)}</strong>
          <span className="hint">/{SECTIONS.length}</span>
        </span>
      </td>
      <td className="hint">{r.feedbackCount === 0 ? '피드백 없음' : `${r.feedbackCount}건`}</td>
      <td className="hint">{formatDate(r.updatedAt)}</td>
      {/* ⋯ 메뉴를 눌러도 줄이 펼쳐지거나 열리지 않게 */}
      <td onClick={(e) => e.stopPropagation()}>{menu(r)}</td>
    </>
  );

  return (
    <>
      <tr
        className="resume-others__row"
        onClick={() => (hasCopies ? setOpen((v) => !v) : openResume(resume))}
        aria-expanded={hasCopies ? open : undefined}
      >
        <td>
          <span className="resume-others__name">
            <span className="resume-others__link">{resume.title}</span>
            {hasCopies && (
              <span className="resume-copies">
                맞춤 {children.length}
                <Icon name="expand_more" size={16} className={open ? 'resume-copies__icon--open' : undefined} />
              </span>
            )}
          </span>
        </td>
        {cells(resume)}
      </tr>
      {open &&
        children.map((c) => (
          <tr key={c.id} className="resume-others__row resume-others__child" onClick={() => openResume(c)}>
            <td>
              <span className="resume-others__name">
                <Icon name="subdirectory_arrow_right" size={16} />
                <span className="resume-others__child-title">{c.title}</span>
              </span>
            </td>
            {cells(c)}
          </tr>
        ))}
    </>
  );
}

