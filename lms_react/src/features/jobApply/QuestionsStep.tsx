import { useState } from 'react';

import { nextId } from '../../data/store';
import { Icon } from '../../ui/Icon';
import { Button, TextArea } from '../../ui/components';
import type { Posting } from '../jobs/JobPostingScreen';
import { CaptureUpload } from './CaptureUpload';
import { COMMON_QUESTIONS, splitQuestions, type CompanyQuestion } from './companyQuestions';

/**
 * 회사 자기소개서 문항 정하기 — 붙여넣기 · 캡처 올리기 · 자주 나오는 문항 · 기본 여섯 문항.
 *
 * 문항은 대개 회사 채용 사이트에 있고 우리가 수집한 공고 글에는 거의 없다(companyQuestions.ts).
 * 채용 사이트 주소도 모으지 않으므로 「지원 방법 보기」는 사람인 · 잡코리아 공고 페이지를 연다.
 * 거기의 「홈페이지 지원」 버튼으로 회사 사이트에 간다.
 */
export type QuestionChoice = CompanyQuestion[] | 'default';

type Tab = 'paste' | 'upload' | 'common' | 'default';

const SOURCE_LABEL: Record<string, string> = { SARAMIN_POC: '사람인', JOBKOREA_POC: '잡코리아' };

const TABS: { id: Tab; icon: string; label: string }[] = [
  { id: 'paste', icon: 'content_paste', label: '붙여넣기' },
  { id: 'upload', icon: 'upload_file', label: '캡처 · PDF 올리기' },
  { id: 'common', icon: 'checklist', label: '자주 나오는 문항' },
  { id: 'default', icon: 'list', label: '기본 6문항' },
];

