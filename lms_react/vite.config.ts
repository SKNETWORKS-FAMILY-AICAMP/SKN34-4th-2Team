import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const COOP_COEP = {
  'Cross-Origin-Opener-Policy': 'same-origin',
  'Cross-Origin-Embedder-Policy': 'require-corp',
};

export default defineConfig({
  // BrowserRouter를 쓰므로 자산 경로는 절대경로여야 한다. './'로 두면
  // /admin/students 같은 깊은 경로에서 자산을 그 아래에서 찾는다.
  base: '/',
  plugins: [react()],
  // 연습장의 즉석 input() — 워커가 SharedArrayBuffer 로 잠들었다 깨어나려면 페이지가 cross-origin
  // isolated 여야 한다. 배포(Django · nginx)에서도 이 두 헤더를 그대로 보낸다. 없어도 연습장은
  // 「입력값」 칸 방식으로 돈다.
  server: { headers: COOP_COEP },
  build: {
    rollupOptions: {
      output: {
        // 라이브러리는 앱 코드와 따로 둔다 — 앱을 고쳐 다시 배포해도 브라우저가 이 청크는 캐시에서 쓴다.
        // CodeMirror 는 연습장 청크만 불러 쓰므로 연습장을 열 때만 받는다.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (/node_modules\/(@codemirror|@lezer|style-mod|w3c-keyname|crelt|@marijn)\//.test(id)) return 'codemirror';
          if (/node_modules\/(react|react-dom|scheduler|react-router|react-router-dom|@remix-run)\//.test(id)) return 'react';
          return undefined;
        },
      },
    },
  },
  preview: { headers: COOP_COEP },
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
  },
});
