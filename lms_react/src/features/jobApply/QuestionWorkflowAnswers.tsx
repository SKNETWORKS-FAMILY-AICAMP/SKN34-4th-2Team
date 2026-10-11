import { useRef, useState } from 'react';

import { updateResume, useResume } from '../../data/repository';
import type { ResumeCompanyQuestion, ResumeContent } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Button, TextArea } from '../../ui/components';
import { reviewApi, type Json } from '../resume/review/reviewApi';

/**
 * 공고 맞춤 지원의 문항별 답변 — 문항 전체를 함께 계획하고 쓴다(첨삭 서버 app/question_workflow).
 *
 * 문항 하나씩 쓰던 QuestionAnswers 와 달리 「AI 초안 쓰기」 한 번에 모든 문항을 쓴다. 문항끼리 중심 경험을 나누고,
 * 같은 이야기를 여러 문항에 자세히 쓰면 가장 맞는 문항 하나에만 남기고 나머지는 줄인다 — 무엇을 줄였는지 위에 알린다.
 * 문장마다 이력서 · 내 메모 · 내 답변 · 공고 중 어디서 왔는지 붙고, 재료가 모자라면 답 대신 질문을 낸다.
 * 메모 · 질문 답 · 저장한 답은 사본의 content.companyQuestions 에 담는다(QuestionAnswers 와 같은 자리).
 * 초안은 비어 있는 답 칸에만 넣는다. 쓴 글이 있으면 덮지 않고 「이 초안으로 바꾸기」로 고르게 한다.
 */
type Ref = { kind: 'resume' | 'memo' | 'note' | 'posting'; label: string; text: string };
type Coverage = { total: number; covered: number; unused: string[] };
type Overlap = { story: string; keep: string; others: string[]; unchanged: string[] };
interface Result {
  draft: string;
  charCount: number;
  limit: number | null;
  angle: string;
  questions: string[];
  trimmed: string[];
  /** 다른 문항과 겹치지만 줄이면 너무 짧아져 그대로 둔 이야기 */
  unchanged: string[];
  removed: number;
  sentences: { text: string; sources: Ref[]; requirements: { id: string; label: string }[] }[];
}

const BASIS: Record<Ref['kind'], { label: string; tone: 'resume' | 'answer' | 'posting' }> = {
  resume: { label: '이력서', tone: 'resume' },
  memo: { label: '내 메모', tone: 'answer' },
  note: { label: '내 답변', tone: 'answer' },
  posting: { label: '공고', tone: 'posting' },
};

const list = <T,>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);

function toResult(r: Json): Result {
  return {
    draft: String(r.draft ?? ''),
    charCount: Number(r.char_count ?? 0),
    limit: typeof r.limit === 'number' ? r.limit : null,
    angle: String(r.angle ?? ''),
    questions: list<string>(r.questions),
    trimmed: list<string>(r.trimmed_overlap),
    unchanged: list<string>(r.overlap_unchanged),
    removed: list<unknown>(r.removed).length,
    sentences: list<Json>(r.sentences).map((s) => ({
      text: String(s.text ?? ''), sources: list<Ref>(s.sources), requirements: list<{ id: string; label: string }>(s.requirements),
    })),
  };
}

/** 저장된 질문 답 — 고른 경험(selection)처럼 답이 빈 것은 근거가 아니라 뺀다 */
const savedNotes = (q: ResumeCompanyQuestion) =>
  (q.notes ?? []).filter((n) => n.answer.trim() !== '').map((n) => ({ question: n.question, answer: n.answer }));