export function QuestionsStep({
  posting,
  value,
  locked,
  onChange,
}: {
  posting: Posting;
  value: QuestionChoice | null;
  /** 공고용 이력서를 만든 뒤에는 여기서 바꾸지 않는다 */
  locked: boolean;
  onChange(value: QuestionChoice | null): void;
}) {
  const [tab, setTab] = useState<Tab>('paste');
  const [pasted, setPasted] = useState('');
  const [parsed, setParsed] = useState<CompanyQuestion[] | null>(null);
  /** 캡처에서 읽었는데 캡처 글에 없어 뺀 문항 수 */
  const [dropped, setDropped] = useState(0);
  const [picked, setPicked] = useState<Record<string, number | null>>({ motivation: 600, competency: 800 });

  const link = posting.links?.find((l) => l.source_url.startsWith('http')) ?? posting;
  const site = SOURCE_LABEL[link.source] ?? '공고 사이트';

  if (value !== null) {
    return (
      <div className="apply-q-done">
        {value === 'default' ? (
          <p>기본 6문항(자기소개 · 지원동기 · 어려움 극복 · 성장과정 · 성격의 장단점 · 입사 후 포부)으로 써요.</p>
        ) : (
          <ol className="apply-q-list">
            {value.map((q) => (
              <li key={q.id}>
                <span>{q.question}</span>
                <span className="apply-q-limit">{q.limit === null ? '글자 수 없음' : `${q.limit.toLocaleString()}자`}</span>
              </li>
            ))}
          </ol>
        )}
        {!locked && (
          <div>
            <Button variant="text" size="sm" onClick={() => onChange(null)}>
              다시 고르기
            </Button>
          </div>
        )}
      </div>
    );
  }

  const edit = (id: string, patch: Partial<CompanyQuestion>) =>
    setParsed((list) => (list ?? []).map((q) => (q.id === id ? { ...q, ...patch } : q)));
  const commonPicked = COMMON_QUESTIONS.filter((c) => c.key in picked);
  const commonChoice = () =>
    commonPicked.map((c) => ({ id: nextId('cq'), question: c.question, limit: picked[c.key] ?? null, answer: '' }));
  const pastedChoice = (parsed ?? []).filter((q) => q.question.trim() !== '');

  return (
    <>
      <div className="apply-note">
        <Icon name="info" size={18} />
        <span>
          자기소개서 문항은 대개 회사 채용 사이트에 있어요. {site} 공고의 「홈페이지 지원」이나 지원 안내에서 확인해 주세요.
        </span>
        {link.source_url.startsWith('http') && (
          <a className="btn btn--outline btn--sm" href={link.source_url} target="_blank" rel="noreferrer">
            <Icon name="open_in_new" size={16} />
            {site}에서 지원 방법 보기
          </a>
        )}
      </div>

      <div className="apply-tabs" role="tablist" aria-label="문항 입력 방법">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`apply-tab${tab === t.id ? ' is-on' : ''}`}
            onClick={() => setTab(t.id)}
          >
            <Icon name={t.icon} size={18} />
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'paste' && (
        <div className="apply-tabpanel" role="tabpanel">
          <TextArea
            value={pasted}
            onChange={(e) => setPasted(e.target.value)}
            rows={5}
            aria-label="자기소개서 문항 붙여넣기"
            placeholder={'회사 채용 사이트의 문항을 복사해 붙여 넣으세요.\n1. 지원 동기와 입사 후 포부를 기술하시오. (공백 포함 600자 이내)\n2. …'}
          />
          <div>
            <Button
              variant="outline"
              onClick={() => {
                setParsed(splitQuestions(pasted, () => nextId('cq')));
                setDropped(0);
              }}
              disabled={pasted.trim() === ''}
            >
              <Icon name="format_list_numbered" size={18} />
              문항 나누기
            </Button>
          </div>
        </div>
      )}

      {tab === 'upload' && (
        <CaptureUpload
          onParsed={(list, droppedCount) => {
            setParsed(list);
            setDropped(droppedCount);
          }}
        />
      )}

      {/* 붙여넣기 · 캡처 모두 여기서 확인하고 고친 뒤 정한다 */}
      {(tab === 'paste' || tab === 'upload') && (
        <div className="apply-tabpanel">
          {parsed !== null && (
            <div className="apply-q-edit">
              {parsed.length === 0 ? (
                <p className="hint">
                  {tab === 'upload'
                    ? '캡처에서 문항을 찾지 못했어요. 문항 글이 다 보이게 다시 캡처하거나, 직접 추가해 주세요.'
                    : '문항을 찾지 못했어요. 문항마다 줄을 바꾸고 앞에 번호(1. 2. …)를 붙여 보세요.'}
                </p>
              ) : (
                <>
                  <div className="apply-q-edit__head">
                    <span className="apply-label">
                      뽑은 문항 · 확인하고 고쳐 주세요
                      {dropped > 0 && ` (캡처 글에서 확인되지 않은 ${dropped}개는 뺐어요)`}
                    </span>
                    <span className="hint">글자 수 (공백 포함)</span>
                  </div>
                  {parsed.map((q, i) => (
                    <div key={q.id} className={`apply-q-row${q.limit === null ? ' is-unknown' : ''}`}>
                      <span className="apply-q-no">{i + 1}</span>
                      <input
                        className="apply-q-input"
                        value={q.question}
                        aria-label={`문항 ${i + 1}`}
                        onChange={(e) => edit(q.id, { question: e.target.value })}
                      />
                      <input
                        className="apply-q-limit-input"
                        inputMode="numeric"
                        value={q.limit ?? ''}
                        placeholder="?"
                        aria-label={`문항 ${i + 1} 글자 수`}
                        onChange={(e) => {
                          const n = Number(e.target.value.replace(/\D/g, ''));
                          edit(q.id, { limit: n > 0 ? n : null });
                        }}
                      />
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label={`문항 ${i + 1} 지우기`}
                        onClick={() => setParsed((list) => (list ?? []).filter((x) => x.id !== q.id))}
                      >
                        <Icon name="delete" size={20} />
                      </button>
                    </div>
                  ))}
                </>
              )}
              <div>
                <Button
                  variant="text"
                  size="sm"
                  onClick={() => setParsed((list) => [...(list ?? []), { id: nextId('cq'), question: '', limit: null, answer: '' }])}
                >
                  <Icon name="add" size={16} />
                  문항 추가
                </Button>
              </div>
            </div>
          )}
          <div>
            <Button onClick={() => onChange(pastedChoice)} disabled={pastedChoice.length === 0}>
              <Icon name="check" size={18} />
              {pastedChoice.length === 0 ? '문항을 먼저 뽑아 주세요' : `이 문항 ${pastedChoice.length}개로 정하기`}
            </Button>
          </div>
        </div>
      )}

      {tab === 'common' && (
        <div className="apply-tabpanel" role="tabpanel">
          <p className="hint">아직 문항을 모르면 회사들이 자주 묻는 문항으로 먼저 써 두세요. 필요한 것만 고르고 글자 수를 정해요.</p>
          {COMMON_QUESTIONS.map((c) => {
            const on = c.key in picked;
            return (
              <div key={c.key} className={`apply-q-row${on ? ' is-picked' : ''}`}>
                <input
                  type="checkbox"
                  checked={on}
                  aria-label={c.question}
                  onChange={() =>
                    setPicked((p) => {
                      const next = { ...p };
                      if (on) delete next[c.key];
                      else next[c.key] = c.limit;
                      return next;
                    })
                  }
                />
                <span className="apply-q-input apply-q-input--text">{c.question}</span>
                <input
                  className="apply-q-limit-input"
                  inputMode="numeric"
                  value={on ? (picked[c.key] ?? '') : c.limit}
                  disabled={!on}
                  aria-label={`${c.question} 글자 수`}
                  onChange={(e) => {
                    const n = Number(e.target.value.replace(/\D/g, ''));
                    setPicked((p) => ({ ...p, [c.key]: n > 0 ? n : null }));
                  }}
                />
              </div>
            );
          })}
          <p className="hint">진짜 문항을 알게 되면 이 화면으로 돌아와 다시 고르면 돼요.</p>
          <div>
            <Button onClick={() => onChange(commonChoice())} disabled={commonPicked.length === 0}>
              <Icon name="check" size={18} />
              {commonPicked.length === 0 ? '문항을 골라 주세요' : `이 문항 ${commonPicked.length}개로 정하기`}
            </Button>
          </div>
        </div>
      )}

      {tab === 'default' && (
        <div className="apply-tabpanel" role="tabpanel">
          <p className="hint">
            자유양식이거나 문항이 없는 공고면 기본 6문항(자기소개 · 지원동기 · 어려움 극복 · 성장과정 · 성격의 장단점 · 입사 후 포부)을
            그대로 써요. 바탕 이력서의 자기소개서가 그대로 옮겨져요.
          </p>
          <div>
            <Button onClick={() => onChange('default')}>
              <Icon name="check" size={18} />
              기본 6문항으로 정하기
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
