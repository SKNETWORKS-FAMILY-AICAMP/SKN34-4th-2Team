import { useState } from 'react';

import { nextId } from '../../data/store';
import { Icon } from '../../ui/Icon';
import { Button, Checkbox, Dialog, TextArea } from '../../ui/components';
import { CaptureUpload } from './CaptureUpload';
import { COMMON_QUESTIONS, splitQuestions, type CompanyQuestion } from './companyQuestions';
import { SharedQuestions } from './SharedQuestions';
import { COMMON_ROLE, roleFromTitle, sharedQuestionsApi } from './sharedQuestionsApi';

/**
 * 회사 자기소개서 문항 정하기 — 다른 수강생이 정리한 문항 · 붙여넣기 · 캡처 올리기 · 자주 나오는 문항 · 기본 여섯 문항.
 *
 * 문항은 대개 회사 채용 사이트에 있고 우리가 수집한 공고 글에는 거의 없다(companyQuestions.ts).
 * 회사 사이트로 가는 버튼은 위의 공고 요약에 하나만 둔다(ApplySiteButton.tsx). 여기서는 그 버튼을 가리킨다.
 * 붙여넣기 · 캡처로 정한 문항은 같은 회사 · 시즌 · 직무를 고른 수강생에게도 보이게 남긴다(SharedQuestions.tsx).
 */
export type QuestionChoice = CompanyQuestion[] | 'default';

type Tab = 'paste' | 'upload' | 'common' | 'default';

const TABS: { id: Tab; icon: string; label: string }[] = [
  { id: 'paste', icon: 'content_paste', label: '붙여넣기' },
  { id: 'upload', icon: 'upload_file', label: '캡처 · 파일 올리기' },
  { id: 'common', icon: 'checklist', label: '자주 나오는 문항' },
  { id: 'default', icon: 'list', label: '기본 6문항' },
];

export function QuestionsStep({
  value,
  locked,
  onChange,
  posting,
}: {
  value: QuestionChoice | null;
  /** 공고용 이력서를 만든 뒤에는 여기서 바꾸지 않는다 */
  locked: boolean;
  onChange(value: QuestionChoice | null): void;
  /** 고른 공고 — 있으면 다른 수강생이 정리한 문항을 보여 주고, 정한 문항을 남긴다 */
  posting?: { job_id: string; company: string; title: string };
}) {
  const [tab, setTab] = useState<Tab>('paste');
  const [pasted, setPasted] = useState('');
  const [parsed, setParsed] = useState<CompanyQuestion[] | null>(null);
  /** 캡처에서 읽었는데 캡처 글에 없어 뺀 문항 수 */
  const [dropped, setDropped] = useState(0);
  const [picked, setPicked] = useState<Record<string, number | null>>({ motivation: 600, competency: 800 });
  const [role, setRole] = useState('');
  const [common, setCommon] = useState(false);
  const [share, setShare] = useState(true);
  const [saving, setSaving] = useState(false);
  const [roleError, setRoleError] = useState<string | null>(null);
  /** 이름은 다른데 문항이 같은 직무 — 합칠지 묻는다 */
  const [same, setSame] = useState<{ name: string; useCount: number; list: CompanyQuestion[] } | null>(null);

  /** 붙여넣기 · 캡처로 정한 문항을 남기고 정한다. 남기다 실패해도 정하기는 막지 않는다 */
  const keep = async (list: CompanyQuestion[], roleName: string) => {
    setSame(null);
    if (posting !== undefined) {
      try {
        await sharedQuestionsApi.save(posting.job_id, roleName, list, share);
      } catch {
        // 공유는 덤이다
      }
    }
    onChange(list);
  };

  const confirm = async (list: CompanyQuestion[]) => {
    if (posting === undefined) {
      onChange(list);
      return;
    }
    const roleName = common ? COMMON_ROLE : role.trim();
    if (roleName === '') {
      setRoleError('위에서 지원 직무를 적어 주세요. 같은 직무를 고른 수강생과 문항을 나눠요.');
      return;
    }
    setRoleError(null);
    setSaving(true);
    try {
      const { sameRole } = await sharedQuestionsApi.check(posting.job_id, roleName, list).catch(() => ({ sameRole: null }));
      if (sameRole !== null) setSame({ ...sameRole, list });
      else await keep(list, roleName);
    } finally {
      setSaving(false);
    }
  };


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
      {posting !== undefined && (
        <SharedQuestions
          jobId={posting.job_id}
          role={role}
          onRole={(name) => {
            setRole(name);
            setRoleError(null);
          }}
          common={common}
          onCommon={setCommon}
          guess={roleFromTitle(posting.title, posting.company)}
          onPick={(list) => onChange(list)}
        />
      )}

      <div className="apply-note">
        <Icon name="info" size={18} />
        <span>
          자기소개서 문항은 대개 회사 채용 사이트에 있어요. 위의 「회사 채용 사이트 열기」로 지원서 화면을 열고, 문항을 복사해
          붙여 넣거나 캡처 · 양식 파일을 올려 주세요.
        </span>
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
          {posting !== undefined && pastedChoice.length > 0 && (
            <div className="apply-shared__share">
              <Checkbox checked={share} onChange={setShare} label="다른 수강생에게도 보여주기" />
              <span className="hint">
                문항 · 글자 수만 공유돼요. 내 답과 메모는 공유되지 않아요. 유료 문항집처럼 나누면 안 되는 자료면 꺼 주세요.
              </span>
            </div>
          )}
          {roleError !== null && <p className="apply-error">{roleError}</p>}
          <div>
            <Button onClick={() => void confirm(pastedChoice)} disabled={pastedChoice.length === 0 || saving}>
              <Icon name="check" size={18} />
              {pastedChoice.length === 0 ? '문항을 먼저 뽑아 주세요' : `이 문항 ${pastedChoice.length}개로 정하기`}
            </Button>
          </div>
        </div>
      )}

      {same !== null && (
        <Dialog
          title={`「${same.name}」에 같은 문항이 이미 있어요`}
          onClose={() => setSame(null)}
          width={560}
          actions={
            <>
              <Button variant="outline" onClick={() => void keep(same.list, role.trim())}>
                아니요, 다른 직무예요
              </Button>
              <Button
                onClick={() => {
                  setRole(same.name);
                  void keep(same.list, same.name);
                }}
              >
                네, 같은 직무예요 — {same.name}로 합치기
              </Button>
            </>
          }
        >
          <p>
            내가 정한 직무는 <b>{role.trim()}</b>이에요. 같은 회사 · 시즌의 <b>{same.name}</b>에 문항이 모두 같은 정리가 있어요
            {same.useCount > 0 && ` (${same.useCount}명 사용)`}.
          </p>
          <p className="hint">따로 두어도 다른 수강생에게는 문항이 같은 정리 한 장으로 보여요.</p>
        </Dialog>
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
