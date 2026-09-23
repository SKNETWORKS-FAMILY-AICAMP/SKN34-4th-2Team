import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';

import { resumeEditPath } from '../../../app/routePaths';
import { applyBootstrap } from '../../../data/repository';
import { Icon } from '../../../ui/Icon';
import './review.css';
import type { ReviewDockStatus } from './reviewSession';
import { ReviewWindow, type ReviewWindowProps } from './ReviewWindow';

/**
 * 첨삭 창을 앱 맨 위 층에 띄우고, 기다리는 동안 아래 막대로 내려둔다 — review_dock.dart.
 *
 * 첨삭 한 번이 40~70초 걸린다. 대화 상자로 띄우면 그동안 앱이 막히고, 닫으면 진행 중인 결과를 잃는다.
 * 그래서 창을 화면(route)이 아니라 이 층에 올린다. 화면을 옮겨도 창이 살아 있어 요청과 대화가 남는다.
 */

export interface DockScope {
  minimized: boolean;
  minimize(): void;
  close(result?: string): void;
  report(status: ReviewDockStatus): void;
}

export type OpenReviewOptions = Omit<ReviewWindowProps, 'dock'>;

interface DockContextValue {
  openReview(key: string, options: OpenReviewOptions): void;
}

const DockContext = createContext<DockContextValue | null>(null);

export function useReviewDock(): DockContextValue {
  const value = useContext(DockContext);
  if (value === null) throw new Error('ReviewDockHost 밖에서 첨삭 창을 열 수 없습니다.');
  return value;
}

const IDLE: ReviewDockStatus = {
  title: '이력서 첨삭',
  subtitle: '',
  busy: false,
  stageLabel: null,
  stageIndex: null,
  stageCount: null,
  failed: false,
};

