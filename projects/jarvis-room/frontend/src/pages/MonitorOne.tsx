import { lazy, Suspense, useState, type CSSProperties } from 'react';
import { usePresentation, useReducedMotion, useVisibility } from '../state';
import { DemoPanel } from '../components/DemoPanel';
import { Icon } from '../components/Icon';
import type { Quality } from '../scene/motion';
const Scene = lazy(() => import('../scene/Scene').then(module => ({ default: module.SceneSurface })));
const stateLabels = { IDLE: 'Em espera', LISTENING: 'Ouvindo', TRANSCRIBING: 'Transcrevendo', THINKING: 'Pensando', RESPONDING: 'Respondendo', ERROR: 'Atenção necessária' };

export function MonitorOne() {
  const { snapshot } = usePresentation(); const reduced = useReducedMotion(); const visible = useVisibility();
  const [quality, setQuality] = useState<Quality>('auto'); const [fullscreenError, setFullscreenError] = useState(false);
  async function fullscreen() { try { if (document.fullscreenElement) await document.exitFullscreen(); else await document.documentElement.requestFullscreen(); } catch { setFullscreenError(true); } }
  return <main className={`monitor-one voice-${snapshot.voiceState.toLowerCase()}`} style={{ '--voice-energy': reduced ? 0 : snapshot.amplitude } as CSSProperties}>
    <div className="lab-backdrop" aria-hidden="true" /><div className="lab-vignette" aria-hidden="true" />
    <div className="environment-wash" aria-hidden="true" /><div className="floor-reflection" aria-hidden="true" />
    <div className="monitor-one-meta"><span className="small-logo">J<span> / </span>ROOM</span><span className="subtle-divider" /><span className="demo-badge">{snapshot.mode === 'demo' ? 'DEMO' : 'LIVE · ' + snapshot.connection.state}</span></div>
    <div className="monitor-one-actions"><DemoPanel quality={quality} setQuality={setQuality} /><button className="icon-button" aria-label="Alternar tela cheia" onClick={fullscreen}><Icon name="expand" /></button><a className="icon-button" href="/monitor/2" target="_blank" rel="noopener noreferrer" aria-label="Abrir dashboard em outra janela"><Icon name="monitor" /></a></div>
    <Suspense fallback={<div className="scene-loading" role="status">Preparando ambiente visual…</div>}><Scene state={snapshot.voiceState} amplitude={reduced ? 0 : snapshot.amplitude} quality={quality} reduced={reduced} visible={visible} /></Suspense>
    <div className="hologram-identity"><h1>J.A.R.V.I.S.</h1><div className="status-rail"><span /><i /><span /></div><p data-testid="voice-state" aria-live="polite">{snapshot.voiceState}</p><span className="state-translation">{stateLabels[snapshot.voiceState]}</span></div>
    <footer className="scene-footer"><span>SALA TEMÁTICA <b> / </b> INTERFACE VISUAL</span><span>{reduced ? 'MOVIMENTO REDUZIDO' : 'HOLOGRAFIA PROCEDURAL'} <b> / </b> {snapshot.mode === 'demo' ? 'AMPLITUDE SIMULADA · SEM TTS REAL' : snapshot.playback === 'playing' ? 'TTS · REPRODUÇÃO REAL' : snapshot.playback === 'synthesizing' ? 'PREPARANDO VOZ' : 'SEM REPRODUÇÃO ATIVA'}</span></footer>
    {fullscreenError && <p className="fullscreen-notice" role="status">Tela cheia indisponível neste navegador. Use o modo de janela.</p>}
  </main>;
}
