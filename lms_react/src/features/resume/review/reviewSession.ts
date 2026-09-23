import { ReviewApiError, reviewApi, type Json } from './reviewApi';
import {
  REVIEW_STAGE_LABELS,
  requirementRowFromMap,
  requirementRowToMap,
  requirementRowsFrom,
  starCheckToMap,
  starChecksByPath,
  type RequirementRow,
  type StarCheck,
} from './reviewRequirements';

/**
 * 첨삭 대화의 상태와 흐름 — job_resume_review_dialog.dart 의 _JobResumeReviewDialogState 를 옮긴 것.
 *
 * 원본은 맵을 제자리에서 고치고 setState 로 다시 그렸다. 흐름(질문 대기열 · 수정안 대기열 · 누락 점검 ·
 * 없음 답변 · 세션 저장)이 그 가정 위에 짜여 있어서 같은 모양으로 둔다. 바뀌면 notify() 로 화면에 알린다.
 */

export type BusyKind = 'review' | 'answer' | 'apply' | 'undo';

export const GENERAL_REVIEW_STEPS = ['기본 이력서 불러오기', '이력서 항목 확인', '경험 근거 비교', '수정안과 확인 질문 준비'];
export const JOB_REVIEW_STEPS = ['공고 요건 정리', '이력서 근거 대조', '경험·문장 점검', '확인 질문과 수정안 준비'];

export function busyLabel(kind: BusyKind): string {
  switch (kind) {
    case 'answer':
      return '답변을 검토하고 다음 보완 항목을 준비하고 있어요';
    case 'undo':
      return '변경 내용을 되돌리고 있어요';
    case 'review':
      return '이력서를 분석하고 있어요';
    case 'apply':
      return '수정안을 반영하고 있어요';
  }
}

export type ChatMessage =
  | { type: 'assistant'; text: string }
  | { type: 'user'; text: string }
  | { type: 'question'; payload: Json }
  | { type: 'suggestion'; payload: Json }
  | { type: 'identity'; payload: Json };

const assistant = (text: string): ChatMessage => ({ type: 'assistant', text });
const userMessage = (text: string): ChatMessage => ({ type: 'user', text });
const questionMessage = (payload: Json): ChatMessage => ({ type: 'question', payload });
const suggestionMessage = (payload: Json): ChatMessage => ({ type: 'suggestion', payload });
const identityMessage = (payload: Json): ChatMessage => ({ type: 'identity', payload });

const questionOf = (m: ChatMessage): Json | null => (m.type === 'question' ? m.payload : null);
const suggestionOf = (m: ChatMessage): Json | null => (m.type === 'suggestion' ? m.payload : null);
const identityOf = (m: ChatMessage): Json | null => (m.type === 'identity' ? m.payload : null);

function messageFromMap(raw: Json): ChatMessage {
  const payload = raw.payload !== null && typeof raw.payload === 'object' ? { ...(raw.payload as Json) } : {};
  switch (raw.type) {
    case 'user':
      return userMessage(String(raw.text ?? ''));
    case 'question':
      return questionMessage(payload);
    case 'suggestion':
      return suggestionMessage(payload);
    case 'identity':
      return identityMessage(payload);
    default:
      return assistant(String(raw.text ?? ''));
  }
}

function messageToMap(m: ChatMessage): Json {
  if (m.type === 'user' || m.type === 'assistant') return { type: m.type, text: m.text };
  return { type: m.type, payload: m.payload };
}

const asMaps = (value: unknown): Json[] =>
  (Array.isArray(value) ? value : []).filter((v): v is Json => v !== null && typeof v === 'object').map((v) => ({ ...v }));

const ints = (value: unknown): number[] =>
  (Array.isArray(value) ? value : []).filter((v): v is number => typeof v === 'number');

const str = (value: unknown): string | null => (typeof value === 'string' ? value : null);

/** 창이 내려둔 막대에 알리는 지금 상태 — review_dock.dart 의 ReviewDockStatus */
export interface ReviewDockStatus {
  title: string;
  subtitle: string;
  busy: boolean;
  stageLabel: string | null;
  stageIndex: number | null;
  stageCount: number | null;
  failed: boolean;
}

export interface ReviewSessionOptions {
  /** Django 가 소유를 확인하는 이력서 id. 공고 맞춤이면 원본(기본) 이력서 */
  resumeId: string;
  jobId: string;
  jobCompany: string;
  jobTitle: string;
  /** 이미 만든 공고 맞춤본으로 다시 들어올 때 */
  tailoredResumeId: string;
  initialReviewSession: Json;
  generalReview: boolean;
  /** 일반 첨삭에서 이력서가 바뀌었다. 편집 화면을 새로 그린다 */
  onChanged(): void;
  /** 창을 닫는다. 공고 맞춤은 편집기로 옮긴 이력서 id 를 함께 준다 */
  onClose(result?: string): void;
  /** 「첨삭을 완료할까요?」 */
  confirmComplete(): Promise<boolean>;
  onStatus(status: ReviewDockStatus): void;
  /** 미리보기에서 이 칸으로 옮겨 간다 */
  onFocusPreview(target: string): void;
  /** 다음 질문에 바로 답하게 입력칸에 포커스를 준다 */
  onRefocusAnswer(): void;
}

export interface ReviewView {
  activeQuestion: Json | null;
  highlightedFieldPath: string | null;
  remainingQuestionCount: number;
  reviewCompleted: boolean;
  currentStage: number;
}

const MAX_REVIEW_QUESTIONS = 10;

export class ReviewSession {
  result: Json | null = null;
  private reviewRequest: Json | null = null;
  private applyRequest: Json | null = null;
  private selected = new Set<number>();
  readonly appliedSuggestionIndices = new Set<number>();
  answer = '';
  messages: ChatMessage[] = [];
  private answeredQuestionIds = new Set<string>();
  private questionQueue: Json[] = [];
  private suggestionQueue: ChatMessage[] = [];
  busy = false;
  changed = false;
  busyKind: BusyKind | null = null;
  busyStage = 0;
  mutationPending = false;
  private gapAuditScheduled = false;
  private gapAuditStarted = false;
  private gapAuditFinished = false;
  private manuallyCompleted = false;
  pendingQuestion: Json | null = null;
  error: string | null = null;
  private focusedFieldPath: string | null = null;
  tailoredResumeId: string | null;
  restartNotice: string | null = null;
  private restartedFromSaved = false;
  requirementRows: RequirementRow[] = [];
  starChecks: Record<string, StarCheck> = {};
  private requirementFocusPath: string | null = null;
  private noneAnswerChain: Promise<void> = Promise.resolve();
  private pendingNoneAnswers = 0;
  private sessionSaveChain: Promise<void> = Promise.resolve();
  preview: Json = {};
  private disposed = false;
  private listeners = new Set<() => void>();
  version = 0;

  constructor(readonly opts: ReviewSessionOptions) {
    this.tailoredResumeId = opts.tailoredResumeId === '' ? null : opts.tailoredResumeId;
    // 새 공고는 창을 열어보는 것만으로 맞춤 이력서를 만들지 않는다. 첨삭을 시작할 때 만든다.
    // 기존 맞춤 이력서로 다시 들어온 경우에만 전달받은 세션을 복원한다.
    if (!opts.generalReview && this.tailoredResumeId !== null && Object.keys(opts.initialReviewSession).length > 0) {
      this.restoreSession(opts.initialReviewSession);
    }
  }

