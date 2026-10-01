import { useEffect, useRef, useState, type FormEvent, type MouseEvent, type ReactNode } from 'react';

import { http } from '../../../data/http';
import type { Resume } from '../../../domain/types';
import { Icon } from '../../../ui/Icon';
import { RobotHead } from '../../../ui/RobotHead';
import { JobPostingDialog } from '../../jobs/JobPostingDialog';
import { jobPostingPath } from '../../jobs/JobPostingScreen';
import { deadlineDate, requestJobs, type JobPick } from '../JobRecommendationRun';
import {
  emptyScopeReason,
  nextSeenJobIds,
  nextShownJobIds,
  recommendBusyLabels,
  recommendSummary,
  sameChatConditions,
  shouldSendResume,
} from './chatRefs';
import { StreamFailed, StreamUnavailable, streamChat } from './chatStream';
import { parseChatText } from './chatText';

/**
 * 코치에게 묻기 — ai_job_coach_panel.dart 의 _chatMode(_Header + _ChatView).
 *
 * 말로 공고를 찾고 채용을 묻는다. 조건 해석 · 검색 · 집계는 공고 서버가 한다
 * (`/api/jobs/chat` → job_matching_bot). 서버는 대화를 저장하지 않으므로 직전 조건과
 * 보여 준 공고를 화면이 들고 있다가 다음 말에 실어 보낸다.
 *
 * 이 화면은 코치 패널을 통째로 차지한다. 뒤로 가도 대화는 남는다 — 편집 화면이 접어 둘 뿐
 * 지우지 않는다.
 *
 * 공고 맞춤 지원 1단계에서도 같은 대화로 공고를 찾는다. 찾은 공고 카드에 「고르기」를 달려면 `onPickJob` 을 준다
 * (편집기는 그 공고로 공고 맞춤 지원을 열고, 공고 맞춤 지원은 그 자리에서 공고를 불러온다). 라우터는 모른다.
 */

/** 서버가 돌려준 공고 한 건 — JobChatJob */
interface ChatJob {
  jobId: string;
  company: string;
  title: string;
  region: string;
  career: string;
  employmentType: string;
  deadline: string | null;
  techStack: string[];
}

interface ChatMessage {
  id: string;
  role: 'user' | 'coach';
  text: string;
  mode?: string;
  jobs: ChatJob[];
  suggestions: string[];
  /** 이력서를 읽고 고른 공고. 적합도와 근거가 붙는다 */
  recommendations: JobPick[];
  /** 검색 답이면 같은 조건으로 이어 볼 거리(「더 보기」) */
  more?: MoreQuery;
  /** 같은 조건으로 더 보여 줄 공고가 남았나 */
  hasMore?: boolean;
}

/** 검색 답을 이어 볼 거리. 서버가 준 그대로 되돌려 보낸다 — 서버는 대화를 저장하지 않는다 */
interface MoreQuery {
  filters: Record<string, unknown>;
  /** 뜻으로 찾을 때 쓴 문장. 「돈 다루는 일」은 조건에 남는 것이 없어 이것으로만 이어 찾는다 */
  requirementQuery: string;
  /** 앞에 세운 직무. 이어 본 공고도 같은 순서로 */
  preferRoles: string[];
}

interface ChatResponse {
  mode?: string;
  resume_scope?: string;
  reply?: string;
  filters?: Record<string, unknown>;
  jobs?: Record<string, unknown>[];
  suggestions?: string[];
  requirement_query?: string;
  prefer_roles?: string[];
  has_more?: boolean;
}

const INTRO_SUGGESTIONS = ['서울 백엔드 신입', '백엔드 신입은 뭘 준비해야 해?', '요즘 많이 요구하는 기술이 뭐야?'];
const ASK_ABOUT_SUGGESTIONS = ['자격요건이 뭐야?', '신입도 지원할 수 있어?', '어떤 일을 하는 자리야?'];
/** 공고 검색만이 아니라 준비 · 자소서 같은 질문도 온다. 어느 쪽이든 맞는 말로 */
const CHAT_BUSY = ['질문을 살펴보는 중…', '필요한 정보를 찾는 중…', '답을 정리하는 중…'];
const ASK_ABOUT_BUSY = ['공고 내용을 살펴보는 중…', '답을 정리하는 중…'];
/** 기다림 문구가 넘어가는 간격. 추천이 11초쯤 걸려 세 단계가 고르게 지나간다 */
const BUSY_STEP_MS = 3200;

