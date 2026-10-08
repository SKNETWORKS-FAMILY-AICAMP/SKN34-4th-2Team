import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from 'react';

import { Icon } from '../../../ui/Icon';
import { RobotHead } from '../../../ui/RobotHead';
import type { Json } from './reviewApi';
import { changedRevisionSpans } from './reviewDiff';
import type { DockScope } from './ReviewDock';
import {
  ReviewItemTag,
  ReviewRequirementStrip,
  ReviewStageBar,
  ReviewStarCells,
  isEligibility,
  requirementGroupLabel,
  requirementGroupSummary,
  reviewStageLabel,
  type RequirementRow,
  type StarCheck,
} from './reviewRequirements';
import {
  GENERAL_REVIEW_STEPS,
  JOB_REVIEW_STEPS,
  ReviewSession,
  busyLabel,
  type BusyKind,
  type ChatMessage,
} from './reviewSession';

/**
 * 이력서 첨삭 창 — ai_coach/presentation/job_resume_review_dialog.dart.
 *
 * 일반 첨삭과 공고 맞춤 첨삭이 같은 창을 쓴다. 왼쪽은 첨삭 중인 이력서, 오른쪽은 첨삭 대화.
 * 공고 맞춤 첨삭은 그 공고용 사본을 떠서 고치고, 「첨삭 완료」를 누르면 사본을 편집할 수 있는
 * 이력서로 옮겨 연다.
 */
export interface ReviewWindowProps {
  /** Django 가 소유를 확인하는 이력서 id. 공고 맞춤이면 원본(기본) 이력서 */
  resumeId: string;
  generalReview: boolean;
  jobId?: string;
  jobCompany?: string;
  jobTitle?: string;
  /** 이미 만든 공고 맞춤본으로 다시 들어올 때(재첨삭) */
  tailoredResumeId?: string;
  initialReviewSession?: Json;
  /** 일반 첨삭이 이력서를 바꿨다 */
  onChanged?(): void;
  dock: DockScope;
}

