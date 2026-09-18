import { useEffect, useRef, useState, type FormEvent } from 'react';

import type { Resume } from '../../domain/types';
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
}

const SUGGESTIONS = [
  '이 이력서의 약한 곳은 어디야?',
  '프로젝트 설명을 더 낫게 고쳐 줘',
  '데이터 분석가 공고에 맞는지 봐 줘',
];

/** 이력서를 읽고 규칙으로 답을 고른다. */
function answerFor(question: string, resume: Resume): string {
  const c = resume.content;
  if (question.includes('약한') || question.includes('부족')) {
    const gaps: string[] = [];
    if (c.basicInfo.phone.trim() === '') gaps.push('연락처가 비어 있어요');
    if (c.coreCompetencies.text.length < 60) gaps.push('핵심역량이 3문장보다 짧아요');
    if (!c.projects.some((p) => /\d/.test(p.description))) gaps.push('프로젝트에 수치가 없어요');
    if (c.experience.length === 0) gaps.push('경력사항이 비어 있어요');
    return gaps.length === 0
      ? '큰 구멍은 안 보여요. 이제 문장을 다듬는 단계예요.'
      : `지금 눈에 띄는 곳은 ${gaps.length}가지예요.\n\n${gaps.map((g, i) => `${i + 1}. ${g}`).join('\n')}`;
  }
  if (question.includes('프로젝트')) {
    const p = c.projects[0];
    return p === undefined
      ? '프로젝트가 아직 없어요. 부트캠프 프로젝트라도 넣으면 읽는 사람이 무엇을 할 수 있는지 가늠합니다.'
      : `「${p.name}」을 이렇게 고쳐 볼까요?\n\n${p.description}\n↓\n${p.description.replace(/\.$/, '')}. 처리량과 정확도를 숫자로 적으면 규모가 드러납니다.`;
  }
  if (question.includes('공고') || question.includes('분석가')) {
    return `기술 ${c.techStack.length}개 중 공고가 요구하는 항목과 겹치는 것을 먼저 위로 올리세요.\n\n지금 순서: ${c.techStack.map((t) => t.name).join(' · ') || '없음'}`;
  }
  return '이력서의 어느 항목을 볼까요? 핵심역량·프로젝트·경력 중에 골라 주시면 그 부분만 짚어 드릴게요.';
}

/** 첨삭 대화가 시작하며 코치가 던지는 확인 질문 */
function openingQuestions(resume: Resume): string[] {
  const c = resume.content;
  const questions: string[] = [];
  if (c.projects.length > 0) {
    questions.push(`「${c.projects[0].name}」에서 맡은 범위가 어디까지였나요? 혼자 한 일과 함께 한 일을 나눠 적으면 근거가 또렷해집니다.`);
  }
  if (c.experience.length > 0) {
    questions.push(`${c.experience[0].company}에서의 성과를 숫자로 말할 수 있을까요? 기간·규모·개선 폭 중 하나면 됩니다.`);
  }
  if (questions.length === 0) {
    questions.push('먼저 프로젝트를 하나 적어 주세요. 그 내용을 근거로 문장을 다듬겠습니다.');
  }
  return questions;
}

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
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [thinking, setThinking] = useState(false);
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
  const stream = (text: string) => {
    const id = `coach-${Date.now()}-${Math.random()}`;
    setThinking(true);
    timers.current.push(
      window.setTimeout(() => {
        setThinking(false);
        setMessages((m) => [...m, { id, role: 'coach', text: '', streaming: true }]);
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

  /** 첨삭 시작 — 네 단계를 지나고 확인 질문으로 대화를 연다. */
  const startReview = () => {
    setStarted(true);
    setPreparing(true);
    [0, 1, 2, 3].forEach((i) =>
      timers.current.push(
        window.setTimeout(() => {
          if (i < 3) {
            setStage(i + 1);
            return;
          }
          setPreparing(false);
          const questions = openingQuestions(resume);
          stream(`이력서를 다 읽었어요. 근거가 부족한 곳부터 물어볼게요.\n\n${questions[0]}`);
        }, 1000 * (i + 1)),
      ),
    );
  };

  const ask = (question: string) => {
    setMessages((m) => [...m, { id: `me-${Date.now()}`, role: 'user', text: question }]);
    stream(answerFor(question, resume));
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
        <span className="hint">근거가 부족한 내용은 질문으로 확인합니다.</span>
      </header>

      <div className="coach-chat__body" ref={bodyRef}>
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
            <p className="coach-msg__text">{message.text}</p>
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
            {SUGGESTIONS.map((s) => (
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
          placeholder="코치에게 물어보세요"
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
