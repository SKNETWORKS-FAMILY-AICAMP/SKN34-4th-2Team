import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';

import { useYieldToOtherWindows } from '../../ui/floatingWindows';
import { Icon } from '../../ui/Icon';
import { reviewApi } from '../resume/review/reviewApi';
import '../resume/review/review.css';
import { requirementRows, type PostingRequirement } from './alignDraft';
import { QuestionWorkflowAnswers, type WritingStatus } from './QuestionWorkflowAnswers';
import './jobApply.css';

/**
 * 공고 맞춤 지원 자소서 쓰기 창 — 이력서 첨삭 창(ReviewDock)과 같은 모양 · 같은 층.
 *
 * 초안 한 문항에 1분 남짓 걸린다. 화면 안에 두면 다른 메뉴로 가는 순간 화면이 사라져 결과를 못 받았다.
 * 그래서 창을 화면(route) 밖 앱 맨 위 층에 띄운다. 「내려두기」로 아래 막대로 접어도 창을 치우지 않아
 * 쓰는 중인 요청이 끝까지 돌고, 끝나면 막대가 초록으로 바뀐다.
 */

export interface WriteTarget {
  resumeId: string;
  tailoredId: string;
  editId: string;
  /** 창 머리 — 자소서 이름 */
  title: string;
  /** 창 머리 아래 줄 — 회사 · 공고 */
  job: string;
  jobId: string;
  /** 2단계에서 이미 불러온 공고 요건. 없으면(「내 자소서」에서 바로 열면) 창이 직접 읽는다 */
  requirements?: PostingRequirement[];
}

interface WriteDockValue {
  openWrite(target: WriteTarget): void;
  /** 창이 열려 있는(내려둔 것 포함) 자소서 */
  writingId: string | null;
}

const WriteDockContext = createContext<WriteDockValue | null>(null);

export function useWriteDock(): WriteDockValue {
  const value = useContext(WriteDockContext);
  if (value === null) throw new Error('WriteDockHost 밖에서 자소서 쓰기 창을 열 수 없습니다.');
  return value;
}

const IDLE: WritingStatus = { busy: false, failed: false, label: '' };