export function ReviewWindow(props: ReviewWindowProps) {
  const { generalReview, dock } = props;
  const previewRef = useRef<HTMLDivElement>(null);
  const chatRef = useRef<HTMLDivElement>(null);
  const answerRef = useRef<HTMLTextAreaElement>(null);
  const dockRef = useRef(dock);
  dockRef.current = dock;
  const changedRef = useRef(props.onChanged);
  changedRef.current = props.onChanged;
  const [confirming, setConfirming] = useState<((ok: boolean) => void) | null>(null);

  const [session] = useState(
    () =>
      new ReviewSession({
        resumeId: props.resumeId,
        jobId: props.jobId ?? '',
        jobCompany: props.jobCompany ?? '',
        jobTitle: props.jobTitle ?? '',
        tailoredResumeId: props.tailoredResumeId ?? '',
        initialReviewSession: props.initialReviewSession ?? {},
        generalReview,
        onChanged: () => changedRef.current?.(),
        onClose: (result) => dockRef.current.close(result),
        confirmComplete: () => new Promise<boolean>((resolve) => setConfirming(() => resolve)),
        onStatus: (status) => dockRef.current.report(status),
        onFocusPreview: (target) => {
          window.requestAnimationFrame(() => {
            const container = previewRef.current;
            const el = [...(container?.querySelectorAll<HTMLElement>('[data-preview-key]') ?? [])].find(
              (node) => node.dataset.previewKey === target,
            );
            if (container == null || el == null) return;
            container.scrollTo({ top: el.offsetTop - container.clientHeight * 0.18, behavior: 'smooth' });
          });
        },
        onRefocusAnswer: () => {
          window.setTimeout(() => {
            if (session.canRefocus) answerRef.current?.focus();
          }, 0);
        },
      }),
  );
  useSyncExternalStore(
    useCallback((listener) => session.subscribe(listener), [session]),
    () => session.version,
  );

  useEffect(() => {
    const detach = session.attach();
    void session.open();
    session.reportDock();
    return detach;
  }, [session]);

  useEffect(() => session.afterRender());

  const view = session.view();
  const { reviewCompleted } = view;

  // 새 말풍선 · 진행 표시 · 오류가 붙으면 대화를 맨 아래로 내린다
  const tail = `${session.messages.length}|${session.busy}|${session.busyStage}|${session.error ?? ''}|${reviewCompleted}`;
  useEffect(() => {
    const chat = chatRef.current;
    chat?.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' });
  }, [tail]);

  // 첨삭 중에는 창을 닫지 않는다(원본 PopScope). 브라우저를 떠나려 하면 묻는다
  useEffect(() => {
    if (!session.busy && !session.mutationPending) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [session.busy, session.mutationPending]);

  const jobSource =
    session.result?.job_source !== null && typeof session.result?.job_source === 'object'
      ? (session.result.job_source as Json)
      : { company: props.jobCompany ?? '', title: props.jobTitle ?? '' };

  const preview = (
    <ResumeDraftPreview
      content={session.preview}
      changed={session.changed}
      highlightedFieldPath={view.highlightedFieldPath}
      starChecks={session.starChecks}
      scrollRef={previewRef}
    />
  );
  const chat = (
    <ReviewChatPane
      session={session}
      view={view}
      generalReview={generalReview}
      chatRef={chatRef}
      answerRef={answerRef}
      canMinimize
    />
  );

  return (
    <div className="rv-window" role="dialog" aria-modal="true" aria-label={generalReview ? '이력서 첨삭' : '공고 맞춤 이력서 첨삭'}>
      <header className="rv-head">
        <Icon name="auto_awesome" size={20} className="rv-head__icon" />
        <div className="rv-head__text">
          <strong>{generalReview ? '이력서 첨삭' : '공고 맞춤 이력서 첨삭'}</strong>
          {generalReview ? (
            <span>문장 표현과 이력서 근거를 검토해 수정안을 제시합니다.</span>
          ) : (
            <span className="rv-head__job">{`${String(jobSource.company ?? '')} ${String(jobSource.title ?? '')}`.trim()}</span>
          )}
        </div>
        {session.result !== null && (
          <button
            type="button"
            className="btn btn--outline btn--sm"
            disabled={session.busy}
            onClick={() => void session.completeReview()}
          >
            <Icon name="check" size={16} />
            첨삭 완료
          </button>
        )}
        {/* 기다리는 동안에만 내려둔다 */}
        {session.busy && (
          <button type="button" className="btn btn--outline btn--sm rv-head__minimize" onClick={dock.minimize}>
            <Icon name="keyboard_arrow_down" size={18} />
            내려두기
          </button>
        )}
        <button
          type="button"
          className="icon-btn"
          aria-label="닫기"
          title="닫기"
          disabled={session.busy || session.mutationPending}
          onClick={() => dock.close()}
        >
          <Icon name="close" size={22} />
        </button>
      </header>
      <SplitBody preview={preview} chat={chat} />
      {confirming !== null && (
        <div className="rv-confirm-backdrop">
          <div className="rv-confirm" role="alertdialog" aria-labelledby="rv-confirm-title">
            <strong id="rv-confirm-title">첨삭을 완료할까요?</strong>
            <p>현재까지 적용한 내용은 유지됩니다. 남은 질문과 적용하지 않은 수정안은 건너뛰고 첨삭을 완료합니다.</p>
            <div className="rv-confirm__actions">
              <button
                type="button"
                className="btn btn--text btn--sm"
                onClick={() => {
                  confirming(false);
                  setConfirming(null);
                }}
              >
                계속 첨삭
              </button>
              <button
                type="button"
                className="btn btn--filled btn--sm"
                onClick={() => {
                  confirming(true);
                  setConfirming(null);
                }}
              >
                첨삭 완료
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/** 넓으면 좌우로 나누고 가운데 손잡이로 폭을 바꾼다(더블클릭하면 반반). 좁으면 위아래로 */
function SplitBody({ preview, chat }: { preview: ReactNode; chat: ReactNode }) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [horizontal, setHorizontal] = useState(true);
  const [fraction, setFraction] = useState(0.5);

  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (el === null) return;
    const observer = new ResizeObserver(() => setHorizontal(el.clientWidth >= 820));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const startDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    const el = bodyRef.current;
    if (el === null) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const rect = el.getBoundingClientRect();
    const move = (ev: PointerEvent) => {
      setFraction(Math.min(0.7, Math.max(0.3, (ev.clientX - rect.left) / rect.width)));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  return (
    <div ref={bodyRef} className={`rv-body${horizontal ? ' is-horizontal' : ''}`}>
      <div className="rv-body__preview" style={horizontal ? { flexBasis: `${fraction * 100}%` } : undefined}>
        {preview}
      </div>
      {horizontal ? (
        <div
          className="rv-body__handle"
          role="separator"
          aria-orientation="vertical"
          onPointerDown={startDrag}
          onDoubleClick={() => setFraction(0.5)}
        />
      ) : (
        <hr className="rv-body__divider" />
      )}
      <div className="rv-body__chat">{chat}</div>
    </div>
  );
}

// ── 왼쪽: 첨삭 중인 이력서 ──────────────────────────────────────

const SECTION_LABELS: [string, string][] = [
  ['coreCompetencies', '핵심 역량'],
  ['experience', '경력'],
  ['education', '학력'],
  ['techStack', '기술 스택'],
  ['certifications', '자격증'],
  ['awards', '수상 내역'],
  ['trainingExperience', '교육 경험'],
  ['otherActivities', '기타 활동'],
  ['projects', '프로젝트'],
  ['selfIntroduction', '자기소개서'],
];

const SELF_INTRO: [string, string][] = [
  ['intro', '자기소개'],
  ['motivation', '지원동기'],
  ['challenge', '직무와 관련된 경험 중 어려움을 극복한 사례'],
  ['growth', '성장과정'],
  ['strengthsWeaknesses', '직무와 관련된 성격의 장단점'],
  ['aspiration', '지원한 회사에 대한 포부'],
];

interface CompactConfig {
  primary: string;
  secondary?: string[];
  startDate?: string;
  endDate?: string;
  singleDate?: string;
  description?: string;
}

const COMPACT: Record<string, CompactConfig> = {
  experience: { primary: 'company', secondary: ['role'], startDate: 'startDate', endDate: 'endDate', description: 'description' },
  education: { primary: 'school', secondary: ['major', 'status'], startDate: 'startDate', endDate: 'endDate' },
  certifications: { primary: 'name', secondary: ['issuer'], singleDate: 'acquiredDate' },
  awards: { primary: 'name', secondary: ['organization'], singleDate: 'date', description: 'description' },
  trainingExperience: {
    primary: 'course',
    secondary: ['organization'],
    startDate: 'startDate',
    endDate: 'endDate',
    description: 'description',
  },
  otherActivities: { primary: 'name', startDate: 'startDate', endDate: 'endDate', description: 'description' },
  projects: { primary: 'name', secondary: ['role', 'techStack'], startDate: 'startDate', endDate: 'endDate', description: 'description' },
};

const IGNORED = new Set(['id', 'url', 'githubUrl', 'blogUrl', 'isCurrent']);

function renderValue(value: unknown): string {
  if (typeof value === 'string') return value.trim();
  if (Array.isArray(value)) return value.map(renderValue).filter((t) => t !== '').join('\n\n');
  if (value !== null && typeof value === 'object') {
    return Object.entries(value as Json)
      .filter(([key]) => !IGNORED.has(key))
      .map(([, v]) => renderValue(v))
      .filter((t) => t !== '')
      .join('\n');
  }
  return '';
}

const text = (item: Json, key?: string) => (key === undefined ? '' : typeof item[key] === 'string' ? (item[key] as string).trim() : '');
const listOf = (value: unknown): Json[] =>
  (Array.isArray(value) ? value : []).filter((v): v is Json => v !== null && typeof v === 'object');

function ResumeDraftPreview({
  content,
  changed,
  highlightedFieldPath,
  starChecks,
  scrollRef,
}: {
  content: Json;
  changed: boolean;
  highlightedFieldPath: string | null;
  starChecks: Record<string, StarCheck>;
  scrollRef: React.RefObject<HTMLDivElement>;
}) {
  const info = (content.basicInfo as Json | undefined) ?? {};
  const highlighted = (key: string) =>
    highlightedFieldPath?.startsWith(`${key}.`) === true || highlightedFieldPath?.startsWith(`${key}[`) === true;

  return (
    // 이력서 문장을 드래그해 복사할 수 있다. 첨삭 결과를 다른 곳에 옮겨 적는 일이 많다
    <div className="rv-preview" ref={scrollRef}>
      <div className="rv-paper">
        <div className="rv-paper__name">
          <strong>{text(info, 'name') === '' ? '작성 중인 이력서' : text(info, 'name')}</strong>
          {changed && <span className="rv-updated">수정 반영됨</span>}
        </div>
        {text(info, 'email') !== '' && <span className="rv-paper__email">{text(info, 'email')}</span>}
        {SECTION_LABELS.map(([key, label]) => {
          if (key === 'selfIntroduction') {
            const sections = (content.selfIntroduction as Json | undefined) ?? {};
            const filled = SELF_INTRO.map(([k, l]) => ({
              key: k,
              label: l,
              body: text((sections[k] as Json | undefined) ?? {}, 'body'),
            })).filter((s) => s.body !== '');
            if (filled.length === 0) return null;
            return (
              <div key={key} data-preview-key={key}>
                <h4 className="rv-section__title">자기소개서</h4>
                {filled.map((s) => (
                  <PreviewSection
                    key={s.key}
                    previewKey={`selfIntroduction.${s.key}`}
                    title={s.label}
                    body={s.body}
                    highlighted={
                      highlightedFieldPath?.startsWith(`selfIntroduction.${s.key}.`) === true ||
                      highlightedFieldPath === `selfIntroduction.${s.key}`
                    }
                    star={starChecks[`selfIntroduction.${s.key}.body`]}
                  />
                ))}
              </div>
            );
          }
          if (key === 'techStack') {
            const items = listOf(content.techStack).filter((item) => text(item, 'name') !== '');
            if (items.length === 0) return null;
            return (
              <div key={key} data-preview-key={key} className={`rv-section${highlighted(key) ? ' is-highlighted' : ''}`}>
                <SectionTitle title={label} highlighted={highlighted(key)} />
                <div className="rv-tech">
                  {items.map((item, i) => (
                    <span key={i} className="rv-tech__chip">
                      <strong>{text(item, 'name')}</strong>
                      {text(item, 'level') !== '' && <span> {text(item, 'level')}</span>}
                    </span>
                  ))}
                </div>
              </div>
            );
          }
          const config = COMPACT[key];
          if (config !== undefined) {
            const items = listOf(content[key]);
            // 서버의 field_path(「projects[2].description」)는 원래 목록 번호라 빈 항목을 거르기 전 번호를 함께 둔다
            const filled = items.map((item, index) => ({ item, index })).filter(({ item }) => text(item, config.primary) !== '');
            if (filled.length === 0) return null;
            return (
              <div key={key} data-preview-key={key} className={`rv-section${highlighted(key) ? ' is-highlighted' : ''}`}>
                <SectionTitle title={label} highlighted={highlighted(key)} />
                {filled.map(({ item, index }) => {
                  const single = text(item, config.singleDate);
                  const start = text(item, config.startDate);
                  const end = text(item, config.endDate);
                  const date = single !== '' ? single : start === '' ? end : end === '' ? start : `${start} – ${end}`;
                  const meta = [...(config.secondary ?? []).map((k) => text(item, k)), date].filter((v) => v !== '');
                  const description = text(item, config.description);
                  const star = starChecks[`${key}[${index}].${config.description ?? ''}`];
                  return (
                    <div key={index} className="rv-item">
                      <div className="rv-item__head">
                        <strong>{text(item, config.primary)}</strong>
                        {meta.length > 0 && <span>{meta.join(' · ')}</span>}
                      </div>
                      {description !== '' && <p>{description}</p>}
                      {star !== undefined && description !== '' && <ReviewStarCells check={star} />}
                    </div>
                  );
                })}
              </div>
            );
          }
          const body = renderValue(content[key]);
          if (body === '') return null;
          return <PreviewSection key={key} previewKey={key} title={label} body={body} highlighted={highlighted(key)} />;
        })}
      </div>
    </div>
  );
}

function SectionTitle({ title, highlighted }: { title: string; highlighted: boolean }) {
  return (
    <div className="rv-section__title">
      {title}
      {highlighted && <span className="rv-section__target">AI 질문 대상</span>}
    </div>
  );
}

function PreviewSection({
  previewKey,
  title,
  body,
  highlighted,
  star,
}: {
  previewKey: string;
  title: string;
  body: string;
  highlighted: boolean;
  star?: StarCheck;
}) {
  return (
    <div data-preview-key={previewKey} className={`rv-section${highlighted ? ' is-highlighted' : ''}`}>
      <SectionTitle title={title} highlighted={highlighted} />
      <p className="rv-section__body">{body}</p>
      {star !== undefined && <ReviewStarCells check={star} />}
    </div>
  );
}

// ── 오른쪽: 첨삭 대화 ────────────────────────────────────────

function ReviewChatPane({
  session,
  view,
  generalReview,
  chatRef,
  answerRef,
  canMinimize,
}: {
  session: ReviewSession;
  view: ReturnType<ReviewSession['view']>;
  generalReview: boolean;
  chatRef: React.RefObject<HTMLDivElement>;
  answerRef: React.RefObject<HTMLTextAreaElement>;
  canMinimize: boolean;
}) {
  const { activeQuestion, remainingQuestionCount, reviewCompleted, currentStage } = view;
  const resultAvailable = session.result !== null;
  const requirementRows = generalReview ? [] : session.requirementRows;
  const onAnswer = activeQuestion === null ? null : () => void session.submitAnswer(activeQuestion);
  const onNoneAnswer = activeQuestion === null ? null : () => session.submitNoneAnswer(activeQuestion);
  const awaitingSuggestionApply = session.pendingQuestion !== null;

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      onAnswer?.();
    }
  };

  return (
    <div className="rv-chat">
      <div className="rv-chat__head">
        <RobotHead size={20} inverted />
        <strong>AI 첨삭 대화</strong>
        <span className="hint">
          {generalReview ? '문장 표현과 경험 근거를 함께 검토합니다.' : '근거가 부족한 내용은 질문으로 확인합니다.'}
        </span>
        <span className="spacer" />
        {resultAvailable && remainingQuestionCount > 0 && (
          <span className="rv-chat__remaining">남은 질문 약 {remainingQuestionCount}개</span>
        )}
      </div>
      {requirementRows.length > 0 && <ReviewRequirementStrip rows={requirementRows} onTapRow={session.focusRequirement} />}
      {resultAvailable && currentStage > 0 && (
        <ReviewStageBar currentStage={currentStage} includeRequirementStage={requirementRows.length > 0} />
      )}
      <div className="rv-chat__list" ref={chatRef}>
        {!resultAvailable && !session.busy && session.error === null && (
          <>
            {session.restartNotice !== null && <NoticeLine text={session.restartNotice} />}
            <div className="rv-intro">
              <Icon name="auto_awesome" size={34} className="rv-intro__spark" />
              <strong>{generalReview ? '이력서 문장과 경험 근거를 확인합니다.' : '선택 공고 기준으로 이력서를 확인합니다.'}</strong>
              <p className="hint">
                {generalReview
                  ? '필요한 사실은 질문으로 확인하고, 맞춤법·문법·표현도 함께 다듬습니다.'
                  : '부족한 사실은 AI가 질문하고, 답변을 근거로 수정안을 제시합니다.'}
              </p>
              <button type="button" className="btn btn--filled btn--md" onClick={() => void session.review()}>
                <Icon name="play_arrow" size={18} />
                첨삭 시작
              </button>
            </div>
          </>
        )}
        {session.answerEditSupported && <AnswerManager session={session} />}
        {session.messages.map((message, i) => (
          <ChatBubble
            key={i}
            message={message}
            resumeContent={session.preview}
            requirementRows={requirementRows}
            starChecks={session.starChecks}
            isSuggestionApplied={session.isSuggestionApplied}
            onApply={(indices) => void session.applySuggestion(indices, String('payload' in message ? message.payload._review_id ?? '' : ''))}
            onSkip={(indices) => session.skipSuggestion(indices, String('payload' in message ? message.payload._review_id ?? '' : ''))}
            onUndo={(item) => void session.undoSuggestion(item)}
          />
        ))}
        {session.busy &&
          (session.busyKind === 'review' ? (
            <><InitialReviewProgress currentStage={session.busyStage} generalReview={generalReview} canMinimize={canMinimize} />
              {session.processingLabel && <div role="status">{session.processingLabel}</div>}</>
          ) : (
            <CompactBusyCard label={session.processingLabel ?? busyLabel((session.busyKind ?? 'answer') as BusyKind)} />
          ))}
        {session.error !== null && <div className="rv-error">{session.error}
          {session.canRetryProcessing && <button type="button" className="btn btn--text btn--sm" disabled={session.busy} onClick={session.retryProcessing}>
            저장된 처리 재개
          </button>}
        </div>}
        {reviewCompleted && (
          <ReviewCompletedNotice
            requirementRows={requirementRows}
            hasFailures={session.hasUnresolvedReviewFailure}
            informationPending={session.informationReviewPending}
            hasSuggestions={session.messages.some((m) => m.type === 'suggestion' || m.type === 'identity')}
            onClose={() => void session.completeReview(false)}
            onRestart={session.restartReview}
          />
        )}
      </div>
      {resultAvailable && !reviewCompleted && (
        <div className="rv-chat__foot">
          {/* 칩을 통째로 빼지 않고 자리만 둔다. 빼면 입력칸이 밀려 포커스를 잃었다(2026-09-16 앱) */}
          <button
            type="button"
            className="chip rv-none"
            style={{ visibility: onNoneAnswer !== null && !session.busy ? 'visible' : 'hidden' }}
            title={activeQuestion?.owner_scope === 'unassigned' ? '해당 경험이 없다면 누르세요. 기억이 불확실하면 답변에 모르겠다고 적어 주세요.' : '이 항목에서 추가로 확인할 내용이 없으면 누르세요.'}
            onClick={() => onNoneAnswer?.()}
          >
            <Icon name="remove_circle_outline" size={16} />
            없음
          </button>
          <div className={`rv-answer${session.busy || activeQuestion === null ? ' is-idle' : ''}`}>
            {activeQuestion?.owner_scope === 'unassigned' && <label>
              답변이 속한 경험
              <select aria-label="답변 경험 항목 선택" disabled={session.busy}
                value={String(session.answerOwner(activeQuestion)?.experience_id ?? '')}
                onChange={e => session.selectAnswerOwner(activeQuestion, e.target.value)}>
                <option value="">{activeQuestion.information_aspect==='experience_presence'
                  ? '경험 유무 먼저 답변 가능 · 항목 연결은 다음 단계' : '항목 선택 (경험 없음 / 모름은 선택 없이 답변)'}</option>
                {(Array.isArray(activeQuestion.owner_options) ? activeQuestion.owner_options as Json[] : []).map(option =>
                  <option key={String(option.experience_id)} value={String(option.experience_id)}>{String(option.experience_title)}</option>)}
              </select>
            </label>}
            {/* 입력칸은 항상 쓸 수 있게 둔다. 처리 중 전송은 흐름이 막는다. 못 쓰는 상태는 힌트와 바탕색으로 알린다 */}
            <textarea
              ref={answerRef}
              rows={1}
              value={session.answer}
              placeholder={
                session.busy
                  ? '처리 중입니다. 끝나면 입력할 수 있어요.'
                  : activeQuestion === null
                    ? awaitingSuggestionApply
                      ? '수정안을 반영하면 다음 질문을 이어갑니다.'
                      : '현재 추가 확인 질문이 없습니다.'
                    : '답변을 입력하세요. (Enter 전송 · Shift+Enter 줄바꿈)'
              }
              onChange={(e) => session.setAnswer(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <button type="button" className="icon-btn" aria-label="답변 보내기" title="답변 보내기" onClick={() => onAnswer?.()}>
              <Icon name="send" size={20} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function AnswerManager({session}: {session: ReviewSession}) {
  const [editing, setEditing] = useState<string | null>(null);
  const [text, setText] = useState('');
  return <details>
    <summary>답변 수정·취소</summary>
    <p>답변 변경과 문서 반영 취소는 별도입니다. 이미 적용한 문장은 자동 삭제되지 않으며, 영향을 받은 문장은 반영 취소 후 재검토해야 합니다.</p>
    {session.editableAnswers.map(answer => <div key={String(answer.question_id)}>
      <p>대상 · {session.answerTargetLabel(answer)}</p>
      <p>{String(answer.question)}</p><p>{String(answer.answer)}</p>
      {editing === answer.question_id ? <>
        <textarea aria-label="수정할 답변" value={text} onChange={e => setText(e.target.value)} disabled={session.busy} />
        <button type="button" disabled={session.busy || !text.trim()} onClick={() => void session.changeAnswer(String(answer.question_id),text).then(() => {if (!session.error) setEditing(null);})}>수정 저장</button>
        <button type="button" onClick={() => setEditing(null)}>편집 취소</button>
      </> : <>
        <button type="button" disabled={session.busy} onClick={() => {setEditing(String(answer.question_id));setText(String(answer.answer));}}>답변 수정</button>
        <button type="button" disabled={session.busy} onClick={() => {
          if (window.confirm('답변 근거를 취소합니다. 이미 적용한 문장은 자동 삭제되지 않습니다. 계속할까요?')) void session.changeAnswer(String(answer.question_id),null);
        }}>답변 취소</button>
      </>}
    </div>)}
    {session.awaitingDocumentUndo && <p role="status">이미 적용한 수정안을 반영 취소해 이전 원문을 복원해 주세요. 답변 취소만으로 문장을 삭제하거나 검증 완료로 처리하지 않습니다.</p>}
  </details>;
}

function InitialReviewProgress({
  currentStage,
  generalReview,
  canMinimize,
}: {
  currentStage: number;
  generalReview: boolean;
  canMinimize: boolean;
}) {
  const steps = generalReview ? GENERAL_REVIEW_STEPS : JOB_REVIEW_STEPS;
  return (
    <div className="rv-progress">
      <div className="rv-progress__head">
        <strong>{generalReview ? '이력서 첨삭 준비 중' : '공고 맞춤 첨삭 준비 중'}</strong>
        <span>
          {Math.min(Math.max(currentStage + 1, 1), steps.length)} / {steps.length} 단계
        </span>
      </div>
      <p className="hint">
        {generalReview ? '이력서의 문장과 경험 근거를 문항별로 확인합니다.' : '선택한 공고 기준으로 첨삭 항목을 준비하고 있어요.'}
      </p>
      {/* 첫 첨삭은 33~71초였다(2026-09-14 기록). 「15초」라고 하면 더 답답하다 */}
      <p className={`rv-progress__wait${canMinimize ? ' is-strong' : ''}`}>
        {canMinimize
          ? '보통 1분 안팎 걸립니다. 내려두기를 누르고 다른 화면을 봐도 첨삭은 계속됩니다.'
          : '보통 1분 안팎 걸립니다. 창을 닫지 않고 잠시 기다려 주세요.'}
      </p>
      <ol className="rv-steps">
        {steps.map((label, index) => {
          const state = index < currentStage ? 'done' : index === currentStage ? 'running' : 'waiting';
          return (
            <li key={label} className={`rv-step is-${state}`}>
              <span className="rv-step__mark">
                {state === 'done' ? (
                  <Icon name="check_circle" size={16} />
                ) : state === 'running' ? (
                  <span className="rv-spinner" />
                ) : (
                  <Icon name="radio_button_unchecked" size={16} />
                )}
              </span>
              <span className="rv-step__label">{label}</span>
              {state === 'running' && <span className="rv-step__now">진행 중</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function CompactBusyCard({ label }: { label: string }) {
  return (
    <div className="rv-busy" role="status">
      <span className="rv-busy__dots" aria-label="처리 중">
        <i />
        <i />
        <i />
      </span>
      <strong>{label}</strong>
    </div>
  );
}

function ReviewCompletedNotice({
  requirementRows,
  hasFailures,
  informationPending,
  hasSuggestions,
  onClose,
  onRestart,
}: {
  requirementRows: RequirementRow[];
  hasFailures: boolean;
  informationPending: boolean;
  hasSuggestions: boolean;
  onClose(): void;
  onRestart(): void;
}) {
  /** 「공고 요건: 필수 4/5 · 우대 2/3 근거 확인」. 공고 없는 첨삭이면 빈 문자열 */
  const part = (group: string) => requirementGroupSummary(requirementRows,group);
  const parts = [part('must'), part('preferred')].filter((t) => t !== '');
  const missing = requirementRows.some((row) => row.status !== 'met' && row.group !== 'task' && !isEligibility(row));
  const pendingRequirementCount = requirementRows.filter((row) => row.assessmentState === 'pending').length;
  const summary =
    parts.length === 0
      ? ''
      : `공고 요건: ${parts.join(' · ')} 근거 확인${missing ? '. 확인되지 않은 요건은 이력서에 넣지 않았습니다.' : ''}`;

  return (
    <div className="rv-done">
      <Icon name={hasFailures ? 'warning' : 'check_circle'} size={22} className="rv-done__icon" />
      <div className="rv-done__text">
        <strong>{hasFailures ? '일부 항목 재검토 필요' : informationPending ? '첨삭 흐름 종료 · 일부 검토 대기' : '첨삭 완료'}</strong>
        {summary !== '' && <span className="rv-done__summary">{summary}</span>}
        <span>
          {hasFailures
            ? '일부 항목은 분석 또는 검증을 마치지 못했습니다. 적용한 내용과 답변은 유지되며, 모든 항목의 첨삭이 성공한 것은 아닙니다.'
            : informationPending
              ? pendingRequirementCount
                ? `표시할 추가 질문과 수정안은 끝났지만 공고 요건 ${pendingRequirementCount}개의 근거 대조가 미완료입니다. 경험이 없다는 판정이나 자동 재요청 예정이라는 뜻은 아닙니다. 이미 적용한 내용과 답변은 유지됩니다.`
                : '표시할 추가 질문과 수정안은 끝났지만 일부 정보 검토 또는 경험 항목 연결이 남아 있습니다. 이미 적용한 내용과 답변은 유지됩니다.'
            : hasSuggestions
            ? '추가 확인 질문이 없습니다. 표시된 수정안은 원하는 것만 반영한 뒤 마칠 수 있습니다.'
            : '추가 확인 질문과 적용할 수정안이 없습니다. 첨삭을 마칠 수 있습니다.'}
        </span>
        {/* 이력서에 내용을 더 넣은 뒤 여기서 다시 첨삭한다. 지난 대화는 정리하고 처음부터 본다 */}
        <button type="button" className="rv-done__restart" onClick={onRestart}>
          <Icon name="refresh" size={15} />
          이력서를 고쳤다면 다시 첨삭
        </button>
      </div>
      <button type="button" className="btn btn--filled btn--sm rv-green" onClick={onClose}>
        {hasFailures || informationPending ? '첨삭 닫기' : '첨삭 완료'}
      </button>
    </div>
  );
}

// ── 말풍선 · 카드 ─────────────────────────────────────────────

/** 수정안 카드 밑에 붙일 안내. 칸 사이 중복과 원문 부정 표현이 빠진 것 */
function noticesFor(item: Json): string[] {
  return ['overlap_notice', 'meaning_notice', 'fact_notice', 'flow_notice']
    .map((key) => item[key])
    .filter((v): v is string => typeof v === 'string' && v !== '');
}

const STAR_GAPS: Record<string, string> = {
  situation: '상황이 빠짐',
  task: '과제가 빠짐',
  action: '행동이 빠짐',
  result: '결과가 빠짐',
};

/** 질문 · 수정안 위의 표시. 요건에 연결되면 「필수 · Git 협업」, 아니면 단계 이름(+ STAR 에서 빠진 것) */
function tagFor(item: Json, requirementRows: RequirementRow[], starChecks: Record<string, StarCheck>): ReactNode {
  const requirementId = typeof item.requirement_id === 'string' ? item.requirement_id : null;
  if (requirementId !== null) {
    const row = requirementRows.find((r) => r.id === requirementId);
    if (row !== undefined) {
      return <ReviewItemTag text={`${requirementGroupLabel(row.group)} · ${row.label}`} requirementGroup={row.group} />;
    }
  }
  const stage = reviewStageLabel(typeof item.stage === 'number' ? item.stage : null);
  const topic = typeof item.topic === 'string' ? item.topic : null;
  const check = starChecks[String(item.field_path)];
  const starText =
    'question' in item && topic !== null && check !== undefined && check.diagnosticStatus === undefined && topic in STAR_GAPS && !check.present.includes(topic)
      ? STAR_GAPS[topic]
      : null;
  if (stage === '') return null;
  return <ReviewItemTag text={starText === null ? stage : `${stage} · ${starText}`} requirementGroup={null} />;
}

function Revision({ original, revision }: { original: string; revision: string }) {
  return (
    <p className="rv-revision">
      {changedRevisionSpans(original, revision).map((span, i) => (span.changed ? <b key={i}>{span.text}</b> : <span key={i}>{span.text}</span>))}
    </p>
  );
}

function NoticeLine({ text }: { text: string }) {
  return (
    <p className="rv-noticeline">
      <Icon name="info" size={14} />
      <span>{text}</span>
    </p>
  );
}

function AppliedNotice({ text, onUndo }: { text: string; onUndo?(): void }) {
  return (
    <div className="rv-applied">
      <span>✓ {text}</span>
      {onUndo !== undefined && (
        <button type="button" className="btn btn--text btn--sm" onClick={onUndo}>
          <Icon name="undo" size={14} />
          되돌리기
        </button>
      )}
    </div>
  );
}

function ChatBubble({
  message,
  resumeContent,
  requirementRows,
  starChecks,
  isSuggestionApplied,
  onApply,
  onSkip,
  onUndo,
}: {
  message: ChatMessage;
  resumeContent: Json | null;
  requirementRows: RequirementRow[];
  starChecks: Record<string, StarCheck>;
  isSuggestionApplied(item: Json): boolean;
  onApply(indices: number[]): void;
  onSkip(indices: number[]): void;
  onUndo(item: Json): void;
}) {
  if (message.type === 'identity' && message.payload._kind === 'polish') {
    const item = message.payload;
    const count = Array.isArray(item._indices) ? item._indices.length : 0;
    if (item._undone === true) return <AppliedNotice text="문장 다듬기 반영을 취소했습니다." />;
    if (item._applied === true) {
      return (
        <AppliedNotice
          text={`문장 다듬기 ${count}개를 이력서에 반영했습니다.`}
          onUndo={item._undo_available === true ? () => onUndo(item) : undefined}
        />
      );
    }
    if (item._skipped === true) return <AppliedNotice text="문장 다듬기를 건너뛰었습니다." />;
    return <PolishBundleCard item={item} onApply={onApply} onSkip={onSkip} tag={tagFor(item, requirementRows, starChecks)} />;
  }

  if (message.type === 'identity') {
    const item = message.payload;
    const indices = (Array.isArray(item._indices) ? item._indices : [item._index]).filter(
      (v): v is number => typeof v === 'number',
    );
    const company = String(item._company ?? '');
    const title = String(item._title ?? '');
    const applied = isSuggestionApplied(item);
    if (item._undone === true) return <AppliedNotice text="회사명·직무명 수정안 반영을 취소했습니다." />;
    if (applied) {
      return (
        <AppliedNotice
          text="회사명·직무명 수정안을 반영했습니다."
          onUndo={item._undo_available === true ? () => onUndo(item) : undefined}
        />
      );
    }
    if (item._skipped === true) return <AppliedNotice text="회사명·직무명 수정안을 건너뛰었습니다." />;
    return (
      <div className="rv-bubble rv-identity">
        <p>
          {indices.length > 1
            ? `이력서의 ${indices.length}개 항목에 있는 회사명·직무명 자리표시자를 ${company} / ${title}(으)로 한 번에 반영할까요?`
            : `회사명을 ${company}, 직무명을 ${title}(으)로 변경할까요?`}
        </p>
        <div className="rv-actions">
          <button type="button" className="btn btn--outline btn--sm" onClick={() => onSkip(indices)}>
            건너뛰기
          </button>
          <button type="button" className="btn btn--filled btn--sm rv-green" onClick={() => onApply(indices)}>
            <Icon name="check" size={15} />네, 변경할게요
          </button>
        </div>
      </div>
    );
  }

  if (message.type === 'suggestion') {
    const item = message.payload;
    const index = item._index as number;
    const applied = isSuggestionApplied(item);
    if (item._undone === true) return <AppliedNotice text="수정안 반영을 취소했습니다." />;
    const newItem = item.new_item !== null && typeof item.new_item === 'object' ? (item.new_item as Json) : null;
    if (applied) {
      return (
        <AppliedNotice
          text={newItem !== null ? '새 프로젝트를 이력서에 추가했습니다. 기간은 직접 채워 주세요.' : '수정안을 이력서에 반영했습니다.'}
          onUndo={item._undo_available === true ? () => onUndo(item) : undefined}
        />
      );
    }
    if (item._skipped === true) return <AppliedNotice text="수정안을 건너뛰었습니다." />;
    if (newItem !== null) {
      return (
        <NewProjectCard
          item={item}
          newItem={newItem}
          tag={tagFor(item, requirementRows, starChecks)}
          onSkip={() => onSkip([index])}
          onApply={() => onApply([index])}
        />
      );
    }
    const original = String(item.original_quote ?? '');
    const reason = String(item.reason ?? '');
    return (
      <div className="rv-card">
        {tagFor(item, requirementRows, starChecks)}
        <strong className="rv-card__title">AI 수정안</strong>
        <span className="rv-card__label">원문</span>
        <p className="rv-revision">{original}</p>
        <hr />
        <span className="rv-card__label is-green">수정안</span>
        <Revision original={original} revision={String(item.suggested_revision ?? '')} />
        {reason !== '' && <p className="rv-card__reason">{reason}</p>}
        {/* 다른 칸과 겹치거나 원문의 부정 표현이 빠진 수정안은 막지 않고 알린다. 사용자가 보고 고른다 */}
        {noticesFor(item).map((notice) => (
          <NoticeLine key={notice} text={notice} />
        ))}
        <div className="rv-actions">
          <button type="button" className="btn btn--outline btn--sm" onClick={() => onSkip([index])}>
            건너뛰기
          </button>
          <button type="button" className="btn btn--filled btn--sm rv-green" onClick={() => onApply([index])}>
            <Icon name="check" size={15} />이 문장으로 바꾸기
          </button>
        </div>
      </div>
    );
  }

  const isUser = message.type === 'user';
  const body = message.type === 'question' ? String(message.payload.question ?? '') : message.text;
  const experienceLabel = message.type === 'question' ? questionExperienceLabel(message.payload, resumeContent) : '';
  return (
    <div className={`rv-bubble${isUser ? ' is-user' : ''}${message.type === 'question' ? ' is-question' : ''}`}>
      {message.type === 'question' && tagFor(message.payload, requirementRows, starChecks)}
      {message.type === 'question' && experienceLabel !== '' && (
          <strong className="rv-question-experience">
            {String(message.payload.field_path ?? '').startsWith('projects[') ? '프로젝트' : '경험'} · {experienceLabel}
          </strong>
        )}
      {message.type === 'question' && Array.isArray(message.payload.target_contexts) && message.payload.target_contexts.map((raw, index) => {
        const context=raw as Json;
        return <div key={index} className="rv-question-source">
          <strong>{context.type==='posting_source' ? '공고 요건 · 지원자 경험과 별개' : context.type==='applicant_source' ? (context.source_type==='user_answer' ? '이전 답변에서 확인할 부분' : '원문에서 확인할 부분') : String(context.label ?? '추가 정보 확인')}</strong>
          {typeof context.quote==='string' && <blockquote style={{whiteSpace:'pre-wrap'}}>
            <QuestionSourceQuote context={context} />
          </blockquote>}
          {typeof context.context_quote==='string' && <details><summary>주변 원문 보기</summary>
            <p style={{whiteSpace:'pre-wrap'}}>{context.context_quote}</p>
          </details>}
        </div>;
      })}
      {message.type === 'question' ? (
        <div className="rv-question-box" role="group" aria-label="답변할 질문">
          <span className="rv-question-box__label">답변할 질문</span>
          <p className="rv-question-box__body">{body}</p>
        </div>
      ) : <p style={{whiteSpace:'pre-wrap'}}>{body}</p>}
    </div>
  );
}

/** Highlight exact source targets in place; never display a cut fragment alone. */
function QuestionSourceQuote({context}: {context: Json}) {
  const quote=String(context.quote ?? '');
  const spans=Array.isArray(context.anchors) && context.anchors.length ? context.anchors : context.selected_source_quotes;
  const terms=Array.isArray(spans) ? spans.filter((s): s is string => typeof s==='string' && s.length>0) : [];
  const ranges=terms.flatMap(term => {
    const found=[];let offset=0;
    while (offset<quote.length) {const start=quote.indexOf(term,offset);if (start<0) break;found.push([start,start+term.length]);offset=start+term.length;}
    return found;
  }).sort((a,b)=>a[0]-b[0]);
  const merged: number[][]=[];
  for (const range of ranges) {
    const last=merged.at(-1);
    if (last && range[0]<=last[1]) last[1]=Math.max(last[1],range[1]);else merged.push([...range]);
  }
  let offset=0;
  const parts=merged.flatMap(([start,end],i)=>{const before=quote.slice(offset,start);offset=end;return [before,<mark key={i}>{quote.slice(start,end)}</mark>];});
  return <>{parts}{quote.slice(offset)}</>;
}

function questionExperienceLabel(question: Json, content: Json | null): string {
  const title = typeof question.experience_title === 'string' ? question.experience_title.trim() : '';
  const owner = String(question.experience_id ?? '');
  // Older persisted B conversations can contain the internal training identity
  // as their title. Resolve by stable item ID, never by array position or name.
  const trainingId = owner.startsWith('trainingExperience:') ? owner.slice('trainingExperience:'.length) : '';
  if (trainingId && (!title || title === owner)) {
    const rows = Array.isArray(content?.trainingExperience) ? content.trainingExperience : [];
    const item = rows.find((row): row is Json => row !== null && typeof row === 'object' &&
      !Array.isArray(row) && (row as Json).id === trainingId);
    return typeof item?.course === 'string' && item.course.trim() ? item.course.trim() : '교육 경험';
  }
  return title;
}

/** 답변이 이력서에 없는 별도 경험일 때. 기존 칸을 고치지 않고 프로젝트 목록 끝에 하나 더한다 */
function NewProjectCard({
  item,
  newItem,
  tag,
  onSkip,
  onApply,
}: {
  item: Json;
  newItem: Json;
  tag: ReactNode;
  onSkip(): void;
  onApply(): void;
}) {
  const notice = String(item.overlap_notice ?? '');
  const reason = String(item.reason ?? '');
  const row = (label: string, value: string) => (
    <div className="rv-newproj__row">
      <span>{label}</span>
      <p className={value === '' ? 'is-empty' : undefined}>{value === '' ? '비워 둠 · 직접 채워 주세요' : value}</p>
    </div>
  );
  return (
    <div className="rv-card">
      {tag}
      <strong className="rv-card__title">
        <Icon name="add_box" size={16} />새 프로젝트로 추가
      </strong>
      {row('이름', String(newItem.name ?? ''))}
      {row('형태', String(newItem.role ?? ''))}
      {row('기술', String(newItem.tech_stack ?? ''))}
      {row('기간', '')}
      {row('설명', String(newItem.description ?? ''))}
      {reason !== '' && <p className="rv-card__reason">{reason}</p>}
      {notice !== '' && <NoticeLine text={notice} />}
      <div className="rv-actions">
        <button type="button" className="btn btn--outline btn--sm" onClick={onSkip}>
          건너뛰기
        </button>
        <button type="button" className="btn btn--filled btn--sm rv-green" onClick={onApply}>
          <Icon name="add" size={15} />
          프로젝트로 추가
        </button>
      </div>
    </div>
  );
}

const FIELD_SECTIONS: Record<string, string> = {
  coreCompetencies: '핵심 역량',
  experience: '경력',
  projects: '프로젝트',
  awards: '수상',
  otherActivities: '기타 활동',
  trainingExperience: '교육',
  education: '학력',
  certifications: '자격증',
};

const FIELD_INTRO: Record<string, string> = {
  intro: '자기소개',
  motivation: '지원동기',
  challenge: '어려움 극복 경험',
  growth: '성장과정',
  strengthsWeaknesses: '성격의 장단점',
  aspiration: '입사 후 포부',
};

function fieldLabel(path: string): string {
  const parts = path.split('.');
  if (parts[0] === 'selfIntroduction' && parts.length > 1) return FIELD_INTRO[parts[1]] ?? '자기소개서';
  const match = /^(\w+)\[(\d+)\]/.exec(path);
  if (match !== null) return `${FIELD_SECTIONS[match[1]] ?? match[1]} ${Number(match[2]) + 1}`;
  return FIELD_SECTIONS[parts[0]] ?? parts[0];
}

/**
 * 첫 첨삭의 문장 다듬기 수정안을 한 카드에 모은다. 새 사실이 없는 표현 수정이라 하나씩 넘기지 않고
 * 고른 것만 한 번에 적용한다
 */
function PolishBundleCard({
  item,
  onApply,
  onSkip,
  tag,
}: {
  item: Json;
  onApply(indices: number[]): void;
  onSkip(indices: number[]): void;
  tag: ReactNode;
}) {
  const items = (Array.isArray(item.items) ? item.items : []).filter((v): v is Json => v !== null && typeof v === 'object');
  const all = items.map((i) => i._index as number);
  const [chosen, setChosen] = useState<Set<number>>(() => new Set(all));
  const toggle = (index: number) =>
    setChosen((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });

  return (
    <div className="rv-card">
      {tag}
      <strong className="rv-card__title">문장 다듬기 {items.length}개</strong>
      <p className="rv-card__reason">
        새 사실 없이 읽기 좋게 고친 문장이에요. 원하는 것만 골라 한 번에 적용하세요. 적용한 뒤 질문에 답하면 다듬어진 문장을
        기준으로 다시 첨삭합니다.
      </p>
      {items.map((row) => {
        const index = row._index as number;
        const original = String(row.original_quote ?? '');
        return (
          <label key={index} className="rv-polish">
            <input type="checkbox" checked={chosen.has(index)} onChange={() => toggle(index)} />
            <span className="rv-polish__body">
              <span className="rv-polish__label">{fieldLabel(String(row.field_path ?? ''))}</span>
              <span className="rv-polish__original">{original}</span>
              <Revision original={original} revision={String(row.suggested_revision ?? '')} />
              {noticesFor(row).map((notice) => (
                <NoticeLine key={notice} text={notice} />
              ))}
            </span>
          </label>
        );
      })}
      <div className="rv-actions">
        <button
          type="button"
          className="btn btn--text btn--sm"
          onClick={() => setChosen(chosen.size === all.length ? new Set() : new Set(all))}
        >
          {chosen.size === all.length ? '모두 해제' : '모두 선택'}
        </button>
        <span className="spacer" />
        <button type="button" className="btn btn--outline btn--sm" onClick={() => onSkip(all)}>
          건너뛰기
        </button>
        <button
          type="button"
          className="btn btn--filled btn--sm rv-green"
          disabled={chosen.size === 0}
          onClick={() => {
            const selected = all.filter((i) => chosen.has(i));
            // 고르지 않은 수정안은 이 카드에서 버린다. 적용 표시와 되돌리기가 고른 것만 본다
            item._indices = selected;
            onApply(selected);
          }}
        >
          <Icon name="check" size={15} />
          선택한 {chosen.size}개 적용
        </button>
      </div>
    </div>
  );
}
