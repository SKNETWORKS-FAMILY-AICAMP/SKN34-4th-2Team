import { useEffect, useRef, useState, type FormEvent } from 'react';

import { readApiError } from '../../data/http';
import { askTutor, fetchTutorThread, type TutorQuestion, type TutorTurn } from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { OPEN_CHATBOT_EVENT } from '../chatbot/ChatbotHost';
import { useTutor, type TutorTarget } from './TutorContext';

const LADDER = ['방향', '위치', '거의'];

function threadKey(t: TutorTarget | null) {
  if (!t) return '';
  return t.mode === 'problem' ? `set:${t.setId}:${t.index}` : 'cell';
}

/**
 * 연습장 오른쪽에 붙는 튜터.
 *
 * - 문제 튜터: 문제 셀은 3단계 힌트(방향 → 위치 → 거의). 「힌트 더」를 눌러야 단계가 오른다.
 *   정답 코드는 주지 않는다 — 「정답 알려 줘」는 문제 아래 「모범답안 보기」 규칙을 알려 준다.
 *   일반 코드 셀은 코드 · 오류 설명.
 * - 학습 도우미: 출결 · 공지 같은 LMS 질문은 챗봇으로 보낸다.
 *
 * 한도는 없다. 잡담은 서버가 LLM 없이 돌려보내고, 이어지면 잠시 멈춘다.
 */