let seq = 0;
const nextId = () => `ask-${Date.now()}-${seq++}`;

function coach(text: string, extra: Partial<ChatMessage> = {}): ChatMessage {
  return { id: nextId(), role: 'coach', text, jobs: [], suggestions: [], recommendations: [], ...extra };
}

function toChatJob(raw: Record<string, unknown>): ChatJob {
  return {
    jobId: String(raw.job_id ?? ''),
    company: String(raw.company ?? ''),
    title: String(raw.title ?? ''),
    region: String(raw.region ?? ''),
    career: String(raw.career ?? ''),
    employmentType: String(raw.employment_type ?? ''),
    deadline: typeof raw.deadline === 'string' && raw.deadline !== '' ? raw.deadline : null,
    techStack: Array.isArray(raw.tech_stack) ? raw.tech_stack.map(String) : [],
  };
}

function moreQueryOf(data: ChatResponse): MoreQuery {
  return {
    filters: data.filters ?? {},
    requirementQuery: String(data.requirement_query ?? ''),
    preferRoles: Array.isArray(data.prefer_roles) ? data.prefer_roles.map(String) : [],
  };
}

function errorDetail(err: unknown): string | null {
  if (err instanceof StreamFailed) return err.message;
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof detail === 'string' && detail !== '' ? detail : null;
}

