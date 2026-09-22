import { useEffect, useRef, useState } from 'react';

import type { RunnerEvent, RunResult, WorkerRequest } from './pythonProtocol';

/**
 * 파이썬 워커 하나를 붙잡고 실행을 맡는다.
 *
 * - 첫 실행 때 워커를 띄운다(런타임 내려받기는 그때 한 번).
 * - 시간을 넘기거나 「중단」을 누르면 워커를 terminate 한다. 파이썬 안에서는 무한 루프를 끊을 수 없다.
 *   다음 실행 때 새 워커를 띄우므로 다시 불러오는 시간이 든다(브라우저 캐시 덕에 첫 번보다 빠르다).
 * - 시간 제한은 코드가 실제로 돌기 시작한 순간부터 잰다. 런타임·패키지 내려받기는 넣지 않는다.
 */
export type RunnerStatus = 'idle' | 'loading' | 'ready' | 'running' | 'error';

export interface RunOptions {
  timeoutMs?: number;
  /** 노트북 세션 이름. 같은 이름이면 앞에서 만든 변수가 남는다. */
  session?: string;
  /** input() 이 한 줄씩 읽을 값 */
  stdin?: string;
  /**
   * 즉석 입력. input() 이 불리면 안내문을 받아 값을 돌려준다(null 이면 EOF).
   * 페이지가 SharedArrayBuffer 를 쓸 수 있을 때만 동작한다(canPromptInput). 기다리는 동안 시간 제한은 멈춘다.
   */
  onInput?: (prompt: string) => Promise<string | null>;
  /** 마지막 줄이 식이면 그 값을 result.value 로 */
  displayLast?: boolean;
  onStdout?: (text: string) => void;
  onPhase?: (phase: 'loading-packages' | 'exec') => void;
}

interface Pending {
  id: string;
  stdout: string;
  timer: number | null;
  /** 시간 제한이 시작된 시각과 남은 시간 — 입력을 기다리는 동안 멈춘다 */
  deadlineLeft: number;
  timerStarted: number;
  inputBuffer: SharedArrayBuffer | null;
  options: RunOptions;
  resolve: (result: RunResult) => void;
}

let seq = 0;

/** 즉석 input() 을 쓸 수 있는 페이지인지 — COOP/COEP 헤더가 있어야 SharedArrayBuffer 가 켜진다 */
export const canPromptInput = typeof SharedArrayBuffer !== 'undefined' && (globalThis as { crossOriginIsolated?: boolean }).crossOriginIsolated === true;
const INPUT_BUFFER_BYTES = 8 + 64 * 1024;

export class PythonRunner {
  private worker: Worker | null = null;
  private pending: Pending | null = null;
  private listeners = new Set<(status: RunnerStatus) => void>();
  status: RunnerStatus = 'idle';
  /** 워커를 새로 띄울 때마다 1 씩 는다. 바뀌었으면 노트북 세션의 변수는 사라진 것이다. */
  generation = 0;
  version = '';
  bootError = '';

