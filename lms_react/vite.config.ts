import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  // BrowserRouter를 쓰므로 자산 경로는 절대경로여야 한다. './'로 두면
  // /admin/students 같은 깊은 경로에서 자산을 그 아래에서 찾는다.
  base: '/',
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['src/test/setup.ts'],
  },
});
