/// <reference lib="webworker" />
/**
 * 브라우저 안에서 파이썬을 돌리는 워커.
 *
 * 서버의 practice_verifier/worker.mjs 와 같은 Pyodide 버전·같은 잠금을 쓴다. 검증기에서
 * 통과한 문제가 학생 브라우저에서도 똑같이 돌게 하려는 것이다. 한쪽을 바꾸면 다른 쪽도 바꾼다.
 *
 * 무한 루프는 파이썬 안에서 끊을 수 없다. 화면 쪽(pythonRunner.ts)이 이 워커를 terminate 한다.
 * 그러면 노트북 세션의 변수도 함께 사라진다.
 *
 * input() 은 실행 중에 화면에 물어볼 수 없다. 워커는 답을 기다리며 멈출 수 없기 때문이다.
 * 대신 실행 전에 받은 stdin 문자열을 한 줄씩 넘긴다(온라인 저지의 입력 칸과 같은 방식).
 */
import {
  PYODIDE_VERSION,
  type RunError,
  type RunnerEvent,
  type RunRequest,
  type TableData,
  type WorkerRequest,
} from './pythonProtocol';

declare const self: DedicatedWorkerGlobalScope;

const INDEX_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const MAX_STDOUT_CHARS = 20_000;

/**
 * 셀 하나를 돈다 — 결과는 JSON 문자열 {"text", "table", "images"}.
 *
 * - 마지막 문장이 식이면 그 값을 따로 계산한다(노트북의 Out). DataFrame 이면 표로, 아니면 repr.
 * - 셀이 연 matplotlib 그림은 plt.show() 가 없어도 PNG 로 모아 온다(Jupyter inline 과 같다).
 *   워커에는 화면이 없으므로 그리기 백엔드는 Agg 로 둔다.
 * - 줄 번호가 학생 코드 그대로 나오도록 파일 이름을 "<exec>" 로 둔다.
 */
const HELPER = `
import ast as _ast, base64 as _b64, io as _io, json as _json, math as _math, os as _os, sys as _sys, warnings as _warnings

_os.environ["MPLBACKEND"] = "Agg"
_warnings.filterwarnings("ignore", message=".*non-interactive.*")
MAX_ROWS = 50

def _figures():
    plt = _sys.modules.get("matplotlib.pyplot")
    if plt is None:
        return []
    images = []
    for num in plt.get_fignums():
        buf = _io.BytesIO()
        plt.figure(num).savefig(buf, format="png", dpi=110, bbox_inches="tight")
        images.append("data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode())
    plt.close("all")
    return images

def _cell(v):
    if isinstance(v, float):
        return "NaN" if _math.isnan(v) else format(v, ".6g")
    return str(v)

def _table(value):
    pd = _sys.modules.get("pandas")
    if pd is None or not isinstance(value, pd.DataFrame):
        return None
    head = value.head(MAX_ROWS)
    return {
        "columns": [str(c) for c in head.columns],
        "index": [str(i) for i in head.index],
        "indexName": "" if head.index.name is None else str(head.index.name),
        "rows": [[_cell(v) for v in row] for row in head.itertuples(index=False, name=None)],
        "shape": list(value.shape),
    }

_images = []

def run_cell(src, ns, display):
    tree = _ast.parse(src, "<exec>", "exec")
    last = None
    if display and tree.body and isinstance(tree.body[-1], _ast.Expr) and not src.rstrip().endswith(";"):
        last = tree.body.pop()
    value = None
    try:
        exec(compile(tree, "<exec>", "exec"), ns)
        if last is not None:
            value = eval(compile(_ast.Expression(last.value), "<exec>", "eval"), ns)
    finally:
        # 도중에 멈춰도 그때까지 그린 그림은 보여 준다.
        _images.extend(_figures())
    table = _table(value) if value is not None else None
    text = None if value is None or table is not None else repr(value)
    return _json.dumps({"text": text, "table": table})

def take_images():
    out = _json.dumps(_images)
    _images.clear()
    return out
`;

const LOCKDOWN = `
import sys
class _PracticeImportBlock:
    BLOCKED = ("js", "pyodide", "pyodide_js", "_pyodide", "micropip")
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.BLOCKED:
            raise ImportError(f"{name} 모듈은 실습에서 쓸 수 없습니다")
        return None
for _m in [k for k in list(sys.modules) if k.split(".")[0] in _PracticeImportBlock.BLOCKED]:
    del sys.modules[_m]
sys.meta_path.insert(0, _PracticeImportBlock())
del _m, _PracticeImportBlock
`;

interface PyProxy {
  destroy(): void;
}
interface PyDict extends PyProxy {
  get(key: string): unknown;
  set(key: string, value: unknown): void;
}
interface Pyodide {
  version: string;
  globals: { get(name: string): (...args: unknown[]) => PyDict };
  runPython(code: string, options?: { globals: PyDict }): unknown;
  runPythonAsync(code: string, options?: { globals: PyDict }): Promise<unknown>;
  loadPackagesFromImports(code: string, options?: object): Promise<void>;
  setStdout(options: object): void;
  setStderr(options: object): void;
  setStdin(options: object): void;
}
type RunCell = (src: string, ns: PyDict, display: boolean) => string;
type TakeImages = () => string;

