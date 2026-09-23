import { useEffect, useRef, useState, type FormEvent } from 'react';

import type { Resume, ResumeReviewSuggestion } from '../../domain/types';
import { applyBootstrap } from '../../data/repository';
import { http } from '../../data/http';
import { Icon } from '../../ui/Icon';
import { RobotHead } from '../../ui/RobotHead';
import { ReviewProgress } from './JobRecommendationLoading';

/**
 * AI 코치 대화 — features/resume/ai_coach/presentation/job_resume_review_dialog.dart
 *
 * 첨삭도 질문도 대화로 이뤄진다. 코치가 이력서에서 근거가 부족한 곳을 묻고,
 * 사람이 답하면 수정안을 제안한다. 실제 앱은 여기서 모델을 부르고, 프로토타입은
 * 이력서를 규칙으로 읽어 같은 모양의 대화를 만든다.
 */
interface Message {
  id: string;
  role: 'user' | 'coach';
  text: string;
  streaming?: boolean;
  suggestion?: ResumeReviewSuggestion;
}

interface CoachResponse {
  text: string;
  suggestion?: ResumeReviewSuggestion;
}


const REVIEW_SUGGESTIONS = [
  '이 이력서의 약한 곳은 어디야?',
  '프로젝트 설명을 더 낫게 고쳐 줘',
  '데이터 분석가 공고에 맞는지 봐 줘',
];

const CAREER_SUGGESTIONS = [
  '서울 백엔드 신입',
  '백엔드 신입은 뭘 준비해야 해?',
  '요즘 많이 요구하는 기술이 뭐야?',
];

/** 이력서를 읽고 규칙으로 답을 고른다. */
function reviewAnswerFor(question: string, resume: Resume): CoachResponse {
  const c = resume.content;
  if (question.includes('약한') || question.includes('부족')) {
    const gaps: string[] = [];
    if (c.basicInfo.phone.trim() === '') gaps.push('연락처가 비어 있어요');
    if (c.coreCompetencies.text.length < 60) gaps.push('핵심역량이 3문장보다 짧아요');
    if (!c.projects.some((p) => /\d/.test(p.description))) gaps.push('프로젝트에 수치가 없어요');
    if (c.experience.length === 0) gaps.push('경력사항이 비어 있어요');
    return {
      text:
        gaps.length === 0
          ? '큰 구멍은 안 보여요. 이제 문장을 다듬는 단계예요.'
          : `지금 눈에 띄는 곳은 ${gaps.length}가지예요.\n\n${gaps.map((g, i) => `${i + 1}. ${g}`).join('\n')}`,
    };
  }
  if (question.includes('프로젝트')) {
    const p = c.projects[0];
    if (p === undefined) {
      return {
        text: '프로젝트가 아직 없어요. 부트캠프 프로젝트라도 넣으면 읽는 사람이 무엇을 할 수 있는지 가늠합니다.',
      };
    }
    const hasMetric = /\d/.test(p.description);
    return {
      text: hasMetric
        ? `「${p.name}」의 행동과 결과가 한 문장에 보이도록 정리했어요.`
        : `「${p.name}」에는 확인할 수 있는 성과 수치가 없어요. 임의로 만들지 않고 먼저 질문할게요. 처리량·정확도·시간 절감 중 실제로 확인 가능한 값이 있나요?`,
      suggestion: {
        index: 0,
        fieldPath: 'projects[0].description',
        originalQuote: p.description,
        suggestedRevision: hasMetric
          ? p.description
              .replace('출결·과제 제출 로그로', '출결·과제 제출 로그를 활용해')
              .replace('이탈 위험군을 분류했습니다.', '이탈 위험군 분류 모델을 구축하고')
              .replace(/\s*F1\s*/, ' F1 ')
          : null,
        reason: hasMetric
          ? '사용한 데이터, 수행한 행동, 검증된 결과가 한 흐름으로 읽히도록 문장을 정리했습니다.'
          : '근거에 없는 성과를 생성하지 않기 위해 확인이 필요합니다.',
        evidenceSources: [`projects[0].description`, `projects[0].name:${p.name}`],
        status: hasMetric ? 'improved' : 'needs_confirmation',
        editType: hasMetric ? 'clarity' : 'content',
      },
    };
  }
  if (question.includes('공고') || question.includes('분석가')) {
    return {
      text: `기술 ${c.techStack.length}개 중 공고가 요구하는 항목과 겹치는 것을 먼저 위로 올리세요.\n\n지금 순서: ${c.techStack.map((t) => t.name).join(' · ') || '없음'}`,
    };
  }
  return {
    text: '이력서의 어느 항목을 볼까요? 핵심역량·프로젝트·경력 중에 골라 주시면 그 부분만 짚어 드릴게요.',
  };
}

