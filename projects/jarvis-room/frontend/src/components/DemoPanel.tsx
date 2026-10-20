import { useEffect, useState } from 'react';
import { VOICE_STATES } from '../contracts';
import { usePresentation } from '../state';
import { devices } from '../data/catalog';
import type { Quality } from '../scene/motion';
import { Icon } from './Icon';

export function DemoPanel({ quality, setQuality }: { quality?: Quality; setQuality?: (q: Quality) => void }) {
  const { snapshot, mode, setMode, demo } = usePresentation();
  const [open, setOpen] = useState(false);
  useEffect(() => { const key = (event: KeyboardEvent) => {
    if ((event.target as HTMLElement)?.closest('input,select,textarea,button')) return;
    if (event.key.toLowerCase() === 'd') setOpen(value => !value);
    if (event.key === 'Escape') setOpen(false);
  }; window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key); }, []);
  return <div className="demo-control">
    <button className="icon-button demo-trigger" aria-label="Abrir controles de demonstração" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="settings" /><span>Controles</span></button>
    {open && <section className="demo-panel" aria-label="Controles de desenvolvimento">
      <div className="panel-heading"><span>AMBIENTE DE DESENVOLVIMENTO</span><button className="icon-button" aria-label="Fechar controles" onClick={() => setOpen(false)}><Icon name="close" size={16} /></button></div>
      <h2>Laboratório visual <span className="demo-badge">DEMO</span></h2>
      <p>DEMO é simulação; LIVE mostra observações do backend local, sem controle físico.</p>
      <label className="field-label">Fonte de dados<select aria-label="Fonte de dados" value={mode} onChange={e => setMode(e.target.value as 'demo' | 'backend')}><option value="demo">DEMO · simulação local</option><option value="backend">LIVE · backend local somente leitura</option></select></label>
      {demo ? <>
        <span className="field-label">Estado de voz simulado</span>
        <div className="state-controls">{VOICE_STATES.map(state => <button key={state} className={snapshot.voiceState === state ? 'selected' : ''} onClick={() => demo.setVoiceState(state)}>{state}</button>)}</div>
        <label className="field-label">Amplitude simulada <output>{Math.round(snapshot.amplitude * 100)}%</output><input aria-label="Amplitude simulada" type="range" min="0" max="1" step="0.01" value={snapshot.amplitude} onChange={e => demo.setAmplitude(Number(e.target.value))} disabled={snapshot.speakingDemo} /></label>
        <button className="primary-button" onClick={() => demo.demonstrateSpeech()}><Icon name="play" size={15} /> Demonstrar resposta · 8 segundos</button>
        <button className="secondary-button" onClick={() => demo.setVoiceState('IDLE')}>Retornar a IDLE</button>
        <div className="demo-divider" />
        <label className="field-label">Status demonstrativo da Samsung<select aria-label="Status demonstrativo da Samsung" value={snapshot.devices.samsung_lab_tv.status} onChange={e => demo.setDeviceStatus('samsung_lab_tv', e.target.value as typeof snapshot.devices.samsung_lab_tv.status)}>{['unknown', 'planned', 'connected', 'offline', 'unavailable'].map(s => <option key={s} value={s}>{s}</option>)}</select></label>
        <button className="secondary-button" onClick={() => demo.simulateConnection()}>Simular mudança de conexão</button>
        <small>{devices.length} registros do catálogo canônico. Status alterados aqui são DEMO.</small>
      </> : <div className="empty-state">LIVE · {snapshot.connection.state}. Estados e energia vêm da sessão real; sem comandos pelo navegador.</div>}
      {setQuality && <label className="field-label">Qualidade visual<select aria-label="Qualidade visual" value={quality} onChange={e => setQuality(e.target.value as Quality)}><option value="auto">Automática · conservadora</option><option value="low">Econômica</option><option value="balanced">Equilibrada</option><option value="high">Alta · validar na Sala Temática</option></select></label>}
      <small>Atalho D · controles. Esc · fechar.</small>
    </section>}
  </div>;
}
