import { useRef, useState } from 'react';

import { updateResume, useResume } from '../../data/repository';
import type { ResumeCompanyQuestion, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Button, TextArea } from '../../ui/components';
import { reviewApi, type Json } from '../resume/review/reviewApi';

/**
 * 공고 맞춤 지원의 첨삭 — 회사 문항마다 공고 요건 · 이력서 근거로 답을 쓴다.
 *
 * 이력서 관리의 AI 첨삭(문장 다듬기 → 경험 보완 → 지원동기 → 자기소개서)과는 다른 흐름이다.
 * 서버(question_answers.py)가 문장마다 근거 인용을 대조해 확인되지 않는 문장 · 틀 문장 · 근거 없는 숫자를 빼고,
 * 글자 수를 넘기지 않는다. 재료가 모자라면 짧게 쓰고 질문을 낸다. 답하면 그 답을 근거로 다시 쓴다.
 * 초안은 바로 저장하지 않는다. 사용자가 고쳐서 「저장」한 글만 자소서에 들어간다.
 *
 * 캐치처럼 키워드 메모만 적어도 쓴다. 메모는 「사용자 답변」 근거로 넘긴다 — 메모를 문장으로 풀어 쓰되,
 * 메모 · 이력서에 없는 사실(숫자 · 성과 · 역할)은 서버가 대조해 뺀다. 메모가 짧으면 글도 짧고, 대신 질문이 붙는다.
 */
interface Sentence {
  text: string;
  basis: 'resume' | 'answer' | 'posting';
  quote: string;
  requirementIds: string[];
}

interface AnswerResult {
  draft: string;
  charCount: number;
  limit: number | null;
  sentences: Sentence[];
  dropped: number;
  gaps: { requirementId: string; question: string }[];
  requirements: { id: string; group: string; label: string }[];
}

const BASIS_LABEL: Record<Sentence['basis'], string> = { resume: '이력서', answer: '내 메모·답변', posting: '공고' };

function toResult(data: Json): AnswerResult {
  const list = (value: unknown) => (Array.isArray(value) ? (value as Json[]) : []);
  return {
    draft: String(data.draft ?? ''),
    charCount: Number(data.char_count ?? 0),
    limit: typeof data.limit === 'number' ? data.limit : null,
    sentences: list(data.sentences).map((s) => ({
      text: String(s.text ?? ''),
      basis: (['resume', 'answer', 'posting'].includes(String(s.basis)) ? s.basis : 'resume') as Sentence['basis'],
      quote: String(s.quote ?? ''),
      requirementIds: Array.isArray(s.requirement_ids) ? (s.requirement_ids as string[]) : [],
    })),
    dropped: Number(data.dropped ?? 0),
    gaps: list(data.gaps).map((g) => ({ requirementId: String(g.requirement_id ?? ''), question: String(g.question ?? '') })),
    requirements: list(data.requirements).map((r) => ({
      id: String(r.id ?? ''),
      group: String(r.group ?? ''),
      label: String(r.label ?? ''),
    })),
  };
}

export function QuestionAnswers({ resumeId, tailoredId, editId }: { resumeId: string; tailoredId: string; editId: string }) {
  const resume = useResume(editId);
  /**
   * 가장 최근 본문. 여러 문항이 한꺼번에 저장하면(메모에서 나가며 다른 카드의 초안을 누를 때) 화면이 다시 그려지기
   * 전이라 둘 다 옛 본문을 들고 있다가 서로의 메모를 덮는다. 저장할 때마다 여기에 이어 쓴다.
   */
  const latest = useRef<ResumeContent | null>(null);
  if (resume === undefined) return <p className="hint">자소서를 불러오고 있어요…</p>;
  latest.current = resume.content;
  const questions = resume.content.companyQuestions ?? [];
  if (questions.length === 0) return <p className="hint">이 자소서에는 문항이 없어요.</p>;

  // 답 · 메모 · 질문 답은 content.companyQuestions 안에 담는다(표 · migration 변경 없음)
  const update = (id: string, patch: Partial<ResumeCompanyQuestion>) => {
    const base = latest.current ?? resume.content;
    const next = {
      ...base,
      companyQuestions: (base.companyQuestions ?? []).map((q) => (q.id === id ? { ...q, ...patch } : q)),
    };
    latest.current = next;
    return updateResume(editId, { content: next });
  };

  return (
    <div className="qa-list">
      {questions.map((q, i) => (
        <QuestionAnswerCard
          key={q.id}
          index={i}
          question={q}
          request={(answers) => reviewApi.questionAnswer(resumeId, tailoredId, q.id, answers)}
          onUpdate={(patch) => update(q.id, patch)}
        />
      ))}
    </div>
  );
}

