import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { Icon } from '../../ui/Icon';
import { CodeEditor } from './CodeEditor';
import { NotebookMarkdown } from './NotebookMarkdown';
import { PYODIDE_VERSION, type RunResult, type TableData } from './pythonProtocol';
import { usePythonRunner, type RunnerStatus } from './pythonRunner';

/**
 * 셀 내용만 이 브라우저에 임시로 둔다(학생 계정과 무관). 서버 저장은 DB를 붙일 때 이 자리를 바꾼다.
 * v1 은 코드 문자열 배열이었다.
 */
const STORE_KEY = 'lxp.pythonNotebook.v2';
const OLD_STORE_KEY = 'lxp.pythonNotebook.v1';
const SESSION = 'playground';
const TIMEOUT_MS = 10_000;

type CellType = 'code' | 'markdown';

/** 불러오기 예시 — 34기 멀티모달 수업(2026-09)의 코드에서 브라우저로 돌 수 있는 부분만 옮겼다. */
const EXAMPLES: { id: string; label: string; source: string; type: CellType; code: string }[] = [
  {
    id: 'frame-no',
    label: '프레임 번호 뽑기',
    source: '9/15 · 03_video_rag_image_caption',
    type: 'code',
    code: `import re

# 프레임 파일명에서 숫자 프레임 번호를 정수로 추출하는 함수
def extract_frame_no(frame_file):
    match = re.search(r'_frame(\\d+)\\.jpg', frame_file)
    return int(match.group(1))

extract_frame_no('alpinist_frame00300.jpg')`,
  },
  {
    id: 'table',
    label: 'DataFrame 표',
    source: '9/15 · 03_video_rag_image_caption 의 captions_df',
    type: 'code',
    code: `import pandas as pd

# 프레임별 캡션 — 수업의 captions_df 를 작게 흉내 냈다
captions = pd.DataFrame({
    'video': ['skiing', 'skiing', 'alpinist', 'alpinist'],
    'frame_no': [30, 60, 0, 300],
    'caption': ['a skier going down', 'snow slope', 'a climber on rock', 'mountain top'],
})
captions`,
  },
  {
    id: 'plot',
    label: '그래프 그리기',
    source: 'matplotlib · plt.show() 없이도 그려진다',
    type: 'code',
    code: `import matplotlib.pyplot as plt

# 영상별로 추출한 프레임 수 — 브라우저에 한글 글꼴이 없어 그래프 글자는 영어로 쓴다
videos = ['skiing', 'alpinist', 'basketball']
frames = [42, 35, 58]

plt.figure(figsize=(5, 3))
plt.bar(videos, frames, color='#0284c7')
plt.title('Frames per video')
plt.ylabel('frames')
plt.show()`,
  },
  {
    id: 'memo',
    label: '마크다운 메모',
    source: '설명을 적는 셀 · 두 번 눌러 편집',
    type: 'markdown',
    code: `## 오늘 정리
- \`re.search\`는 **처음 맞는 곳** 하나만 찾는다
- 괄호 \`( )\`로 감싼 부분이 \`group(1)\`

> 모르겠는 건 [파이썬 re 문서](https://docs.python.org/ko/3/library/re.html)에서 찾아보기`,
  },
  {
    id: 'input',
    label: 'input() 써 보기',
    source: '위 「입력값」 칸에 한 줄씩 적는다',
    type: 'code',
    code: `name = input()
count = int(input())
for i in range(count):
    print(f'{name} {i + 1}번째 프레임')`,
  },
  {
    id: 'loop',
    label: '끝나지 않는 반복문',
    source: '중단 버튼 · 시간 제한 확인용',
    type: 'code',
    code: `n = 0
while n < 3:
    print('n =', n)
    # n += 1 이 빠졌다 — 「중단」을 누르거나 10초 뒤 자동으로 멈춘다`,
  },
];

const FIRST_CELLS: { type: CellType; source: string }[] = [
  {
    type: 'markdown',
    source: `## 9/15 영상 RAG 복습
프레임 파일명에서 번호를 뽑고, 캡션을 표로 모아 본다. 셀을 고르고 **Shift+Enter**로 실행한다.`,
  },
  { type: 'code', source: EXAMPLES[0].code },
  {
    type: 'code',
    source: `# 앞 셀에서 만든 함수를 그대로 쓴다 — 셀끼리 변수가 이어진다
frames = ['skiing_frame00030.jpg', 'skiing_frame00060.jpg', 'skiing_frame00090.jpg']
[extract_frame_no(f) for f in frames]`,
  },
];

