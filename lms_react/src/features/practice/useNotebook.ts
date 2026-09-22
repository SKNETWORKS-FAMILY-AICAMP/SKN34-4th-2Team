import { useEffect, useRef, useState } from 'react';

import type { PracticeSet } from '../../domain/types';
import type { MiniProblem } from './notebookExamples';
import type { ImportedCell } from './notebookFile';
import {
  CLEAR_OUTPUT,
  loadNotebook,
  newCell,
  saveNotebook,
  storeKey,
  type Cell,
  type CellType,
  type Line,
} from './notebookModel';
import type { RunResult } from './pythonProtocol';
import { canPromptInput, type PythonRunner, type RunOptions } from './pythonRunner';
import { RETRY_SET_ID } from './review';

const SESSION = 'playground';
const TIMEOUT_MS = 10_000;
const GRADE_TIMEOUT_MS = 5_000;

function errorText(result: RunResult): string {
  const e = result.error;
  if (!e) return '';
  if (e.type === 'EOFError') {
    return canPromptInput
      ? '입력을 끝냈어요(Esc). 값을 넣으려면 다시 실행하세요.'
      : 'input()이 읽을 값이 없어요. 위 「입력값」 칸에 한 줄에 하나씩 적어 주세요.';
  }
  const where = e.line ? `${e.line}번째 줄 · ` : '';
  return `${where}${e.type}: ${e.message}`;
}

/**
 * 노트북 한 권 — 셀 상태와 실행.
 *
 * - 셀끼리 변수가 이어진다(세션). 「변수 초기화」나 중단·시간 초과 뒤에는 비워진다.
 * - 실행은 한 번에 하나씩 줄을 선다. 문제 셀의 실행·채점도 같은 줄에 서서 앞 실행을 끊지 않는다.
 * - 워커를 새로 띄우면(중단·시간 초과) 앞 셀의 변수가 사라졌다고 알린다.
 * - 셀과 입력값은 세트마다 따로 저장한다. 다시 풀 문제는 저장하지 않는다.
 */
