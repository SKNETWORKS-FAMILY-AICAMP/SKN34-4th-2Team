import { useEffect, useRef, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';

import {
  askAdminAssistant,
  executeAssistantAction,
  type AssistantAction,
  type AssistantTurn,
} from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { Badge, Button, Chip, Spacer, TextArea, TextInput } from '../../ui/components';
import { useSession } from '../auth/session';
import './manager.css';

/**
 * 관리자 AI 어시스턴트 — 말로 시키면 학생을 조회하고, 알림 발송 · 공지 등록은 확인 카드로 제안한다.
 * 카드의 「실행」을 눌러야 실제로 반영된다. 보내기 전에 문구와 대상을 고칠 수 있다.
 */

type ActionStatus = 'pending' | 'running' | 'done' | 'cancelled';

interface CardState {
  action: AssistantAction;
  status: ActionStatus;
  error?: string;
}

interface Message {
  id: string;
  role: 'user' | 'assistant' | 'error';
  text: string;
  cards?: CardState[];
}

const EXAMPLES = [
  '오늘 입실 체크 안 했는데 출결 신청도 안 한 학생들에게 출결 신청 알림 보내줘',
  '오늘 확인 대기 중인 출결 신청 알려줘',
  '오늘 출결 현황 요약해줘',
  '방금 불시 점검에서 자리에 없던 학생 알려줘',
  '내일 오전 특강 안내 공지 만들어줘',
];

let seq = 0;
const newId = (prefix: string) => `${prefix}-${Date.now()}-${(seq += 1)}`;

const STATUS_LABEL: Record<ActionStatus, string> = {
  pending: '확인 대기',
  running: '실행 중',
  done: '실행함',
  cancelled: '취소함',
};

/** 다음 질문 때 모델이 앞서 제안한 내용을 알 수 있게 대화에 적어 보낸다 */
function cardSummary(card: CardState): string {
  const { action } = card;
  const who =
    action.type === 'send_alert'
      ? action.allStudents
        ? '기수 전체'
        : action.targets.map((t) => t.name).join(', ')
      : '게시판';
  const kind = action.type === 'send_alert' ? '알림' : '공지';
  return `[${kind} 제안 · ${STATUS_LABEL[card.status]}] ${action.title} → ${who}`;
}

export function AdminAssistantHost() {
  const { user } = useSession();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [thinking, setThinking] = useState(false);
  const bodyRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bodyRef.current?.scrollTo?.({ top: bodyRef.current.scrollHeight });
  }, [messages, thinking]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  if (user === null || (user.role !== 'admin' && user.role !== 'instructor')) return null;

  const ask = (question: string) => {
    const history: AssistantTurn[] = [
      ...messages
        .filter((m): m is Message & { role: 'user' | 'assistant' } => m.role !== 'error')
        .map((m) => ({ role: m.role, content: [m.text, ...(m.cards ?? []).map(cardSummary)].join('\n').trim() }))
        .filter((t) => t.content !== ''),
      { role: 'user', content: question },
    ];
    setMessages((m) => [...m, { id: newId('u'), role: 'user', text: question }]);
    setThinking(true);
    askAdminAssistant(history)
      .then(({ reply, actions }) =>
        setMessages((m) => [
          ...m,
          {
            id: newId('a'),
            role: 'assistant',
            text: reply,
            cards: actions.map((action) => ({ action, status: 'pending' as const })),
          },
        ]),
      )
      .catch((err: unknown) =>
        setMessages((m) => [
          ...m,
          { id: newId('e'), role: 'error', text: err instanceof Error ? err.message : '답을 받지 못했습니다.' },
        ]),
      )
      .finally(() => setThinking(false));
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const question = draft.trim();
    if (question === '' || thinking) return;
    setDraft('');
    ask(question);
  };

  const updateCard = (messageId: string, actionId: string, change: (card: CardState) => CardState) =>
    setMessages((list) =>
      list.map((m) =>
        m.id !== messageId
          ? m
          : { ...m, cards: m.cards?.map((c) => (c.action.id === actionId ? change(c) : c)) },
      ),
    );

  const run = (messageId: string, card: CardState) => {
    updateCard(messageId, card.action.id, (c) => ({ ...c, status: 'running', error: undefined }));
    executeAssistantAction(card.action)
      .then(() => updateCard(messageId, card.action.id, (c) => ({ ...c, status: 'done' })))
      .catch((err: unknown) =>
        updateCard(messageId, card.action.id, (c) => ({
          ...c,
          status: 'pending',
          error: err instanceof Error ? err.message : '실행하지 못했습니다.',
        })),
      );
  };

  const launcher = (
    <button
      type="button"
      className="assistant-launcher"
      onClick={() => setOpen((v) => !v)}
      aria-expanded={open}
      aria-label={open ? 'AI 어시스턴트 닫기' : 'AI 어시스턴트 열기'}
    >
      <Icon name="auto_awesome" size={20} />
      AI 어시스턴트
    </button>
  );

  if (!open) return launcher;

  return (
    <section className="assistant" aria-label="관리자 AI 어시스턴트">
      <header className="assistant__head">
        <Icon name="auto_awesome" size={22} />
        <div>
          <strong>AI 어시스턴트</strong>
          <p className="hint">{user.cohortName} · 알림 · 공지는 확인 후에 실행됩니다</p>
        </div>
        <Spacer />
        {messages.length > 0 && (
          <Button size="sm" variant="text" onClick={() => setMessages([])} disabled={thinking}>
            새 대화
          </Button>
        )}
        <button type="button" className="dialog__close" onClick={() => setOpen(false)} aria-label="닫기">
          ✕
        </button>
      </header>

      <div className="assistant__body" ref={bodyRef}>
        {messages.length === 0 && (
          <div className="assistant__examples">
            <p className="muted">이렇게 시켜 보세요.</p>
            {EXAMPLES.map((example) => (
              <button key={example} type="button" className="chip" onClick={() => ask(example)}>
                {example}
              </button>
            ))}
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className="assistant__turn">
            {message.text !== '' && (
              <div className={`assistant__msg assistant__msg--${message.role}`}>{message.text}</div>
            )}
            {message.cards?.map((card) => (
              <ActionCard
                key={card.action.id}
                card={card}
                onChange={(action) => updateCard(message.id, card.action.id, (c) => ({ ...c, action }))}
                onRun={() => run(message.id, card)}
                onCancel={() => updateCard(message.id, card.action.id, (c) => ({ ...c, status: 'cancelled' }))}
              />
            ))}
          </div>
        ))}

        {thinking && (
          <div className="assistant__msg assistant__msg--assistant" role="status" aria-live="polite">
            확인하고 있어요…
          </div>
        )}
      </div>

      <form className="assistant__form" onSubmit={submit}>
        <input
          className="input"
          value={draft}
          placeholder="예: 출결 신청 안 한 학생에게 알림 보내줘"
          aria-label="어시스턴트에게 요청"
          onChange={(e) => setDraft(e.target.value)}
        />
        <Button type="submit" size="sm" disabled={draft.trim() === '' || thinking}>
          보내기
        </Button>
      </form>
    </section>
  );
}

