/**
 * 워커 하나를 붙잡고 작업을 차례로 돌린다. 시간을 넘기면 워커를 죽이고 새로 띄운다.
 *
 * 작업: { id, steps: [code, ...], timeoutMs }
 *   steps 는 같은 변수 공간에서 이어서 실행된다 — [학생 코드, 숨긴 테스트] 처럼.
 * 결과: { id, ok, stdout, stdoutTruncated, error: {type, message, step} | null, timedOut, ms }
 */
import { Worker } from 'node:worker_threads';

const WORKER_URL = new URL('./worker.mjs', import.meta.url);
const DEFAULT_TIMEOUT_MS = 3000;

export class Sandbox {
  #worker = null;
  #ready = null;
  version = null;

  #spawn() {
    const worker = new Worker(WORKER_URL);
    this.#worker = worker;
    this.#ready = new Promise((resolve, reject) => {
      const onMessage = (msg) => {
        if (msg.ready) {
          this.version = msg.version;
          worker.off('message', onMessage);
          resolve(worker);
        }
      };
      worker.on('message', onMessage);
      worker.once('error', reject);
    });
    return this.#ready;
  }

  async #get() {
    return this.#ready ?? this.#spawn();
  }

  async #kill() {
    const worker = this.#worker;
    this.#worker = null;
    this.#ready = null;
    if (worker) await worker.terminate();
  }

  async run({ id, steps, timeoutMs = DEFAULT_TIMEOUT_MS }) {
    const worker = await this.#get();
    return new Promise((resolve) => {
      let timer = null;
      const finish = (result) => {
        clearTimeout(timer);
        worker.off('message', onMessage);
        worker.off('error', onError);
        resolve(result);
      };
      const onMessage = (msg) => {
        if (msg.id !== id) return;
        if (msg.phase === 'exec') {
          timer = setTimeout(async () => {
            finish({ id, ok: false, stdout: '', error: null, timedOut: true, ms: timeoutMs });
            await this.#kill();
          }, timeoutMs);
          return;
        }
        finish({ ...msg, timedOut: false });
      };
      const onError = async (err) => {
        finish({ id, ok: false, stdout: '', error: { type: 'WorkerCrash', message: String(err), step: -1 }, timedOut: false, ms: 0 });
        await this.#kill();
      };
      worker.on('message', onMessage);
      worker.once('error', onError);
      worker.postMessage({ id, steps });
    });
  }

  async close() {
    await this.#kill();
  }
}
