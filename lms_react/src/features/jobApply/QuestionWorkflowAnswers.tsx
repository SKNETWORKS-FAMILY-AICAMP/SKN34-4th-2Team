import { useEffect, useRef, useState } from 'react';

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
  /** 같은 묶음이 모두 비어 질문을 모아 둔 앞 하위 문항 id — 거기 답하면 이 문항도 같이 쓴다 */
  questionsOn: string;
  /** 다른 문항과 겹치지만 줄이면 너무 짧아져 그대로 둔 이야기 */
  unchanged: string[];
  removed: number;
  sentences: { text: string; sources: Ref[]; requirements: { id: string; label: string }[] }[];
  /** 서버가 준 문장 그대로(근거 · 요건 id 포함) — 문항 전체 쓰기의 마지막 한 벌 점검에 돌려보낸다 */
  raw: Json[];
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
    questionsOn: String(r.questions_on ?? ''),
    unchanged: list<string>(r.overlap_unchanged),
    removed: list<unknown>(r.removed).length,
    sentences: list<Json>(r.sentences).map((s) => ({
      text: String(s.text ?? ''), sources: list<Ref>(s.sources), requirements: list<{ id: string; label: string }>(s.requirements),
    })),
    raw: list<Json>(r.sentences),
  };
}

/**
 * 한 문항을 쓰는 동안 보여 줄 단계와 보통 끝나는 시점(초). 서버는 한 번에 결과를 돌려줘서 그 안의 단계는 받지 못한다 —
 * 2026-10-12 시간 재기(문항 하나 60~85초)로 어림한 순서다. 멈춘 것처럼 보이지 않게 하는 게 목적.
 */
const STEPS_ONE = [
  { label: '쓰는 중', until: 20 },
  { label: '근거 · 빠진 내용 검토', until: 35 },
  { label: '필요하면 다시 쓰고 검토', until: 60 },
  { label: '읽기 좋게 다듬는 중', until: 80 },
];
const PLAN_STEP = { label: '문항 뼈대 세우는 중', until: 30 };

/** 지난 초 — 쓰는 동안 1초마다 */
function useSeconds() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return seconds;
}

function WorkingSteps({ planned }: { planned: boolean }) {
  const seconds = useSeconds();
  const steps = planned ? STEPS_ONE : [PLAN_STEP, ...STEPS_ONE.map((st) => ({ ...st, until: st.until + PLAN_STEP.until }))];
  const total = steps[steps.length - 1].until;
  const now = Math.max(0, steps.findIndex((st) => seconds < st.until));
  const current = seconds >= total ? steps.length - 1 : now;
  return (
    <div className="qw-steps" role="status" aria-live="polite">
      <ol>
        {steps.map((st, k) => (
          <li key={st.label} className={k < current ? 'is-done' : k === current ? 'is-now' : ''}>
            <Icon name={k < current ? 'check_circle' : k === current ? 'progress_activity' : 'radio_button_unchecked'} size={15} />
            {st.label}
          </li>
        ))}
      </ol>
      <span className="hint">
        {seconds}초 지남 · {seconds < total ? `보통 ${Math.round(total / 10) * 10}초쯤 걸려요` : '조금 더 걸리고 있어요. 창을 닫지 말고 기다려 주세요'}
      </span>
    </div>
  );
}

const SET_STEPS: { at: 'plan' | 'write' | 'finish'; label: string }[] = [
  { at: 'plan', label: '문항 전체 뼈대 세우는 중' },
  { at: 'write', label: '문항마다 쓰고 검토' },
  { at: 'finish', label: '문항끼리 겹침 · 공고 필수 요건 점검' },
];

