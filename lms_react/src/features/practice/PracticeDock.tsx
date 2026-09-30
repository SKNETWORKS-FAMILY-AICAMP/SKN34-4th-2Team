import {
  createContext,
  lazy,
  Suspense,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
  type UIEvent,
} from 'react';
import { useNavigate } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { usePracticeSet } from '../../data/repository';
import { useYieldToOtherWindows } from '../../ui/floatingWindows';
import { Icon } from '../../ui/Icon';
import './practiceDock.css';
import type { ImportedCell } from './notebookFile';
import { RETRY_SET_ID } from './review';

/**
 * 복습 문제 · 연습장 창 — 이력서 첨삭 창(ReviewDock)과 같은 방식으로 화면 위 층에 뜬다.
 *
 * 공부방에서 「문제 풀기」를 누르면 화면을 옮기지 않고 그 위에 창이 열린다. 여러 개를 열면 창 하나에
 * 탭으로 쌓이고, 내려놓으면 화면 아래 막대로 접힌다. 창은 화면(route)이 아니라 이 층에 있어서
 * 다른 화면으로 옮겨도 풀던 코드와 실행 상태가 남는다. 탭마다 파이썬 런타임이 따로 떠서 수를 제한한다.
 *
 * 주소(/study-room/playground?set=)로 들어오는 길도 그대로 둔다 — 새로고침 · 새 탭 · 링크 공유.
 */

const MAX_TABS = 4;

const EmbeddedPlayground = lazy(() =>
  import('./PythonPlaygroundScreen').then((m) => ({ default: m.EmbeddedPlayground })),
);

/**
 * 공부방 노트에서 여는 코드 — 노트마다 탭 하나에 모은다. 노트 코드 블록(「연습장에서 열기」)이나
 * 수업 파일의 그 셀 앞뒤(「수업 파일에서 보기」)를 탭에 없을 때만 덧붙이고 그 셀로 간다.
 */
export interface NoteCodeRequest {
  noteId: string;
  /** 노트 이름 — 「09/11 수업」 */
  title: string;
  /** 탭에 없으면 덧붙일 셀 */
  cells: ImportedCell[];
  /** 이 코드가 든 셀로 간다 */
  focusText: string;
  /** 누를 때마다 다른 값 — 같은 코드를 다시 눌러도 다시 간다 */
  seq: number;
}

export interface OpenPracticeOptions {
  /** 없으면 자유 연습장 */
  setId: string | null;
  /** 이 번호(1부터)의 문제로 바로 간다 */
  focus?: number;
  /** 노트 코드 탭으로 연다(setId 는 null) */
  note?: NoteCodeRequest;
}

interface PracticeTab {
  key: string;
  setId: string | null;
  focus: number;
  note?: NoteCodeRequest;
}

interface PracticeDockValue {
  open(options: OpenPracticeOptions): void;
}

const PracticeDockContext = createContext<PracticeDockValue | null>(null);

/** 창 안의 탭에서 그리는 중인가 — 연습장이 다른 세트를 열 때 화면을 옮기지 않고 탭을 연다 */
const InDockContext = createContext(false);

export function useInPracticeDock(): boolean {
  return useContext(InDockContext);
}

/** 창으로 여는 함수. 창을 둘 수 없는 곳(호스트 밖)이면 null — 그때는 화면으로 간다 */
export function usePracticeDock(): PracticeDockValue | null {
  return useContext(PracticeDockContext);
}

export function practiceUrl({ setId, focus }: OpenPracticeOptions): string {
  if (!setId) return RoutePaths.studyRoomPlayground;
  return `${RoutePaths.studyRoomPlayground}?set=${encodeURIComponent(setId)}${focus ? `&focus=${focus}` : ''}`;
}

/**
 * 복습 문제 · 연습장을 여는 링크. 누르면 창으로 열고, Ctrl · Shift · 가운데 버튼은 예전처럼 새 탭으로 간다.
 */