/** 원본 Flutter의 공고 찾기 챗봇을 DB 없이 보여 주는 데모 응답. */
function jobSearchAnswerFor(question: string): CoachResponse {
  if (question.includes('서울') || question.includes('찾아') || question.includes('공고')) {
    return {
      text: '데모 화면에서는 예시 공고로 보여 드려요. 실제 서비스에서는 지금 열려 있는 공고에서 찾습니다.\n\n1. 주니어 백엔드 개발자 · 서울 · 신입\n2. Python API 개발자 · 서울 · 신입 가능\n3. 웹서비스 백엔드 엔지니어 · 서울 · 경력 무관\n\n실제 공고 DB가 연결되면 이 자리에 검색 결과 카드가 표시됩니다.',
    };
  }
  if (question.includes('준비') || question.includes('기술')) {
    return {
      text: '백엔드 신입 공고에서는 언어와 프레임워크뿐 아니라 REST API, 데이터베이스, Git 협업 경험을 자주 확인합니다. 프로젝트에서 직접 구현한 API와 데이터 흐름을 설명할 수 있게 준비해 보세요. 실제 서버 연결 시 현재 열린 공고를 집계해서 답합니다.',
    };
  }
  return {
    text: '채용 조건을 말해 주세요. 직무·기술·지역·경력·고용형태를 조합해 공고를 찾거나, 채용 준비에 관해 물을 수 있어요.',
  };
}

/** 첨삭 대화가 시작하며 코치가 던지는 확인 질문 */

/** 서버 첨삭 결과 — cover_letter_rag 가 돌려주는 것 중 화면이 쓰는 것만 */
interface ReviewResult {
  summary: string;
  suggestions: ResumeReviewSuggestion[];
  questions: string[];
  /** 이 첨삭 결과의 이름 — 서버가 어느 수정안인지 찾는 데 쓴다 */
  reviewId: string;
  /** 첨삭 당시 이력서 상태. 그 뒤 이력서를 고쳤으면 서버가 반영을 막는다 */
  inputHash: string;
}

/**
 * 첨삭은 40초쯤 걸리고 LLM 을 부른다. 같은 이력서로 가는 요청은 하나로 묶는다
 * (React 는 개발 모드에서 효과를 두 번 실행한다).
 */
const reviewPending = new Map<string, Promise<ReviewResult>>();

function requestReview(resumeId: string): Promise<ReviewResult> {
  const going = reviewPending.get(resumeId);
  if (going !== undefined) return going;
  const promise = http
    .post<Record<string, unknown>>('/resume-review', { resumeId })
    .then(({ data }) => toReviewResult(data))
    .finally(() => reviewPending.delete(resumeId));
  reviewPending.set(resumeId, promise);
  return promise;
}

function toReviewResult(data: Record<string, unknown>): ReviewResult {
  const rows = Array.isArray(data.sentence_reviews) ? (data.sentence_reviews as Record<string, unknown>[]) : [];
  const asked = Array.isArray(data.questions) ? (data.questions as Record<string, unknown>[]) : [];
  return {
    reviewId: String(data.review_id ?? ''),
    inputHash: String(data.input_hash ?? ''),
    summary: String(data.summary ?? ''),
    suggestions: rows.map((r, order) => {
      const fieldPath = String(r.field_path ?? '');
      return {
        // 서버가 반영할 수정안을 고를 때 쓰는 차례(칸 번호가 아니다)
        index: order,
        fieldPath,
        originalQuote: String(r.original_quote ?? ''),
        suggestedRevision: r.suggested_revision == null ? null : String(r.suggested_revision),
        reason: String(r.reason ?? ''),
        evidenceSources: Array.isArray(r.evidence_sources) ? (r.evidence_sources as string[]) : [],
        status: (r.status as ResumeReviewSuggestion['status']) ?? 'needs_confirmation',
        editType: (r.edit_type as ResumeReviewSuggestion['editType']) ?? 'content',
      };
    }),
    questions: asked.map((q) => String(q.question ?? '')).filter((q) => q !== ''),
  };
}