function QuestionAnswerCard({
  index,
  question,
  request,
  onUpdate,
}: {
  index: number;
  question: ResumeCompanyQuestion;
  request(answers: { question: string; answer: string }[]): Promise<Json>;
  onUpdate(patch: Partial<ResumeCompanyQuestion>): Promise<void>;
}) {
  const [text, setText] = useState(question.answer ?? '');
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** 질문에 답한 것 — 다음 초안의 근거가 된다. 저장돼 있어 다시 열어도 이어 간다 */
  const [history, setHistory] = useState<{ question: string; answer: string }[]>(question.notes ?? []);
  const [gapAnswers, setGapAnswers] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle');
  /** 쓰고 싶은 내용 메모 — 키워드만 적어도 된다. 부를 때마다 최신 메모를 근거로 싣는다. 칸에서 나갈 때 저장 */
  const [memo, setMemo] = useState(question.memo ?? '');
  const savedMemo = useRef(question.memo ?? '');
  const saveMemo = (value: string) => {
    if (value === savedMemo.current) return;
    savedMemo.current = value;
    void onUpdate({ memo: value }).catch(() => undefined);
  };

  const limit = question.limit;
  const over = limit !== null && text.length > limit;
  const answeredGaps = (result?.gaps ?? [])
    .map((g) => ({ question: g.question, answer: (gapAnswers[g.question] ?? '').trim() }))
    .filter((g) => g.answer !== '');

  const run = async () => {
    if (busy) return;
    const answered = [...history, ...answeredGaps];
    const note = memo.trim();
    const memoItem = note === '' ? [] : [{ question: `「${question.question}」에 쓰고 싶은 내용 (지원자 메모)`, answer: note }];
    setBusy(true);
    setError(null);
    try {
      const next = toResult(await request([...memoItem, ...answered]));
      setHistory(answered);
      // 쓴 메모와 질문 답을 남긴다 — 다시 열어도 같은 근거로 이어 쓴다
      savedMemo.current = memo;
      void onUpdate({ memo, notes: answered }).catch(() => undefined);
      setGapAnswers({});
      setResult(next);
      // 아직 아무것도 안 쓴 칸이면 초안을 바로 넣는다. 쓴 글이 있으면 덮지 않고 고르게 한다
      if (text.trim() === '') setText(next.draft);
    } catch (err) {
      setError(err instanceof Error ? err.message : '답변을 쓰지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    setSaved('saving');
    try {
      await onUpdate({ answer: text });
      setSaved('saved');
    } catch {
      setSaved('failed');
    }
  };

  const labelOf = (id: string) => result?.requirements.find((r) => r.id === id)?.label ?? id;
  const thin = result !== null && result.limit !== null && result.charCount < result.limit * 0.6;

  return (
    <section className="qa-card">
      <header className="qa-card__head">
        <span className="qa-card__no">{index + 1}</span>
        <strong className="qa-card__question">{question.question}</strong>
        <span className="qa-card__limit">{limit === null ? '글자 수 없음' : `${limit.toLocaleString()}자`}</span>
      </header>

      <div className="qa-memo">
        <label className="apply-label" htmlFor={`qa-memo-${question.id}`}>
          쓰고 싶은 내용 메모{' '}
          <span className="hint">· 키워드만 적어도 돼요. 메모와 이력서에 없는 사실은 붙이지 않아요. 메모는 자동으로 저장돼요</span>
        </label>
        <TextArea
          id={`qa-memo-${question.id}`}
          value={memo}
          rows={2}
          placeholder="예: 마케팅 인턴 때 인스타 운영 맡음, 팔로워 3천→6천, 디자이너랑 매주 회의"
          onChange={(e) => setMemo(e.target.value)}
          onBlur={() => saveMemo(memo)}
        />
      </div>

      <TextArea
        value={text}
        rows={6}
        aria-label={`문항 ${index + 1} 답변`}
        placeholder="AI 초안을 받거나 직접 써 보세요."
        onChange={(e) => {
          setText(e.target.value);
          setSaved('idle');
        }}
      />
      <div className="qa-card__bar">
        <span className={`qa-count${over ? ' is-over' : ''}`}>
          {text.length.toLocaleString()}
          {limit !== null && ` / ${limit.toLocaleString()}자`}
          {over && ' · 글자 수를 넘었어요'}
        </span>
        <span className="spacer" />
        <Button variant="outline" size="sm" onClick={() => void run()} disabled={busy}>
          <Icon name="auto_fix_high" size={16} />
          {busy ? '쓰는 중…' : result !== null ? '다시 쓰기' : memo.trim() !== '' ? '메모로 쓰기' : 'AI 초안 쓰기'}
        </Button>
        <Button size="sm" onClick={() => void save()} disabled={saved === 'saving' || text.trim() === '' || over}>
          <Icon name={saved === 'saved' ? 'check' : 'save'} size={16} />
          {saved === 'saving' ? '저장 중…' : saved === 'saved' ? '저장됨' : '저장'}
        </Button>
      </div>
      {saved === 'failed' && <p className="apply-error">저장하지 못했어요. 다시 눌러 주세요.</p>}
      {error !== null && <p className="apply-error">{error}</p>}

      {result !== null && (
        <div className="qa-result">
          <div className="qa-result__head">
            <span className="apply-label">AI 초안 · 근거</span>
            <span className="hint">
              {result.charCount.toLocaleString()}
              {result.limit !== null && ` / ${result.limit.toLocaleString()}자`}
              {result.dropped > 0 && ` · 근거를 확인하지 못한 문장 ${result.dropped}개는 뺐어요`}
            </span>
            <span className="spacer" />
            {result.draft !== '' && result.draft !== text && (
              <Button variant="text" size="sm" onClick={() => setText(result.draft)}>
                이 초안으로 바꾸기
              </Button>
            )}
          </div>
          {result.sentences.length === 0 ? (
            <p className="hint">이력서에서 이 문항에 쓸 근거를 찾지 못했어요. 아래 질문에 답해 주세요.</p>
          ) : (
            <ol className="qa-sentences">
              {result.sentences.map((s, i) => (
                <li key={i}>
                  <span className={`qa-basis qa-basis--${s.basis}`}>{BASIS_LABEL[s.basis]}</span>
                  <div>
                    <span>{s.text}</span>
                    <q className="qa-quote">{s.quote}</q>
                    {s.requirementIds.length > 0 && (
                      <span className="qa-reqs">
                        {s.requirementIds.map((id) => (
                          <span key={id} className="qa-req">
                            {labelOf(id)}
                          </span>
                        ))}
                      </span>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
          {thin && <p className="apply-note">근거가 모자라 짧게 썼어요. 지어서 채우지 않아요. 아래 질문에 답하면 그 답을 근거로 더 써요.</p>}
          {result.gaps.length > 0 && (
            <div className="qa-gaps">
              <span className="apply-label">더 쓰려면 알려 주세요</span>
              {result.gaps.map((g) => (
                <label key={g.question} className="qa-gap">
                  <span>
                    {g.requirementId !== '' && <span className="qa-req">{labelOf(g.requirementId)}</span>} {g.question}
                  </span>
                  <TextArea
                    rows={2}
                    value={gapAnswers[g.question] ?? ''}
                    placeholder="해 본 적이 없으면 비워 두세요. 없는 경험은 쓰지 않아요."
                    onChange={(e) => setGapAnswers((a) => ({ ...a, [g.question]: e.target.value }))}
                  />
                </label>
              ))}
              <div>
                <Button size="sm" onClick={() => void run()} disabled={busy || answeredGaps.length === 0}>
                  <Icon name="send" size={16} />
                  답하고 다시 쓰기
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
