import {createRoot} from 'react-dom/client';
import App from './App.tsx';
import './index.css';

window.addEventListener('vite:preloadError', (event) => {
  if (!('payload' in event) || typeof event.payload !== 'string') return;

  const retryKey = `vite:preload-retry:${event.payload}`;
  if (sessionStorage.getItem(retryKey) === '1') return;

  event.preventDefault();
  sessionStorage.setItem(retryKey, '1');
  window.setTimeout(() => sessionStorage.removeItem(retryKey), 30_000);
  window.location.reload();
});

createRoot(document.getElementById('root')!).render(<App />);