export function TutorPanel() {
  const tutor = useTutor();
  const target = tutor?.target ?? null;
  const key = threadKey(target);
  const [tab, setTab] = useState<'tutor' | 'helper'>('tutor');
  const [turns, setTurns] = useState<TutorTurn[]>([]);
  const [level, setLevel] = useState(0);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [draft, setDraft] = useState('');
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // 문제가 바뀌면 그 문제의 지난 대화 · 힌트 단계를 불러온다
  useEffect(() => {
    if (!target) return;
    let alive = true;
    setTurns([]);
    setLevel(0);
    setError('');
    setLoading(true);
    fetchTutorThread(target.mode, target.setId, target.index)
      .then((th) => {
        if (!alive) return;
        setTurns(th.turns);
        setLevel(th.hintLevel);
      })
      .catch(async (e) => {
        const message = await readApiError(e);
        if (alive) setError(message);
      })
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
    // 같은 대화(일반 셀끼리)면 다시 부르지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // 처음 열 때만 입력칸으로 — 열린 채 셀을 옮겨 다닐 땐(따라가기) 편집기 포커스를 뺏지 않는다
  const isOpen = Boolean(target);
  useEffect(() => {
    if (!isOpen) return;
    setTab('tutor');
    inputRef.current?.focus();
  }, [isOpen]);

  useEffect(() => {
    bodyRef.current?.scrollTo?.({ top: bodyRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, sending]);

  if (!tutor || !target) return null;
  const isProblem = target.mode === 'problem';
  const snapshot = target.read();
  const hasError = /Error|오류|에러|Traceback/.test(snapshot.run);

  const send = async (action: TutorQuestion['action'], question = '', fromDraft = false) => {
    if (sending) return;
    const now = target.read();
    const text = question.trim() || (action === 'more' ? '힌트 더 주세요' : action === 'answer' ? '정답 알려 주세요' : '');
    if (!text) return;
    setSending(true);
    setError('');
    setTurns((t) => [...t, { role: 'user', text, kind: null, hintLevel: null, lines: [], at: new Date().toISOString() }]);
    try {
      const r = await askTutor({
        mode: target.mode,
        action,
        question: question.trim() || undefined,
        setId: target.setId,
        index: target.index,
        ...now,
      });
      const at = new Date().toISOString();
      setTurns((t) => [...t, { role: 'assistant', text: r.reply, kind: r.kind, hintLevel: r.hintLevel, lines: r.lines, at }]);
      if (r.hintLevel) setLevel(r.hintLevel);
      tutor.mark(target.cellId, r.lines);
    } catch (e) {
      setTurns((t) => t.slice(0, -1));
      setError(await readApiError(e));
      if (fromDraft) setDraft(question);
    } finally {
      setSending(false);
    }
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = draft.trim();
    if (!q) return;
    setDraft('');
    void send('ask', q, true);
  };

  return (
    <aside className="tutor" aria-label="튜터">
      <header className="tutor__head">
        <div className="tutor__tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'tutor'} onClick={() => setTab('tutor')}>
            <Icon name="school" size={17} />
            {isProblem ? '문제 튜터' : '코드 튜터'}
          </button>
          <button type="button" role="tab" aria-selected={tab === 'helper'} onClick={() => setTab('helper')}>
            <Icon name="smart_toy" size={17} />
            학습 도우미
          </button>
        </div>
        <button type="button" className="py-icon-btn" onClick={tutor.close} aria-label="튜터 닫기" title="닫기">
          <Icon name="close" size={18} />
        </button>
      </header>

      {tab === 'helper' ? (
        <div className="tutor__helper">
          <Icon name="smart_toy" size={36} />
          <p>
            출결 · 공지 · 과제 제출 같은 <strong>LMS 질문</strong>은 학습 도우미가 답해요.
            <br />
            코드 · 문제 질문은 「{isProblem ? '문제 튜터' : '코드 튜터'}」 탭에서 물어보세요.
          </p>
          <button type="button" className="btn btn--outline btn--sm" onClick={() => window.dispatchEvent(new Event(OPEN_CHATBOT_EVENT))}>
            학습 도우미 열기
          </button>
        </div>
      ) : (
        <>
          <div className="tutor__target">
            <strong>{target.label}</strong>
            {isProblem ? (
              <div className="tutor__ladder" aria-label={`힌트 ${level} / 3단계`}>
                {LADDER.map((name, i) => (
                  <span key={name} className={i < level ? 'on' : ''}>
                    {i + 1} {name}
                  </span>
                ))}
              </div>
            ) : (
              <span className="tutor__sub">코드가 하는 일이나 오류를 설명해 줘요</span>
            )}
          </div>

          <div className="tutor__body" ref={bodyRef} aria-live="polite">
            {loading && <p className="tutor__empty">지난 대화를 불러오는 중…</p>}
            {!loading && turns.length === 0 && (
              <p className="tutor__empty">
                {isProblem
                  ? '막힌 곳을 물어보세요. 정답 코드는 주지 않고, 스스로 고칠 수 있게 한 단계씩 힌트를 줘요.'
                  : '이 셀의 코드나 오류를 물어보세요. 실행한 결과도 함께 보내요.'}
              </p>
            )}
            {turns.map((t, i) => (
              <TurnBubble key={i} turn={t} onLines={(lines) => tutor.mark(target.cellId, lines)} />
            ))}
            {sending && (
              <div className="tutor__msg tutor__msg--bot tutor__msg--wait">
                <span className="tutor__dots" aria-label="답을 쓰는 중">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            )}
          </div>

          {error && (
            <p className="tutor__error" role="alert">
              {error}
            </p>
          )}

          <div className="tutor__chips">
            {isProblem ? (
              <>
                <button type="button" onClick={() => send('more')} disabled={sending || level >= 3}>
                  <Icon name="lightbulb" size={15} />
                  {level >= 3 ? '마지막 힌트까지 봤어요' : `힌트 더 (${level + 1}/3)`}
                </button>
                <button type="button" onClick={() => send('ask', '어디가 틀렸는지 알려 주세요')} disabled={sending}>
                  어디가 틀렸어요?
                </button>
                <button type="button" onClick={() => send('answer')} disabled={sending}>
                  정답 알려 줘
                </button>
              </>
            ) : (
              <>
                {hasError && (
                  <button type="button" onClick={() => send('ask', '이 오류가 왜 났는지 설명해 주세요')} disabled={sending}>
                    <Icon name="error" size={15} />이 오류 설명
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => send('ask', '이 코드가 하는 일을 설명해 주세요')}
                  disabled={sending || !snapshot.code.trim()}
                >
                  이 코드 설명
                </button>
              </>
            )}
          </div>

          <form className="tutor__form" onSubmit={submit}>
            <textarea
              ref={inputRef}
              value={draft}
              rows={2}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder={isProblem ? '예: 왜 테스트 2번이 틀려요?' : '예: 3번째 줄이 뭘 하는 거예요?'}
              aria-label="튜터에게 질문"
            />
            <button type="submit" className="btn btn--filled btn--sm" disabled={sending || !draft.trim()} aria-label="보내기">
              <Icon name="send" size={17} />
            </button>
          </form>
          <p className="tutor__foot">
            지금 코드 · 실행 결과{isProblem ? ' · 채점 결과' : ''}를 함께 보내요. 문제와 코드에 대한 질문만 받아요.
          </p>
        </>
      )}
    </aside>
  );
}

function TurnBubble({ turn, onLines }: { turn: TutorTurn; onLines: (lines: number[]) => void }) {
  if (turn.role === 'user') return <div className="tutor__msg tutor__msg--me">{turn.text}</div>;
  const muted = turn.kind === 'offtopic' || turn.kind === 'locked';
  return (
    <div className={`tutor__msg tutor__msg--bot${muted ? ' tutor__msg--muted' : ''}`}>
      {turn.kind === 'hint' && turn.hintLevel && (
        <span className="tutor__badge">
          힌트 {turn.hintLevel}단계 · {LADDER[turn.hintLevel - 1]}
        </span>
      )}
      {turn.kind === 'locked' && (
        <span className="tutor__badge">
          <Icon name="lock" size={13} />
          정답은 직접
        </span>
      )}
      <p>{turn.text}</p>
      {turn.lines.length > 0 && (
        <div className="tutor__lines">
          {turn.lines.map((n) => (
            <button key={n} type="button" onClick={() => onLines([n])}>
              {n}번째 줄 보기
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