export function PracticeLink({
  setId,
  focus,
  className,
  children,
  title,
}: OpenPracticeOptions & { className?: string; children: ReactNode; title?: string }) {
  const dock = usePracticeDock();
  const navigate = useNavigate();
  const href = practiceUrl({ setId, focus });
  const onClick = (e: MouseEvent<HTMLAnchorElement>) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    if (dock) dock.open({ setId, focus });
    else navigate(href);
  };
  return (
    <a href={href} className={className} onClick={onClick} title={title}>
      {children}
    </a>
  );
}

export function PracticeDockHost({ children }: { children: ReactNode }) {
  const [tabs, setTabs] = useState<PracticeTab[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [minimized, setMinimized] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const open = useCallback(({ setId, focus = 0, note }: OpenPracticeOptions) => {
    const key = note ? `note:${note.noteId}` : (setId ?? 'free');
    setTabs((current) => {
      // 같은 노트면 새 탭 대신 그 탭에 이번 코드를 덧붙인다
      if (current.some((t) => t.key === key)) return note ? current.map((t) => (t.key === key ? { ...t, note } : t)) : current;
      const next = [...current, { key, setId: note ? null : setId, focus, note }];
      if (next.length <= MAX_TABS) return next;
      // 가장 먼저 연 탭을 닫는다. 탭마다 파이썬이 따로 떠서 많이 열면 브라우저가 무거워진다
      setNotice(`탭은 ${MAX_TABS}개까지 열 수 있어요. 가장 먼저 연 탭을 닫았어요.`);
      return next.slice(next.length - MAX_TABS);
    });
    setActive(key);
    setMinimized(false);
  }, []);

  const closeTab = useCallback((key: string) => {
    setTabs((current) => {
      const index = current.findIndex((t) => t.key === key);
      const next = current.filter((t) => t.key !== key);
      setActive((was) => (was === key ? (next[Math.max(0, index - 1)]?.key ?? null) : was));
      return next;
    });
  }, []);

  const closeAll = useCallback(() => {
    setTabs([]);
    setActive(null);
    setMinimized(false);
  }, []);

  useEffect(() => {
    if (notice === null) return;
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // 첨삭 창이 펼쳐지면 이 창은 내려놓는다(둘이 겹쳐 펼쳐지지 않게)
  const minimizeDock = useCallback(() => setMinimized(true), []);
  useYieldToOtherWindows('practice', tabs.length > 0 && !minimized, minimizeDock);

  // 첨삭 막대와 나란히 놓으려고 알린다(practiceDock.css)
  const docked = tabs.length > 0 && minimized;
  useEffect(() => {
    document.body.classList.toggle('pd-docked', docked);
    return () => document.body.classList.remove('pd-docked');
  }, [docked]);

  const value = useMemo(() => ({ open }), [open]);
  const shown = tabs.find((t) => t.key === active) ?? tabs[0];

  // 노트북을 내리면 탭 줄 아래에 그림자 — 없으면 내용이 탭에서 뚝 잘려 보였다
  const bodyRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const onBodyScroll = useCallback((e: UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('pd-pane')) setScrolled(target.scrollTop > 0);
  }, []);
  useEffect(() => {
    const pane = bodyRef.current?.querySelector<HTMLElement>('.pd-pane:not([hidden])');
    setScrolled((pane?.scrollTop ?? 0) > 0);
  }, [shown?.key, minimized]);

  return (
    <PracticeDockContext.Provider value={value}>
      {children}
      {tabs.length > 0 && (
        <>
          {!minimized && <div className="rv-barrier" />}
          {/* 내려놔도 창을 치우지 않는다. 치우면 풀던 코드와 파이썬 실행 상태가 사라진다 */}
          <div className="rv-layer" hidden={minimized}>
            <section className="pd-window" role="dialog" aria-label="복습 문제 · 연습장">
              <header className="pd-head">
                <span className="pd-head__icon">
                  <Icon name="terminal" size={20} />
                </span>
                <span className="pd-head__text">
                  <strong>복습 · 연습장</strong>
                  <span>창을 내려놔도 풀던 코드와 실행 상태는 그대로예요</span>
                </span>
                <button type="button" className="icon-btn" onClick={() => setMinimized(true)} aria-label="내려놓기" title="내려놓기">
                  <Icon name="remove" size={20} />
                </button>
                <button type="button" className="icon-btn" onClick={closeAll} aria-label="모두 닫기" title="모두 닫기">
                  <Icon name="close" size={20} />
                </button>
              </header>
              <div className={`pd-tabs${scrolled ? ' pd-tabs--scrolled' : ''}`} role="tablist">
                {tabs.map((tab) => (
                  <PracticeTabButton
                    key={tab.key}
                    tab={tab}
                    selected={tab.key === shown?.key}
                    onSelect={() => setActive(tab.key)}
                    onClose={() => closeTab(tab.key)}
                  />
                ))}
                {!tabs.some((t) => t.key === 'free') && (
                  <button type="button" className="pd-tab pd-tab--add" onClick={() => open({ setId: null })} title="연습장 열기">
                    <Icon name="add" size={16} />
                    연습장
                  </button>
                )}
              </div>
              <div className="pd-body" ref={bodyRef} onScrollCapture={onBodyScroll}>
                <Suspense fallback={<div className="pd-loading">연습장을 불러오는 중…</div>}>
                  {tabs.map((tab) => (
                    <div key={tab.key} className="pd-pane" hidden={tab.key !== shown?.key} role="tabpanel">
                      <InDockContext.Provider value>
                        <EmbeddedPlayground
                          setId={tab.setId}
                          focusProblem={tab.focus}
                          note={tab.note}
                          active={!minimized && tab.key === shown?.key}
                        />
                      </InDockContext.Provider>
                    </div>
                  ))}
                </Suspense>
              </div>
            </section>
          </div>
          {minimized && shown && (
            <div className="pd-dockbar-wrap">
              <div className="rv-dockbar pd-dockbar" role="button" tabIndex={0} onClick={() => setMinimized(false)}
                onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setMinimized(false); }}
                aria-label="복습 · 연습장 창 펼치기">
                <div className="rv-dockbar__row">
                  <span className="rv-dockbar__icon">
                    <Icon name="terminal" size={18} />
                  </span>
                  <span className="rv-dockbar__text">
                    <strong>{tabs.length > 1 ? `복습 · 연습장 ${tabs.length}개` : <TabLabel tab={shown} short />}</strong>
                    <span>{tabs.length > 1 ? <>보던 탭 · <TabLabel tab={shown} short /></> : '창을 내려두었어요'}</span>
                  </span>
                  <Icon name="expand_less" size={20} />
                </div>
                {tabs.length > 1 && (
                  <div className="pd-dockbar__chips">
                    {tabs.map((t) => (
                      <span key={t.key} className="pd-chip">
                        <TabLabel tab={t} short />
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </>
      )}
      {notice !== null && (
        <div className="rv-notice" role="status">
          {notice}
        </div>
      )}
    </PracticeDockContext.Provider>
  );
}

function PracticeTabButton({
  tab,
  selected,
  onSelect,
  onClose,
}: {
  tab: PracticeTab;
  selected: boolean;
  onSelect(): void;
  onClose(): void;
}) {
  return (
    <div className={`pd-tab${selected ? ' pd-tab--on' : ''}`} role="tab" aria-selected={selected}>
      <button type="button" className="pd-tab__label" onClick={onSelect}>
        <TabLabel tab={tab} short />
      </button>
      <button type="button" className="pd-tab__close" onClick={onClose} aria-label="탭 닫기" title="탭 닫기">
        <Icon name="close" size={14} />
      </button>
    </div>
  );
}

/** 탭 이름 — 「09/21 복습」, 「다시 풀 문제」, 「연습장」 */
function TabLabel({ tab, short = false }: { tab: PracticeTab; short?: boolean }) {
  const set = usePracticeSet(tab.setId === RETRY_SET_ID ? null : tab.setId);
  if (tab.note) return <>{tab.note.title} 코드</>;
  if (tab.setId === null) return <>연습장</>;
  if (tab.setId === RETRY_SET_ID) return <>다시 풀 문제</>;
  if (!set) return <>복습 문제</>;
  const day = set.lessonDate ? `${set.lessonDate.slice(5).replace('-', '/')} ` : '';
  return <>{short ? `${day}복습` : `${day}복습 · ${set.title}`}</>;
}
