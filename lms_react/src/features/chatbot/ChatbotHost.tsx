import { useEffect, useRef, useState, type FormEvent } from 'react';

import { RobotHead } from '../../ui/RobotHead';
import { Button, Row, Spacer } from '../../ui/components';
import { http } from '../../data/http';
import { useSession } from '../auth/session';
import { answerFor, chatbotGreeting, quickTopics } from './chatbotAnswers';

/**
 * 학생 챗봇 — features/chatbot/presentation/student_chatbot_host.dart
 *
 * 화면 오른쪽 아래에 떠 있다가 누르면 대화 패널이 열린다. 답은 데모 클라이언트와
 * 같은 규칙으로 고르고, 한 번에 뱉지 않고 몇 글자씩 흘려보낸다 — 실제 앱의
 * 스트리밍이 그렇게 보였다.
 */
interface Message {
  id: string;
  role: 'user' | 'bot';
  text: string;
  /** 아직 흘러나오는 중인가 */
  streaming?: boolean;
  feedback?: 'up' | 'down';
}

export function ChatbotHost() {
  const { user } = useSession();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [thinking, setThinking] = useState(false);
  const [topic, setTopic] = useState<string | null>(null);
  // 로봇 버튼을 누를 때마다 1씩 올린다. 그때만 머리가 한 번 튄다.
  const [bounce, setBounce] = useState(0);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const timers = useRef<number[]>([]);

  useEffect(
    () => () => {
      timers.current.forEach((t) => window.clearTimeout(t));
    },
    [],
  );

  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages, thinking]);

  // 학생만 쓴다. 강사·관리자 화면에는 뜨지 않는다.
  if (user === null || user.role !== 'student') return null;

  /** 답을 몇 글자씩 흘려보낸다. */
  const stream = (text: string) => {
    const id = `bot-${Date.now()}`;
    // API 대기 중에도 thinking 이 true 일 수 있다. 타이핑 직전에 잠깐 더 보여 준다.
    setThinking(true);
    const start = window.setTimeout(() => {
      setThinking(false);
      setMessages((m) => [...m, { id, role: 'bot', text: '', streaming: true }]);
      let cursor = 0;
      const tick = () => {
        cursor = Math.min(text.length, cursor + 6);
        const slice = text.slice(0, cursor);
        setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, text: slice } : msg)));
        if (cursor < text.length) {
          timers.current.push(window.setTimeout(tick, 22));
        } else {
          setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, streaming: false } : msg)));
        }
      };
      tick();
    }, 700);
    timers.current.push(start);
  };

  const ask = (question: string) => {
    setMessages((m) => [...m, { id: `user-${Date.now()}`, role: 'user', text: question }]);
    if (import.meta.env.MODE === 'test') {
      stream(answerFor(question));
      return;
    }
    // 서버(LLM) 응답을 기다리는 동안 로딩을 보여 준다.
    setThinking(true);
    void (async () => {
      try {
        const { data } = await http.post<{ answer?: string }>('/chat', { message: question });
        stream(data.answer || '답변을 받지 못했습니다.');
      } catch {
        stream('학습 도우미에 잠시 연결하지 못했습니다. 잠시 후 다시 시도하세요.');
      }
    })();
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = draft.trim();
    if (question === '' || thinking) return;
    setDraft('');
    ask(question);
  };

  const openTopic = (title: string) => {
    const found = quickTopics.find((t) => t.title === title);
    if (found === undefined) return;
    setTopic(title);
    setMessages((m) => [...m, { id: `user-${Date.now()}`, role: 'user', text: title }]);
    stream(found.answer);
  };

  const followUps = quickTopics.find((t) => t.title === topic)?.followUps ?? [];

  const launcher = (
    <button
      type="button"
      className="chatbot-launcher"
      onClick={() => {
        // 원본과 같다: 누를 때마다 머리가 한 번 늘어났다 돌아오고, 패널이 열리고 닫힌다.
        setBounce((b) => b + 1);
        setOpen((v) => !v);
      }}
      aria-label={open ? '챗봇 닫기' : '학생 챗봇 열기'}
    >
      {!open && <span className="chatbot-launcher__bubble">{chatbotGreeting}</span>}
      <RobotHead size={104} bounce={bounce} />
    </button>
  );

  if (!open) return launcher;

  return (
    <>
      {launcher}
      <section className="chatbot" aria-label="학습 도우미 챗봇">
      <header className="chatbot__head">
        <RobotHead size={44} />
        <div>
          <strong>학습 도우미</strong>
          <p className="hint">LMS 정책·출결·프로젝트를 물어보세요</p>
        </div>
        <Spacer />
        <button type="button" className="chatbot__close" onClick={() => setOpen(false)} aria-label="닫기">
          ✕
        </button>
      </header>

      <div className="chatbot__body" ref={bodyRef}>
        {messages.length === 0 && (
          <>
            <p className="muted">자주 묻는 질문을 골라 보세요.</p>
            <Row gap={6}>
              {quickTopics.map((t) => (
                <button key={t.title} type="button" className="chip" onClick={() => openTopic(t.title)}>
                  {t.title}
                </button>
              ))}
            </Row>
          </>
        )}

        {messages.map((message) => (
          <div key={message.id} className={`bubble-row bubble-row--${message.role}`}>
            {message.role === 'bot' && <RobotHead size={36} />}
            <div className={`bubble bubble--${message.role}`}>
            <MarkdownLite text={message.text} />
            {message.role === 'bot' && message.streaming !== true && (
              <Row gap={4}>
                <Spacer />
                <button
                  type="button"
                  className={`bubble__vote${message.feedback === 'up' ? ' bubble__vote--on' : ''}`}
                  onClick={() =>
                    setMessages((m) =>
                      m.map((x) => (x.id === message.id ? { ...x, feedback: 'up' } : x)),
                    )
                  }
                  aria-label="도움이 됐어요"
                >
                  👍
                </button>
                <button
                  type="button"
                  className={`bubble__vote${message.feedback === 'down' ? ' bubble__vote--on' : ''}`}
                  onClick={() =>
                    setMessages((m) =>
                      m.map((x) => (x.id === message.id ? { ...x, feedback: 'down' } : x)),
                    )
                  }
                  aria-label="아쉬워요"
                >
                  👎
                </button>
              </Row>
            )}
            </div>
          </div>
        ))}

        {thinking && (
          <div className="bubble bubble--bot bubble--loading" role="status" aria-live="polite">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
            <span className="hint">답변을 생성하고 있어요</span>
          </div>
        )}

        {followUps.length > 0 && !thinking && (
          <Row gap={6}>
            {followUps.map((f) => (
              <button key={f.question} type="button" className="chip" onClick={() => ask(f.question)}>
                {f.question}
              </button>
            ))}
          </Row>
        )}
      </div>

      <form className="chatbot__form" onSubmit={submit}>
        <input
          className="input"
          value={draft}
          placeholder="궁금한 점을 적어 주세요"
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button type="submit" size="sm" disabled={draft.trim() === '' || thinking}>
          보내기
        </Button>
      </form>
      </section>
    </>
  );
}

/** 굵게(**)와 줄바꿈만 다루는 최소 표시기 */
function MarkdownLite({ text }: { text: string }) {
  return (
    <div className="bubble__text">
      {text.split('\n').map((line, i) => (
        <p key={i}>
          {line.split(/(\*\*[^*]+\*\*)/g).map((part, j) =>
            part.startsWith('**') && part.endsWith('**') ? (
              <strong key={j}>{part.slice(2, -2)}</strong>
            ) : (
              <span key={j}>{part}</span>
            ),
          )}
        </p>
      ))}
    </div>
  );
}
