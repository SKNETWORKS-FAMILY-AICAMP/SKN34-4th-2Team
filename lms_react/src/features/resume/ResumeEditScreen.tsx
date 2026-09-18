import { useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  addResumeFeedback,
  updateResume,
  useResume,
  useResumeFeedbacks,
} from '../../data/repository';
import {
  ResumeSectionKeys,
  ResumeSectionLabels,
  ResumeStatusLabels,
  computeSections,
} from '../../domain/constants';
import type { Resume, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Card, EmptyState } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { CoachChat } from './CoachChat';
import { JobRecommendationRun } from './JobRecommendationRun';
import { ResumePrintDoc } from './ResumePrintDoc';
import { SectionBody } from './ResumeSections';
import { RobotHead } from '../../ui/RobotHead';

/**
 * 이력서 편집 — features/resume/presentation/resume_edit_screen.dart
 *
 * 왼쪽에 이력서, 오른쪽에 역할별 패널을 둔다.
 * - 학생: AI 코치(첨삭·공고 추천·코치에게 묻기). 받은 피드백은 섹션 아래 댓글로 읽는다.
 * - 강사·관리자: 이력서 항목 목록과 피드백 작성 창만 둔다. 코치는 없다.
 */
export function ResumeEditScreen() {
  const { resumeId } = useParams<{ resumeId: string }>();
  const [search] = useSearchParams();
  const resume = useResume(resumeId);
  const feedbacks = useResumeFeedbacks(resumeId ?? '');
  const user = useCurrentUser();
  const navigate = useNavigate();
  const reviewer = user.role !== 'student';

  const [mode, setMode] = useState<'doc' | 'edit'>(reviewer ? 'doc' : 'edit');
  const [panel, setPanel] = useState<'coach' | 'review' | 'ask' | 'jobs'>('coach');
  const [current, setCurrent] = useState<string>(search.get('section') ?? 'basicInfo');

  if (resume === undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="이력서를 찾을 수 없습니다" />
        </Card>
      </div>
    );
  }

  const done = computeSections(resume.content);
  const filled = ResumeSectionKeys.filter((k) => done[k]).length;
  const patch = (change: Partial<ResumeContent>) =>
    updateResume(resume.id, {
      content: { ...resume.content, ...change },
      revisionCount: resume.revisionCount + 1,
    });

  const backTo = reviewer
    ? user.role === 'admin'
      ? RoutePaths.adminResumes
      : RoutePaths.instructorResumes
    : RoutePaths.resume;

  return (
    <div className="resume-edit">
      <header className="resume-edit__bar">
        <button type="button" className="resume-edit__back" onClick={() => navigate(backTo)}>
          <Icon name="arrow_back" size={18} />
          목록으로
        </button>
        {reviewer && <span className="resume-edit__owner">{resume.userDisplayName}님의 이력서</span>}
        <span className="spacer" />
        {!reviewer && <FeedbackBell resume={resume} onGoTo={setCurrent} />}
        <span className="seg">
          {(['doc', 'edit'] as const).map((m) => (
            <button
              key={m}
              type="button"
              className={`seg__btn${mode === m ? ' seg__btn--on' : ''}`}
              onClick={() => setMode(m)}
              disabled={reviewer && m === 'edit'}
            >
              {m === 'doc' ? 'Doc' : 'Edit'}
            </button>
          ))}
        </span>
        {/* PDF는 Doc 보기에서만 나온다 — 종이에 나갈 모양을 보고 있을 때만 쓴다. */}
        {mode === 'doc' && (
          <button
            type="button"
            className="icon-btn resume-edit__pdf"
            onClick={() => window.print()}
            aria-label="PDF 내보내기"
            title="PDF 내보내기"
          >
            <Icon name="picture_as_pdf" size={20} />
          </button>
        )}
        {reviewer
          ? resume.status === 'feedbackRequested' && (
              <button
                type="button"
                className="btn btn--filled btn--md"
                onClick={() => updateResume(resume.id, { status: 'approved' })}
              >
                <Icon name="check_circle" size={17} />
                승인
              </button>
            )
          : mode === 'edit' && (
              <>
                <button type="button" className="btn btn--outline btn--md">
                  저장
                </button>
                {resume.status === 'draft' && (
                  <button
                    type="button"
                    className="btn btn--filled btn--md"
                    onClick={() => updateResume(resume.id, { status: 'feedbackRequested' })}
                  >
                    <Icon name="send" size={17} />
                    피드백 요청
                  </button>
                )}
              </>
            )}
      </header>

      <div className="resume-edit__status">
        <span>
          {filled}/{ResumeSectionKeys.length} 완료 · {ResumeStatusLabels[resume.status]}
        </span>
        <span className="spacer" />
        <span className="hint">v{resume.revisionCount}</span>
      </div>
      <span className="resume-edit__progress">
        <i style={{ width: `${(filled / ResumeSectionKeys.length) * 100}%` }} />
      </span>

      {!reviewer && resume.status === 'feedbackRequested' && (
        <p className="resume-edit__banner resume-edit__banner--wait">
          피드백 요청됨 — 계속 수정할 수 있습니다.
        </p>
      )}
      {!reviewer && resume.status === 'approved' && (
        <p className="resume-edit__banner resume-edit__banner--ok">
          승인 완료 — 계속 수정할 수 있습니다.
        </p>
      )}

      {/* 칩은 표시가 아니라 이동이다. 누르면 그 항목으로 내려간다. */}
      {!reviewer && (
        <div className="resume-edit__chips">
          {ResumeSectionKeys.map((key) => (
            <button
              key={key}
              type="button"
              className={`sec-chip${done[key] ? ' sec-chip--done' : ''}${
                current === key ? ' sec-chip--on' : ''
              }`}
              onClick={() => {
                setCurrent(key);
                document
                  .getElementById(`sec-${key}`)
                  ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
              }}
            >
              {done[key] && <Icon name="check" size={14} />}
              {ResumeSectionLabels[key]}
            </button>
          ))}
        </div>
      )}

      <div className={`resume-edit__body${reviewer ? ' resume-edit__body--review' : ''}`}>
        <div className="resume-doc">
          <label className="resume-doc__field">
            <span className="resume-doc__label">이력서 제목</span>
            {mode === 'doc' ? (
              <p className="doc-read__title">{resume.title}</p>
            ) : (
              <span className="resume-doc__input-wrap">
                <input
                  className="input"
                  value={resume.title}
                  maxLength={100}
                  onChange={(e) => updateResume(resume.id, { title: e.target.value })}
                />
                <span className="resume-doc__count">{resume.title.length}/100</span>
              </span>
            )}
          </label>

          <section id="sec-basicInfo" className="doc-section doc-section--basic">
            <h2 className="resume-doc__name">{resume.content.basicInfo.name || user.displayName}</h2>
            {mode === 'edit' && (
              <button
                type="button"
                className="resume-doc__fill"
                onClick={() =>
                  patch({
                    basicInfo: {
                      ...resume.content.basicInfo,
                      name: resume.content.basicInfo.name || user.displayName,
                      email: resume.content.basicInfo.email || user.email,
                    },
                  })
                }
              >
                <Icon name="person" size={16} />
                마이페이지 정보로 빈 칸 채우기
              </button>
            )}
            <BasicInfo resume={resume} patch={patch} readOnly={mode === 'doc'} />
            {!reviewer && <SectionComments sectionKey="basicInfo" resume={resume} />}
          </section>

          {ResumeSectionKeys.filter((k) => k !== 'basicInfo').map((key) => (
            <section key={key} className="doc-section" id={`sec-${key}`}>
              <h3 className="doc-section__title">{ResumeSectionLabels[key]}</h3>
              {key === 'coreCompetencies' && (
                <div className="doc-section__help">
                  <p>채용 담당자들이 가장 먼저 읽게 되는 글입니다.</p>
                  <p>경력을 기반으로 나의 역량과 강점을 소개해 주세요.</p>
                  <p>5줄 이내로 간결하게 작성하는 것을 권장합니다.</p>
                </div>
              )}
              <SectionBody sectionKey={key} resume={resume} patch={patch} readOnly={mode === 'doc'} />
              {!reviewer && <SectionComments sectionKey={key} resume={resume} />}
            </section>
          ))}
        </div>

        {reviewer ? (
          <ReviewPanel
            resume={resume}
            current={current}
            onSelect={setCurrent}
            authorId={user.uid}
            authorName={user.displayName}
          />
        ) : (
          <aside className="resume-coach">
            <div className="coach-head">
              <span className="hint">현재 분석 중인 이력서</span>
              <span className="spacer" />
              <span className="badge badge--success">준비 완료</span>
            </div>
            <strong className="coach-title">{resume.title}</strong>
            <p className="hint">
              기술 {resume.content.techStack.length}개 · 프로젝트 {resume.content.projects.length}개
            </p>

            <span className="coach-label">빠른 실행</span>
            <div className="coach-actions">
              <button type="button" className="coach-action" onClick={() => setPanel('review')}>
                <Icon name="edit" size={22} className="coach-action__icon coach-action__icon--red" />
                이력서 첨삭
              </button>
              <button type="button" className="coach-action" onClick={() => setPanel('jobs')}>
                <Icon name="star" size={22} className="coach-action__icon coach-action__icon--yellow" />
                맞춤 공고 추천
              </button>
              <button type="button" className="coach-action" onClick={() => setPanel('ask')}>
                <RobotHead size={26} inverted />
                코치에게 묻기
              </button>
            </div>

            {panel === 'review' ? (
              <CoachChat key="review" resume={resume} mode="review" />
            ) : panel === 'ask' ? (
              <CoachChat key="ask" resume={resume} mode="ask" />
            ) : panel === 'jobs' ? (
              <JobRecommendationRun resume={resume} />
            ) : (
              <div className="coach-empty">
                <Icon name="hub" size={34} />
                <strong>이력서와 채용공고를 연결해볼까요?</strong>
                <p className="hint">
                  분석 버튼을 누르면 명시 조건, 추천 순위, Skill Gap을 한 번에 확인합니다.
                </p>
              </div>
            )}

            {feedbacks.length > 0 && (
              <p className="hint">받은 피드백 {feedbacks.length}건은 각 항목 아래 댓글로 있습니다.</p>
            )}
          </aside>
        )}
      </div>

      {/* 종이에는 이 문서만 나간다. 화면에서는 보이지 않는다. */}
      <ResumePrintDoc resume={resume} />
    </div>
  );
}

