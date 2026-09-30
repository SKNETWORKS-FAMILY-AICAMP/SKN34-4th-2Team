/**
 * 표준입력 JSON {jobs: [...]} → 표준출력 JSON {version, results: [...]}.
 *
 * 파이썬(study_notes/practice/runner.py)이 subprocess로 부른다. 작업 여러 개를
 * 한 번에 넘겨야 Pyodide 부팅(약 1초)을 한 번만 한다.
 * kind 가 'web' 인 작업(웹 실습)은 jsdom 으로 돈다(web.mjs) — 그것만 있으면 Pyodide 를 띄우지 않는다.
 */
import { Sandbox } from './sandbox.mjs';
import { runWeb } from './web.mjs';

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const { jobs = [] } = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');

const sandbox = new Sandbox();
const results = [];
for (const job of jobs) results.push(job.kind === 'web' ? runWeb(job) : await sandbox.run(job));
const version = sandbox.version;
await sandbox.close();

process.stdout.write(JSON.stringify({ version, results }));