type LineKind = 'out' | 'sys' | 'err';
interface Line {
  kind: LineKind;
  text: string;
}
type CellState = 'idle' | 'queued' | 'running' | 'ok' | 'error';
interface Cell {
  id: string;
  type: CellType;
  code: string;
  /** 마크다운 셀이 편집 중인지 */
  editing: boolean;
  lines: Line[];
  value: string | null;
  table: TableData | null;
  images: string[];
  count: number | null;
  state: CellState;
  ms: number | null;
}

let cellSeq = 0;
function newCell(code = '', type: CellType = 'code'): Cell {
  cellSeq += 1;
  return {
    id: `c${Date.now().toString(36)}${cellSeq}`,
    type,
    code,
    editing: type === 'markdown' && code.trim() === '',
    lines: [],
    value: null,
    table: null,
    images: [],
    count: null,
    state: 'idle',
    ms: null,
  };
}

const CLEAR_OUTPUT = { lines: [], value: null, table: null, images: [], count: null, state: 'idle' as CellState, ms: null };

function loadNotebook(): { cells: Cell[]; stdin: string } {
  try {
    const raw = window.localStorage.getItem(STORE_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as { cells?: { type?: CellType; source?: string }[]; stdin?: string };
      if (Array.isArray(saved.cells) && saved.cells.length) {
        return {
          cells: saved.cells.map((c) => newCell(String(c.source ?? ''), c.type === 'markdown' ? 'markdown' : 'code')),
          stdin: saved.stdin ?? '',
        };
      }
    }
    const old = window.localStorage.getItem(OLD_STORE_KEY);
    if (old) {
      const saved = JSON.parse(old) as { cells?: string[]; stdin?: string };
      if (Array.isArray(saved.cells) && saved.cells.length) {
        return { cells: saved.cells.map((code) => newCell(String(code))), stdin: saved.stdin ?? '' };
      }
    }
  } catch {
    // 저장본이 깨졌거나 저장소가 막혀 있으면 처음 셀로 연다.
  }
  return { cells: FIRST_CELLS.map((c) => newCell(c.source, c.type)), stdin: '민지\n3' };
}

function saveNotebook(cells: Cell[], stdin: string) {
  try {
    window.localStorage.setItem(
      STORE_KEY,
      JSON.stringify({ cells: cells.map((c) => ({ type: c.type, source: c.code })), stdin }),
    );
  } catch {
    // 저장이 막혀 있어도 연습장은 돈다.
  }
}

const STATUS_TEXT: Record<RunnerStatus, string> = {
  idle: '대기',
  loading: '런타임 불러오는 중',
  ready: '준비됨',
  running: '실행 중',
  error: '불러오지 못함',
};

function errorText(result: RunResult): string {
  const e = result.error;
  if (!e) return '';
  if (e.type === 'EOFError') return 'input()이 읽을 값이 없어요. 위 「입력값」 칸에 한 줄에 하나씩 적어 주세요.';
  const where = e.line ? `${e.line}번째 줄 · ` : '';
  return `${where}${e.type}: ${e.message}`;
}

/**
 * 파이썬 연습장 — 노트북처럼 셀을 나눠 돌린다.
 *
 * - 코드 셀과 마크다운 셀. 마크다운은 Shift+Enter 로 보기, 두 번 눌러 편집.
 * - 셀끼리 변수가 이어진다(세션). 「변수 초기화」나 중단·시간 초과 뒤에는 비워진다.
 * - 마지막 줄이 식이면 print 없이 값이 Out 으로 나온다(DataFrame 은 표). 끝에 ; 를 붙이면 숨긴다.
 * - matplotlib 그림은 셀 아래에 그림으로 나온다.
 * - 단축키는 Jupyter 와 같다. 실행은 한 번에 하나씩 줄을 선다.
 * - 코드는 서버로 가지 않고 이 브라우저 안(Pyodide)에서만 돈다.
 */