function post(event: RunnerEvent) {
  self.postMessage(event);
}

/** PythonError 메시지의 마지막 줄 "ValueError: ..." 과, 학생 코드 쪽 줄 번호를 꺼낸다. */
function describe(err: unknown): Omit<RunError, 'step'> {
  const text = String((err as { message?: string })?.message ?? err);
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const last = lines.at(-1) ?? '';
  const match = /^([A-Za-z_][\w.]*)(?::\s?(.*))?$/.exec(last);
  // 학생 코드는 "<exec>" 로 찍힌다. 가장 마지막 것이 실제로 멈춘 줄이다.
  const frames = [...text.matchAll(/File "<exec>", line (\d+)/g)];
  const line = frames.length ? Number(frames[frames.length - 1][1]) : null;
  return match ? { type: match[1], message: match[2] ?? '', line } : { type: 'Error', message: last, line };
}

let stdoutChars = 0;
let currentId = '';
let stdinLines: string[] = [];
const sessions = new Map<string, PyDict>();

const ready: Promise<{ py: Pyodide; runCell: RunCell; takeImages: TakeImages }> = (async () => {
  const { loadPyodide } = (await import(/* @vite-ignore */ `${INDEX_URL}pyodide.mjs`)) as {
    loadPyodide: (options: { indexURL: string }) => Promise<Pyodide>;
  };
  const py = await loadPyodide({ indexURL: INDEX_URL });
  // 도우미는 학생 변수 공간과 따로 둔다.
  const helperNs = py.globals.get('dict')();
  py.runPython(HELPER, { globals: helperNs });
  const runCell = helperNs.get('run_cell') as RunCell;
  const takeImages = helperNs.get('take_images') as TakeImages;
  await py.runPythonAsync(LOCKDOWN);
  py.setStdin({ stdin: () => stdinLines.shift() });
  const decoder = new TextDecoder();
  py.setStdout({
    write(buf: Uint8Array) {
      if (stdoutChars < MAX_STDOUT_CHARS) {
        const text = decoder.decode(buf, { stream: true });
        stdoutChars += text.length;
        post({ type: 'stdout', id: currentId, text });
      }
      return buf.length;
    },
  });
  py.setStderr({ batched: (text: string) => post({ type: 'stderr', id: currentId, text: `${text}\n` }) });
  post({ type: 'ready', version: py.version });
  return { py, runCell, takeImages };
})().catch((err) => {
  post({ type: 'boot-error', message: String(err) });
  throw err;
});

function namespace(py: Pyodide, session: string | undefined): PyDict {
  if (session && sessions.has(session)) return sessions.get(session)!;
  const ns = py.globals.get('dict')();
  ns.set('__name__', '__main__');
  if (session) sessions.set(session, ns);
  return ns;
}

async function run(req: RunRequest) {
  const { py, runCell, takeImages } = await ready;
  const { id, steps, session, stdin, displayLast } = req;
  currentId = id;
  stdoutChars = 0;
  stdinLines = stdin ? stdin.replace(/\r\n/g, '\n').split('\n') : [];
  if (stdinLines.length && stdinLines[stdinLines.length - 1] === '') stdinLines.pop();
  const ns = namespace(py, session);
  const finish = () => {
    if (!session) ns.destroy();
  };

  try {
    post({ type: 'loading-packages', id });
    const quiet = { messageCallback: () => {}, errorCallback: () => {} };
    for (const code of steps) await py.loadPackagesFromImports(code, quiet);
  } catch (err) {
    finish();
    post({ type: 'done', id, ok: false, error: { ...describe(err), step: -1 }, value: null, table: null, images: [], ms: 0, truncated: false });
    return;
  }

  post({ type: 'exec', id });
  const t0 = performance.now();
  let error: RunError | null = null;
  let value: string | null = null;
  let table: TableData | null = null;
  for (let i = 0; i < steps.length; i++) {
    try {
      const last = i === steps.length - 1;
      const out = JSON.parse(runCell(steps[i], ns, Boolean(displayLast && last))) as {
        text: string | null;
        table: TableData | null;
      };
      if (last) {
        value = out.text;
        table = out.table;
      }
    } catch (err) {
      error = { ...describe(err), step: i };
      break;
    }
  }
  finish();
  const images = JSON.parse(takeImages()) as string[];
  post({
    type: 'done',
    id,
    ok: error === null,
    error,
    value,
    table,
    images,
    ms: Math.round(performance.now() - t0),
    truncated: stdoutChars >= MAX_STDOUT_CHARS,
  });
}

self.onmessage = async (e: MessageEvent<WorkerRequest>) => {
  const req = e.data;
  if (req.type === 'reset') {
    sessions.get(req.session)?.destroy();
    sessions.delete(req.session);
    return;
  }
  await run(req);
};