export function CoachAsk({
  resume,
  hidden,
  onBack,
  onOpenDetail,
  onPickJob,
  pickLabel = '이 공고로 자소서 쓰기',
}: {
  resume: Resume;
  /** 코치 첫 화면을 보는 동안 접어 둔다. 대화는 그대로 남는다 */
  hidden: boolean;
  /** 없으면 뒤로 단추를 두지 않는다(공고 맞춤 지원처럼 돌아갈 코치 첫 화면이 없는 곳) */
  onBack?(): void;
  /** 추천 근거 전체를 보러 코치 첫 화면의 추천 목록으로 넘어간다. 없으면 「근거 전체 보기」를 두지 않는다 */
  onOpenDetail?(): void;
  /** 찾은 공고로 공고 맞춤 지원을 연다. 없으면 카드에 고르기 단추를 두지 않는다 */
  onPickJob?(jobId: string): void;
  pickLabel?: string;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => [
    coach(
      '채용에 대해 물어보세요. 공고를 찾아드리고, 궁금한 것에도 답해드려요.\n답은 지금 열려 있는 공고를 직접 세어 드립니다.',
      { suggestions: INTRO_SUGGESTIONS },
    ),
  ]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [busyLabels, setBusyLabels] = useState<string[]>([]);
  /** 서버가 쓰고 있는 답. 다 쓰면 최종 답으로 바꿔 끼운다 */
  const [streaming, setStreaming] = useState<string | null>(null);
  /** 공고 하나를 놓고 묻는 중이면 그 공고. 이 동안의 말은 전부 이 공고에 대한 물음으로 간다 */
  const [askingAbout, setAskingAbout] = useState<ChatJob | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  /** 「더 보기」를 불러오는 답과, 불러오지 못한 답 */
  const [moreLoading, setMoreLoading] = useState<string | null>(null);
  const [moreFailed, setMoreFailed] = useState<string | null>(null);
  /**
   * 서버에 되돌려 보낼 대화 기억. 화면에 그리지 않으므로 상태가 아니라 ref 로 든다.
   * - filters: 직전 검색 조건. "그중 판교만"이 통한다
   * - shown: 번호가 가리킬 목록("2번")
   * - answered: 방금 이야기한 공고("두 공고")
   * - seen: 같은 조건으로 본 공고 전부("이거 말고")
   * - query: 직전 검색 답의 뜻 문장 · 앞에 세운 직무. "더 보여줘"가 같은 것을 이어 찾는다
   */
  const memory = useRef<{
    filters: Record<string, unknown> | null;
    shown: string[];
    answered: string[];
    seen: string[];
    query: Omit<MoreQuery, 'filters'>;
  }>({
    filters: null,
    shown: [],
    answered: [],
    seen: [],
    query: { requirementQuery: '', preferRoles: [] },
  });
  const listRef = useRef<HTMLDivElement>(null);

  // 새 말이 붙거나 기다리기 시작하면 아래로 따라간다
  useEffect(() => {
    const list = listRef.current;
    if (list === null || hidden) return;
    list.scrollTo?.({ top: list.scrollHeight, behavior: 'smooth' });
  }, [messages.length, busy, hidden, streaming]);

  // 「더 보기」로 붙은 공고는 말이 늘지 않아 위가 따라가지 않는다. 새로 붙은 첫 카드를 맨 위로 올린다
  const [revealJob, setRevealJob] = useState<string | null>(null);
  useEffect(() => {
    if (revealJob === null || hidden) return;
    const cards = listRef.current?.querySelectorAll<HTMLElement>('[data-job-id]') ?? [];
    const card = [...cards].find((c) => c.dataset.jobId === revealJob);
    card?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, [revealJob, hidden]);

  const push = (message: ChatMessage) => setMessages((m) => [...m, message]);

  /** 이력서로 골라 달라는 말이었다. 말만 하고 끝내지 않고 그 자리에서 추천을 돌린다 */
  const recommendInChat = async (scope: string) => {
    const missing = emptyScopeReason(scope, resume.content);
    if (missing !== null) {
      push(coach(missing));
      return;
    }
    setBusy(true);
    setBusyLabels(recommendBusyLabels(scope));
    try {
      const result = await requestJobs(resume.id, scope);
      push(
        coach(recommendSummary(result.jobs.length, scope), {
          mode: '추천',
          recommendations: result.jobs.slice(0, 3),
        }),
      );
    } catch (err) {
      push(coach(errorDetail(err) ?? '공고를 고르지 못했습니다. 잠시 후 다시 물어봐 주세요.'));
    } finally {
      setBusy(false);
      setBusyLabels([]);
    }
  };

  const send = async (preset?: string) => {
    const text = (preset ?? draft).trim();
    if (text === '' || busy) return;
    const about = askingAbout;
    const mem = memory.current;
    push({ id: nextId(), role: 'user', text, jobs: [], suggestions: [], recommendations: [] });
    setDraft('');
    setBusy(true);
    setBusyLabels(about !== null ? ASK_ABOUT_BUSY : CHAT_BUSY);

    let recommendScope: string | null = null;
    const body = {
      message: text,
      filters: mem.filters,
      jobId: about?.jobId ?? null,
      // 이력서 평문은 서버가 DB 에서 만든다. 화면은 어느 이력서인지만 알린다
      resumeId: shouldSendResume(about !== null, mem.shown.length > 0) ? resume.id : null,
      lastJobIds: mem.shown,
      lastAnswerJobIds: mem.answered,
      seenJobIds: mem.seen,
      requirementQuery: mem.query.requirementQuery,
      preferRoles: mem.query.preferRoles,
    };
    try {
      let data: ChatResponse;
      try {
        // 서버가 실제로 하는 일을 띄우고, 답을 쓰는 동안의 글을 그대로 보인다
        data = await streamChat<ChatResponse>(body, {
          onProgress: (label) => setBusyLabels([label]),
          onText: (delta) => setStreaming((t) => (t ?? '') + delta),
        });
      } catch (err) {
        if (!(err instanceof StreamUnavailable)) throw err;
        setStreaming(null);
        ({ data } = await http.post<ChatResponse>('/jobs/chat', body));
      }
      const mode = String(data.mode ?? '검색');
      const jobs = (data.jobs ?? []).map(toChatJob);
      const ids = jobs.map((j) => j.jobId);
      const filters = data.filters ?? null;
      mem.seen = nextSeenJobIds(mode, ids, mem.seen, sameChatConditions(mem.filters, filters));
      mem.filters = filters;
      mem.shown = nextShownJobIds(mode, ids, mem.shown);
      // 답에 공고가 들어 있으면 방금 이야기한 대상이 곧 그 공고들이다
      if (ids.length > 0) mem.answered = ids;
      const more = mode === '검색' ? moreQueryOf(data) : undefined;
      if (more !== undefined) mem.query = { requirementQuery: more.requirementQuery, preferRoles: more.preferRoles };
      push(
        coach(String(data.reply ?? ''), {
          mode,
          jobs,
          suggestions: data.suggestions ?? [],
          ...(more !== undefined && jobs.length > 0 ? { more, hasMore: data.has_more === true } : {}),
        }),
      );
      if (mode === '추천') recommendScope = String(data.resume_scope ?? '전체');
    } catch (err) {
      push(coach(errorDetail(err) ?? '답을 찾지 못했습니다. 잠시 후 다시 물어봐 주세요.'));
    } finally {
      setBusy(false);
      setBusyLabels([]);
      setStreaming(null);
    }
    if (recommendScope !== null) await recommendInChat(recommendScope);
  };

  /** 「더 보기」 — 같은 조건으로 다음 공고를 그 답의 카드 밑에 잇는다. 말을 해석하지 않아 곧 온다 */
  const loadMore = async (message: ChatMessage) => {
    if (message.more === undefined || moreLoading !== null) return;
    const mem = memory.current;
    const own = message.jobs.map((j) => j.jobId);
    // 지금 대화가 이 답의 조건 그대로면 "더 보여줘"로 본 공고까지 뺀다
    const current = sameChatConditions(mem.filters, message.more.filters);
    const seen = current ? [...mem.seen, ...own.filter((id) => !mem.seen.includes(id))] : own;
    setMoreLoading(message.id);
    setMoreFailed(null);
    try {
      const { data } = await http.post<ChatResponse>('/jobs/chat/more', { ...message.more, seenJobIds: seen });
      const jobs = (data.jobs ?? []).map(toChatJob).filter((j) => !own.includes(j.jobId));
      const ids = jobs.map((j) => j.jobId);
      if (current) {
        mem.seen = [...seen, ...ids];
        // "7번"도 가리킬 수 있게 번호 목록을 늘린다(서버는 20개까지 받는다)
        mem.shown = [...own, ...ids].slice(0, 20);
      }
      setMessages((ms) =>
        ms.map((m) =>
          m.id === message.id ? { ...m, jobs: [...m.jobs, ...jobs], hasMore: data.has_more === true && jobs.length > 0 } : m,
        ),
      );
      if (ids.length > 0) setRevealJob(ids[0]);
    } catch {
      setMoreFailed(message.id);
    } finally {
      setMoreLoading(null);
    }
  };
  // 「더 보기」는 마지막 검색 답에만. 지나간 답은 그때 조건이라 지금 본 공고와 섞인다
  const lastSearchId = [...messages].reverse().find((m) => m.more !== undefined)?.id;

  const askAbout = (job: ChatJob) => {
    setAskingAbout(job);
    push(
      coach(`"${job.title}" 공고에 대해 물어보세요. 공고에 적힌 것만 근거로 답해드려요.`, {
        mode: '공고',
        suggestions: ASK_ABOUT_SUGGESTIONS,
      }),
    );
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void send();
  };

  const name = resume.content.basicInfo.name.trim();

  return (
    <section className="coach-ask" hidden={hidden} aria-label="코치에게 묻기">
      <header className="coach-ask__head">
        {onBack !== undefined && (
          <button type="button" className="coach-ask__back" onClick={onBack} aria-label="코치 화면으로" title="코치 화면으로">
            <Icon name="arrow_back" size={20} />
          </button>
        )}
        <RobotHead size={40} inverted />
        <span className="coach-ask__who">
          <strong>커리어 코치</strong>
          <span>{name === '' ? '나의 취업 코치' : `${name} 님의 코치`}</span>
        </span>
      </header>

      <div className="coach-ask__list" ref={listRef}>
        {messages.map((message, index) => (
          <Bubble
            key={message.id}
            message={message}
            // 제안은 마지막 답에서만. 지나간 답의 제안은 그때가 아니라 지금 조건에 붙는다
            onSuggestion={index === messages.length - 1 && !busy ? (s) => void send(s) : undefined}
            onAskAbout={busy ? undefined : askAbout}
            onOpenDetail={busy ? undefined : onOpenDetail}
            onOpenPosting={setViewing}
            pick={onPickJob === undefined ? undefined : { onPick: onPickJob, label: pickLabel }}
            more={
              message.id === lastSearchId && message.hasMore === true
                ? {
                    onMore: busy ? undefined : () => void loadMore(message),
                    loading: moreLoading === message.id,
                    failed: moreFailed === message.id,
                  }
                : undefined
            }
          />
        ))}
        {busy && streaming !== null && <Bubble message={coach(streaming)} onOpenPosting={setViewing} />}
        {busy && streaming === null && <Typing labels={busyLabels.length === 0 ? ['답을 찾는 중…'] : busyLabels} />}
      </div>

      {/* 무엇에 대해 묻는 중인지. 이게 없으면 짧은 말이 어디로 가는지 알 수 없다 */}
      {askingAbout !== null && (
        <div className="coach-ask__about">
          <Icon name="help" size={14} />
          <span className="coach-ask__about-text">"{askingAbout.title}"에 대해 묻는 중</span>
          <button type="button" className="icon-btn" onClick={() => setAskingAbout(null)} aria-label="그만 묻기" title="그만 묻기">
            <Icon name="close" size={14} />
          </button>
        </div>
      )}

      <form className="coach-ask__form" onSubmit={submit}>
        <input
          className="input"
          value={draft}
          maxLength={500}
          placeholder={askingAbout === null ? '공고를 찾거나, 채용에 대해 물어보세요' : '이 공고에 대해 물어보세요'}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="icon-btn" disabled={busy || draft.trim() === ''} aria-label="보내기" title="보내기">
          <Icon name="send" size={18} />
        </button>
      </form>

      {viewing !== null && <JobPostingDialog jobId={viewing} onClose={() => setViewing(null)} />}
    </section>
  );
}

function Bubble({
  message,
  onSuggestion,
  onAskAbout,
  onOpenDetail,
  onOpenPosting,
  pick,
  more,
}: {
  message: ChatMessage;
  onSuggestion?: (text: string) => void;
  onAskAbout?: (job: ChatJob) => void;
  onOpenDetail?: () => void;
  onOpenPosting(jobId: string): void;
  pick?: PickAction;
  /** 「더 보기」. 없으면 단추를 두지 않는다 */
  more?: { onMore?: () => void; loading: boolean; failed: boolean };
}) {
  const bubble = (
    <div className={`coach-ask__bubble coach-ask__bubble--${message.role}`}>
      <ChatText text={message.text} />

      {message.recommendations.map((job) => (
        <RecommendCard key={job.jobId} job={job} onOpenPosting={onOpenPosting} pick={pick} />
      ))}
      {message.recommendations.length > 0 && onOpenDetail !== undefined && (
        <button type="button" className="coach-ask__more" onClick={onOpenDetail}>
          근거 전체 보기 →
        </button>
      )}

      {/* 질문에 답한 경우 목록은 찾아 준 결과가 아니라 답의 근거다. 그렇게 적어 둔다 */}
      {message.mode === '질문' && message.jobs.length > 0 && (
        <span className="coach-ask__note">이 숫자를 센 공고들이에요</span>
      )}
      {message.jobs.map((job) => (
        <JobCard
          key={job.jobId}
          job={job}
          onAsk={onAskAbout === undefined ? undefined : () => onAskAbout(job)}
          onOpenPosting={onOpenPosting}
          pick={pick}
        />
      ))}
      {more !== undefined && (
        <>
          {more.failed && <span className="coach-ask__note">공고를 더 불러오지 못했어요. 다시 눌러 주세요.</span>}
          <button type="button" className="coach-ask__load-more" onClick={more.onMore} disabled={more.onMore === undefined || more.loading}>
            {more.loading ? '불러오는 중…' : '공고 더 보기'}
          </button>
        </>
      )}

      {onSuggestion !== undefined &&
        message.suggestions.map((s) => (
          <button key={s} type="button" className="coach-ask__suggest" onClick={() => onSuggestion(s)}>
            {s}
          </button>
        ))}
    </div>
  );

  if (message.role === 'user') return <div className="coach-ask__row coach-ask__row--user">{bubble}</div>;
  // 코치의 답 옆에는 머리를 둔다. 누가 말하는지 보이게
  return (
    <div className="coach-ask__row">
      <span className="coach-ask__avatar">
        <RobotHead size={36} inverted />
      </span>
      {bubble}
    </div>
  );
}

/** 굵게와 항목 줄만 읽어 그린다 */
function ChatText({ text }: { text: string }) {
  return (
    <div className="coach-ask__text">
      {parseChatText(text).map((block, i) => (
        <p key={i} className={block.bullet ? 'coach-ask__bullet' : undefined}>
          {block.spans.map((span, j) => (span.bold ? <strong key={j}>{span.text}</strong> : <span key={j}>{span.text}</span>))}
        </p>
      ))}
    </div>
  );
}

/** 공고 원문은 채용 사이트로 보내지 않고 화면 위 창으로 연다. Ctrl · ⌘ 로 누르면 새 탭 */
function PostingLink({ jobId, onOpen, className, children }: { jobId: string; onOpen(jobId: string): void; className: string; children: ReactNode }) {
  const open = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0) return;
    e.preventDefault();
    onOpen(jobId);
  };
  return (
    <a className={className} href={jobPostingPath(jobId)} target="_blank" rel="noreferrer" onClick={open}>
      {children}
    </a>
  );
}

