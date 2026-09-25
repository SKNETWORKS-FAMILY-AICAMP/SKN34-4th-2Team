import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type RefObject,
} from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  addResumeFeedback,
  applyBootstrap,
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
import { Card, EmptyState, PageHeader } from '../../ui/components';
import { usePageCrumbs } from '../../app/crumbs';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { CoachAsk } from './ask/CoachAsk';
import { JobRecommendationRun } from './JobRecommendationRun';
import { useReviewDock } from './review/ReviewDock';
import { ResumePrintDoc } from './ResumePrintDoc';
import { SectionBody } from './ResumeSections';
import { RobotHead } from '../../ui/RobotHead';

/** 코치 열림 상태를 남긴다 — Flutter의 SharedPreferences 자리 */
const COACH_VISIBILITY_KEY = 'resume_edit_coach_visible';

/**
 * 오른쪽(좁으면 아래) 패널 크기 — `resume_edit_screen.dart` 값 그대로.
 * 코치 최소 360은 첨삭 대화가 접히지 않는 폭이고, 이력서 본문은 늘 520 이상 남긴다.
 * 좁은 화면에서는 위아래로 끌어 높이를 바꾸고, 본문과 패널 모두 200을 지킨다.
 */
const PANEL = {
  coach: { min: 360, initial: 420 },
  // 항목 목록(140)이 붙는다. 목록을 208 에서 줄인 만큼 패널도 줄였다
  review: { min: 440, initial: 480 },
  maxWidth: 900,
  // 셸 안에 들어와 520 으로 낮췄다. 560 이면 1280 창에서 강사 · 관리자 패널이 나란히 서지 못했다
  minResumeWidth: 520,
  minHeight: 200,
  initialHeight: 430,
  maxHeight: 900,
  minResumeHeight: 200,
  handle: 28,
} as const;

/**
 * 손잡이로 맞춘 패널 크기. 다음에 열어도 그 크기로 연다.
 * 범위는 화면 폭에 따라 달라지므로 여기서 자르지 않는다. CSS 와 손잡이가 그때그때 자른다.
 */
function useStoredSize(key: string, initial: number): [number, (size: number) => void] {
  const [size, setSize] = useState<number>(() => {
    try {
      const saved = Number(window.localStorage.getItem(key));
      return Number.isFinite(saved) && saved > 0 ? saved : initial;
    } catch {
      return initial;
    }
  });

  const set = (next: number) => {
    setSize(next);
    try {
      window.localStorage.setItem(key, String(next));
    } catch {
      /* 못 남겨도 이번 화면에서는 바뀐 크기로 보인다 */
    }
  };

  return [size, set];
}

/**
 * 이력서와 패널을 나란히 둘 만큼 넓은가 — `resume_edit_screen.dart`의 `wide`처럼 바깥 틀 폭으로 본다.
 *
 * 편집기가 셸 안에 있어 창 폭이 아니라 편집기 폭을 잰다. 왼쪽 메뉴를 접고 펴면 폭이 달라진다.
 * 기준은 본문 최소 + 손잡이 + 패널 최소. 검토자는 패널에 항목 목록이 붙어 더 넓어야 한다.
 */