function BasicInfo({
  resume,
  patch,
  readOnly,
}: {
  resume: Resume;
  patch(change: Partial<ResumeContent>): void;
  readOnly: boolean;
}) {
  const info = resume.content.basicInfo;
  const set = (key: keyof typeof info, value: string) =>
    patch({ basicInfo: { ...info, [key]: value } });

  const rows: [string, string, keyof typeof info][] = [
    ['call', '연락처', 'phone'],
    ['mail', '이메일', 'email'],
    ['calendar_month', '생년월일', 'birthDate'],
    ['code', 'Github URL', 'githubUrl'],
    ['language', 'Blog URL', 'blogUrl'],
  ];

  return (
    <div className="resume-doc__contacts">
      {rows.map(([icon, label, key]) => (
        <label key={key} className="contact-field">
          <Icon name={icon} size={19} className="contact-field__icon" />
          {/* Doc 보기에는 칸이 없다. 아이콘·라벨·값만 남는다. */}
          <span className={`contact-field__box${readOnly ? ' contact-field__box--read' : ''}`}>
            <span className="contact-field__label">{label}</span>
            {readOnly ? (
              <strong className={info[key].trim() === '' ? 'doc-read__empty' : undefined}>
                {info[key].trim() === '' ? '미작성' : info[key]}
              </strong>
            ) : (
              <input
                className="contact-field__input"
                value={info[key]}
                onChange={(e) => set(key, e.target.value)}
              />
            )}
          </span>
        </label>
      ))}
    </div>
  );
}