/** 찾은 공고를 공고 맞춤 지원으로 넘기는 단추 */
interface PickAction {
  onPick(jobId: string): void;
  label: string;
}

function PickButton({ jobId, pick }: { jobId: string; pick?: PickAction }) {
  if (pick === undefined || jobId === '') return null;
  return (
    <button type="button" className="coach-ask__card-pick" onClick={() => pick.onPick(jobId)}>
      <Icon name="edit_note" size={14} />
      {pick.label}
    </button>
  );
}

function JobCard({
  job,
  onAsk,
  onOpenPosting,
  pick,
}: {
  job: ChatJob;
  onAsk?: () => void;
  onOpenPosting(jobId: string): void;
  pick?: PickAction;
}) {
  const hasLink = job.jobId !== '';
  return (
    <div className="coach-ask__card" data-job-id={job.jobId}>
      {hasLink ? (
        <PostingLink jobId={job.jobId} onOpen={onOpenPosting} className="coach-ask__card-title">
          {job.title}
        </PostingLink>
      ) : (
        <strong className="coach-ask__card-title">{job.title}</strong>
      )}
      <span className="coach-ask__card-meta">{[job.company, job.region, job.career].filter((v) => v !== '').join(' · ')}</span>
      {job.deadline !== null && <span className="coach-ask__card-due">마감 {deadlineDate(job.deadline)}</span>}
      {job.techStack.length > 0 && <span className="coach-ask__card-skills">{job.techStack.slice(0, 5).join(' · ')}</span>}
      <span className="coach-ask__card-foot">
        {hasLink && (
          <PostingLink jobId={job.jobId} onOpen={onOpenPosting} className="coach-ask__card-open">
            공고 보기 →
          </PostingLink>
        )}
        <span className="spacer" />
        {onAsk !== undefined && (
          <button type="button" className="coach-ask__card-ask" onClick={onAsk}>
            이 공고 물어보기
          </button>
        )}
      </span>
      <PickButton jobId={job.jobId} pick={pick} />
    </div>
  );
}