  subscribe(listener: (status: RunnerStatus) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private setStatus(status: RunnerStatus) {
    this.status = status;
    this.listeners.forEach((l) => l(status));
  }

  private spawn(): Worker {
    const worker = new Worker(new URL('./pythonWorker.ts', import.meta.url), { type: 'module' });
    worker.onmessage = (e: MessageEvent<RunnerEvent>) => this.handle(e.data);
    worker.onerror = (e) => {
      this.bootError = e.message || '파이썬 런타임을 띄우지 못했습니다';
      this.finish({ ok: false, stdout: '', error: { type: 'RuntimeError', message: this.bootError, step: -1, line: null }, value: null, table: null, images: [], timedOut: false, stopped: false, ms: 0 });
      this.kill('error');
    };
    this.worker = worker;
    this.generation += 1;
    this.setStatus('loading');
    return worker;
  }

  private handle(event: RunnerEvent) {
    const p = this.pending;
    switch (event.type) {
      case 'ready':
        this.version = event.version;
        if (!p) this.setStatus('ready');
        return;
      case 'boot-error':
        this.bootError = event.message;
        this.finish({ ok: false, stdout: '', error: { type: 'RuntimeError', message: '파이썬 런타임을 내려받지 못했습니다. 네트워크를 확인하세요.', step: -1, line: null }, value: null, table: null, images: [], timedOut: false, stopped: false, ms: 0 });
        this.kill('error');
        return;
    }
    if (!p || event.id !== p.id) return;
    switch (event.type) {
      case 'loading-packages':
        p.options.onPhase?.('loading-packages');
        return;
      case 'exec':
        this.setStatus('running');
        p.options.onPhase?.('exec');
        this.armTimer(p, p.options.timeoutMs ?? 5000);
        return;
      case 'input':
        this.promptInput(p, event.prompt);
        return;
      case 'stdout':
      case 'stderr':
        p.stdout += event.text;
        p.options.onStdout?.(event.text);
        return;
      case 'done':
        this.finish({ ok: event.ok, stdout: p.stdout, error: event.error, value: event.value, table: event.table, images: event.images, timedOut: false, stopped: false, ms: event.ms });
        this.setStatus('ready');
    }
  }

  private armTimer(p: Pending, ms: number) {
    p.deadlineLeft = ms;
    p.timerStarted = performance.now();
    p.timer = window.setTimeout(() => {
      this.finish({ ok: false, stdout: p.stdout, error: null, value: null, table: null, images: [], timedOut: true, stopped: false, ms: p.options.timeoutMs ?? 0 });
      this.kill('idle');
    }, ms);
  }

  /** 워커가 input() 에서 잠들어 있다. 화면에 물어보고 공유 메모리에 써서 깨운다. 그동안 시간 제한은 멈춘다. */
  private async promptInput(p: Pending, prompt: string) {
    if (p.timer !== null) {
      window.clearTimeout(p.timer);
      p.timer = null;
      p.deadlineLeft = Math.max(1000, p.deadlineLeft - (performance.now() - p.timerStarted));
    }
    const buffer = p.inputBuffer;
    if (!buffer) return;
    const state = new Int32Array(buffer, 0, 2);
    const answer = p.options.onInput ? await p.options.onInput(prompt) : null;
    if (this.pending !== p) return; // 기다리는 사이 중단됐다
    if (answer === null) {
      Atomics.store(state, 0, 2);
    } else {
      const bytes = new TextEncoder().encode(answer).slice(0, INPUT_BUFFER_BYTES - 8);
      new Uint8Array(buffer, 8, bytes.length).set(bytes);
      Atomics.store(state, 1, bytes.length);
      Atomics.store(state, 0, 1);
    }
    Atomics.notify(state, 0);
    // 입력값도 출력처럼 화면에 남긴다 — 터미널에서 친 것처럼
    if (answer !== null) {
      p.stdout += `${answer}\n`;
      p.options.onStdout?.(`${answer}\n`);
    }
    this.armTimer(p, p.deadlineLeft);
  }

  private finish(result: RunResult) {
    const p = this.pending;
    if (!p) return;
    if (p.timer !== null) window.clearTimeout(p.timer);
    this.pending = null;
    p.resolve(result);
  }

  private kill(next: RunnerStatus) {
    this.worker?.terminate();
    this.worker = null;
    this.setStatus(next);
  }

  /** steps 를 같은 변수 공간에서 차례로 돌린다. 이미 도는 것이 있으면 먼저 끊는다. */
  run(steps: string[], options: RunOptions = {}): Promise<RunResult> {
    if (this.pending) this.stop();
    const worker = this.worker ?? this.spawn();
    const id = `run-${++seq}`;
    const inputBuffer = options.onInput && canPromptInput ? new SharedArrayBuffer(INPUT_BUFFER_BYTES) : null;
    return new Promise((resolve) => {
      this.pending = { id, stdout: '', timer: null, deadlineLeft: 0, timerStarted: 0, inputBuffer, options, resolve };
      worker.postMessage({
        type: 'run',
        id,
        steps,
        session: options.session,
        stdin: options.stdin,
        inputBuffer: inputBuffer ?? undefined,
        displayLast: options.displayLast,
      } satisfies WorkerRequest);
    });
  }

  /** 노트북 세션의 변수를 비운다. 워커가 없으면 비울 것도 없다. */
  reset(session: string) {
    this.worker?.postMessage({ type: 'reset', session } satisfies WorkerRequest);
  }

  /** 도는 코드를 끊는다. 워커를 통째로 끝낸다(세션 변수도 사라진다). */
  stop() {
    const p = this.pending;
    if (!p) return;
    this.finish({ ok: false, stdout: p.stdout, error: null, value: null, table: null, images: [], timedOut: false, stopped: true, ms: 0 });
    this.kill('idle');
  }

  dispose() {
    this.stop();
    this.kill('idle');
    this.listeners.clear();
  }
}

/** 화면 하나에 실행기 하나. 화면을 떠나면 워커도 끝낸다. */
export function usePythonRunner() {
  const ref = useRef<PythonRunner | null>(null);
  if (ref.current === null) ref.current = new PythonRunner();
  const runner = ref.current;
  const [status, setStatus] = useState<RunnerStatus>(runner.status);

  useEffect(() => {
    const off = runner.subscribe(setStatus);
    return () => {
      off();
      runner.dispose();
    };
  }, [runner]);

  return { runner, status };
}