/** 학생이 받은 피드백 — 항목 아래 댓글로 읽고 답글을 단다. */
function SectionComments({ sectionKey, resume }: { sectionKey: string; resume: Resume }) {
  const user = useCurrentUser();
  const all = useResumeFeedbacks(resume.id);
  const mine = all.filter((f) => f.sectionKey === sectionKey);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const has = mine.length > 0;

  return (
    <div className="comments">
      <button
        type="button"
        className={`feedback-chip${has ? ' feedback-chip--has' : ''}`}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="mode_comment" size={14} />
        {has ? `피드백 ${mine.length}` : '피드백'}
        <Icon name={open ? 'expand_less' : 'expand_more'} size={15} />
      </button>

      {open && (
        <div className="comments__list">
          {!has && <p className="comments__empty">아직 이 항목에 남긴 피드백이 없습니다.</p>}
          {mine.map((f) => (
            <div key={f.id} className={`comment${f.parentId === '' ? '' : ' comment--reply'}`}>
              <span className="comment__head">
                <strong>{f.authorName}</strong>
                <span className="hint">{formatDateTime(f.createdAt)}</span>
              </span>
              <p className="comment__body">{f.content}</p>
            </div>
          ))}

          <div className="comments__reply">
            <input
              className="input"
              value={draft}
              placeholder="이 항목에 대한 피드백을 적어 주세요"
              onChange={(e) => setDraft(e.target.value)}
            />
            <button
              type="button"
              className="btn btn--filled btn--sm"
              disabled={draft.trim() === ''}
              onClick={() => {
                addResumeFeedback({
                  resumeId: resume.id,
                  sectionKey,
                  content: draft.trim(),
                  authorId: user.uid,
                  authorName: user.displayName,
                  parentId: has ? mine[0].id : '',
                });
                setDraft('');
              }}
            >
              등록
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** 강사·관리자 — 이력서 항목 목록 + 피드백 작성 창 */
function ReviewPanel({
  resume,
  current,
  onSelect,
  authorId,
  authorName,
}: {
  resume: Resume;
  current: string;
  onSelect(key: string): void;
  authorId: string;
  authorName: string;
}) {
  const all = useResumeFeedbacks(resume.id);
  const here = all.filter((f) => f.sectionKey === current);
  const [draft, setDraft] = useState('');

  const send = () => {
    if (draft.trim() === '') return;
    addResumeFeedback({
      resumeId: resume.id,
      sectionKey: current,
      content: draft.trim(),
      authorId,
      authorName,
      parentId: '',
    });
    setDraft('');
  };

  return (
    <>
      <nav className="review-nav">
        <span className="review-nav__title">이력서 항목</span>
        {ResumeSectionKeys.map((key) => (
          <button
            key={key}
            type="button"
            className={`review-nav__item${current === key ? ' review-nav__item--on' : ''}`}
            onClick={() => onSelect(key)}
          >
            {computeSections(resume.content)[key] ? (
              <Icon name="check" size={15} className="review-nav__check" />
            ) : (
              <span className="review-nav__dot" />
            )}
            {ResumeSectionLabels[key]}
          </button>
        ))}
      </nav>

      <section className="review-feedback">
        <header className="review-feedback__head">
          <Icon name="chat_bubble" size={18} />
          <span>
            <strong>피드백 작성</strong>
            <span className="hint">현재 항목 · {ResumeSectionLabels[current]}</span>
          </span>
        </header>

        <div className="review-feedback__body">
          {here.length === 0 ? (
            <p className="review-feedback__empty">
              이 항목에 아직 피드백이 없습니다.
              <br />
              아래 입력란에서 첫 피드백을 작성해 주세요.
            </p>
          ) : (
            here.map((f) => (
              <div key={f.id} className="comment">
                <span className="comment__head">
                  <strong>{f.authorName}</strong>
                  <span className="hint">{formatDateTime(f.createdAt)}</span>
                </span>
                <p className="comment__body">{f.content}</p>
              </div>
            ))
          )}
        </div>

        <div className="review-feedback__form">
          <input
            className="input"
            value={draft}
            placeholder="피드백 입력 · Enter 전송 / Shift+Enter 줄바꿈"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button type="button" className="review-feedback__send" onClick={send} aria-label="보내기">
            <Icon name="send" size={18} />
          </button>
        </div>
      </section>
    </>
  );
}

/**
 * 피드백 종 — widgets/feedback_bell.dart
 *
 * 오른쪽 패널은 AI 코치가 쓰고 있다. 받은 피드백은 종 아래로 말풍선이 내려와
 * 한 줄씩 보이고, 한 줄을 누르면 그 항목으로 내려간다.
 */
function FeedbackBell({ resume, onGoTo }: { resume: Resume; onGoTo(key: string): void }) {
  const items = useResumeFeedbacks(resume.id);
  const [open, setOpen] = useState(false);
  const unread = items.filter((f) => !resume.readFeedbackIds.includes(f.id)).length;

  return (
    <span className="bell">
      <button
        type="button"
        className="icon-btn"
        aria-label={open ? '피드백 닫기' : '피드백 열기'}
        onClick={() => setOpen((v) => !v)}
      >
        <Icon name="notifications" size={20} />
        {unread > 0 && <i className="bell__dot" />}
      </button>

      {open && (
        <div className="bell__pop">
          <header className="bell__head">
            <strong>피드백</strong>
            {unread > 0 && <span className="bell__count">{unread}</span>}
            <span className="spacer" />
            <button type="button" className="icon-btn" aria-label="닫기" onClick={() => setOpen(false)}>
              <Icon name="close" size={16} />
            </button>
          </header>

          {items.length === 0 ? (
            <p className="bell__empty">아직 피드백이 없습니다.</p>
          ) : (
            <ul className="bell__list">
              {items.map((f) => (
                <li key={f.id}>
                  <button
                    type="button"
                    className="bell__row"
                    onClick={() => {
                      setOpen(false);
                      onGoTo(f.sectionKey);
                      document
                        .getElementById(`sec-${f.sectionKey}`)
                        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }}
                  >
                    <span className="bell__row-top">
                      <strong>{f.authorName}</strong>
                      <span className="hint">{formatDateTime(f.createdAt)}</span>
                    </span>
                    <span className="bell__row-label">
                      <strong>{ResumeSectionLabels[f.sectionKey]}</strong>
                      <span className="hint">에 대한 피드백</span>
                      <Icon name="chevron_right" size={16} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </span>
  );
}