export function QuestionWorkflowAnswers({ resumeId, tailoredId, editId }: { resumeId: string; tailoredId: string; editId: string }) {
  const resume = useResume(editId);
  /** 가장 최근 본문 — 여러 칸이 연달아 저장할 때 서로의 변경을 덮지 않도록 여기에 이어 쓴다(QuestionAnswers 와 같은 까닭) */
  const latest = useRef<ResumeContent | null>(null);
  const [memos, setMemos] = useState<Record<string, string>>({});
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [saved, setSaved] = useState<Record<string, 'idle' | 'saving' | 'saved' | 'failed'>>({});
  const [results, setResults] = useState<Record<string, Result>>({});
  const [overlaps, setOverlaps] = useState<Overlap[]>([]);
  /** 공고 필수 요건을 답에 얼마나 담았나 — 이력서에 있는데 안 쓴 요건은 알린다(없는 요건은 문항 질문으로 묻는다) */
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [gapAnswers, setGapAnswers] = useState<Record<string, Record<string, string>>>({});
  /** 'all' = 문항 전체를 쓰는 중, 문항 id = 그 문항만 다시 쓰는 중 */
  const [busy, setBusy] = useState<string | null>(null);
  /** 전체를 쓸 때 받은 계획 — 한 문항만 다시 쓸 때 보내면 계획을 다시 세우지 않는다 */
  const [plan, setPlan] = useState<Json | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (resume === undefined) return <p className="hint">자소서를 불러오고 있어요…</p>;
  latest.current = resume.content;
  const questions = resume.content.companyQuestions ?? [];
  if (questions.length === 0) return <p className="hint">이 자소서에는 문항이 없어요.</p>;

  const memoOf = (q: ResumeCompanyQuestion) => memos[q.id] ?? q.memo ?? '';
  const textOf = (q: ResumeCompanyQuestion) => texts[q.id] ?? q.answer ?? '';

  /** 문항 여러 개를 한 번에 저장한다 */
  const persist = (patches: Record<string, Partial<ResumeCompanyQuestion>>) => {
    const base = latest.current ?? resume.content;
    const next = {
      ...base,
      companyQuestions: (base.companyQuestions ?? []).map((q) => (patches[q.id] ? { ...q, ...patches[q.id] } : q)),
    };
    latest.current = next;
    return updateResume(editId, { content: next });
  };

  const answered = (qid: string) =>
    Object.entries(gapAnswers[qid] ?? {}).filter(([, a]) => a.trim() !== '').map(([question, a]) => ({ question, answer: a.trim() }));

  /** only 가 없으면 문항 전체, 있으면 그 문항만 다시 쓴다 — 다른 카드 · 한 벌 알림은 그대로 둔다 */
  const run = async (only?: string) => {
    if (busy !== null) return;
    const touched = only === undefined ? questions : questions.filter((q) => q.id === only);
    const notes = Object.fromEntries(questions.map((q) => [q.id, [...savedNotes(q), ...answered(q.id)]]));
    setBusy(only ?? 'all');
    setError(null);
    try {
      const data = await reviewApi.questionWorkflow(resumeId, tailoredId,
        questions.map((q) => ({ id: q.id, memo: memoOf(q), notes: notes[q.id] })),
        only === undefined ? {} : { only, plan });
      const next: Record<string, Result> = {};
      for (const r of list<Json>(data.questions)) next[String(r.question_id)] = toResult(r);
      // 메모 · 질문 답은 남긴다 — 다시 열어도 같은 근거로 이어 쓴다. 빈 답 칸에는 초안을 넣어 둔다(저장은 「저장」을 눌러야)
      await persist(Object.fromEntries(touched.map((q) => [q.id, {
        memo: memoOf(q),
        notes: [...(q.notes ?? []), ...answered(q.id).map((n) => ({ ...n, source_type: 'answer' as const }))],
      }])));
      setTexts((t) => ({ ...t, ...Object.fromEntries(touched.map((q) => {
        const current = t[q.id] ?? q.answer ?? '';
        return [q.id, current.trim() === '' ? next[q.id]?.draft ?? '' : current];
      })) }));
      setResults((r) => (only === undefined ? next : { ...r, ...next }));
      setGapAnswers((a) => (only === undefined ? {} : { ...a, [only]: {} }));
      if (data.plan !== undefined && data.plan !== null) setPlan(data.plan as Json);
      if (only === undefined) {
        setOverlaps(list<Overlap>(data.overlaps).map((o) => ({ ...o, others: list<string>(o.others), unchanged: list<string>(o.unchanged) })));
        const cov = (data.coverage ?? {}) as Json;
        const musts = list<Json>(cov.requirements).filter((r) => r.group === 'must');
        setCoverage({ total: musts.length, covered: musts.filter((r) => r.covered === true).length,
          unused: list<Json>(cov.unused_must).map((u) => String(u.label ?? '')) });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '답변을 쓰지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(null);
    }
  };

  const save = async (q: ResumeCompanyQuestion) => {
    setSaved((s) => ({ ...s, [q.id]: 'saving' }));
    try {
      await persist({ [q.id]: { answer: textOf(q) } });
      setSaved((s) => ({ ...s, [q.id]: 'saved' }));
    } catch {
      setSaved((s) => ({ ...s, [q.id]: 'failed' }));
    }
  };

  const no = (id: string) => questions.findIndex((q) => q.id === id) + 1;
  const hasResult = Object.keys(results).length > 0;

  return (
    <div className="qa-list">
      <div className="qw-run">
        <Button onClick={() => void run()} disabled={busy !== null}>
          <Icon name="auto_fix_high" size={18} />
          {busy === 'all' ? `문항 ${questions.length}개를 함께 쓰는 중… (1~3분)` : hasResult ? '문항 전체 다시 쓰기' : 'AI 초안 쓰기'}
        </Button>
        <span className="hint">문항 전체를 함께 보고, 문항끼리 같은 경험이 겹치지 않게 나눠 써요. 메모를 먼저 적으면 그 내용으로 써요.</span>
      </div>
      {error !== null && <p className="apply-error">{error}</p>}
      {coverage !== null && coverage.total > 0 && (
        <p className="hint">
          공고 필수 요건 {coverage.total}개 중 {coverage.covered}개를 답에 담았어요.
          {coverage.unused.length > 0 &&
            ` 아직 어느 답에도 안 들어간 필수 요건 ${coverage.unused.map((u) => `「${u}」`).join(' ')} — 이력서에는 관련 내용이 있어요. 넣고 싶은 문항의 메모에 적어 주세요.`}
        </p>
      )}
      {overlaps.length > 0 && (
        <div className="apply-note qw-overlap">
          {overlaps.map((o) => (
            <p key={o.story}>
              「{o.story}」 이야기는 {no(o.keep)}번에 자세히 썼어요.
              {o.others.length > 0 && ` ${o.others.map(no).join(' · ')}번에서는 줄였어요.`}
              {o.unchanged.length > 0 && ` ${o.unchanged.map(no).join(' · ')}번은 줄이면 너무 짧아져 그대로 뒀어요.`}
              {' '}다른 경험으로 바꾸고 싶으면 그 문항 메모에 쓰고 싶은 경험을 적고 다시 써 주세요.
            </p>
          ))}
        </div>
      )}

      {questions.map((q, i) => {
        const result = results[q.id];
        const text = textOf(q);
        const over = q.limit !== null && text.length > q.limit;
        const state = saved[q.id];
        return (
          <section key={q.id} className="qa-card">
            <header className="qa-card__head">
              <span className="qa-card__no">{i + 1}</span>
              <strong className="qa-card__question">{q.question}</strong>
              <span className="qa-card__limit">{q.limit === null ? '글자 수 없음' : `${q.limit.toLocaleString()}자`}</span>
            </header>

            <div className="qa-memo">
              <label className="apply-label" htmlFor={`qw-memo-${q.id}`}>
                쓰고 싶은 내용 메모 <span className="hint">· 키워드만 적어도 돼요. 메모와 이력서에 없는 사실은 붙이지 않아요</span>
              </label>
              <TextArea id={`qw-memo-${q.id}`} rows={2} value={memoOf(q)}
                placeholder="예: LMS 프로젝트 API 오류 3일 붙잡음 / 요청 형식 불일치가 원인 / contract 문서로 공유"
                onChange={(e) => setMemos((m) => ({ ...m, [q.id]: e.target.value }))}
                onBlur={() => { if (memoOf(q) !== (q.memo ?? '')) void persist({ [q.id]: { memo: memoOf(q) } }).catch(() => undefined); }} />
            </div>

            <TextArea rows={7} value={text} aria-label={`문항 ${i + 1} 답변`} placeholder="AI 초안을 받거나 직접 써 보세요."
              onChange={(e) => {
                setTexts((t) => ({ ...t, [q.id]: e.target.value }));
                setSaved((s) => ({ ...s, [q.id]: 'idle' }));
              }} />
            <div className="qa-card__bar">
              <span className={`qa-count${over ? ' is-over' : ''}`}>
                {text.length.toLocaleString()}{q.limit !== null && ` / ${q.limit.toLocaleString()}자`}{over && ' · 글자 수를 넘었어요'}
              </span>
              <span className="spacer" />
              {hasResult && (
                <Button variant="outline" size="sm" onClick={() => void run(q.id)} disabled={busy !== null}>
                  <Icon name="auto_fix_high" size={16} />
                  {busy === q.id ? '이 문항 쓰는 중…' : '이 문항만 다시 쓰기'}
                </Button>
              )}
              <Button size="sm" onClick={() => void save(q)} disabled={state === 'saving' || text.trim() === '' || over}>
                <Icon name={state === 'saved' ? 'check' : 'save'} size={16} />
                {state === 'saving' ? '저장 중…' : state === 'saved' ? '저장됨' : '저장'}
              </Button>
            </div>
            {state === 'failed' && <p className="apply-error">저장하지 못했어요. 다시 눌러 주세요.</p>}

            {result !== undefined && (
              <div className="qa-result">
                {result.angle !== '' && <p className="hint">이 답에서 보여 줄 것: {result.angle}</p>}
                {result.trimmed.length > 0 && (
                  <p className="hint">다른 문항과 겹쳐 줄인 이야기: {result.trimmed.map((t) => `「${t}」`).join(' ')}</p>
                )}
                {result.unchanged.length > 0 && (
                  <p className="hint">
                    다른 문항과 겹친 이야기 {result.unchanged.map((t) => `「${t}」`).join(' ')} — 줄이면 답이 너무 짧아져 그대로 뒀어요.
                    다른 경험을 쓰려면 메모에 적어 주세요.
                  </p>
                )}
                <div className="qa-result__head">
                  <span className="apply-label">AI 초안 · 근거</span>
                  <span className="hint">
                    {result.charCount.toLocaleString()}{result.limit !== null && ` / ${result.limit.toLocaleString()}자`}
                    {result.removed > 0 && ` · 근거를 확인하지 못한 문장 ${result.removed}개는 뺐어요`}
                  </span>
                  <span className="spacer" />
                  {result.draft !== '' && result.draft !== text && (
                    <Button variant="text" size="sm" onClick={() => setTexts((t) => ({ ...t, [q.id]: result.draft }))}>
                      이 초안으로 바꾸기
                    </Button>
                  )}
                </div>
                {result.sentences.length === 0 ? (
                  <p className="hint">이 문항에 쓸 재료가 모자라요. 아래 질문에 답해 주시면 그걸로 써 볼게요.</p>
                ) : (
                  <ol className="qa-sentences">
                    {result.sentences.map((s, k) => {
                      const basis = BASIS[s.sources[0]?.kind ?? 'resume'];
                      return (
                        <li key={k}>
                          <span className={`qa-basis qa-basis--${basis.tone}`}>{basis.label}</span>
                          <div>
                            <span>{s.text}</span>
                            {s.sources.map((ref, r) => <q key={r} className="qa-quote">{ref.text}</q>)}
                            {s.requirements.length > 0 && (
                              <span className="qa-reqs">
                                {s.requirements.map((r) => <span key={r.id} className="qa-req">{r.label}</span>)}
                              </span>
                            )}
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                )}
                {result.questions.length > 0 && (
                  <div className="qa-gaps">
                    <span className="apply-label">더 쓰려면 알려 주세요</span>
                    {result.questions.map((question) => (
                      <label key={question} className="qa-gap">
                        <span>{question}</span>
                        <TextArea rows={2} value={gapAnswers[q.id]?.[question] ?? ''}
                          placeholder="해 본 적이 없으면 비워 두세요. 없는 경험은 쓰지 않아요."
                          onChange={(e) => setGapAnswers((a) => ({ ...a, [q.id]: { ...(a[q.id] ?? {}), [question]: e.target.value } }))} />
                      </label>
                    ))}
                    <div>
                      <Button size="sm" onClick={() => void run(q.id)} disabled={busy !== null || answered(q.id).length === 0}>
                        <Icon name="send" size={16} />
                        {busy === q.id ? '이 문항 쓰는 중…' : '답하고 이 문항 다시 쓰기'}
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
