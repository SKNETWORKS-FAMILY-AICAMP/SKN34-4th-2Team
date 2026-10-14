// 캡처용 미리보기 서버를 띄운다.
// 예전 스크립트는 포트를 고정해 두고 --strictPort + stdio:'ignore' 로 띄웠다.
// 그래서 지난 실행이 남긴 서버가 그 포트를 잡고 있으면, 새 서버는 소리 없이 죽고
// 캡처는 옛 빌드를 찍었다. 여기서는 빈 포트를 골라 쓰고, 안 뜨면 크게 터뜨린다.
import { spawn } from 'node:child_process';
import net from 'node:net';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// 어느 폴더에서 부르든 lms_react 를 기준으로 삼는다.
export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function freePort() {
  return new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.on('error', reject);
    probe.listen(0, '127.0.0.1', () => {
      const { port } = probe.address();
      probe.close(() => resolve(port));
    });
  });
}

export async function startPreview({ timeoutMs = 30000 } = {}) {
  const port = await freePort();
  // 윈도우 노드는 .cmd 를 shell 없이 띄우지 못한다 (spawn EINVAL).
  const server = spawn(`npx vite preview --port ${port} --strictPort`, {
    cwd: ROOT,
    shell: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  let log = '';
  server.stdout.on('data', (c) => { log += c; });
  server.stderr.on('data', (c) => { log += c; });

  // shell 로 띄우면 kill 은 껍데기만 죽이고 vite 는 남는다. 자식까지 지워야 포트가 풀린다.
  const stop = () => {
    if (process.platform === 'win32' && server.pid) {
      spawn('taskkill', ['/pid', String(server.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      server.kill();
    }
  };

  const base = `http://localhost:${port}`;
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (server.exitCode !== null) {
      throw new Error(`vite preview 가 바로 죽었습니다 (exit ${server.exitCode})\n${log}`);
    }
    try {
      const res = await fetch(`${base}/`);
      if (res.ok) break;
    } catch {
      // 아직 안 떴다
    }
    if (Date.now() > deadline) {
      stop();
      throw new Error(`${timeoutMs / 1000}초 안에 ${base} 가 뜨지 않았습니다\n${log}`);
    }
    await new Promise((r) => setTimeout(r, 200));
  }

  return { port, base, stop };
}