export function WriteDockHost({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<WriteTarget | null>(null);
  const [minimized, setMinimized] = useState(false);
  const [status, setStatus] = useState<WritingStatus>(IDLE);
  const [busySince, setBusySince] = useState<number | null>(null);
  /** 내려둔 동안 끝났다 — 막대를 초록(실패면 빨강)으로 바꾸고 「열기」를 보인다 */
  const [finished, setFinished] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  /** 이 자소서의 공고가 마감됐는가 — 요건을 읽을 때 · 답을 쓸 때 서버가 알려 준다 */
  const [jobClosed, setJobClosed] = useState(false);
  useEffect(() => setJobClosed(false), [target?.editId]);
  const [, tick] = useState(0);
  const statusRef = useRef(status);
  const minimizedRef = useRef(minimized);
  const targetRef = useRef(target);
  statusRef.current = status;
  minimizedRef.current = minimized;
  targetRef.current = target;

  const openWrite = useCallback((next: WriteTarget) => {
    const current = targetRef.current;
    setMinimized(false);
    setFinished(false);
    if (current !== null && current.editId !== next.editId && statusRef.current.busy) {
      setNotice('쓰는 중인 자소서 창이 있어요. 다 쓴 뒤에 다른 자소서를 열 수 있어요.');
      return;
    }
    if (current?.editId !== next.editId) {
      statusRef.current = IDLE;
      setStatus(IDLE);
      setBusySince(null);
    }
    setTarget(next);
  }, []);

  const close = useCallback(() => {
    if (statusRef.current.busy) return;
    setTarget(null);
    setMinimized(false);
    setFinished(false);
  }, []);

  const report = useCallback((next: WritingStatus) => {
    const was = statusRef.current.busy;
    if (next.busy && !was) {
      setBusySince(Date.now());
      setFinished(false);
    }
    if (!next.busy && was) {
      setBusySince(null);
      if (minimizedRef.current) setFinished(true);
    }
    statusRef.current = next;
    setStatus(next);
  }, []);

  // 내려둔 막대의 지난 시간을 1초마다 새로 그린다
  useEffect(() => {
    if (!(minimized && status.busy)) return undefined;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [minimized, status.busy]);

  useEffect(() => {
    if (notice === null) return undefined;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // 첨삭 · 복습 창이 펼쳐지면 이 창은 내려놓는다(늘 창 하나만 펼친다)
  const minimize = useCallback(() => setMinimized(true), []);
  useYieldToOtherWindows('apply-write', target !== null && !minimized, minimize);

  // 첨삭 막대와 함께 내려두면 그 위로 비켜 선다
  const docked = target !== null && minimized;
  useEffect(() => {
    document.body.classList.toggle('aw-docked', docked);
    return () => document.body.classList.remove('aw-docked');
  }, [docked]);

  const value = useMemo(() => ({ openWrite, writingId: target?.editId ?? null }), [openWrite, target]);

  return (
    <WriteDockContext.Provider value={value}>
      {children}
      {target !== null && (
        <>
          {!minimized && <div className="rv-barrier" />}
          {/* 내려둬도 창을 치우지 않는다. 치우면 쓰는 중인 초안 요청이 사라진다 */}
          <div className="rv-layer" hidden={minimized}>
            <div className="rv-window aw-window" role="dialog" aria-modal="true" aria-label="자소서 쓰기">
              <header className="rv-head">
                <Icon name="edit_note" size={20} className="rv-head__icon" />
                <div className="rv-head__text">
                  <strong>{target.title}</strong>
                  <span className="rv-head__job">{target.job}</span>
                </div>
                <button type="button" className="btn btn--outline btn--sm rv-head__minimize" onClick={minimize}>
                  <Icon name="keyboard_arrow_down" size={18} />
                  내려두기
                </button>
                <button type="button" className="icon-btn" aria-label="닫기" title={status.busy ? '쓰는 중에는 닫을 수 없어요. 내려두기를 쓰세요' : '닫기'}
                  disabled={status.busy} onClick={close}>
                  <Icon name="close" size={22} />
                </button>
              </header>
              <div className="aw-body">
                {jobClosed && (
                  <div className="apply-warn" role="note">
                    <span>마감된 공고입니다. 자소서 쓰기 · 다듬기는 미리 사용해 보실 수 있어요(마감 당시 공고 요건 기준).</span>
                  </div>
                )}
                <RequirementBar key={target.editId} jobId={target.jobId} given={target.requirements}
                  onClosed={() => setJobClosed(true)} />
                <QuestionWorkflowAnswers key={target.editId} resumeId={target.resumeId} tailoredId={target.tailoredId}
                  editId={target.editId} onStatus={report} onJobClosed={() => setJobClosed(true)} />
              </div>
            </div>
          </div>
          {minimized && (
            <WriteDockBar
              status={status}
              finished={finished}
              elapsed={busySince === null ? 0 : Date.now() - busySince}
              onOpen={() => {
                setMinimized(false);
                setFinished(false);
              }}
            />
          )}
        </>
      )}
      {notice !== null && <div className="rv-notice" role="status">{notice}</div>}
    </WriteDockContext.Provider>
  );
}

function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** 내려둔 자소서 쓰기 창 — 첨삭 막대와 같은 모양 */
function WriteDockBar({ status, finished, elapsed, onOpen }: {
  status: WritingStatus; finished: boolean; elapsed: number; onOpen(): void;
}) {
  const failed = finished && status.failed;
  const tone = failed ? 'error' : finished ? 'success' : 'primary';
  const title = failed ? '자소서 초안을 쓰지 못했어요' : finished ? '자소서 초안 완료' : status.busy ? '자소서 초안 쓰는 중' : '자소서 쓰기';
  const detail = failed ? '창을 열어 다시 시도해 주세요'
    : finished ? '결과를 확인해 주세요'
      : status.busy ? `${status.label} · 보통 2분 남짓 걸려요` : '창을 내려두었어요';
  return (
    <div className="rv-dockbar-wrap aw-dockbar-wrap">
      <div className={`rv-dockbar is-${tone}${finished ? ' is-finished' : ''}`} role="status" aria-live="polite"
        aria-label={`${title}, ${detail}`} onClick={onOpen}>
        <div className="rv-dockbar__row">
          <span className="rv-dockbar__icon">
            {finished ? <Icon name={failed ? 'priority_high' : 'check'} size={18} />
              : status.busy ? <span className="rv-spinner" /> : <Icon name="edit_note" size={18} />}
          </span>
          <span className="rv-dockbar__text">
            <span className="rv-dockbar__title">
              <strong>{title}</strong>
              {status.busy && <span className="rv-dockbar__clock">{clock(elapsed)}</span>}
            </span>
            <span className="rv-dockbar__detail">{detail}</span>
          </span>
          {finished ? (
            <button type="button" className={`btn btn--filled btn--sm rv-dockbar__open is-${tone}`} onClick={onOpen}>열기</button>
          ) : (
            <button type="button" className="btn btn--text btn--sm" onClick={onOpen}>펼치기</button>
          )}
        </div>
        <div className="rv-dockbar__progress">
          {finished ? <i style={{ width: '100%' }} /> : status.busy ? <i className="is-indeterminate" /> : <i style={{ width: '0%' }} />}
        </div>
      </div>
    </div>
  );
}

const GROUPS: { key: string; label: string }[] = [
  { key: 'must', label: '필수' },
  { key: 'preferred', label: '우대' },
  { key: 'task', label: '주요 업무' },
];

/**
 * 공고 요건 — 창이 화면을 덮어 답을 쓰면서 2단계 요건 목록을 볼 수 없었다. 접어 두고 필요할 때 펼친다.
 * 칩에 마우스를 올리면 공고 원문 구절이 보인다.
 */
function RequirementBar({ jobId, given, onClosed }: { jobId: string; given?: PostingRequirement[]; onClosed?(): void }) {
  const [rows, setRows] = useState<PostingRequirement[] | null>(given ?? null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (given !== undefined || jobId === '') return undefined;
    let alive = true;
    reviewApi.requirements(jobId, true) // 이미 만든 자소서 — 마감된 공고의 요건도 본다
      .then((data) => {
        if (!alive) return;
        setRows(requirementRows(data));
        if (data.job_closed === true) onClosed?.();
      })
      .catch(() => { if (alive) setFailed(true); });
    return () => { alive = false; };
  }, [jobId, given]);
  useEffect(() => { if (given !== undefined) setRows(given); }, [given]);

  if (failed) return <p className="hint aw-reqs">공고 요건을 불러오지 못했어요. 공고 맞춤 지원 2단계에서 볼 수 있어요.</p>;
  if (rows === null) return <p className="hint aw-reqs">공고 요건을 불러오고 있어요…</p>;
  if (rows.length === 0) return null;
  const groups = GROUPS.map((g) => ({ ...g, rows: rows.filter((r) => r.group === g.key) })).filter((g) => g.rows.length > 0);
  return (
    <section className={`aw-reqs${open ? ' is-open' : ''}`}>
      <button type="button" className="aw-reqs__toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <Icon name="checklist" size={18} />
        <strong>공고 요건 보기</strong>
        <span className="hint">{groups.map((g) => `${g.label} ${g.rows.length}`).join(' · ')}</span>
        <Icon name={open ? 'expand_less' : 'expand_more'} size={18} />
      </button>
      {open && (
        <div className="aw-reqs__body">
          {groups.map((g) => (
            <div key={g.key} className="aw-reqs__group">
              <span className={`apply-label apply-label--${g.key}`}>{g.label}</span>
              <ul>
                {g.rows.map((r) => (
                  <li key={r.id} className="aw-req" title={r.postingQuote === '' ? undefined : `공고 원문: ${r.postingQuote}`}>
                    {r.label}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
