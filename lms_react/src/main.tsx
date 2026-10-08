import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './app/App';
import { registerRuntimeCache } from './features/practice/runtimeCache';
import 'material-symbols/rounded.css';
import './app/theme.css';
import './app/styles.css';
import './ui/ui.css';
import { LocalResumeE2E } from './features/jobApply/LocalResumeE2E';

// Dedicated debug route bypasses production bootstrap/v1 requests entirely.
const localPreview = import.meta.env.DEV && import.meta.env.VITE_LOCAL_RESUME_E2E === '1'
  && ['localhost', '127.0.0.1'].includes(location.hostname)
  && location.pathname === '/local/resume-e2e';

const host = document.getElementById('root');
if (host === null) throw new Error('#root 를 찾지 못했다');

createRoot(host).render(
  <StrictMode>
    <BrowserRouter>
      {localPreview ? <LocalResumeE2E /> : <App />}
    </BrowserRouter>
  </StrictMode>,
);

if (!localPreview) registerRuntimeCache();