export function PythonPlaygroundScreen() {
  const { runner, status } = usePythonRunner();
  const initial = useRef(loadNotebook());
  const [cells, setCells] = useState<Cell[]>(initial.current.cells);
  const [stdin, setStdin] = useState(initial.current.stdin);
  const [showStdin, setShowStdin] = useState(false);
  const [activeId, setActiveId] = useState(initial.current.cells[0]?.id ?? '');
  const [focus, setFocus] = useState<{ id: string; n: number }>({ id: '', n: 0 });
  const [kernelNote, setKernelNote] = useState('');
  const [busy, setBusy] = useState(false);

  const cellsRef = useRef(cells);
  cellsRef.current = cells;
  const stdinRef = useRef(stdin);
  stdinRef.current = stdin;
  const queue = useRef<Promise<void>>(Promise.resolve());
  const pending = useRef(0);
  const cancel = useRef(0);
  const counter = useRef(0);
  const lastGeneration = useRef(0);

  useEffect(() => saveNotebook(cells, stdin), [cells, stdin]);

  const patch = (id: string, change: Partial<Cell> | ((c: Cell) => Partial<Cell>)) =>
    setCells((prev) => prev.map((c) => (c.id === id ? { ...c, ...(typeof change === 'function' ? change(c) : change) } : c)));

  const focusCell = (id: string) => {
    setActiveId(id);
    setFocus((f) => ({ id, n: f.n + 1 }));
  };

  /** 셀 하나를 실제로 돌린다. 줄 서 있다가 차례가 오면 불린다. */
  const execute = async (id: string, token: number) => {
    if (token !== cancel.current) return;
    const cell = cellsRef.current.find((c) => c.id === id);
    if (!cell || cell.type !== 'code') return;
    const cold = runner.status === 'idle' || runner.status === 'error';
    const heavy = /^\s*(import|from)\s+(matplotlib|pandas)/m.test(cell.code);
    patch(id, {
      state: 'running',
      value: null,
      table: null,
      images: [],
      ms: null,
      lines: cold
        ? [{ kind: 'sys', text: runner.version ? '파이썬을 다시 띄우는 중…' : '파이썬 런타임을 불러오는 중… 처음 한 번은 몇 초 걸립니다.' }]
        : [],
    });

    const result = await runner.run([cell.code], {
      session: SESSION,
      stdin: stdinRef.current,
      displayLast: true,
      timeoutMs: TIMEOUT_MS,
      onPhase: (phase) => {
        if (phase === 'loading-packages' && heavy) {
          patch(id, { lines: [{ kind: 'sys', text: '패키지를 불러오는 중… (matplotlib·pandas 는 처음 한 번 몇 초 걸립니다)' }] });
        }
        if (phase === 'exec') patch(id, (c) => ({ lines: c.lines.filter((l) => l.kind !== 'sys') }));
      },
      onStdout: (text) =>
        patch(id, (c) => {
          const last = c.lines[c.lines.length - 1];
          if (last?.kind === 'out') return { lines: [...c.lines.slice(0, -1), { kind: 'out', text: last.text + text }] };
          return { lines: [...c.lines, { kind: 'out', text }] };
        }),
    });

    // 워커를 새로 띄웠으면(첫 실행 제외) 앞 셀들의 변수는 없다.
    if (lastGeneration.current !== 0 && runner.generation !== lastGeneration.current) {
      counter.current = 0;
      setCells((prev) => prev.map((c) => (c.id === id ? c : { ...c, count: null })));
      setKernelNote('파이썬을 다시 띄워서 앞 셀에서 만든 변수가 사라졌어요. 필요한 셀을 위에서부터 다시 실행하세요.');
    }
    lastGeneration.current = runner.generation;

    const tail: Line[] = [];
    if (result.timedOut) tail.push({ kind: 'err', text: `${TIMEOUT_MS / 1000}초가 지나 멈췄습니다. 반복문이 끝나는지 확인해 보세요.` });
    else if (result.stopped) tail.push({ kind: 'err', text: '실행을 중단했습니다. 변수도 함께 초기화됩니다.' });
    else if (result.error) tail.push({ kind: 'err', text: errorText(result) });

    counter.current += 1;
    const count = counter.current;
    patch(id, (c) => ({
      lines: [...c.lines.filter((l) => l.kind !== 'sys'), ...tail],
      value: result.value,
      table: result.table,
      images: result.images,
      count,
      state: result.ok ? 'ok' : 'error',
      ms: result.timedOut || result.stopped ? null : result.ms,
    }));
    if (result.timedOut || result.stopped) {
      // 줄 서 있던 셀은 취소한다.
      cancel.current += 1;
      setCells((prev) => prev.map((c) => (c.state === 'queued' ? { ...c, state: 'idle' } : c)));
      counter.current = 0;
    }
  };

  /** 코드 셀은 줄을 세우고, 마크다운 셀은 바로 보기로 바꾼다. */
  const enqueue = (id: string) => {
    const cell = cellsRef.current.find((c) => c.id === id);
    if (!cell) return;
    if (cell.type === 'markdown') {
      patch(id, { editing: false });
      return;
    }
    patch(id, { state: 'queued' });
    pending.current += 1;
    setBusy(true);
    const token = cancel.current;
    queue.current = queue.current
      .then(() => execute(id, token))
      .finally(() => {
        pending.current -= 1;
        if (pending.current === 0) setBusy(false);
      });
  };

  const insertAfter = (id: string, code = '', type: CellType = 'code'): string => {
    const cell = newCell(code, type);
    setCells((prev) => {
      const i = prev.findIndex((c) => c.id === id);
      const next = prev.slice();
      next.splice(i < 0 ? prev.length : i + 1, 0, cell);
      return next;
    });
    return cell.id;
  };

  const runAndNext = (id: string) => {
    enqueue(id);
    const list = cellsRef.current;
    const i = list.findIndex((c) => c.id === id);
    const next = list[i + 1];
    if (next) {
      if (next.type === 'markdown') setActiveId(next.id);
      else focusCell(next.id);
    } else {
      const created = insertAfter(id);
      requestAnimationFrame(() => focusCell(created));
    }
  };

  const runAndInsert = (id: string) => {
    enqueue(id);
    const created = insertAfter(id);
    requestAnimationFrame(() => focusCell(created));
  };

  const runAll = () => cellsRef.current.forEach((c) => enqueue(c.id));

  const resetKernel = () => {
    if (busy) runner.stop();
    runner.reset(SESSION);
    counter.current = 0;
    setKernelNote('');
    setCells((prev) => prev.map((c) => ({ ...c, ...CLEAR_OUTPUT })));
  };

  const move = (id: string, delta: number) =>
    setCells((prev) => {
      const i = prev.findIndex((c) => c.id === id);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = prev.slice();
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const remove = (id: string) =>
    setCells((prev) => (prev.length === 1 ? [newCell()] : prev.filter((c) => c.id !== id)));

  const changeType = (id: string, type: CellType) => {
    patch(id, { ...CLEAR_OUTPUT, type, editing: type === 'markdown' });
    requestAnimationFrame(() => focusCell(id));
  };

  const editMarkdown = (id: string) => {
    patch(id, { editing: true });
    requestAnimationFrame(() => focusCell(id));
  };

  const addExample = (code: string, type: CellType) => {
    const created = insertAfter(cellsRef.current[cellsRef.current.length - 1]?.id ?? '', code, type);
    if (type === 'code') requestAnimationFrame(() => focusCell(created));
    else setActiveId(created);
  };

  const stdinLines = stdin.split('\n').filter((l) => l !== '').length;

  return (
    <div className="screen__inner py-playground">
      <header className="study-head">
        <div>
          <nav className="py-crumbs" aria-label="위치">
            <Link to={RoutePaths.studyRoom}>학습실</Link>
            <Icon name="chevron_right" size={16} />
            <span>파이썬 연습장</span>
          </nav>
          <h1 className="study-head__title">파이썬 연습장</h1>
          <p className="study-head__desc">
            노트북처럼 셀을 나눠 실행합니다. 앞 셀에서 만든 변수는 다음 셀에서 그대로 쓸 수 있어요. 코드는 이 브라우저 안에서만 돕니다.
          </p>
        </div>
        <span className={`py-status py-status--${status}`} title={`Pyodide ${PYODIDE_VERSION}`}>
          <span className="py-status__lamp" />
          <span>
            <strong>Python</strong> · {STATUS_TEXT[status]}
          </span>
        </span>
      </header>

      <div className="py-toolbar">
        <button type="button" className="btn btn--filled btn--sm" onClick={runAll} disabled={busy}>
          <Icon name="fast_forward" size={18} />
          모두 실행
        </button>
        {busy && (
          <button type="button" className="btn btn--danger btn--sm" onClick={() => runner.stop()}>
            <Icon name="stop" size={18} />
            중단
          </button>
        )}
        <button type="button" className="btn btn--outline btn--sm" onClick={resetKernel} title="모든 변수를 비우고 실행 번호를 1부터 다시 셉니다">
          <Icon name="restart_alt" size={18} />
          변수 초기화
        </button>
        <button type="button" className="btn btn--outline btn--sm" onClick={() => focusCell(insertAfter(activeId))}>
          <Icon name="add" size={18} />
          코드
        </button>
        <button
          type="button"
          className="btn btn--outline btn--sm"
          onClick={() => focusCell(insertAfter(activeId, '', 'markdown'))}
        >
          <Icon name="notes" size={18} />
          마크다운
        </button>
        <button
          type="button"
          className={`btn btn--outline btn--sm${showStdin ? ' py-toolbar__on' : ''}`}
          onClick={() => setShowStdin((v) => !v)}
          aria-expanded={showStdin}
        >
          <Icon name="keyboard" size={18} />
          입력값{stdinLines ? ` · ${stdinLines}줄` : ''}
        </button>
        <span className="py-grow" />
        <details className="py-keys">
          <summary>단축키</summary>
          <dl>
            <dt>Shift + Enter</dt>
            <dd>실행하고 다음 셀로</dd>
            <dt>Ctrl + Enter</dt>
            <dd>실행하고 그 자리에</dd>
            <dt>Alt + Enter</dt>
            <dd>실행하고 아래에 새 셀</dd>
            <dt>Tab / Shift + Tab</dt>
            <dd>들여쓰기 / 내어쓰기</dd>
            <dt>Ctrl + /</dt>
            <dd>주석 켜고 끄기</dd>
            <dt>Ctrl + Space</dt>
            <dd>자동완성 목록 열기</dd>
            <dt>두 번 누르기</dt>
            <dd>마크다운 셀 편집</dd>
          </dl>
        </details>
      </div>

      {showStdin && (
        <section className="py-stdin">
          <label htmlFor="py-stdin">
            입력값 — <code>input()</code>이 위에서부터 한 줄씩 읽어요. 셀을 실행할 때마다 첫 줄부터 다시 읽습니다.
          </label>
          <textarea id="py-stdin" value={stdin} onChange={(e) => setStdin(e.target.value)} rows={3} spellCheck={false} />
        </section>
      )}

      <section className="py-examples" aria-label="예시 셀 추가">
        <span className="py-examples__label">예시 셀 추가</span>
        {EXAMPLES.map((e) => (
          <button key={e.id} type="button" className="chip" onClick={() => addExample(e.code, e.type)} title={e.source}>
            {e.label}
          </button>
        ))}
      </section>

      {kernelNote && (
        <div className="py-kernel-note" role="status">
          <Icon name="info" size={18} />
          <span>{kernelNote}</span>
          <button type="button" onClick={() => setKernelNote('')} aria-label="닫기">
            <Icon name="close" size={16} />
          </button>
        </div>
      )}

      <div className="py-notebook">
        {cells.map((cell, index) => {
          const isMarkdown = cell.type === 'markdown';
          const rendered = isMarkdown && !cell.editing;
          return (
            <article
              key={cell.id}
              className={`py-nb-cell py-nb-cell--${cell.type} py-nb-cell--${cell.state}${cell.id === activeId ? ' py-nb-cell--active' : ''}`}
              onClick={() => setActiveId(cell.id)}
            >
              <div className="py-nb-cell__prompt" aria-label={isMarkdown ? undefined : '실행 번호'}>
                {isMarkdown ? '' : `[${cell.state === 'running' || cell.state === 'queued' ? '*' : cell.count ?? ' '}]`}
              </div>
              <div className="py-nb-cell__main">
                <div className="py-nb-cell__tools">
                  <button
                    type="button"
                    className="py-icon-btn py-icon-btn--run"
                    onClick={() => enqueue(cell.id)}
                    aria-label={isMarkdown ? '마크다운 보기' : '이 셀 실행'}
                    title={isMarkdown ? '보기 (Shift+Enter)' : '이 셀 실행 (Ctrl+Enter)'}
                  >
                    <Icon name={isMarkdown ? 'visibility' : 'play_arrow'} size={18} />
                  </button>
                  <select
                    className="py-nb-cell__type"
                    value={cell.type}
                    onChange={(e) => changeType(cell.id, e.target.value as CellType)}
                    aria-label="셀 종류"
                  >
                    <option value="code">코드</option>
                    <option value="markdown">마크다운</option>
                  </select>
                  <span className="py-grow" />
                  {cell.ms !== null && cell.ms >= 10 && <span className="py-nb-cell__ms">{(cell.ms / 1000).toFixed(2)}초</span>}
                  {rendered && (
                    <button type="button" className="py-icon-btn" onClick={() => editMarkdown(cell.id)} aria-label="편집" title="편집">
                      <Icon name="edit" size={16} />
                    </button>
                  )}
                  <button type="button" className="py-icon-btn" onClick={() => move(cell.id, -1)} disabled={index === 0} aria-label="위로" title="위로">
                    <Icon name="arrow_upward" size={16} />
                  </button>
                  <button type="button" className="py-icon-btn" onClick={() => move(cell.id, 1)} disabled={index === cells.length - 1} aria-label="아래로" title="아래로">
                    <Icon name="arrow_downward" size={16} />
                  </button>
                  <button type="button" className="py-icon-btn" onClick={() => focusCell(insertAfter(cell.id))} aria-label="아래에 셀 추가" title="아래에 셀 추가">
                    <Icon name="add" size={16} />
                  </button>
                  <button type="button" className="py-icon-btn" onClick={() => remove(cell.id)} aria-label="셀 삭제" title="셀 삭제">
                    <Icon name="delete" size={16} />
                  </button>
                </div>

                {rendered ? (
                  <div
                    className="py-nb-md"
                    onDoubleClick={() => editMarkdown(cell.id)}
                    title="두 번 눌러 편집"
                  >
                    {cell.code.trim() ? (
                      <NotebookMarkdown source={cell.code} />
                    ) : (
                      <span className="py-line--sys">빈 마크다운 셀 — 두 번 눌러 편집</span>
                    )}
                  </div>
                ) : (
                  <CodeEditor
                    value={cell.code}
                    language={isMarkdown ? 'markdown' : 'python'}
                    onChange={(code) => patch(cell.id, { code })}
                    onRun={() => enqueue(cell.id)}
                    onRunAndNext={() => runAndNext(cell.id)}
                    onRunAndInsert={() => runAndInsert(cell.id)}
                    onFocus={() => setActiveId(cell.id)}
                    focusSignal={focus.id === cell.id ? focus.n : 0}
                    minLines={2}
                    label={`셀 ${index + 1} ${isMarkdown ? '마크다운' : '코드'}`}
                    placeholder={isMarkdown ? '## 제목, - 목록, **굵게**, `코드` … Shift+Enter 로 보기' : '코드를 입력하고 Shift+Enter'}
                  />
                )}

                {!isMarkdown && (cell.lines.length > 0 || cell.value !== null || cell.table || cell.images.length > 0) && (
                  <div className="py-nb-out" aria-live="polite">
                    {cell.lines.map((l, i) => (
                      <div key={i} className={`py-line--${l.kind}`}>
                        {l.kind === 'out' ? l.text.replace(/\n$/, '') : l.text}
                      </div>
                    ))}
                    {cell.images.map((src, i) => (
                      <img key={i} className="py-nb-out__img" src={src} alt={`그래프 ${i + 1}`} />
                    ))}
                    {cell.table && <OutputTable table={cell.table} count={cell.count} />}
                    {cell.value !== null && (
                      <div className="py-nb-out__value">
                        <span className="py-nb-out__label">Out[{cell.count}]</span>
                        <span>{cell.value}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </article>
          );
        })}
        <div className="py-add-row">
          <button type="button" className="py-add-cell" onClick={() => focusCell(insertAfter(cells[cells.length - 1]?.id ?? ''))}>
            <Icon name="add" size={18} />
            코드 셀
          </button>
          <button
            type="button"
            className="py-add-cell"
            onClick={() => focusCell(insertAfter(cells[cells.length - 1]?.id ?? '', '', 'markdown'))}
          >
            <Icon name="notes" size={18} />
            마크다운 셀
          </button>
        </div>
      </div>

      <p className="py-foot">
        파일 읽기·인터넷 요청은 쓸 수 없습니다. torch·cv2 같은 모델 라이브러리도 브라우저에서는 돌지 않습니다. 그래프의 한글은 글꼴이 없어 네모로
        나오니 영어로 적어 주세요. 마지막 줄 끝에 <code>;</code>를 붙이면 값 표시를 숨깁니다.
      </p>
    </div>
  );
}

/** DataFrame 표 — 앞 50행까지. 글자로만 그린다. */
function OutputTable({ table, count }: { table: TableData; count: number | null }) {
  const [rows, cols] = table.shape;
  return (
    <div className="py-nb-table">
      <span className="py-nb-out__label">Out[{count}]</span>
      <div className="py-nb-table__scroll">
        <table>
          <thead>
            <tr>
              <th>{table.indexName}</th>
              {table.columns.map((c, i) => (
                <th key={i}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r}>
                <th>{table.index[r]}</th>
                {row.map((v, c) => (
                  <td key={c}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="py-nb-table__shape">
        {rows}행 × {cols}열{rows > table.rows.length ? ` · 앞 ${table.rows.length}행만 표시` : ''}
      </span>
    </div>
  );
}