/** 문항 전체를 쓰는 동안 — 화면이 단계마다 따로 부르므로 지금 단계와 다 쓴 문항 수를 그대로 보여 준다 */
function SetSteps({ step }: { step: { at: 'plan' | 'write' | 'finish'; done: number; total: number } }) {
  const seconds = useSeconds();
  const current = SET_STEPS.findIndex((st) => st.at === step.at);
  return (
    <div className="qw-steps" role="status" aria-live="polite">
      <ol>
        {SET_STEPS.map((st, k) => (
          <li key={st.at} className={k < current ? 'is-done' : k === current ? 'is-now' : ''}>
            <Icon name={k < current ? 'check_circle' : k === current ? 'progress_activity' : 'radio_button_unchecked'} size={15} />
            {st.label}
            {st.at === 'write' && step.total > 0 && ` ${step.done}/${step.total}`}
          </li>
        ))}
      </ol>
      <span className="hint">{seconds}초 지남 · 보통 2~3분 걸려요. 다 쓴 문항부터 아래에 보여요.</span>
    </div>
  );
}

/** 키워드만 적은 답(「밴드부 키보드」) — 막지는 않고 더 적어 달라고만 한다 */
const BRIEF_CHARS = 15;
const isBrief = (answer: string) => {
  const n = answer.replace(/\s/g, '').length;
  return n > 0 && n < BRIEF_CHARS;
};

/** 저장된 질문 답 — 고른 경험(selection)처럼 답이 빈 것은 근거가 아니라 뺀다 */
const savedNotes = (q: ResumeCompanyQuestion) =>
  (q.notes ?? []).filter((n) => n.answer.trim() !== '').map((n) => ({ question: n.question, answer: n.answer }));

/** 쓰는 중인지 · 실패했는지 · 무엇을 쓰는지 — 자소서 쓰기 창이 내려둔 막대에 보여 준다 */
export interface WritingStatus {
  busy: boolean;
  failed: boolean;
  label: string;
}