/** `selfIntroduction.motivation.body` → 'motivation'. 모르는 이름이면 undefined */

/**
 * 바로 반영해도 되는 수정안인가 — 원본(job_resume_review_dialog.dart) 규칙 그대로.
 *
 * 상태가 아니라 **고침 종류**로 가른다. 맞춤법 · 말투 · 표현 정리는 새 사실을 더하지 않으므로
 * 바로 반영한다. 내용(content)을 바꾸는 수정안은 사람이 사실을 확인한 뒤에 넣어야 한다.
 */
const POLISH_EDITS = ['spelling', 'tone', 'clarity'];

function canApply(suggestion: ResumeReviewSuggestion): boolean {
  return suggestion.suggestedRevision !== null && POLISH_EDITS.includes(suggestion.editType);
}

/** 첨삭이 가리키는 칸의 지금 글. 못 찾으면 undefined — 그 수정안은 반영 단추를 달지 않는다 */

/** `projects[2].description` → ['projects', 2]. 설명 칸이 있는 목록만 다룬다 */


/** 그 칸만 바꾼 새 이력서 내용 */

export function CoachChat({
  resume,
  mode,
}: {
  resume: Resume;
  /** review = 이력서 첨삭, ask = 코치에게 묻기 */
  mode: 'review' | 'ask';
}) {
  const [started, setStarted] = useState(mode === 'ask');
  const [stage, setStage] = useState(0);
  const [preparing, setPreparing] = useState(false);
  const [messages, setMessages] = useState<Message[]>(() =>
    mode === 'ask'
      ? [
          {
            id: 'job-chat-intro',
            role: 'coach',
            text: '채용에 대해 물어보세요. 공고를 찾아드리고, 궁금한 것에도 답해드려요.\n답은 지금 열려 있는 공고를 직접 세어 드립니다.',
          },
        ]
      : [],
  );
  const [draft, setDraft] = useState('');
  const [thinking, setThinking] = useState(false);
  /**
   * 반영한 수정안 → 되돌리는 데 필요한 것.
   *
   * `inputHash` 는 **반영 뒤** 이력서 상태다. 서버는 되돌릴 때 그 값을 보고, 그 사이 이력서가
   * 또 바뀌었으면 막는다(409 resume_changed_after_application). 그래서 첨삭 당시 값이 아니라
   * 반영 응답이 준 값을 들고 있어야 한다.
   */
  const [appliedReviews, setAppliedReviews] = useState<Record<string, { operationId: string; inputHash: string }>>({});
  const [review, setReview] = useState<ReviewResult | null>(null);
  const [actionNotice, setActionNotice] = useState('');
  const bodyRef = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);

  useEffect(
    () => () => {
      timers.current.forEach((t) => window.clearTimeout(t));
    },
    [],
  );

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages, thinking, preparing]);

  /** 답을 몇 글자씩 흘려보낸다. 실제 앱의 스트리밍이 그렇게 보였다. */
  const stream = ({ text, suggestion }: CoachResponse) => {
    const id = `coach-${Date.now()}-${Math.random()}`;
    setThinking(true);
    timers.current.push(
      window.setTimeout(() => {
        setThinking(false);
        setMessages((m) => [...m, { id, role: 'coach', text: '', streaming: true, suggestion }]);
        let cursor = 0;
        const tick = () => {
          cursor = Math.min(text.length, cursor + 7);
          const slice = text.slice(0, cursor);
          setMessages((m) => m.map((x) => (x.id === id ? { ...x, text: slice } : x)));
          if (cursor < text.length) timers.current.push(window.setTimeout(tick, 20));
          else setMessages((m) => m.map((x) => (x.id === id ? { ...x, streaming: false } : x)));
        };
        tick();
      }, 600),
    );
  };

  /**
   * 첨삭 시작 — 서버(cover_letter_rag)가 이력서를 읽고 문장별 수정안과 확인 질문을 돌려준다.
   *
   * 40초쯤 걸린다. 그동안 준비 단계를 차례로 켜 두되 **끝났다고 먼저 말하지 않는다.**
   * 마지막 단계는 답이 올 때까지 켜 둔 채로 기다린다.
   */
  const startReview = () => {
    setStarted(true);
    setPreparing(true);
    [0, 1, 2].forEach((i) =>
      timers.current.push(window.setTimeout(() => setStage(i + 1), 2500 * (i + 1))),
    );
    void requestReview(resume.id)
      .then((result) => {
        setPreparing(false);
        setStage(3);
        setReview(result);
        const found = result.suggestions.filter((s) => s.suggestedRevision !== null);
        stream({
          text:
            result.summary === ''
              ? '이력서를 다 읽었어요.'
              : `이력서를 다 읽었어요.\n\n${result.summary}`,
        });
        // 고칠 문장을 하나씩. 각 말풍선에 원문 · 수정안 · 반영 단추가 붙는다
        for (const suggestion of found) {
          stream({ text: suggestion.reason, suggestion });
        }
        if (found.length === 0) {
          stream({ text: '바로 고칠 문장은 찾지 못했어요. 아래 질문에 답해 주시면 근거를 더 채울 수 있어요.' });
        }
        if (result.questions.length > 0) {
          stream({ text: `확인하고 싶은 것이 있어요.\n\n${result.questions.slice(0, 5).map((q, i) => `${i + 1}. ${q}`).join('\n')}` });
        }
      })
      .catch((err: unknown) => {
        setPreparing(false);
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        stream({ text: detail ?? '첨삭하지 못했어요. 잠시 후 다시 시도해 주세요.' });
      });
  };

  const ask = (question: string) => {
    setMessages((m) => [...m, { id: `me-${Date.now()}`, role: 'user', text: question }]);
    stream(mode === 'review' ? reviewAnswerFor(question, resume) : jobSearchAnswerFor(question));
  };

  /**
   * 수정안 반영 — 글자는 **서버가** 바꾼다.
   *
   * 첨삭은 칸 전체가 아니라 그 안의 한 문장을 인용한다. 화면에서 글자를 갈아 끼우면
   * 어느 문장인지 다시 찾아야 하고, 서버가 남기는 반영 기록(resume_ai_applications)과도
   * 어긋난다. 그래서 「몇 번째 수정안」만 보내고, 바뀐 이력서를 다시 받아 온다.
   */
  const applySuggestion = (suggestion: ResumeReviewSuggestion) => {
    if (review === null) return;
    setActionNotice('수정안을 반영하고 있어요…');
    void http
      .post<{ operation_id?: string; input_hash?: string }>('/resume-review/apply', {
        resumeId: resume.id,
        reviewId: review.reviewId,
        requestId: `apply-${Date.now()}`,
        expectedInputHash: review.inputHash,
        selectedIndices: [suggestion.index],
      })
      .then(async ({ data }) => {
        await applyBootstrap();
        setAppliedReviews((rows) => ({
          ...rows,
          [suggestion.fieldPath]: {
            operationId: String(data.operation_id ?? ''),
            inputHash: String(data.input_hash ?? ''),
          },
        }));
        setActionNotice('수정안을 이력서에 반영했습니다.');
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setActionNotice(detail ?? '반영하지 못했습니다. 그 사이 이력서를 고쳤다면 다시 첨삭해 주세요.');
      });
  };

  const undoSuggestion = (fieldPath: string) => {
    const applied = appliedReviews[fieldPath];
    if (applied === undefined || review === null) return;
    setActionNotice('되돌리고 있어요…');
    void http
      .post('/resume-review/undo', {
        resumeId: resume.id,
        reviewId: review.reviewId,
        requestId: `undo-${Date.now()}`,
        applicationId: applied.operationId,
        expectedInputHash: applied.inputHash,
      })
      .then(async () => {
        await applyBootstrap();
        setAppliedReviews((rows) => {
          const next = { ...rows };
          delete next[fieldPath];
          return next;
        });
        setActionNotice('수정안 반영을 되돌렸습니다.');
      })
      .catch((err: unknown) => {
        const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        setActionNotice(detail ?? '되돌리지 못했습니다.');
      });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = draft.trim();
    if (question === '' || thinking) return;
    setDraft('');
    ask(question);
  };

  return (
    <section className="coach-chat">
      <header className="coach-chat__head">
        <RobotHead size={26} inverted />
        <strong>{mode === 'review' ? 'AI 첨삭 대화' : '코치에게 묻기'}</strong>
        <span className="hint">
          {mode === 'review'
            ? '근거가 부족한 내용은 질문으로 확인합니다.'
            : '조건을 말하면 채용공고를 찾고 질문에 답합니다.'}
        </span>
      </header>

      <div className="coach-chat__body" ref={bodyRef}>
        {actionNotice !== '' && (
          <div className="coach-chat__notice" role="status">
            {actionNotice}
          </div>
        )}
        {!started && (
          <div className="coach-chat__intro">
            <Icon name="auto_awesome" size={30} className="coach-chat__spark" />
            <strong>이력서 기준으로 문장과 근거를 확인합니다.</strong>
            <p className="hint">부족한 사실은 코치가 질문하고, 답변을 근거로 수정안을 제시합니다.</p>
            <button type="button" className="btn btn--filled btn--md" onClick={startReview}>
              <Icon name="play_arrow" size={18} />
              첨삭 시작
            </button>
          </div>
        )}

        {preparing && <ReviewProgress stage={stage} />}

        {messages.map((message) => (
          <div key={message.id} className={`coach-msg coach-msg--${message.role}`}>
            {message.role === 'coach' && <RobotHead size={30} inverted />}
            <div className="coach-msg__content">
              <p className="coach-msg__text">{message.text}</p>
              {!message.streaming && message.suggestion !== undefined && (
                <article className="review-suggestion">
                  <span className="review-suggestion__label">원문</span>
                  <p>{message.suggestion.originalQuote}</p>
                  {message.suggestion.suggestedRevision !== null && (
                    <>
                      <span className="review-suggestion__label">수정안</span>
                      <p className="review-suggestion__revision">
                        {message.suggestion.suggestedRevision}
                      </p>
                    </>
                  )}
                  <span className="review-suggestion__label">수정 이유</span>
                  <p>{message.suggestion.reason}</p>
                  <small>근거: {message.suggestion.evidenceSources.join(' · ')}</small>
                  {canApply(message.suggestion) ? (
                    <div className="review-suggestion__actions">
                      <button
                        type="button"
                        className="btn btn--filled btn--sm"
                        disabled={appliedReviews[message.suggestion.fieldPath] !== undefined}
                        onClick={() => applySuggestion(message.suggestion!)}
                      >
                        <Icon name="check" size={16} />
                        {appliedReviews[message.suggestion.fieldPath] !== undefined
                          ? '반영됨'
                          : '이 수정안 반영'}
                      </button>
                      {appliedReviews[message.suggestion.fieldPath] !== undefined && (
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => undoSuggestion(message.suggestion!.fieldPath)}
                        >
                          <Icon name="undo" size={16} />
                          되돌리기
                        </button>
                      )}
                    </div>
                  ) : (
                    <span className="badge badge--warning">사실 확인 필요</span>
                  )}
                </article>
              )}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="coach-msg coach-msg--coach">
            <RobotHead size={30} inverted />
            <p className="coach-msg__text coach-msg__text--wait">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
            </p>
          </div>
        )}

        {started && !preparing && !thinking && (
          <div className="coach-chat__suggest">
            {(mode === 'review' ? REVIEW_SUGGESTIONS : CAREER_SUGGESTIONS).map((s) => (
              <button key={s} type="button" className="chip" onClick={() => ask(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
      </div>

      <form className="coach-chat__form" onSubmit={submit}>
        <input
          className="input"
          value={draft}
          placeholder={mode === 'review' ? '이력서 첨삭 내용을 물어보세요' : '찾을 공고나 채용 질문을 입력하세요'}
          disabled={!started}
          onChange={(e) => setDraft(e.target.value)}
        />
        <button type="submit" className="btn btn--filled btn--sm" disabled={draft.trim() === '' || thinking}>
          보내기
        </button>
      </form>
    </section>
  );
}