function ActionCard({
  card,
  onChange,
  onRun,
  onCancel,
}: {
  card: CardState;
  onChange(action: AssistantAction): void;
  onRun(): void;
  onCancel(): void;
}) {
  const { action, status } = card;
  const editable = status === 'pending';
  const noTargets = action.type === 'send_alert' && !action.allStudents && action.targets.length === 0;

  return (
    <div
      className={`assistant-action${status === 'done' ? ' assistant-action--done' : ''}${
        status === 'cancelled' ? ' assistant-action--cancelled' : ''
      }`}
    >
      <span className="assistant-action__kind">
        {action.type === 'send_alert' ? '알림 팝업 보내기' : '공지 등록'}
        {action.type === 'create_notice' && action.important && ' · 중요'}
      </span>
      {editable ? (
        <>
          <TextInput
            aria-label="제목"
            value={action.title}
            onChange={(e) => onChange({ ...action, title: e.target.value })}
          />
          <TextArea
            aria-label="내용"
            rows={4}
            value={action.content}
            onChange={(e) => onChange({ ...action, content: e.target.value })}
          />
        </>
      ) : (
        <>
          <strong>{action.title}</strong>
          <p className="assistant-action__content">{action.content}</p>
        </>
      )}

      {action.type === 'send_alert' && (
        <div className="assistant-action__targets">
          {action.allStudents ? (
            <Badge tone="info">기수 전체</Badge>
          ) : (
            <>
              <span className="hint">받는 학생 {action.targets.length}명</span>
              {action.targets.map((t) =>
                editable ? (
                  <Chip
                    key={t.uid}
                    onClick={() => onChange({ ...action, targets: action.targets.filter((x) => x.uid !== t.uid) })}
                  >
                    {t.name} ✕
                  </Chip>
                ) : (
                  <Chip key={t.uid}>{t.name}</Chip>
                ),
              )}
            </>
          )}
        </div>
      )}

      {action.type === 'send_alert' && (
        <div className="assistant-action__targets">
          <span className="hint">노출</span>
          {editable ? (
            <>
              <TextInput
                type="date"
                aria-label="노출 마지막 날"
                style={{ width: 160 }}
                value={action.endDate ?? ''}
                onChange={(e) => onChange({ ...action, endDate: e.target.value || null })}
              />
              <span className="hint">{action.endDate ? '까지' : '끌 때까지'}</span>
            </>
          ) : (
            <span className="hint">{action.endDate ? `${action.endDate}까지` : '끌 때까지'}</span>
          )}
        </div>
      )}

      {card.error !== undefined && (
        <p className="field__error" role="alert">
          {card.error}
        </p>
      )}

      {status === 'done' && (
        <div className="row" style={{ gap: 8 }}>
          <Badge tone="success">{action.type === 'send_alert' ? '보냈습니다' : '등록했습니다'}</Badge>
          <Link className="hint" to={action.type === 'send_alert' ? RoutePaths.adminAlertPopups : RoutePaths.adminBoard}>
            {action.type === 'send_alert' ? '알림 팝업에서 보기' : '게시판에서 보기'}
          </Link>
        </div>
      )}
      {status === 'cancelled' && <span className="hint">취소했습니다.</span>}
      {(status === 'pending' || status === 'running') && (
        <div className="row" style={{ gap: 6 }}>
          <Spacer />
          <Button size="sm" variant="text" onClick={onCancel} disabled={status === 'running'}>
            취소
          </Button>
          <Button
            size="sm"
            onClick={onRun}
            disabled={status === 'running' || action.title.trim() === '' || noTargets}
          >
            {status === 'running' ? '실행 중' : action.type === 'send_alert' ? '보내기' : '등록하기'}
          </Button>
        </div>
      )}
    </div>
  );
}
