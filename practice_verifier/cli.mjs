/**
 * 표준입력 JSON {jobs: [...]} → 표준출력 JSON {version, results: [...]}.
 *
 * 파이썬(study_notes/practice/runner.py)이 subprocess로 부른다. 작업 여러 개를
 * 한 번에 넘겨야 Pyodide 부팅(약 1초)을 한 번만 한다.
 */
import { Sandbox } from './sandbox.mjs';

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const { jobs = [] } = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');

const sandbox = new Sandbox();
const results = [];
for (const job of jobs) results.push(await sandbox.run(job));
const version = sandbox.version;
await sandbox.close();

process.stdout.write(JSON.stringify({ version, results }));