  // ── 화면 연결 ────────────────────────────────────────────

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    if (this.disposed) return;
    this.version++;
    this.listeners.forEach((l) => l());
  }

  /**
   * 창이 떠 있는 동안만 화면에 알린다. React 개발 모드(StrictMode)는 붙였다 뗐다 다시 붙이므로
   * 뗄 때 영영 끝내지 않고, 다시 붙으면 이어 간다.
   */
  attach(): () => void {
    this.disposed = false;
    return () => {
      this.disposed = true;
    };
  }

  setAnswer(text: string) {
    this.answer = text;
    this.notify();
  }

  /** 창을 열면 미리보기를 채운다. 목록에서 이어 연 대화면 저장된 이력서와 같은 판인지도 본다 */
  async open() {
    try {
      const snapshot = await reviewApi.context(
        this.opts.resumeId,
        undefined,
        this.opts.generalReview ? undefined : (this.tailoredResumeId ?? undefined),
      );
      if (Object.keys(this.preview).length === 0) this.preview = (snapshot.content as Json) ?? {};
      if (this.result !== null && this.tailoredResumeId !== null && !this.sessionCompleted) {
        this.checkRestoredResumeVersion(snapshot);
      }
      this.notify();
    } catch {
      // 미리보기를 못 채워도 첨삭은 시작할 수 있다. 첨삭이 스냅샷을 다시 읽는다
    }
  }

  // ── 세션 ────────────────────────────────────────────────

  /** 저장된 대화를 버리고 첫 첨삭 전 상태로 돌린다(재첨삭) */
  private resetSession() {
    this.result = null;
    this.reviewRequest = null;
    this.applyRequest = null;
    this.selected.clear();
    this.appliedSuggestionIndices.clear();
    this.messages = [];
    this.answeredQuestionIds.clear();
    this.questionQueue = [];
    this.suggestionQueue = [];
    this.pendingQuestion = null;
    this.gapAuditScheduled = false;
    this.gapAuditStarted = false;
    this.gapAuditFinished = false;
    this.manuallyCompleted = false;
    this.changed = false;
    this.requirementRows = [];
    this.starChecks = {};
    this.requirementFocusPath = null;
    this.error = null;
  }

  /** 목록에서 이어 연 대화가 지금 저장된 이력서와 같은 판인지. 다르면 정리하고 처음부터 시작하게 한다 */
  private checkRestoredResumeVersion(snapshot: Json) {
    if (this.result === null || this.result.input_hash === snapshot.input_hash) return;
    this.resetSession();
    this.restartNotice = '이력서가 바뀌어 지난 대화를 정리했어요. 첨삭 시작을 누르면 바뀐 이력서로 다시 첨삭해요.';
    this.preview = (snapshot.content as Json) ?? {};
  }

  /** 완료 안내의 「다시 첨삭」. 고친 이력서로 처음부터 다시 첨삭한다 */
  restartReview = () => {
    if (this.busy) return;
    this.resetSession();
    this.restartedFromSaved = true;
    this.notify();
    void this.review();
  };

  private restoreSession(state: Json) {
    if (state.version !== 1 || state.result === null || typeof state.result !== 'object') return;
    const savedResumeId = str(state.resume_id);
    const savedJobId = str(state.job_id);
    const savedResult = { ...(state.result as Json) };
    const savedJobSource = (savedResult.job_source as Json | undefined) ?? {};
    const sourceJobId = str(savedJobSource.job_id);
    const sourceCompany = (str(savedJobSource.company) ?? '').trim();
    const sourceTitle = (str(savedJobSource.title) ?? '').trim();
    const { resumeId, jobId, jobCompany, jobTitle } = this.opts;
    if (
      (savedResumeId !== null && savedResumeId !== resumeId) ||
      (savedJobId !== null && savedJobId !== jobId) ||
      (sourceJobId !== null && sourceJobId !== '' && sourceJobId !== jobId) ||
      ((sourceJobId === null || sourceJobId === '') && sourceCompany !== '' && jobCompany !== '' && sourceCompany !== jobCompany) ||
      ((sourceJobId === null || sourceJobId === '') && sourceTitle !== '' && jobTitle !== '' && sourceTitle !== jobTitle)
    ) {
      return;
    }
    this.result = savedResult;
    this.messages = asMaps(state.messages).map(messageFromMap);
    this.questionQueue = asMaps(state.question_queue);
    this.suggestionQueue = asMaps(state.suggestion_queue).map(messageFromMap);
    this.pendingQuestion =
      state.pending_question !== null && typeof state.pending_question === 'object'
        ? { ...(state.pending_question as Json) }
        : null;
    this.answeredQuestionIds = new Set(
      (Array.isArray(state.answered_question_ids) ? state.answered_question_ids : []).filter(
        (v): v is string => typeof v === 'string',
      ),
    );
    this.appliedSuggestionIndices.clear();
    ints(state.applied_indices).forEach((i) => this.appliedSuggestionIndices.add(i));
    this.gapAuditStarted = state.gap_audit_started === true;
    this.gapAuditFinished = state.gap_audit_finished === true;
    this.manuallyCompleted = state.manually_completed === true;
    this.changed = state.changed === true;
    this.requirementRows = requirementRowsFrom(state.requirement_map);
    this.starChecks = starChecksByPath(state.star_checks);
    this.trimQuestionBacklog();
  }

  private sessionState(): Json {
    return {
      version: 1,
      resume_id: this.opts.resumeId,
      job_id: this.opts.jobId,
      tailored_resume_id: this.tailoredResumeId,
      // 원문 전체가 든 input_fields 와 진단 결과는 복제하지 않는다. 이어하기에는 review id · hash · 공고만 필요하다
      result: this.compactSessionResult(),
      messages: this.messages.map(messageToMap),
      question_queue: this.questionQueue,
      suggestion_queue: this.suggestionQueue.map(messageToMap),
      pending_question: this.pendingQuestion,
      answered_question_ids: [...this.answeredQuestionIds],
      applied_indices: [...this.appliedSuggestionIndices],
      gap_audit_started: this.gapAuditStarted,
      gap_audit_finished: this.gapAuditFinished,
      manually_completed: this.manuallyCompleted,
      changed: this.changed,
      requirement_map: this.requirementRows.map(requirementRowToMap),
      star_checks: Object.values(this.starChecks).map(starCheckToMap),
      completed: this.sessionCompleted,
    };
  }

  private compactSessionResult(): Json {
    const result = this.result ?? {};
    const out: Json = {};
    for (const key of ['review_id', 'input_hash', 'job_source', 'summary', 'grounding_warnings']) {
      if (key in result) out[key] = result[key];
    }
    return out;
  }

  /** 적용도 건너뛰기도 하지 않은 수정안이 대화에 남아 있는가 */
  get hasActiveSuggestion(): boolean {
    return this.messages.some((m) => {
      const item = suggestionOf(m) ?? identityOf(m);
      return item !== null && item._applied !== true && item._skipped !== true;
    });
  }

  /**
   * 질문을 다 마쳤지만 마지막 누락 점검이 아직 시작되지 않았다. 이때 완료로 보면 점검이 붙기 직전
   * 초록 「첨삭 완료」 카드가 잠깐 떴다가 사라졌다(2026-09-15 앱).
   */
  private get awaitingGapAudit(): boolean {
    return this.result !== null && !this.manuallyCompleted && !this.gapAuditStarted && !this.hasActiveSuggestion;
  }

  get sessionCompleted(): boolean {
    if (this.manuallyCompleted) return this.result !== null;
    const hasActiveQuestion = this.messages.some((m) => {
      const q = questionOf(m);
      const id = q === null ? null : str(q.question_id);
      return q !== null && (id === null || !this.answeredQuestionIds.has(id));
    });
    return (
      this.result !== null &&
      !hasActiveQuestion &&
      !this.hasActiveSuggestion &&
      this.pendingQuestion === null &&
      this.questionQueue.length === 0 &&
      this.suggestionQueue.length === 0 &&
      !this.gapAuditScheduled &&
      this.pendingNoneAnswers === 0 &&
      this.gapAuditFinished
    );
  }

  private persistSession(): Promise<void> {
    const tailoredId = this.tailoredResumeId;
    if (this.opts.generalReview || tailoredId === null || this.result === null) return Promise.resolve();
    const state = this.sessionState();
    this.sessionSaveChain = this.sessionSaveChain.then(async () => {
      try {
        await reviewApi.saveSession(this.opts.resumeId, tailoredId, state);
      } catch {
        // 이력서 적용 자체는 이미 원자 저장됐다. 세션 저장 실패로 적용을 실패처럼 보이게 하지 않는다
      }
    });
    return this.sessionSaveChain;
  }

  // ── 실행 ────────────────────────────────────────────────

  private async run(action: () => Promise<void>, kind: BusyKind = 'review') {
    this.busy = true;
    this.busyKind = kind;
    this.busyStage = 0;
    this.error = null;
    this.notify();
    this.reportDock();
    try {
      await action();
    } catch (err) {
      this.error = err instanceof Error ? err.message : String(err);
    } finally {
      this.busy = false;
      this.busyKind = null;
      this.busyStage = 0;
      this.notify();
      this.reportDock();
    }
  }

  private setBusyStage(stage: number) {
    this.busyStage = stage;
    this.notify();
    this.reportDock();
  }

  reportDock() {
    const kind = this.busyKind;
    const staged = kind === 'review' && this.result === null;
    const steps = this.opts.generalReview ? GENERAL_REVIEW_STEPS : JOB_REVIEW_STEPS;
    const stage = Math.min(Math.max(this.busyStage, 0), steps.length - 1);
    this.opts.onStatus({
      title: this.opts.generalReview ? '이력서 첨삭' : '공고 맞춤 첨삭',
      subtitle: this.opts.generalReview ? '' : `${this.opts.jobCompany} ${this.opts.jobTitle}`.trim(),
      busy: this.busy,
      stageLabel: kind === null ? null : staged ? steps[stage] : busyLabel(kind),
      stageIndex: staged ? stage : null,
      stageCount: staged ? steps.length : null,
      failed: this.error !== null,
    });
  }

  review = () => this.run(() => this.reviewOnce().then(() => undefined), 'review');

  /** 첨삭을 한 번 돌린다. 저장된 대화만 보여 주고 모델을 부르지 않았으면 false */
  private async reviewOnce(): Promise<boolean> {
    const general = this.opts.generalReview;
    this.setBusyStage(0);
    await this.ensureTailoredResume();
    this.setBusyStage(1);
    if (this.reviewRequest === null) {
      const snapshot = await reviewApi.context(
        this.opts.resumeId,
        general ? undefined : this.opts.jobId,
        general ? undefined : (this.tailoredResumeId ?? undefined),
      );
      this.preview = (snapshot.content as Json) ?? {};
      // 재첨삭: 저장된 대화가 있으면 이력서가 그대로인지 본다. 고쳤으면 처음부터 첨삭한다.
      // 그대로인데 이미 마친 대화면 모델을 부르지 않고 저장된 대화만 보여 준다
      const restored = this.result;
      if (restored !== null) {
        if (restored.input_hash !== snapshot.input_hash) {
          this.resetSession();
          this.restartedFromSaved = true;
        } else if (this.sessionCompleted) {
          this.setBusyStage(4);
          return false;
        }
      }
      this.reviewRequest = {
        request_id: newId(),
        expected_input_hash: snapshot.input_hash,
        review_mode: general ? 'general' : 'job',
        ...(!general && this.tailoredResumeId !== null ? { tailored_resume_id: this.tailoredResumeId } : {}),
        ...(!general
          ? {
              selected_job_id: this.opts.jobId,
              expected_job_hash: ((snapshot.job_source as Json | undefined) ?? {}).snapshot_hash,
            }
          : {}),
      };
    }
    this.setBusyStage(2);
    this.result = await reviewApi.review(this.opts.resumeId, this.reviewRequest);
    this.setBusyStage(4);
    this.appendReview(this.result, { isFirstReview: this.messages.length === 0 });
    if (this.restartedFromSaved) {
      this.restartedFromSaved = false;
      this.messages.unshift(assistant('이력서를 처음부터 다시 첨삭했어요. 지난 대화는 정리했어요.'));
    }
    this.restartNotice = null;
    await this.persistSession();
    return true;
  }

  private async ensureTailoredResume() {
    if (this.opts.generalReview || this.tailoredResumeId !== null) return;
    const tailored = await reviewApi.createTailored(this.opts.resumeId, this.opts.jobId);
    const tailoredId = str(tailored.tailored_resume_id);
    const content = tailored.content;
    if (tailoredId === null || tailoredId === '' || content === null || typeof content !== 'object') {
      throw new Error('공고별 이력서를 준비하지 못했습니다. 다시 시도해 주세요.');
    }
    this.tailoredResumeId = tailoredId;
    this.preview = content as Json;
    const session = tailored.review_session;
    this.restoreSession(session !== null && typeof session === 'object' ? (session as Json) : {});
    this.notify();
  }

  private async reload() {
    const general = this.opts.generalReview;
    const snapshot = await reviewApi.context(
      this.opts.resumeId,
      general ? undefined : this.opts.jobId,
      general ? undefined : (this.tailoredResumeId ?? undefined),
    );
    // 공고 맞춤본은 기본 이력서와 분리되어 서버에 자동 저장된다
    if (general) this.opts.onChanged();
    this.preview = (snapshot.content as Json) ?? {};
    this.changed = true;
    this.mutationPending = false;
    this.notify();
  }

  // ── 첨삭 결과를 대화에 붙인다 ──────────────────────────

  private appendReview(
    review: Json,
    opts: {
      isFirstReview: boolean;
      answeredFieldPath?: string | null;
      answeredQuestionId?: string | null;
      answeredRequirementId?: string | null;
      isGapAudit?: boolean;
    },
  ) {
    const { isFirstReview, answeredFieldPath = null, answeredQuestionId = null, answeredRequirementId = null } = opts;
    const isGapAudit = opts.isGapAudit ?? false;
    const general = this.opts.generalReview;
    this.pendingQuestion = null;
    this.requirementFocusPath = null;
    const requirementMap = requirementRowsFrom(review.requirement_map);
    if (requirementMap.length > 0) this.requirementRows = requirementMap;
    const starChecks = starChecksByPath(review.star_checks);
    if (Object.keys(starChecks).length > 0) this.starChecks = starChecks;
    if (isFirstReview) {
      const summary = str(review.summary) ?? (general ? '이력서 문장을 검토했습니다.' : '이력서와 선택 공고를 비교했습니다.');
      this.messages.push(assistant(formatInitialSummary(summary)));
    }
    const reviews = asMaps(review.sentence_reviews);
    const job: Json =
      review.job_source !== null && typeof review.job_source === 'object'
        ? (review.job_source as Json)
        : { company: this.opts.jobCompany, title: this.opts.jobTitle };
    let displayedSuggestions = 0;
    const identitySuggestions: Json[] = [];
    const polishSuggestions: Json[] = [];
    // 서버는 「어느 항목에서 했나요?」 질문의 답을 답에 적힌 항목으로 옮긴다. 수정안은 옮겨진 항목에 생기므로
    // 질문이 붙어 있던 칸이 아니라 서버가 기록한 답의 칸으로 거른다(2026-09-15)
    const resolvedFieldPath = resolvedAnswerFieldPath(review, answeredQuestionId, answeredFieldPath);
    // 답에 이름이 나온 다른 항목도 이번 재첨삭에서 함께 고쳤다. 그 항목의 수정안도 보여 준다
    const scopePaths = new Set(
      (Array.isArray(review.answer_scope_paths) ? review.answer_scope_paths : []).filter(
        (p): p is string => typeof p === 'string',
      ),
    );
    // 답한 칸의 수정안을 먼저, 이름이 나온 다른 항목의 수정안을 그 뒤에
    const order = [
      ...reviews.map((_, i) => i).filter((i) => resolvedFieldPath === null || reviews[i].field_path === resolvedFieldPath),
      ...reviews.map((_, i) => i).filter((i) => resolvedFieldPath !== null && reviews[i].field_path !== resolvedFieldPath),
    ];
    for (const index of order) {
      const sentence = { ...reviews[index] };
      // 새 프로젝트 추가 수정안은 아직 없는 칸(projects[N])이라 방금 답한 질문에서 나온 것만 보여 준다
      const newItem = sentence.new_item as Json | undefined;
      const fromThisAnswer =
        (newItem !== null && typeof newItem === 'object' && newItem.question_id === answeredQuestionId) ||
        scopePaths.has(String(sentence.field_path));
      if (resolvedFieldPath !== null && sentence.field_path !== resolvedFieldPath && !fromThisAnswer) continue;
      const revision = str(sentence.suggested_revision);
      if (revision !== null && revision.trim() !== '') {
        sentence._index = index;
        if (!general && isIdentityPlaceholderSuggestion(sentence)) {
          sentence._company = job.company ?? this.opts.jobCompany;
          sentence._title = job.role_title ?? job.title ?? this.opts.jobTitle;
          identitySuggestions.push(sentence);
        } else if (isFirstReview && ['spelling', 'tone', 'clarity'].includes(String(sentence.edit_type))) {
          // 새 사실 없이 표현만 고친 수정안. 하나씩 넘기지 않고 한 카드에서 골라 한 번에 적용한다
          polishSuggestions.push(sentence);
        } else {
          this.suggestionQueue.push(suggestionMessage(sentence));
        }
        displayedSuggestions++;
      }
    }
    if (polishSuggestions.length === 1) {
      this.suggestionQueue.unshift(suggestionMessage(polishSuggestions[0]));
    } else if (polishSuggestions.length > 1) {
      // 회사명 · 직무명 카드와 같은 묶음 적용 경로(_indices)를 쓴다. 첫 질문보다 먼저 보여 준다
      this.suggestionQueue.unshift(
        identityMessage({
          _kind: 'polish',
          field_path: polishSuggestions[0].field_path,
          stage: 1,
          items: polishSuggestions,
          _indices: polishSuggestions.map((item) => item._index),
        }),
      );
    }
    if (identitySuggestions.length > 0) {
      // 회사명 · 직무명 자리표시자는 같은 공고의 확정값으로 바뀐다. 항목마다 묻지 않고 한 번에 확인한다
      this.suggestionQueue.push(
        identityMessage({ ...identitySuggestions[0], _indices: identitySuggestions.map((s) => s._index as number) }),
      );
    }
    const queued = this.takeNextSuggestion();
    if (queued !== null) {
      this.messages.push(queued);
      this.focusPreviewField(fieldPathOf(queued));
    }
    const answeredNone = ((review.telemetry as Json | undefined) ?? {}).model_skipped === 'none_answer';
    if (!isFirstReview && !isGapAudit && answeredNone) {
      // 「없음」 카드. 수정안을 만들려다 실패한 게 아니라 고칠 사실이 없는 것이다
      const label = this.requirementRows.find((row) => row.id === answeredRequirementId)?.label;
      this.messages.push(
        assistant(label !== undefined ? '알겠어요. 이력서에는 넣지 않을게요.' : '알겠어요. 다음 질문으로 넘어갈게요.'),
      );
    } else if (!isFirstReview && !isGapAudit && displayedSuggestions === 0) {
      const warnings = (Array.isArray(review.grounding_warnings) ? review.grounding_warnings : []).filter(
        (w): w is string => typeof w === 'string',
      );
      const answerAlreadyPresent = warnings.some((w) => w.startsWith('answer_already_present:'));
      // 답변으로 공고 요건이 확인됐는지. 수정안은 없어도 요건 표는 바뀐다
      const requirementConfirmed =
        answeredRequirementId !== null &&
        asMaps(review.requirement_map).some(
          (row) => row.id === answeredRequirementId && (row.status === 'met' || row.status === 'partial'),
        );
      // 수정안이 없다고 실패가 아니다. 확인만 되고 이력서에 적을 문장이 없는 답이 많다(2026-09-15 앱)
      this.messages.push(
        assistant(
          answerAlreadyPresent
            ? '확인했어요. 이미 이력서에 들어 있는 내용이라 그대로 두고 다음으로 넘어갈게요.'
            : requirementConfirmed
              ? '확인했어요. 공고 요건 표에 반영하고 다음으로 넘어갈게요.'
              : '확인했어요. 다음으로 넘어갈게요.',
        ),
      );
    }
    this.syncQuestionsWithServer(asMaps(review.questions), !isFirstReview && !isGapAudit);
    const nextQuestion = this.takeNextQuestion();
    if (nextQuestion !== null) {
      if (displayedSuggestions > 0 || this.suggestionQueue.length > 0) {
        // 지금 수정안을 반영할지 먼저 정하게 한다. 다음 질문은 반영한 뒤에 띄운다
        this.pendingQuestion = nextQuestion;
      } else {
        this.messages.push(questionMessage(nextQuestion));
        this.focusPreviewField(str(nextQuestion.field_path));
      }
    } else if (!isFirstReview && displayedSuggestions > 0) {
      this.messages.push(assistant('방금 답한 항목을 기준으로 수정안을 만들었습니다. 적용 전 내용을 확인해 주세요.'));
    }
    if (isGapAudit && nextQuestion === null) {
      this.messages.push(assistant('누락 점검까지 완료했습니다. 추가로 확인할 중요한 항목이 없습니다.'));
    } else if (!isFirstReview && displayedSuggestions === 0 && nextQuestion === null) {
      this.scheduleGapAudit();
    }
    this.notify();
  }

  // ── 질문 대기열 ────────────────────────────────────────

  private hasQuestionKey(key: string): boolean {
    if (this.pendingQuestion !== null && questionKey(this.pendingQuestion) === key) return true;
    return (
      this.questionQueue.some((q) => questionKey(q) === key) ||
      this.messages.some((m) => {
        const q = questionOf(m);
        return q !== null && questionKey(q) === key;
      })
    );
  }

  private acceptedQuestionKeys(): Set<string> {
    const keys = new Set<string>();
    for (const m of this.messages) {
      const q = questionOf(m);
      if (q !== null) keys.add(questionKey(q));
    }
    this.questionQueue.forEach((q) => keys.add(questionKey(q)));
    if (this.pendingQuestion !== null) keys.add(questionKey(this.pendingQuestion));
    return keys;
  }

  private trimQuestionBacklog() {
    const accepted = new Set<string>();
    for (const m of this.messages) {
      const q = questionOf(m);
      if (q !== null) accepted.add(questionKey(q));
    }
    if (this.pendingQuestion !== null) {
      const key = questionKey(this.pendingQuestion);
      if (accepted.size >= MAX_REVIEW_QUESTIONS && !accepted.has(key)) this.pendingQuestion = null;
      else accepted.add(key);
    }
    this.questionQueue = this.questionQueue.filter((q) => {
      const key = questionKey(q);
      if (accepted.has(key)) return false;
      if (accepted.size >= MAX_REVIEW_QUESTIONS) return false;
      accepted.add(key);
      return true;
    });
  }

  private enqueueQuestions(questions: Json[]) {
    const acceptedKeys = this.acceptedQuestionKeys();
    for (const raw of questions) {
      const question = { ...raw };
      const questionId = str(question.question_id);
      if (questionId !== null && this.answeredQuestionIds.has(questionId)) continue;
      if ((str(question.field_path) ?? '') === '' || (str(question.question) ?? '').trim() === '') continue;
      const key = questionKey(question);
      const queuedIndex = this.questionQueue.findIndex((q) => questionKey(q) === key);
      if (queuedIndex >= 0) {
        // 재첨삭이 대기 중인 질문을 새 review_id 로 다시 냈다. 자리는 두고 서버의 최신 id 로 바꾼다
        this.questionQueue[queuedIndex] = question;
      } else if (this.pendingQuestion !== null && questionKey(this.pendingQuestion) === key) {
        this.pendingQuestion = question;
      } else if (!this.hasQuestionKey(key) && acceptedKeys.size < MAX_REVIEW_QUESTIONS) {
        this.questionQueue.push(question);
        acceptedKeys.add(key);
      }
    }
  }

  private takeNextQuestion(): Json | null {
    while (this.questionQueue.length > 0) {
      const question = this.questionQueue.shift()!;
      const questionId = str(question.question_id);
      if (questionId === null || !this.answeredQuestionIds.has(questionId)) return question;
    }
    return null;
  }

  private takeNextSuggestion(): ChatMessage | null {
    return this.suggestionQueue.shift() ?? null;
  }

  private get hasUnansweredDisplayedQuestion(): boolean {
    return this.messages.some((m) => {
      const q = questionOf(m);
      const id = q === null ? null : str(q.question_id);
      return q !== null && (id === null || !this.answeredQuestionIds.has(id));
    });
  }

  /**
   * 서버가 돌려준 질문 목록을 기준으로 대기열을 맞춘다. 서버는 답할 때마다 남은 질문을 다시 정리하는데
   * 앱이 옛 목록을 들고 있으면 서버가 뺀 질문을 띄우고, 거기 답하면 거절당했다(2026-09-15 앱)
   */
  private syncQuestionsWithServer(questions: Json[], dropMissing: boolean) {
    this.adoptReissuedQuestionIds(questions);
    if (dropMissing) {
      const keys = new Set(questions.map(questionKey));
      this.questionQueue = this.questionQueue.filter((q) => keys.has(questionKey(q)));
      // 화면에 먼저 띄웠지만 서버가 뺀 질문은 답하지 않은 채 대화에서 걷어낸다
      this.messages = this.messages.filter((m) => {
        const shown = questionOf(m);
        const shownId = shown === null ? null : str(shown.question_id);
        const stale = shown !== null && shownId !== null && !this.answeredQuestionIds.has(shownId) && !keys.has(questionKey(shown));
        if (stale) this.answeredQuestionIds.add(shownId!);
        return !stale;
      });
      if (this.pendingQuestion !== null && !keys.has(questionKey(this.pendingQuestion))) this.pendingQuestion = null;
    }
    this.enqueueQuestions(questions);
  }

  /** 화면에 띄운 질문이 서버의 최신 질문 목록에 아직 있는가 */
  private isQuestionStillOpen(question: Json): boolean {
    return asMaps(this.result?.questions).some((raw) => raw.question_id === question.question_id);
  }

  /**
   * 서버가 이미 뺀 질문에 답하려 할 때. 보내지 않고 다음 질문으로 넘어간다. 친 글은 안내 안에 실어
   * 다시 쓸 수 있게 한다(2026-09-16 앱)
   */
  private skipStaleQuestion(question: Json, typed?: string) {
    const text = (typed ?? this.answer).trim();
    this.answer = '';
    const questionId = str(question.question_id);
    if (questionId !== null) this.answeredQuestionIds.add(questionId);
    const last = this.messages[this.messages.length - 1];
    if (typed !== undefined && last !== undefined && last.type === 'user' && last.text === text) this.messages.pop();
    this.messages.push(
      assistant(
        text === ''
          ? '앞 질문이 정리돼 넘어갈게요.'
          : `앞 질문이 정리돼 이 답은 보내지 못했어요. 필요하면 다시 붙여 넣어 주세요.\n\n${text}`,
      ),
    );
    const next = this.takeNextQuestion();
    if (next !== null) this.messages.push(questionMessage(next));
    this.notify();
    if (next !== null) {
      this.focusPreviewField(str(next.field_path));
      this.opts.onRefocusAnswer();
    } else {
      this.scheduleGapAudit();
    }
  }

  /** 서버는 응답마다 남은 질문에 새 번호를 매긴다. 이미 띄운 질문도 새 번호로 답해야 받아 준다 */
  private adoptReissuedQuestionIds(questions: Json[]) {
    const adopt = (target: Json | null, key: string, reissuedId: unknown) => {
      if (target === null || questionKey(target) !== key) return;
      const currentId = str(target.question_id);
      if (currentId !== null && this.answeredQuestionIds.has(currentId)) return;
      target.question_id = reissuedId;
    };
    for (const raw of questions) {
      const key = questionKey(raw);
      for (const m of this.messages) adopt(questionOf(m), key, raw.question_id);
      // 아직 띄우지 않은 질문도 새 번호를 받아야 한다. 안 그러면 죽은 번호로 답을 보내지 못했다
      for (const queued of this.questionQueue) adopt(queued, key, raw.question_id);
      adopt(this.pendingQuestion, key, raw.question_id);
    }
  }

  // ── 누락 점검 ──────────────────────────────────────────

  private scheduleGapAudit() {
    if (this.gapAuditScheduled || this.gapAuditStarted || this.result === null) return;
    this.gapAuditScheduled = true;
    window.setTimeout(() => {
      if (this.disposed) return;
      this.gapAuditScheduled = false;
      if (
        this.gapAuditStarted ||
        this.busy ||
        this.pendingNoneAnswers > 0 ||
        this.result === null ||
        this.suggestionQueue.length > 0 ||
        this.pendingQuestion !== null ||
        this.questionQueue.length > 0 ||
        this.hasUnansweredDisplayedQuestion
      ) {
        this.notify();
        return;
      }
      const previous = this.result;
      this.gapAuditStarted = true;
      this.messages.push(assistant('기존 질문이 끝났습니다. 놓친 중요한 보완 항목이 있는지 한 번만 점검합니다.'));
      void this.run(async () => {
        const request: Json = {
          request_id: newId(),
          review_mode: this.opts.generalReview ? 'general' : 'job',
          review_phase: 'gap_audit',
          previous_review_id: previous.review_id,
          expected_input_hash: previous.input_hash,
          ...this.jobFields(previous),
        };
        this.result = await reviewApi.review(this.opts.resumeId, request);
        this.gapAuditFinished = true;
        this.appendReview(this.result, { isFirstReview: false, isGapAudit: true });
        await this.persistSession();
      }, 'answer');
    }, 0);
  }

  private jobFields(previous: Json): Json {
    if (this.opts.generalReview) return {};
    return {
      ...(this.tailoredResumeId !== null ? { tailored_resume_id: this.tailoredResumeId } : {}),
      selected_job_id: this.opts.jobId,
      expected_job_hash: ((previous.job_source as Json | undefined) ?? {}).snapshot_hash,
    };
  }

  // ── 수정안 ────────────────────────────────────────────

  private markAppliedSuggestionMessages(appliedIndices: Set<number>, application: Json) {
    for (const m of this.messages) {
      const item = suggestionOf(m) ?? identityOf(m);
      if (item !== null) item._undo_available = false;
    }
    for (const m of this.messages) {
      const suggestion = suggestionOf(m);
      if (suggestion !== null && appliedIndices.has(suggestion._index as number)) {
        Object.assign(suggestion, {
          _applied: true,
          _undone: false,
          _operation_id: application.operation_id,
          _application_input_hash: application.input_hash,
          _undo_available: true,
        });
      }
      const identity = identityOf(m);
      if (identity !== null) {
        const indices = ints(identity._indices);
        if (indices.length > 0 && indices.every((i) => appliedIndices.has(i))) {
          Object.assign(identity, {
            _applied: true,
            _undone: false,
            _operation_id: application.operation_id,
            _application_input_hash: application.input_hash,
            _undo_available: true,
          });
        }
      }
    }
  }

  skipSuggestion = (indices: number[]) => {
    if (this.busy || indices.length === 0) return;
    for (const m of [...this.messages].reverse()) {
      const suggestion = suggestionOf(m);
      if (
        suggestion !== null &&
        suggestion._applied !== true &&
        suggestion._skipped !== true &&
        indices.includes(suggestion._index as number)
      ) {
        suggestion._skipped = true;
        break;
      }
      const identity = identityOf(m);
      if (identity !== null && identity._applied !== true && identity._skipped !== true) {
        const own = ints(identity._indices);
        if (own.length === indices.length && own.every((i) => indices.includes(i))) {
          identity._skipped = true;
          break;
        }
      }
    }
    const next = this.takeNextSuggestion();
    if (next !== null) {
      this.messages.push(next);
      this.notify();
      this.focusPreviewField(fieldPathOf(next));
      void this.persistSession();
      return;
    }
    if (this.pendingQuestion !== null) {
      const question = this.pendingQuestion;
      this.pendingQuestion = null;
      this.messages.push(questionMessage(question));
      this.notify();
      this.focusPreviewField(str(question.field_path));
      void this.persistSession();
      return;
    }
    this.notify();
    this.scheduleGapAudit();
    void this.persistSession();
  };

  applySuggestion = async (indices: number[]) => {
    if (this.busy || indices.length === 0 || indices.every((i) => this.appliedSuggestionIndices.has(i))) return;
    this.selected = new Set(indices);
    this.applyRequest = null;
    await this.apply();
  };

  private apply = () =>
    this.run(async () => {
      this.setBusyStage(0);
      this.mutationPending = true;
      this.changed = false;
      this.applyRequest ??= {
        request_id: newId(),
        review_id: this.result!.review_id,
        expected_input_hash: this.result!.input_hash,
        selected_indices: [...this.selected].sort((a, b) => a - b),
        ...(this.tailoredResumeId !== null ? { tailored_resume_id: this.tailoredResumeId } : {}),
      };
      const application = await this.mutate(() => reviewApi.apply(this.opts.resumeId, this.applyRequest!));
      this.setBusyStage(1);
      // 서버가 이 첨삭을 저장된 내용에 다시 맞췄다. 다음 답은 적용 뒤 스냅샷을 기준으로 한다
      this.result!.input_hash = application.input_hash;
      this.selected.forEach((i) => this.appliedSuggestionIndices.add(i));
      this.markAppliedSuggestionMessages(this.selected, application);
      this.notify();
      await this.reload();
      this.setBusyStage(2);
      const next = this.takeNextSuggestion();
      if (next !== null) {
        this.messages.push(next);
        this.notify();
        this.focusPreviewField(fieldPathOf(next));
        await this.persistSession();
        return;
      }
      if (this.pendingQuestion !== null) {
        const question = this.pendingQuestion;
        this.pendingQuestion = null;
        this.messages.push(questionMessage(question));
        this.notify();
        this.focusPreviewField(str(question.field_path));
        await this.persistSession();
        return;
      }
      this.scheduleGapAudit();
      await this.persistSession();
    }, 'apply');

  undoSuggestion = async (item: Json) => {
    if (this.busy || item._undo_available !== true) return;
    await this.run(async () => {
      const operationId = str(item._operation_id);
      const applicationInputHash = str(item._application_input_hash);
      if (operationId === null || applicationInputHash === null) return;
      const indices = new Set(Array.isArray(item._indices) ? ints(item._indices) : ints([item._index]));
      this.mutationPending = true;
      this.changed = false;
      const undone = await this.mutate(() =>
        reviewApi.undo(this.opts.resumeId, {
          request_id: newId(),
          application_id: operationId,
          expected_input_hash: applicationInputHash,
          ...(this.tailoredResumeId !== null ? { tailored_resume_id: this.tailoredResumeId } : {}),
        }),
      );
      this.result!.input_hash = undone.input_hash;
      this.applyRequest = null;
      await this.reload();
      indices.forEach((i) => this.appliedSuggestionIndices.delete(i));
      Object.assign(item, { _applied: false, _undone: true, _undo_available: false });
      this.notify();
      await this.persistSession();
    }, 'undo');
  };

  private async mutate(action: () => Promise<Json>): Promise<Json> {
    try {
      return await action();
    } catch (err) {
      if (err instanceof ReviewApiError && err.statusCode < 500) this.mutationPending = false;
      throw err;
    }
  }

  // ── 답변 ─────────────────────────────────────────────

  /**
   * 「없음」 카드. 고칠 사실이 없으니 서버 응답을 기다리지 않고 바로 다음 질문을 띄운다.
   * 기록은 뒤에서 순서대로 보내고, 서버가 다시 매긴 질문 번호는 떠 있는 질문에 옮겨 둔다
   */
  submitNoneAnswer = (question: Json) => {
    if (this.busy || this.result === null) return;
    const questionId = str(question.question_id);
    if (questionId !== null && this.answeredQuestionIds.has(questionId)) return;
    const requirementId = str(question.requirement_id);
    if (questionId !== null) this.answeredQuestionIds.add(questionId);
    this.messages.push(userMessage('없음'));
    this.messages.push(
      assistant(requirementId !== null ? '알겠어요. 이력서에는 넣지 않을게요.' : '알겠어요. 다음 질문으로 넘어갈게요.'),
    );
    if (requirementId !== null) {
      // 근거를 못 찾은 요건만 해당 없음. 일부 근거가 있는 요건은 좁게 물은 질문에만 없다고 한 것이다
      this.requirementRows = this.requirementRows.map((row) =>
        row.id === requirementId && row.status === 'unconfirmed'
          ? requirementRowFromMap({
              ...requirementRowToMap(row),
              status: 'absent',
              source: 'user',
              evidence_paths: [],
              evidence_quotes: [],
            })
          : row,
      );
    }
    const next = this.takeNextQuestion();
    if (next !== null) this.messages.push(questionMessage(next));
    this.notify();
    if (next !== null) this.focusPreviewField(str(next.field_path));
    this.opts.onRefocusAnswer();
    this.pendingNoneAnswers++;
    this.noneAnswerChain = this.noneAnswerChain
      .then(() => this.recordNoneAnswer(question))
      .finally(() => {
        this.pendingNoneAnswers--;
      });
    void this.noneAnswerChain.then(async () => {
      if (this.disposed) return;
      await this.persistSession();
      if (this.pendingNoneAnswers === 0 && !this.hasUnansweredDisplayedQuestion) this.scheduleGapAudit();
      this.notify();
    });
  };

  private async recordNoneAnswer(question: Json) {
    if (this.disposed || this.result === null) return;
    // 앞선 기록 사이에 서버가 이 질문을 뺐으면 기록할 것이 없다
    if (!this.isQuestionStillOpen(question)) return;
    const previous = this.result;
    try {
      const response = await reviewApi.review(this.opts.resumeId, {
        request_id: newId(),
        review_mode: this.opts.generalReview ? 'general' : 'job',
        ...this.jobFields(previous),
        previous_review_id: previous.review_id,
        expected_input_hash: previous.input_hash,
        answers: [
          { question_id: question.question_id, field_path: question.field_path, question: question.question, answer: '없음' },
        ],
      });
      if (this.disposed) return;
      this.result = response;
      const rows = requirementRowsFrom(response.requirement_map);
      if (rows.length > 0) this.requirementRows = rows;
      const checks = starChecksByPath(response.star_checks);
      if (Object.keys(checks).length > 0) this.starChecks = checks;
      this.syncQuestionsWithServer(asMaps(response.questions), true);
      if (!this.hasUnansweredDisplayedQuestion && this.suggestionQueue.length === 0) {
        const next = this.takeNextQuestion();
        if (next !== null) this.messages.push(questionMessage(next));
      }
      this.notify();
    } catch (err) {
      // 서버가 이미 뺀 질문이면(422) 기록할 것이 없으니 넘어간다. 나머지 실패만 알린다
      if (!(err instanceof ReviewApiError && err.statusCode === 422)) {
        this.error = `없음 답변을 저장하지 못했습니다. 다시 시도해 주세요. (${err instanceof Error ? err.message : String(err)})`;
        this.notify();
      }
    }
  }

  submitAnswer = async (question: Json) => {
    const answer = this.answer.trim();
    if (answer === '' || this.busy || this.result === null) return;
    if (this.pendingNoneAnswers > 0) {
      // 앞서 누른 「없음」 기록이 서버에 도착해야 이 답변이 최신 첨삭 결과를 이어받는다
      this.busy = true;
      this.notify();
      await this.noneAnswerChain;
      if (this.disposed) return;
      this.busy = false;
    }
    // 보내기 전에 「이 질문은 죽었다」고 미리 판단하지 않는다. 일단 보내고, 서버가 거절할 때만(422) 넘어간다
    const previous = this.result!;
    this.answer = '';
    const questionId = str(question.question_id);
    if (questionId !== null) this.answeredQuestionIds.add(questionId);
    this.messages.push(userMessage(answer));
    this.notify();
    await this.run(async () => {
      let response: Json;
      try {
        response = await reviewApi.review(this.opts.resumeId, {
          request_id: newId(),
          review_mode: this.opts.generalReview ? 'general' : 'job',
          ...this.jobFields(previous),
          previous_review_id: previous.review_id,
          expected_input_hash: previous.input_hash,
          answers: [
            { question_id: question.question_id, field_path: question.field_path, question: question.question, answer },
          ],
        });
      } catch (err) {
        if (!(err instanceof ReviewApiError && err.statusCode === 422)) throw err;
        // 서버가 이미 정리한 질문이다. 답은 남겨 보여 주고 다음 질문으로 넘어간다
        this.skipStaleQuestion(question, answer);
        return;
      }
      this.result = response;
      // 적용 뒤 서버가 이전 첨삭을 새 스냅샷에 맞췄다. 이 첨삭이 최신 이력서를 가진다
      this.appliedSuggestionIndices.clear();
      this.applyRequest = null;
      this.appendReview(response, {
        isFirstReview: false,
        answeredFieldPath: str(question.field_path),
        answeredQuestionId: str(question.question_id),
        answeredRequirementId: str(question.requirement_id),
      });
      await this.persistSession();
    }, 'answer');
    // 다음 질문이 바로 뜬다. 클릭 없이 이어서 치게 입력칸에 포커스를 돌려준다
    this.opts.onRefocusAnswer();
  };

  get canRefocus(): boolean {
    return !this.busy && this.error === null && this.hasUnansweredDisplayedQuestion;
  }

  // ── 미리보기 ──────────────────────────────────────────

  private focusPreviewField(fieldPath: string | null) {
    if (fieldPath === null || fieldPath === this.focusedFieldPath) return;
    this.focusedFieldPath = fieldPath;
    this.opts.onFocusPreview(previewTargetForFieldPath(fieldPath));
  }

  focusRequirement = (row: RequirementRow) => {
    const path = row.evidencePaths[0] ?? null;
    this.requirementFocusPath = path;
    this.notify();
    if (path !== null) {
      this.focusedFieldPath = null;
      this.focusPreviewField(path);
    }
  };

  // ── 완료 ─────────────────────────────────────────────

  /**
   * 위쪽 「첨삭 완료」와 완료 안내의 초록 「첨삭 완료」가 함께 쓴다. 둘 다 저장을 기다린 뒤 편집기로 옮긴다.
   * 확인 창은 버리게 될 질문이나 수정안이 남아 있을 때만 띄운다
   */
  completeReview = async (alwaysConfirm = true) => {
    if (this.busy || this.result === null) return;
    const shouldComplete = !alwaysConfirm && !this.hasActiveSuggestion ? true : await this.opts.confirmComplete();
    if (!shouldComplete || this.disposed) return;
    this.manuallyCompleted = true;
    this.questionQueue = [];
    this.pendingQuestion = null;
    this.suggestionQueue = [];
    for (const m of this.messages) {
      const questionId = str(questionOf(m)?.question_id);
      if (questionId !== null) this.answeredQuestionIds.add(questionId);
      const suggestion = suggestionOf(m);
      if (suggestion !== null) suggestion._skipped = true;
      const identity = identityOf(m);
      if (identity !== null) identity._skipped = true;
    }
    this.notify();
    await this.run(async () => {
      this.mutationPending = true;
      try {
        await this.persistSession();
        await this.sessionSaveChain;
        let workspaceResumeId: string | undefined;
        if (!this.opts.generalReview && this.tailoredResumeId !== null) {
          workspaceResumeId = await reviewApi.promote(this.opts.resumeId, this.tailoredResumeId);
        }
        this.opts.onClose(workspaceResumeId);
      } finally {
        this.mutationPending = false;
      }
    }, 'apply');
  };

  // ── 화면이 쓰는 파생 값 ─────────────────────────────────

  view(): ReviewView {
    let activeQuestion: Json | null = null;
    for (const m of [...this.messages].reverse()) {
      const q = questionOf(m);
      const id = q === null ? null : str(q.question_id);
      if (q !== null && (id === null || !this.answeredQuestionIds.has(id))) {
        activeQuestion = q;
        break;
      }
    }
    let activeSuggestionFieldPath: string | null = null;
    let activeSuggestionStage: number | null = null;
    for (const m of [...this.messages].reverse()) {
      const suggestion = suggestionOf(m);
      if (suggestion !== null && suggestion._applied !== true && suggestion._skipped !== true) {
        activeSuggestionFieldPath = str(suggestion.field_path);
        activeSuggestionStage = typeof suggestion.stage === 'number' ? suggestion.stage : null;
        break;
      }
      const identity = identityOf(m);
      if (identity !== null && identity._applied !== true && identity._skipped !== true) {
        activeSuggestionFieldPath = str(identity.field_path);
        activeSuggestionStage = identity._kind === 'polish' ? 1 : 4;
        break;
      }
    }
    const highlightedFieldPath =
      this.requirementFocusPath ?? (activeQuestion === null ? null : str(activeQuestion.field_path)) ?? activeSuggestionFieldPath;
    const remainingQuestionCount =
      this.questionQueue.length + (this.pendingQuestion === null ? 0 : 1) + (activeQuestion === null ? 0 : 1);
    const questionsDone =
      this.result !== null &&
      !this.busy &&
      this.error === null &&
      activeQuestion === null &&
      this.pendingQuestion === null &&
      this.questionQueue.length === 0 &&
      this.pendingNoneAnswers === 0;
    const reviewCompleted =
      questionsDone &&
      !this.awaitingGapAudit &&
      !this.gapAuditScheduled &&
      (!this.gapAuditStarted || this.gapAuditFinished);
    const activeStage =
      (activeQuestion !== null && typeof activeQuestion.stage === 'number' ? activeQuestion.stage : null) ??
      activeSuggestionStage;
    const currentStage = reviewCompleted
      ? REVIEW_STAGE_LABELS.length + 1
      : activeStage !== null && activeStage > 0
        ? activeStage
        : 0;
    return { activeQuestion, highlightedFieldPath, remainingQuestionCount, reviewCompleted, currentStage };
  }

  /** 그린 뒤에 부른다 — 원본은 build 에서 질문을 다 마쳤으면 누락 점검을 예약했다 */
  afterRender() {
    const questionsDone =
      this.result !== null &&
      !this.busy &&
      this.error === null &&
      this.view().activeQuestion === null &&
      this.pendingQuestion === null &&
      this.questionQueue.length === 0 &&
      this.pendingNoneAnswers === 0;
    if (questionsDone && this.awaitingGapAudit) this.scheduleGapAudit();
  }
}