export function ReviewDockHost({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [panel, setPanel] = useState<{ key: string; options: OpenReviewOptions } | null>(null);
  const [minimized, setMinimized] = useState(false);
  const [status, setStatus] = useState<ReviewDockStatus>(IDLE);
  const [busySince, setBusySince] = useState<number | null>(null);
  const [lastElapsed, setLastElapsed] = useState(0);
  /** 내려둔 동안 끝났다. 막대를 초록으로 바꾸고 「열기」를 보인다 */
  const [finishedWhileMinimized, setFinishedWhileMinimized] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [, tick] = useState(0);
  const statusRef = useRef(status);
  const minimizedRef = useRef(minimized);
  const busySinceRef = useRef(busySince);
  statusRef.current = status;
  minimizedRef.current = minimized;
  busySinceRef.current = busySince;

  const openReview = useCallback(
    (key: string, options: OpenReviewOptions) => {
      if (panel !== null) {
        setMinimized(false);
        if (panel.key !== key) setNotice('진행 중인 첨삭 창이 있어요. 그 창을 닫은 뒤에 새로 열 수 있어요.');
        return;
      }
      setPanel({ key, options });
      setMinimized(false);
      setFinishedWhileMinimized(false);
      setStatus(IDLE);
      setBusySince(null);
      setLastElapsed(0);
    },
    [panel],
  );

  const close = useCallback(
    (result?: string) => {
      setPanel(null);
      setMinimized(false);
      setFinishedWhileMinimized(false);
      // 공고 맞춤 첨삭을 마치면 편집기로 옮긴 이력서를 연다. 창을 내려두고 다른 화면에 있어도 간다
      void applyBootstrap().then(() => {
        if (result !== undefined && result !== '') navigate(resumeEditPath(result));
      });
    },
    [navigate],
  );

  const report = useCallback((next: ReviewDockStatus) => {
    const wasBusy = statusRef.current.busy;
    // 한 번에 여러 번 알려 올 수 있어 그리기 전에 ref 를 먼저 고친다
    if (next.busy && !wasBusy) {
      busySinceRef.current = Date.now();
      setBusySince(busySinceRef.current);
      setFinishedWhileMinimized(false);
    }
    if (!next.busy && wasBusy) {
      if (busySinceRef.current !== null) setLastElapsed(Date.now() - busySinceRef.current);
      busySinceRef.current = null;
      setBusySince(null);
      if (minimizedRef.current) setFinishedWhileMinimized(true);
    }
    statusRef.current = next;
    setStatus(next);
  }, []);

  // 내려둔 막대의 경과 시간을 1초마다 새로 그린다. 창이 펼쳐져 있으면 멈춘다
  useEffect(() => {
    if (!(minimized && status.busy)) return;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [minimized, status.busy]);

  useEffect(() => {
    if (notice === null) return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const scope = useMemo<DockScope>(
    () => ({
      minimized,
      minimize: () => setMinimized(true),
      close,
      report,
    }),
    [minimized, close, report],
  );

  const value = useMemo(() => ({ openReview }), [openReview]);

  return (
    <DockContext.Provider value={value}>
      {children}
      {panel !== null && (
        <>
          {!minimized && <div className="rv-barrier" />}
          {/* 내려둬도 창을 치우지 않는다. 치우면 진행 중인 첨삭과 대화가 사라진다 */}
          <div className="rv-layer" hidden={minimized}>
            <ReviewWindow key={panel.key} {...panel.options} dock={scope} />
          </div>
          {minimized && (
            <ReviewDockBar
              status={status}
              finished={finishedWhileMinimized}
              elapsed={busySince === null ? lastElapsed : Date.now() - busySince}
              onOpen={() => {
                setMinimized(false);
                setFinishedWhileMinimized(false);
              }}
            />
          )}
        </>
      )}
      {notice !== null && (
        <div className="rv-notice" role="status">
          {notice}
        </div>
      )}
    </DockContext.Provider>
  );
}

function clock(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

/** 내려둔 첨삭 창. 오른쪽 아래 학생 챗봇 로봇 옆에 놓는다 */
function ReviewDockBar({
  status,
  finished,
  elapsed,
  onOpen,
}: {
  status: ReviewDockStatus;
  finished: boolean;
  elapsed: number;
  onOpen(): void;
}) {
  const failed = finished && status.failed;
  const tone = failed ? 'error' : finished ? 'success' : 'primary';
  const title = failed
    ? `${status.title} 중 문제가 생겼어요`
    : finished
      ? `${status.title} 완료`
      : status.busy
        ? `${status.title} 중`
        : status.title;
  const detail = failed
    ? '창을 열어 다시 시도해 주세요'
    : finished
      ? '결과를 확인해 주세요'
      : status.busy
        ? [
            status.stageIndex !== null && status.stageCount !== null ? `${status.stageIndex + 1}/${status.stageCount}` : null,
            status.stageLabel ?? '진행 중',
          ]
            .filter((v) => v !== null)
            .join(' · ')
        : status.subtitle === ''
          ? '창을 내려두었어요'
          : status.subtitle;
  // 단계를 모르는 기다림(답변 검토 등)만 계속 흐르는 막대로 그린다
  const progress = finished
    ? 1
    : !status.busy
      ? 0
      : status.stageIndex !== null && (status.stageCount ?? 0) > 0
        ? (status.stageIndex + 0.5) / status.stageCount!
        : null;

  return (
    <div className="rv-dockbar-wrap">
      <div
        className={`rv-dockbar is-${tone}${finished ? ' is-finished' : ''}`}
        role="status"
        aria-live="polite"
        aria-label={`${title}, ${detail}`}
        onClick={onOpen}
      >
        <div className="rv-dockbar__row">
          <span className="rv-dockbar__icon">
            {finished ? (
              <Icon name={failed ? 'priority_high' : 'check'} size={18} />
            ) : status.busy ? (
              <span className="rv-spinner" />
            ) : (
              <Icon name="auto_awesome" size={18} />
            )}
          </span>
          <span className="rv-dockbar__text">
            <span className="rv-dockbar__title">
              <strong>{title}</strong>
              {(status.busy || finished) && <span className="rv-dockbar__clock">{clock(elapsed)}</span>}
            </span>
            <span className="rv-dockbar__detail">{detail}</span>
          </span>
          {finished ? (
            <button type="button" className={`btn btn--filled btn--sm rv-dockbar__open is-${tone}`} onClick={onOpen}>
              열기
            </button>
          ) : (
            <button type="button" className="btn btn--text btn--sm" onClick={onOpen}>
              펼치기
            </button>
          )}
        </div>
        <div className="rv-dockbar__progress">
          {progress === null ? (
            <i className="is-indeterminate" />
          ) : (
            <i style={{ width: `${progress * 100}%` }} />
          )}
        </div>
      </div>
    </div>
  );
}