function useWide(root: HTMLElement | null, reviewer: boolean): boolean {
  const need = PANEL.minResumeWidth + PANEL.handle + (reviewer ? PANEL.review.min : PANEL.coach.min);
  // 재기 전 첫 그림 — 창 폭에서 펼친 메뉴 · 여백을 뺀 어림값
  const [wide, setWide] = useState(() => window.innerWidth - 256 >= need);

  useEffect(() => {
    if (root === null || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(([entry]) => setWide(entry.contentRect.width >= need));
    observer.observe(root);
    return () => observer.disconnect();
  }, [root, need]);

  return wide;
}

/**
 * AI 코치 패널을 보일지.
 *
 * 넓으면 기본으로 열어 두고(지난번에 접어 뒀다면 그대로 접힌 채로), 좁으면 본문을
 * 먼저 보인다 — 좁은 화면에서는 늘 닫힌 채로 시작한다. 원본과 같다.
 */
function useCoachVisible(wide: boolean): [boolean, (visible: boolean) => void] {
  const [visible, setVisible] = useState(wide);
  const initialized = useRef(false);

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    if (!wide) return;
    try {
      const saved = window.localStorage.getItem(COACH_VISIBILITY_KEY);
      if (saved !== null) setVisible(saved === 'true');
    } catch {
      /* 저장소를 못 읽어도 기본값으로 연다 */
    }
  }, [wide]);

  const set = (next: boolean) => {
    setVisible(next);
    try {
      window.localStorage.setItem(COACH_VISIBILITY_KEY, String(next));
    } catch {
      /* 못 남겨도 이번 화면에서는 바뀐 대로 보인다 */
    }
  };

  return [visible, set];
}

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
  const reviewer = user.role !== 'student';
  const [root, setRoot] = useState<HTMLDivElement | null>(null);
  const wide = useWide(root, reviewer);
  const [coachVisible, setCoachVisible] = useCoachVisible(wide);
  const showCoach = coachVisible;
  const bodyRef = useRef<HTMLDivElement>(null);
  const widthRange = reviewer ? PANEL.review : PANEL.coach;
  // 코치와 검토자 패널은 폭 범위가 달라 따로 기억한다.
  const [panelWidth, setPanelWidth] = useStoredSize(
    reviewer ? 'resume_edit_review_width' : 'resume_edit_coach_width',
    widthRange.initial,
  );
  const [panelHeight, setPanelHeight] = useStoredSize('resume_edit_panel_height', PANEL.initialHeight);

  const [mode, setMode] = useState<'doc' | 'edit'>(reviewer ? 'doc' : 'edit');
  const [panel, setPanel] = useState<'coach' | 'jobs'>('coach');
  // 코치에게 묻기는 코치 패널을 통째로 차지한다. 돌아오면 보던 첫 화면(추천 목록 등)이 그대로다
  const [asking, setAsking] = useState(false);
  // 대화에서 받은 추천을 「근거 전체 보기」로 열 때 목록을 새로 읽게 한다
  const [jobsView, setJobsView] = useState(0);
  const { openReview } = useReviewDock();
  const [current, setCurrent] = useState<string>(search.get('section') ?? 'basicInfo');
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');
  const listPath = reviewer ? (user.role === 'admin' ? RoutePaths.adminResumes : RoutePaths.instructorResumes) : RoutePaths.resume;
  usePageCrumbs([{ label: '이력서 관리', to: listPath }, { label: resume?.title ?? '이력서' }]);

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
  const patch = (change: Partial<ResumeContent>) => {
    setSaveState('idle');
    void updateResume(resume.id, {
      content: { ...resume.content, ...change },
    }).catch(() => setSaveState('error'));
  };
  const saveResume = async () => {
    setSaveState('saving');
    try {
      await updateResume(resume.id, { revisionCount: resume.revisionCount + 1 });
      setSaveState('saved');
    } catch {
      setSaveState('error');
    }
  };

  const headActions = (
    <>
      {/* 좁을 때만 나온다. 넓으면 패널 가장자리의 단추로 접고 편다. */}
      {!wide && (
        <button
          type="button"
          className="icon-btn"
          onClick={() => setCoachVisible(!coachVisible)}
          aria-expanded={coachVisible}
          aria-label={
            coachVisible
              ? (reviewer ? '피드백 접기' : 'AI 코치 접기')
              : (reviewer ? '피드백 열기' : 'AI 코치 열기')
          }
          title={
            coachVisible
              ? (reviewer ? '피드백 접기' : 'AI 코치 접기')
              : (reviewer ? '피드백 열기' : 'AI 코치 열기')
          }
        >
          <Icon
            name={coachVisible ? 'keyboard_arrow_down' : reviewer ? 'chat_bubble' : 'smart_toy'}
            size={20}
          />
        </button>
      )}
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
              className="btn btn--filled btn--sm"
              onClick={() => updateResume(resume.id, { status: 'approved' })}
            >
              <Icon name="check_circle" size={17} />
              승인
            </button>
          )
        : mode === 'edit' && (
            <>
              <button
                type="button"
                className="btn btn--outline btn--md"
                onClick={() => void saveResume()}
                disabled={saveState === 'saving'}
                aria-live="polite"
              >
                {saveState === 'saved' && <Icon name="check" size={17} />}
                {saveState === 'saved' ? '저장됨' : saveState === 'saving' ? '저장 중…' : saveState === 'error' ? '저장 실패 · 재시도' : '저장'}
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
    </>
  );

  return (
    <div className="resume-edit" ref={setRoot}>
      {/* 다른 화면과 같은 머리글. 위치(이력서 관리 › 제목)는 상단 막대에, 진행 상태는 설명 줄에 */}
      <PageHeader
        title={resume.title}
        description={`${reviewer ? `${resume.userDisplayName}님의 이력서 · ` : ''}${filled}/${ResumeSectionKeys.length} 완료 · ${ResumeStatusLabels[resume.status]} · v${resume.revisionCount}`}
        actions={headActions}
      />
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

      <div
        ref={bodyRef}
        className={`resume-edit__body${wide ? '' : ' resume-edit__body--stack'}`}
        style={
          {
            '--panel-min': `${widthRange.min}px`,
            '--panel-w': `${panelWidth}px`,
            '--panel-h': `${panelHeight}px`,
          } as CSSProperties
        }
      >
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
                  onChange={(e) => {
                    setSaveState('idle');
                    void updateResume(resume.id, { title: e.target.value }).catch(() => setSaveState('error'));
                  }}
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

        {showCoach ? (
          <PanelHandle
            axis={wide ? 'x' : 'y'}
            bodyRef={bodyRef}
            size={wide ? panelWidth : panelHeight}
            range={
              wide
                ? (body) => [
                    widthRange.min,
                    Math.max(
                      widthRange.min,
                      Math.min(PANEL.maxWidth, body.width - PANEL.minResumeWidth - PANEL.handle),
                    ),
                  ]
                : (body) => [
                    PANEL.minHeight,
                    Math.max(
                      PANEL.minHeight,
                      Math.min(PANEL.maxHeight, body.height - PANEL.minResumeHeight - PANEL.handle),
                    ),
                  ]
            }
            onCommit={wide ? setPanelWidth : setPanelHeight}
            onReset={() => (wide ? setPanelWidth(widthRange.initial) : setPanelHeight(PANEL.initialHeight))}
            onToggle={wide ? () => setCoachVisible(false) : undefined}
            toggleLabel={reviewer ? '피드백 접기' : 'AI 코치 접기'}
          />
        ) : (
          wide && (
            <div className="resume-edit__edge">
              <CoachEdgeToggle
                expanded={false}
                label={reviewer ? '피드백 열기' : 'AI 코치 열기'}
                onClick={() => setCoachVisible(true)}
              />
            </div>
          )
        )}

        {/* 학생의 코치는 접어도 트리에서 빼지 않는다. 빼면 받아 둔 맞춤 공고와 묻던 대화가
            버려져 다시 열면 빈 화면이 나온다. 검토자의 피드백 창은 남길 상태가 없어
            보일 때만 만든다 — 원본과 같다. */}
        {reviewer ? (
          showCoach && (
            <div className="resume-panel resume-panel--review">
              <ReviewPanel
                resume={resume}
                current={current}
                onSelect={setCurrent}
                authorId={user.uid}
                authorName={user.displayName}
              />
            </div>
          )
        ) : (
          <div className="resume-panel" hidden={!showCoach}>
            <CoachAsk
              resume={resume}
              hidden={!asking}
              onBack={() => setAsking(false)}
              onOpenDetail={() => {
                setPanel('jobs');
                setJobsView((v) => v + 1);
                setAsking(false);
              }}
            />
            <aside className="resume-coach" hidden={asking}>
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
                {/* 원본 _reviewResume — 공고와 무관하게 문장 자체를 다듬는 첨삭 창을 연다 */}
                <button
                  type="button"
                  className="coach-action"
                  onClick={() =>
                    openReview(`general-review-${resume.id}`, {
                      resumeId: resume.id,
                      generalReview: true,
                      // 서버가 이미 저장했다. 편집 화면이 바뀐 이력서를 다시 받아 그린다
                      onChanged: () => void applyBootstrap(),
                    })
                  }
                >
                  <Icon name="edit" size={22} className="coach-action__icon coach-action__icon--red" />
                  이력서 첨삭
                </button>
                <button type="button" className="coach-action" onClick={() => setPanel('jobs')}>
                  <Icon name="star" size={22} className="coach-action__icon coach-action__icon--yellow" />
                  맞춤 공고 추천
                </button>
                <button type="button" className="coach-action" onClick={() => setAsking(true)}>
                  <RobotHead size={26} inverted />
                  코치에게 묻기
                </button>
              </div>

              {panel === 'jobs' ? (
                <JobRecommendationRun key={jobsView} resume={resume} />
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
          </div>
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
            placeholder="피드백 입력 · Enter 전송"
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

/**
 * 패널 크기 손잡이 — `_PanelResizeHandle`.
 *
 * 보이는 선은 1픽셀이지만 잡히는 폭은 28픽셀이다. 두 번 누르면 처음 크기로 돌아간다.
 * 넓은 화면(x)에서는 세로 막대를 좌우로, 좁은 화면(y)에서는 가로 막대를 위아래로 끈다.
 *
 * 끄는 동안에는 상태를 바꾸지 않고 CSS 변수만 고친다. 매번 상태를 바꾸면 입력칸
 * 수십 개짜리 편집 화면 전체를 초당 60번 다시 그려 버벅인다 — 원본이 `ValueNotifier`
 * 를 따로 둔 이유와 같다. 손을 떼면 그때 한 번 상태에 남긴다.
 */
function PanelHandle({
  axis,
  bodyRef,
  size,
  range,
  onCommit,
  onReset,
  onToggle,
  toggleLabel,
}: {
  axis: 'x' | 'y';
  bodyRef: RefObject<HTMLDivElement | null>;
  size: number;
  range(body: DOMRect): [number, number];
  onCommit(size: number): void;
  onReset(): void;
  onToggle?: () => void;
  toggleLabel: string;
}) {
  const drag = useRef<{ start: number; from: number; last: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const cssVar = axis === 'x' ? '--panel-w' : '--panel-h';

  /** 본문과 패널이 각자 최소 크기를 지키도록 자른다. 창 크기가 바뀌면 CSS 가 같은 범위로 자른다. */
  const clamp = (next: number) => {
    const body = bodyRef.current;
    if (body === null) return next;
    const [min, max] = range(body.getBoundingClientRect());
    return Math.round(Math.min(max, Math.max(min, next)));
  };

  const apply = (next: number) => bodyRef.current?.style.setProperty(cssVar, `${next}px`);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    // 누른 채 끌면 이력서 글자가 같이 선택된다. 그걸 막는다.
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const from = clamp(size);
    drag.current = { start: axis === 'x' ? e.clientX : e.clientY, from, last: from };
    setDragging(true);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const d = drag.current;
    if (d === null) return;
    // 패널은 오른쪽(아래)에 있다. 왼쪽(위)으로 끌면 거리가 음수이고 패널이 커진다.
    const next = clamp(d.from - ((axis === 'x' ? e.clientX : e.clientY) - d.start));
    d.last = next;
    apply(next);
  };

  const onPointerEnd = () => {
    const d = drag.current;
    if (d === null) return;
    drag.current = null;
    setDragging(false);
    onCommit(d.last);
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    const grow = axis === 'x' ? 'ArrowLeft' : 'ArrowUp';
    const shrink = axis === 'x' ? 'ArrowRight' : 'ArrowDown';
    if (e.key !== grow && e.key !== shrink) return;
    e.preventDefault();
    onCommit(clamp(size + (e.key === grow ? 24 : -24)));
  };

  return (
    <div
      className={`panel-handle panel-handle--${axis}${dragging ? ' panel-handle--dragging' : ''}`}
      role="separator"
      aria-orientation={axis === 'x' ? 'vertical' : 'horizontal'}
      aria-label="패널 크기 조절 · 두 번 누르면 처음 크기"
      aria-valuenow={size}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onDoubleClick={onReset}
      onKeyDown={onKeyDown}
    >
      {onToggle !== undefined && <CoachEdgeToggle expanded label={toggleLabel} onClick={onToggle} />}
    </div>
  );
}

/** 패널 가장자리의 접기·펴기 단추 — `_CoachEdgeToggle`. 넓은 화면에서만 나온다. */
function CoachEdgeToggle({
  expanded,
  label,
  onClick,
}: {
  expanded: boolean;
  label: string;
  onClick(): void;
}) {
  return (
    <button
      type="button"
      className="coach-edge"
      aria-label={label}
      title={label}
      aria-expanded={expanded}
      // 손잡이 위에 얹혀 있다. 누르는 것이 끌기로 번지지 않게 한다.
      onPointerDown={(e) => e.stopPropagation()}
      onDoubleClick={(e) => e.stopPropagation()}
      onClick={onClick}
    >
      <Icon name={expanded ? 'chevron_right' : 'chevron_left'} size={22} />
    </button>
  );
}
