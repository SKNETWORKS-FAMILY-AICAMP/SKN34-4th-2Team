/**
 * Pyodide를 띄워 두고 작업을 하나씩 실행하는 워커.
 *
 * 무한 루프는 파이썬 안에서 끊을 수 없다. 부모(sandbox.mjs)가 시간을 재다가
 * 이 워커를 통째로 terminate 한다. 그래서 실행을 시작하는 순간을 'exec'로 알린다
 * — 부팅·패키지 내려받기 시간까지 제한 시간에 넣으면 첫 작업만 억울하게 걸린다.
 */
import { parentPort } from 'node:worker_threads';
import { loadPyodide } from 'pyodide';

const MAX_STDOUT_CHARS = 20_000;

// 학생 코드가 JS 세계(= Node의 process 등)로 나가는 문을 닫는다.
// 패키지 로딩은 JS 쪽에서 하므로 파이썬에서 이 모듈들을 못 불러도 지장이 없다.
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

const py = await loadPyodide({ packageCacheDir: process.env.PRACTICE_PKG_DIR || undefined });
await py.runPythonAsync(LOCKDOWN);
py.setStdin({ error: true });

let stdout = '';
let truncated = false;
const decoder = new TextDecoder();
py.setStdout({
  write(buf) {
    if (stdout.length < MAX_STDOUT_CHARS) stdout += decoder.decode(buf, { stream: true });
    else truncated = true;
    return buf.length;
  },
});
py.setStderr({ batched: () => {} });

/** PythonError 메시지의 마지막 줄 "AssertionError: ..." 에서 예외 이름과 문장을 꺼낸다. */
function describe(err) {
  const lines = String(err?.message ?? err).split('\n').map((l) => l.trim()).filter(Boolean);
  const last = lines.at(-1) ?? '';
  const match = /^([A-Za-z_][\w.]*)(?::\s?(.*))?$/.exec(last);
  return match ? { type: match[1], message: match[2] ?? '' } : { type: 'Error', message: last };
}

parentPort.on('message', async ({ id, steps }) => {
  stdout = '';
  truncated = false;
  const globals = py.globals.get('dict')();
  globals.set('__name__', '__main__');
  try {
    // 패키지는 실행 전에 받는다. 이 시간은 제한 시간에 넣지 않는다.
    // 「Loading numpy」 안내가 학생 출력에 섞이지 않게 버린다.
    const quiet = { messageCallback: () => {}, errorCallback: () => {} };
    for (const code of steps) await py.loadPackagesFromImports(code, quiet);
  } catch (err) {
    globals.destroy();
    parentPort.postMessage({ id, ok: false, stdout: '', error: { type: 'PackageError', message: describe(err).message, step: -1 } });
    return;
  }
  parentPort.postMessage({ id, phase: 'exec' });
  const t0 = performance.now();
  let error = null;
  for (let i = 0; i < steps.length; i++) {
    try {
      await py.runPythonAsync(steps[i], { globals });
    } catch (err) {
      error = { ...describe(err), step: i };
      break;
    }
  }
  globals.destroy();
  parentPort.postMessage({
    id,
    ok: error === null,
    stdout,
    stdoutTruncated: truncated,
    error,
    ms: Math.round(performance.now() - t0),
  });
});

parentPort.postMessage({ ready: true, version: py.version });