function newId(): string {
  const random = new Uint32Array(1);
  crypto.getRandomValues(random);
  return `${Date.now()}${Math.floor(performance.now() * 1000) % 1000}_${random[0] & 0x3fffffff}`;
}

function fieldPathOf(message: ChatMessage): string | null {
  return str(suggestionOf(message)?.field_path) ?? str(identityOf(message)?.field_path);
}

/** 재첨삭은 질문마다 새 question_id 를 준다. 같은 것을 두 번 묻지 않게 대상과 의도로 거른다 */
function questionKey(question: Json): string {
  // 공고 요건 질문은 요건마다 하나다
  const requirementId = str(question.requirement_id);
  if (requirementId !== null && requirementId !== '') return `requirement|${requirementId}`;
  return `${String(question.field_path)}|${String(question.topic)}`;
}

function isIdentityPlaceholderSuggestion(sentence: Json): boolean {
  const original = str(sentence.original_quote) ?? '';
  return original.includes('[회사명]') || original.includes('[직무명]');
}

/** 자기소개서는 문항별 카드로 보이므로 body · subtitle 어느 칸을 물어도 그 문항 카드에 맞춘다 */
export function previewTargetForFieldPath(fieldPath: string): string {
  const parts = fieldPath.split('.');
  if (parts.length >= 2 && parts[0] === 'selfIntroduction') return `${parts[0]}.${parts[1]}`;
  return fieldPath.split(/[.[]/)[0];
}

/** 서버가 답을 옮겨 둔 칸. 응답의 confirmed_answers 에서 이 질문의 답을 찾는다 */
function resolvedAnswerFieldPath(review: Json, questionId: string | null, fallback: string | null): string | null {
  if (questionId === null) return fallback;
  for (const raw of asMaps(review.confirmed_answers)) {
    if (raw.question_id === questionId) return str(raw.field_path) ?? fallback;
  }
  return fallback;
}

function formatInitialSummary(summary: string): string {
  const sentences = summary
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s !== '')
    .slice(0, 3);
  if (sentences.length === 0) return '검토 요약\n\n• 이력서와 공고를 비교했습니다.';
  return `검토 요약\n\n${sentences.map((s) => `• ${s}`).join('\n\n')}`;
}
