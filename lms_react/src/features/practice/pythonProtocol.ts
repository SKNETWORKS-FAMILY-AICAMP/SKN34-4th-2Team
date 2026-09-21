/**
 * 화면 ↔ 파이썬 워커가 주고받는 메시지.
 *
 * steps 는 같은 변수 공간에서 이어서 돈다 — [학생 코드, 숨긴 테스트] 처럼.
 * session 이 없으면 작업마다 변수 공간을 새로 만든다(채점). 있으면 그 이름의 공간을 계속 쓴다(노트북).
 * 서버 검증기(practice_verifier/)와 같은 약속이다.
 */

/** practice_verifier/package.json 의 pyodide 버전과 같아야 한다. */
export const PYODIDE_VERSION = '314.0.7';

export interface RunRequest {
  type: 'run';
  id: string;
  steps: string[];
  /** 노트북 세션 이름. 같은 이름이면 앞 셀에서 만든 변수가 남아 있다. */
  session?: string;
  /** input() 이 위에서부터 한 줄씩 읽을 값. 없으면 input() 은 EOFError. */
  stdin?: string;
  /** 마지막 줄이 식이면 그 값의 repr 을 돌려준다 (노트북의 Out). */
  displayLast?: boolean;
}

export interface ResetRequest {
  type: 'reset';
  session: string;
}

export type WorkerRequest = RunRequest | ResetRequest;

/** DataFrame 을 표로 그리기 위한 값. 앞 MAX 행만 온다. 칸은 모두 글자다. */
export interface TableData {
  columns: string[];
  index: string[];
  indexName: string;
  rows: string[][];
  /** 원래 크기 [행, 열] */
  shape: [number, number];
}

export interface RunError {
  type: string;
  message: string;
  /** 몇 번째 step 에서 났는지. -1 은 패키지 불러오기 */
  step: number;
  /** 학생 코드의 줄 번호 (알 수 있을 때) */
  line: number | null;
}

export type RunnerEvent =
  | { type: 'ready'; version: string }
  | { type: 'boot-error'; message: string }
  | { type: 'loading-packages'; id: string }
  | { type: 'exec'; id: string }
  | { type: 'stdout'; id: string; text: string }
  | { type: 'stderr'; id: string; text: string }
  | {
      type: 'done';
      id: string;
      ok: boolean;
      error: RunError | null;
      /** displayLast 일 때 마지막 식의 repr. 값이 None 이거나 식이 아니면 null. 표로 그릴 수 있으면 null */
      value: string | null;
      /** 마지막 값이 DataFrame 이면 표 */
      table: TableData | null;
      /** 셀이 그린 matplotlib 그림 (PNG data URL) */
      images: string[];
      ms: number;
      truncated: boolean;
    };

export interface RunResult {
  ok: boolean;
  stdout: string;
  error: RunError | null;
  value: string | null;
  table: TableData | null;
  images: string[];
  timedOut: boolean;
  stopped: boolean;
  ms: number;
}