/** 이력서로 고른 공고. 왜 맞는지 한 줄만 — 근거 전체는 코치 첫 화면에 있다 */
function RecommendCard({ job, onOpenPosting, pick }: { job: JobPick; onOpenPosting(jobId: string): void; pick?: PickAction }) {
  const reason = job.reasons[0]?.claim ?? '';
  const meta = [job.conditions.region, job.conditions.career].filter((v) => v !== undefined && v !== '').join(' · ');
  return (
    <div className="coach-ask__card">
      <span className="coach-ask__card-company">{job.company}</span>
      {job.jobId !== '' ? (
        <PostingLink jobId={job.jobId} onOpen={onOpenPosting} className="coach-ask__card-title">
          {job.title}
        </PostingLink>
      ) : (
        <strong className="coach-ask__card-title">{job.title}</strong>
      )}
      {meta !== '' && <span className="coach-ask__card-meta">{meta}</span>}
      {reason !== '' && <span className="coach-ask__card-reason">{reason}</span>}
      {job.jobId !== '' && (
        <PostingLink jobId={job.jobId} onOpen={onOpenPosting} className="coach-ask__card-open">
          공고 보기 →
        </PostingLink>
      )}
      <PickButton jobId={job.jobId} pick={pick} />
    </div>
  );
}

/** 코치가 답을 쓰는 중. 답이 올 자리에서 기다리고, 무엇을 하는 중인지 차례로 밝힌다 */
function Typing({ labels }: { labels: string[] }) {
  const [index, setIndex] = useState(0);
  const key = labels.join('|');

  useEffect(() => {
    setIndex(0);
    if (labels.length <= 1) return;
    // 마지막 말에서 멈춘다. 끝났다고 먼저 말하지 않는다
    const timer = window.setInterval(() => setIndex((i) => Math.min(i + 1, labels.length - 1)), BUSY_STEP_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <div className="coach-ask__row" role="status" aria-label="커리어 코치 응답 대기 중">
      <span className="coach-ask__avatar">
        <RobotHead size={36} inverted />
      </span>
      <div className="coach-ask__bubble coach-ask__bubble--coach coach-ask__typing">
        <span className="coach-ask__dots" aria-hidden="true">
          <i />
          <i />
          <i />
        </span>
        <span>{labels[Math.min(index, labels.length - 1)]}</span>
      </div>
    </div>
  );
}
