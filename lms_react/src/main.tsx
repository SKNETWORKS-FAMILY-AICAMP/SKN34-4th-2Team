import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import { App } from './app/App';
import 'material-symbols/rounded.css';
import './app/theme.css';
import './app/styles.css';
import './ui/ui.css';

const host = document.getElementById('root');
if (host === null) throw new Error('#root 를 찾지 못했다');

createRoot(host).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