export function QuestionWorkflowAnswers({ resumeId, tailoredId, editId, onStatus }: {
  resumeId: string; tailoredId: string; editId: string;
  onStatus?(status: WritingStatus): void;
}) {
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
  /** 문항 전체를 쓰는 동안 지금 단계 — 계획 → 문항 쓰기(다 쓴 수/전체) → 한 벌 점검 */
  const [setStep, setSetStep] = useState<{ at: 'plan' | 'write' | 'finish'; done: number; total: number } | null>(null);
  /** 전체를 쓸 때 받은 계획 — 한 문항만 다시 쓸 때 보내면 계획을 다시 세우지 않는다 */
  const [plan, setPlan] = useState<Json | null>(null);
  /** 공고가 마감됐는지 — 자소서는 마감 뒤에도 쓰고 고친다(서버가 알려 준다) */
  const [jobClosed, setJobClosed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const count = resume?.content.companyQuestions?.length ?? 0;
  const busyNo = busy === null || busy === 'all' ? 0 : (resume?.content.companyQuestions ?? []).findIndex((q) => q.id === busy) + 1;
  useEffect(() => {
    onStatus?.({
      busy: busy !== null,
      failed: error !== null,
      label: busy === 'all' ? `문항 ${count}개를 함께 쓰는 중` : busy !== null ? `${busyNo}번 문항 쓰는 중` : '',
    });
  }, [busy, error, count, busyNo, onStatus]);

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
  /**
   * 받은 답을 화면에 넣는다. 빈 답 칸에는 초안을 넣는다(저장은 「저장」을 눌러야).
   * drafted(앞서 넣은 답)가 있으면 한 벌 점검이 다시 쓴 답이다 — 답 칸이 앞 답 그대로면 새 답으로 바꾼다
   */
  const show = (data: Json, drafted?: Record<string, Result>) => {
    const next: Record<string, Result> = {};
    for (const r of list<Json>(data.questions)) next[String(r.question_id)] = toResult(r);
    setTexts((t) => ({ ...t, ...Object.fromEntries(questions.filter((q) => q.id in next).map((q) => {
      const current = t[q.id] ?? q.answer ?? '';
      const untouched = current.trim() === '' || (drafted !== undefined && current === drafted[q.id]?.draft);
      return [q.id, untouched ? next[q.id]?.draft ?? '' : current];
    })) }));
    setResults((r) => ({ ...r, ...next }));
    if (data.plan !== undefined && data.plan !== null) setPlan(data.plan as Json);
    if (data.job_closed === true) setJobClosed(true);
    return next;
  };

  /** 메모 · 질문 답은 남긴다 — 다시 열어도 같은 근거로 이어 쓴다 */
  const keepNotes = async (ids: string[]) => {
    const touched = questions.filter((q) => ids.includes(q.id));
    await persist(Object.fromEntries(touched.map((q) => [q.id, {
      memo: memoOf(q),
      notes: [...(q.notes ?? []), ...answered(q.id).map((n) => ({ ...n, source_type: 'answer' as const }))],
    }])));
    setGapAnswers((a) => ({ ...a, ...Object.fromEntries(touched.map((q) => [q.id, {}])) }));
  };

  /**
   * only 가 있으면 그 문항만 다시 쓴다. 없으면 문항 전체 — 계획 → 문항(묶음)마다 동시에 → 한 벌 점검, 세 번에 나눠 부른다.
   * 한 요청에 다 하면 겹침 다시 쓰기까지 200초를 넘겨 운영 nginx(210초)에 끊길 수 있었다(2026-10-12).
   */
  const run = async (only?: string) => {
    if (busy !== null) return;
    const notes = Object.fromEntries(questions.map((q) => [q.id, [...savedNotes(q), ...answered(q.id)]]));
    // 답 칸의 지금 글도 보낸다 — 문항별로 쓸 때 다른 문항에 이미 쓴 이야기를 되풀이하지 않게
    const items = questions.map((q) => ({ id: q.id, memo: memoOf(q), notes: notes[q.id], written: textOf(q) }));
    const call = (options: Parameters<typeof reviewApi.questionWorkflow>[3]) =>
      reviewApi.questionWorkflow(resumeId, tailoredId, items, options);
    setBusy(only ?? 'all');
    setError(null);
    try {
      if (only !== undefined) {
        const next = show(await call({ only, plan }));
        await keepNotes(Object.keys(next));
        return;
      }
      setSetStep({ at: 'plan', done: 0, total: 0 });
      const planned = await call({ stage: 'plan' });
      const fullPlan = (planned.plan ?? null) as Json | null;
      setPlan(fullPlan);
      setResults({});
      setOverlaps([]);
      setCoverage(null);
      // 같은 묶음은 한 요청이 차례로 쓴다(뒤 하위 문항이 앞 답을 보고 이어 쓴다) — 묶음 첫 문항으로 부른다
      const heads = questions.filter((q, i) => !q.group || questions.findIndex((o) => o.group === q.group) === i).map((q) => q.id);
      setSetStep({ at: 'write', done: 0, total: heads.length });
      const settled = await Promise.allSettled(heads.map((qid) => call({ only: qid, plan: fullPlan }).then((data) => {
        setSetStep((st) => (st === null ? st : { ...st, done: st.done + 1 }));
        return show(data);
      })));
      const drafted: Record<string, Result> = {};
      const answers: Record<string, Json> = {};
      for (const one of settled) {
        if (one.status !== 'fulfilled') continue;
        for (const [qid, r] of Object.entries(one.value)) {
          drafted[qid] = r;
          answers[qid] = { draft: r.draft, sentences: r.raw, questions: r.questions };
        }
      }
      const failed = settled.find((one): one is PromiseRejectedResult => one.status === 'rejected');
      if (Object.keys(drafted).length === 0) throw failed?.reason ?? new Error('답변을 쓰지 못했어요.');
      await keepNotes(Object.keys(drafted));
      setSetStep((st) => (st === null ? st : { ...st, at: 'finish' }));
      const final = await call({ stage: 'finish', plan: fullPlan, answers });
      show(final, drafted);
      setOverlaps(list<Overlap>(final.overlaps).map((o) => ({ ...o, others: list<string>(o.others), unchanged: list<string>(o.unchanged) })));
      const cov = (final.coverage ?? {}) as Json;
      const musts = list<Json>(cov.requirements).filter((r) => r.group === 'must');
      setCoverage({ total: musts.length, covered: musts.filter((r) => r.covered === true).length,
        unused: list<Json>(cov.unused_must).map((u) => String(u.label ?? '')) });
      if (failed !== undefined) {
        setError(`${heads.length - Object.keys(drafted).length}개 문항은 쓰지 못했어요. 그 문항에서 「AI 초안 쓰기」를 눌러 다시 써 주세요.`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '답변을 쓰지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(null);
      setSetStep(null);
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

  return (
    <div className="qa-list">
      <div className="qw-run">
        <Button variant="outline" onClick={() => void run()} disabled={busy !== null}>
          <Icon name="fact_check" size={18} />
          {busy === 'all' ? `문항 ${questions.length}개를 함께 쓰는 중…` : '문항 전체 한 번에 쓰기 · 점검'}
        </Button>
        <span className="hint">
          초안은 이력서를 바탕으로 쓰고, 메모를 적으면 그 내용을 더해 써요. 다른 문항에 이미 쓴 이야기는 되풀이하지 않아요.
          전체를 한 번에 쓰면 같은 이야기 겹침 · 공고 필수 요건까지 점검해요.
        </span>
      </div>
      {jobClosed && <p className="hint">마감된 공고예요. 마감 당시 공고 요건을 기준으로 쓰고 고쳐요.</p>}
      {busy === 'all' && setStep !== null && <SetSteps step={setStep} />}
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
              <strong className="qa-card__question">
                {q.group && <span className="qw-group">{q.group}</span>}
                {q.question}
              </strong>
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
              <Button variant="outline" size="sm" onClick={() => void run(q.id)} disabled={busy !== null}>
                <Icon name="auto_fix_high" size={16} />
                {busy === q.id ? '이 문항 쓰는 중…'
                  : result !== undefined ? '이 문항 다시 쓰기' : memoOf(q).trim() !== '' ? '메모 반영해 AI 초안 쓰기' : 'AI 초안 쓰기'}
              </Button>
              <Button size="sm" onClick={() => void save(q)} disabled={state === 'saving' || text.trim() === '' || over}>
                <Icon name={state === 'saved' ? 'check' : 'save'} size={16} />
                {state === 'saving' ? '저장 중…' : state === 'saved' ? '저장됨' : '저장'}
              </Button>
            </div>
            {state === 'failed' && <p className="apply-error">저장하지 못했어요. 다시 눌러 주세요.</p>}
            {busy === q.id && <WorkingSteps planned={plan !== null} />}

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
                  <p className="hint">
                    {result.questionsOn !== ''
                      ? `같은 묶음 ${no(result.questionsOn)}번 문항의 질문에 답하면 이 문항도 같이 써요.`
                      : '이 문항에 쓸 재료가 모자라요. 아래 질문에 답해 주시면 그걸로 써 볼게요.'}
                  </p>
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
                    {/* 답에 없는 장면은 지어 넣지 않는다 — 짧게 답하면 문장은 매끄러워도 구체적이지 않다(2026-10-12 시험) */}
                    <p className="hint">
                      한두 줄이면 돼요. 그때 상황 · 내가 한 일 · 결과를 적으면 그 장면이 그대로 글이 돼요.
                      예: 「밴드부 키보드」보다 「밴드부에서 키보드를 맡아 합주 일정을 짜고, 못 온 친구에게 녹음을 공유함」
                    </p>
                    {result.questions.map((question) => {
                      const answer = gapAnswers[q.id]?.[question] ?? '';
                      return (
                        <label key={question} className="qa-gap">
                          <span>{question}</span>
                          <TextArea rows={2} value={answer}
                            placeholder="상황 · 내가 한 일 · 결과를 한두 줄로. 해 본 적이 없으면 비워 두세요."
                            onChange={(e) => setGapAnswers((a) => ({ ...a, [q.id]: { ...(a[q.id] ?? {}), [question]: e.target.value } }))} />
                          {isBrief(answer) && (
                            <span className="qa-gap__nudge">
                              조금만 더 적어 주세요 — 무엇을 어떻게 했는지 들어가야 구체적으로 써져요. 이대로 보내면 문장만 다듬어요.
                            </span>
                          )}
                        </label>
                      );
                    })}
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