export function useNotebook(runner: PythonRunner, set: PracticeSet | undefined) {
  const initial = useRef(loadNotebook(set));
  const [cells, setCells] = useState<Cell[]>(initial.current.cells);
  const [stdin, setStdin] = useState(initial.current.stdin);
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
  /** 셀 id → input() 에 답을 넘기는 함수. 값을 치면 워커가 깨어난다 */
  const inputResolvers = useRef(new Map<string, (answer: string | null) => void>());

  useEffect(() => {
    if (set?.id !== RETRY_SET_ID) saveNotebook(storeKey(set), cells, stdin);
  }, [set, cells, stdin]);

  const patch = (id: string, change: Partial<Cell> | ((c: Cell) => Partial<Cell>)) =>
    setCells((prev) => prev.map((c) => (c.id === id ? { ...c, ...(typeof change === 'function' ? change(c) : change) } : c)));

  const focusCell = (id: string) => {
    setActiveId(id);
    setFocus((f) => ({ id, n: f.n + 1 }));
  };

  /** 편집기에 넘길 포커스 신호 — 이 셀 차례일 때만 값이 바뀐다 */
  const focusSignalOf = (id: string) => (focus.id === id ? focus.n : 0);

  /** 워커를 새로 띄웠으면(첫 실행 제외) 앞 셀들의 변수는 없다. */
  const noteGeneration = (keepId?: string) => {
    if (lastGeneration.current !== 0 && runner.generation !== lastGeneration.current) {
      counter.current = 0;
      setCells((prev) => prev.map((c) => (c.id === keepId ? c : { ...c, count: null })));
      setKernelNote('파이썬을 다시 띄워서 앞 셀에서 만든 변수가 사라졌어요. 필요한 셀을 위에서부터 다시 실행하세요.');
    }
    lastGeneration.current = runner.generation;
  };

  /** 문제 셀의 실행·채점도 같은 줄에 선다 — 앞 실행을 끊지 않게. */
  const runQueued = (steps: string[], options: RunOptions): Promise<RunResult> =>
    new Promise((resolve) => {
      pending.current += 1;
      setBusy(true);
      queue.current = queue.current
        .then(async () => {
          const result = await runner.run(steps, options);
          noteGeneration();
          resolve(result);
        })
        .finally(() => {
          pending.current -= 1;
          if (pending.current === 0) setBusy(false);
        });
    });

  /** 문제 셀 실행 — 노트북 세션에서 돌아 아래 셀에서 불러 쓸 수 있다 */
  const runProblemInSession = (code: string) =>
    runQueued([code], { session: SESSION, displayLast: true, timeoutMs: TIMEOUT_MS });

  /** 채점은 세션 밖 새 공간에서. 노트북에 남은 변수가 테스트에 섞이지 않는다. */
  const gradeProblem = (steps: string[]) => runQueued(steps, { timeoutMs: GRADE_TIMEOUT_MS });

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
      // 즉석 input(): 셀 아래 입력칸을 열고 학생이 Enter 를 칠 때까지 기다린다
      onInput: (prompt) =>
        new Promise((resolve) => {
          inputResolvers.current.set(id, resolve);
          patch(id, { awaitingInput: { prompt } });
        }),
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

    inputResolvers.current.delete(id);
    patch(id, { awaitingInput: null });
    noteGeneration(id);

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
    // 문제 셀은 셀 안의 실행·채점 버튼으로만 돈다
    if (cell.type === 'problem') return;
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

  /** 새 셀을 만들고 그 셀로 간다 */
  const addCellAfter = (id: string, type: CellType = 'code') => focusCell(insertAfter(id, '', type));

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

  const stop = () => {
    // 입력을 기다리던 셀이 있으면 그 약속도 끝낸다
    inputResolvers.current.forEach((resolve) => resolve(null));
    inputResolvers.current.clear();
    runner.stop();
  };

  /** 셀 아래 입력칸에 친 값을 input() 에 넘긴다. null 이면 EOF(입력 끝) */
  const answerInput = (id: string, answer: string | null) => {
    const resolve = inputResolvers.current.get(id);
    if (!resolve) return;
    inputResolvers.current.delete(id);
    patch(id, { awaitingInput: null });
    resolve(answer);
  };

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

  /** 문제 셀은 지우지 않는다 — 세트의 일부다 */
  const remove = (id: string) =>
    setCells((prev) => (prev.length === 1 ? [newCell()] : prev.filter((c) => c.id !== id || c.type === 'problem')));

  /** 다음 셀로 넘어간다. 마지막이면 빈 코드 셀을 만든다. */
  const focusNext = (id: string) => {
    const list = cellsRef.current;
    const next = list[list.findIndex((c) => c.id === id) + 1];
    if (next) focusCell(next.id);
    else {
      const created = insertAfter(id);
      requestAnimationFrame(() => focusCell(created));
    }
  };

  const changeType = (id: string, type: CellType) => {
    patch(id, { ...CLEAR_OUTPUT, type, editing: type === 'markdown' });
    requestAnimationFrame(() => focusCell(id));
  };

  const editMarkdown = (id: string) => {
    patch(id, { editing: true });
    requestAnimationFrame(() => focusCell(id));
  };

  /** 연습 문제 — 설명 · 풀 자리 · 확인 코드 세 셀을 끝에 붙이고 풀 자리로 간다 */
  const addMiniProblem = (p: MiniProblem) => {
    const prompt = newCell(`### 연습 · ${p.title}\n${p.prompt}\n\n아래 셀에 작성하고 **Shift+Enter**, 그다음 확인 셀을 실행하세요.`, 'markdown');
    const work = newCell(p.starter);
    const check = newCell(p.check);
    setCells((prev) => [...prev, prompt, work, check]);
    requestAnimationFrame(() => focusCell(work.id));
  };

  /**
   * 파일에서 불러온 셀 — 바꾸기면 노트북을 통째로 갈고 변수도 비운다(앞 노트북의 변수가 섞이지 않게).
   * 붙이기면 「불러온 파일」 제목 셀과 함께 끝에 둔다. 문제 세트에서는 붙이기만 쓴다.
   */
  const importCells = (list: ImportedCell[], how: 'replace' | 'append', title: string) => {
    const made = list.map((c) => newCell(c.source, c.type));
    if (made.length === 0) return;
    if (how === 'replace') {
      if (busy) runner.stop();
      runner.reset(SESSION);
      counter.current = 0;
      setKernelNote('');
      setCells(made);
      setActiveId(made[0].id);
      requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }));
      return;
    }
    const head = newCell(`#### 불러온 파일 · ${title}`, 'markdown');
    setCells((prev) => [...prev, head, ...made]);
    setActiveId(head.id);
    requestAnimationFrame(() =>
      document.querySelector(`[data-cell-id="${head.id}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }),
    );
  };

  const addExample = (code: string, type: CellType) => {
    const created = insertAfter(cellsRef.current[cellsRef.current.length - 1]?.id ?? '', code, type);
    if (type === 'code') requestAnimationFrame(() => focusCell(created));
    else setActiveId(created);
  };

  return {
    cells,
    stdin,
    setStdin,
    stdinLines: stdin.split('\n').filter((l) => l !== '').length,
    activeId,
    setActiveId,
    focusSignalOf,
    kernelNote,
    dismissKernelNote: () => setKernelNote(''),
    busy,
    patch,
    enqueue,
    runAndNext,
    runAndInsert,
    runAll,
    stop,
    resetKernel,
    addCellAfter,
    move,
    remove,
    focusNext,
    changeType,
    editMarkdown,
    addExample,
    addMiniProblem,
    importCells,
    runProblemInSession,
    gradeProblem,
    answerInput,
  };
}

export type Notebook = ReturnType<typeof useNotebook>;
