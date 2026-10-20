import { createRoot } from 'react-dom/client';
import { PresentationProvider } from './state';
import { MonitorOne } from './pages/MonitorOne';
import { MonitorTwo } from './pages/MonitorTwo';
import './styles.css';

const path = window.location.pathname.replace(/\/$/, '') || '/';
if (path === '/') window.history.replaceState(null, '', '/monitor/1');
createRoot(document.getElementById('root')!).render(<PresentationProvider>{path === '/' || path === '/monitor/1' ? <MonitorOne /> : path === '/monitor/2' ? <MonitorTwo /> : <main className="not-found"><h1>Monitor não encontrado</h1><p>Abra uma das interfaces da Sala Temática.</p><a href="/monitor/1">Monitor 1 · J.A.R.V.I.S.</a><a href="/monitor/2">Monitor 2 · Dashboard</a></main>}</PresentationProvider>);
