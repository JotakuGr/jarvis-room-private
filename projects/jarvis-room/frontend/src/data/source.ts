import { amplitude, isVoiceState, type DeviceStatus, type DeviceObservation, type PresentationSnapshot, type PresentationSource, type ServiceStatus, type VoiceState } from '../contracts';
import { devices, deviceById } from './catalog';

const statuses: readonly DeviceStatus[] = ['planned', 'unknown', 'offline', 'connected', 'unavailable'];
const serviceDefinitions = [
  ['voice', 'Sessão de voz', 'Sem sessão real de áudio'], ['ollama', 'Ollama', 'Disponibilidade não consultada'],
  ['llm', 'Modelo de linguagem', 'qwen3.5:4b · configuração Sprint 7'], ['stt', 'Faster-Whisper', 'Reconhecimento local · sem captura'],
  ['tts', 'Síntese de voz', 'Integração visual com TTS pendente'], ['home_assistant', 'Home Assistant', 'Sem conexão no navegador'],
] as const;
function initial(mode: 'demo' | 'backend'): PresentationSnapshot {
  return Object.freeze({
    mode, voiceState: 'IDLE', amplitude: amplitude(0), speakingDemo: false, updatedAt: null,
    connection: { state: 'disconnected' as const, source: mode, receivedAt: null },
    devices: Object.fromEntries(devices.map(d => [d.id, { status: d.integration === 'planned' ? 'planned' : 'unknown', state: null, source: 'catalog', observedAt: null } satisfies DeviceObservation])),
    services: serviceDefinitions.map(([id, label, detail]) => ({ id, label, detail, status: 'unknown', source: 'catalog', observedAt: null } satisfies ServiceStatus)),
    readings: [],
  });
}

/** Volatile DEMO bus. No storage, sockets, device requests or audio access. */
export class DemoSource implements PresentationSource {
  private snapshot = initial('demo');
  private listeners = new Set<() => void>();
  private channel: BroadcastChannel | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private sender = globalThis.crypto?.randomUUID?.() ?? `demo-${Math.random()}`;
  private disposed = false;
  constructor(broadcast = false) { if (broadcast) this.activate(); }
  activate() {
    if (this.channel) return;
    this.disposed = false;
    const broadcast = typeof window !== 'undefined';
    if (broadcast && typeof BroadcastChannel !== 'undefined') {
      this.channel = new BroadcastChannel('jarvis-room.presentation.demo.v1');
      this.channel.onmessage = ({ data }) => this.receiveDemo(data);
      this.channel.postMessage({ schema: 1, sender: this.sender, kind: 'request' });
    }
  }
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  private publish(patch: Partial<PresentationSnapshot>, relay = true) {
    if (this.disposed) return;
    this.snapshot = Object.freeze({ ...this.snapshot, ...patch, updatedAt: new Date().toISOString() });
    this.listeners.forEach(fn => fn());
    if (relay) this.channel?.postMessage({ schema: 1, sender: this.sender, kind: 'snapshot', voiceState: this.snapshot.voiceState, amplitude: this.snapshot.amplitude, devices: this.snapshot.devices, connection: this.snapshot.connection.state, speakingDemo: this.snapshot.speakingDemo });
  }
  setVoiceState(state: VoiceState) { if (!isVoiceState(state)) return; this.stopSpeaking(); this.publish({ voiceState: state, amplitude: amplitude(0), speakingDemo: false }); }
  setAmplitude(value: number) { this.publish({ amplitude: amplitude(value) }); }
  setDeviceStatus(id: string, status: DeviceStatus) {
    if (!deviceById.has(id) || !statuses.includes(status)) return;
    this.publish({ devices: { ...this.snapshot.devices, [id]: { status, state: status === 'connected' ? 'on' : null, source: 'demo', observedAt: new Date().toISOString() } } });
  }
  simulateConnection() {
    const state = this.snapshot.connection.state === 'connected' ? 'disconnected' : 'connected';
    this.publish({ connection: { state, source: 'demo', receivedAt: new Date().toISOString() } });
  }
  demonstrateSpeech() {
    this.stopSpeaking(); const started = Date.now();
    this.publish({ voiceState: 'RESPONDING', speakingDemo: true });
    this.timer = setInterval(() => {
      const t = (Date.now() - started) / 1000;
      if (t >= 8) { this.setVoiceState('IDLE'); return; }
      if (typeof document !== 'undefined' && document.hidden) return;
      this.publish({ amplitude: amplitude(demoEnvelope(t)) });
    }, 60);
  }
  private stopSpeaking() { if (this.timer !== null) clearInterval(this.timer); this.timer = null; }
  private receiveDemo(raw: unknown) {
    if (!raw || typeof raw !== 'object') return;
    const d = raw as Record<string, unknown>;
    if (d.schema !== 1 || d.sender === this.sender || typeof d.sender !== 'string') return;
    if (d.kind === 'request') { this.publish({}); return; }
    if (d.kind !== 'snapshot' || !isVoiceState(d.voiceState) || typeof d.amplitude !== 'number' || !Number.isFinite(d.amplitude) || d.amplitude < 0 || d.amplitude > 1) return;
    const observations: Record<string, DeviceObservation> = { ...this.snapshot.devices };
    if (d.devices && typeof d.devices === 'object') {
      for (const [id, value] of Object.entries(d.devices)) {
        if (!deviceById.has(id) || !value || typeof value !== 'object') continue;
        const item = value as DeviceObservation;
        if (statuses.includes(item.status) && (item.source === 'catalog' || item.source === 'demo')) observations[id] = {
          status: item.status, state: item.status === 'connected' ? 'on' : null, source: item.source, observedAt: item.source === 'demo' ? new Date().toISOString() : null,
        };
      }
    }
    const connection = ['connected', 'disconnected', 'connecting', 'reconnecting'].includes(String(d.connection)) ? d.connection as PresentationSnapshot['connection']['state'] : 'disconnected';
    this.publish({ voiceState: d.voiceState, amplitude: amplitude(d.amplitude), devices: observations,
      speakingDemo: d.speakingDemo === true, connection: { state: connection, source: 'demo', receivedAt: new Date().toISOString() } }, false);
  }
  dispose() { this.disposed = true; this.stopSpeaking(); this.channel?.close(); this.channel = null; this.listeners.clear(); }
}

export function demoEnvelope(t: number): number {
  const attack = Math.min(1, t * 3) * Math.min(1, Math.max(0, 8 - t) * 2);
  const syllable = Math.pow(Math.max(0, Math.sin(t * 8.1) * .55 + Math.sin(t * 13.7) * .3 + .35), 1.4);
  return Math.min(1, .12 + syllable * .65) * attack;
}

/** Future read-only seam. No URL or transport is assumed or opened here. */
export class ReadOnlyEventSource implements PresentationSource {
  private snapshot = initial('backend'); private listeners = new Set<() => void>(); private sequence = -1; private disposed = false;
  activate() { this.disposed = false; }
  getSnapshot = () => this.snapshot;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  receive(raw: unknown): boolean {
    if (this.disposed || !raw || typeof raw !== 'object' || Array.isArray(raw)) return false;
    const data = raw as Record<string, unknown>;
    if (Object.keys(data).sort().join(',') !== 'observedAt,payload,sequence,source,type,version' || data.version !== 1 || data.source !== 'backend'
      || typeof data.sequence !== 'number' || !Number.isSafeInteger(data.sequence) || data.sequence <= this.sequence
      || typeof data.observedAt !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(data.observedAt) || !Number.isFinite(Date.parse(data.observedAt))
      || !data.payload || typeof data.payload !== 'object' || Array.isArray(data.payload)) return false;
    const p = data.payload as Record<string, unknown>; const keys = Object.keys(p).sort().join(',');
    if (data.type !== 'connection' && this.snapshot.connection.state !== 'connected') return false;
    let patch: Partial<PresentationSnapshot>;
    if (data.type === 'voice_state' && keys === 'state' && isVoiceState(p.state)) patch = { voiceState: p.state };
    else if (data.type === 'voice_amplitude' && keys === 'amplitude' && typeof p.amplitude === 'number' && Number.isFinite(p.amplitude) && p.amplitude >= 0 && p.amplitude <= 1) patch = { amplitude: amplitude(p.amplitude) };
    else if (data.type === 'device_status' && keys === 'id,state,status' && typeof p.id === 'string' && deviceById.has(p.id)
      && statuses.includes(p.status as DeviceStatus) && ['on', 'off', 'unknown', 'unavailable', null].includes(p.state as string | null)) {
      // A presentation event cannot upgrade a planned integration to operational.
      if (deviceById.get(p.id)?.integration === 'planned' && (p.status !== 'planned' || p.state !== null)) return false;
      patch = { devices: { ...this.snapshot.devices, [p.id]: { status: p.status as DeviceStatus, state: p.state as DeviceObservation['state'], source: 'backend', observedAt: data.observedAt } } };
    } else if (data.type === 'service_status' && keys === 'id,status' && statuses.includes(p.status as DeviceStatus) && this.snapshot.services.some(s => s.id === p.id)) {
      patch = { services: this.snapshot.services.map(s => s.id === p.id ? { ...s, status: p.status as DeviceStatus, source: 'backend', observedAt: data.observedAt as string } : s) };
    } else if (data.type === 'connection' && keys === 'state' && ['disconnected', 'connecting', 'connected', 'reconnecting'].includes(p.state as string)) {
      patch = { connection: { state: p.state as PresentationSnapshot['connection']['state'], source: 'backend', receivedAt: new Date().toISOString() } };
      if (p.state !== 'connected') patch = { ...patch, devices: initial('backend').devices, services: initial('backend').services, readings: [], voiceState: 'IDLE', amplitude: amplitude(0) };
    } else if (data.type === 'sensor_reading' && keys === 'kind,sensorId,unit,value' && p.kind === 'presence'
      && p.unit === null && typeof p.sensorId === 'string' && deviceById.get(p.sensorId)?.category === 'presence_sensor'
      && (p.value === null || typeof p.value === 'boolean')) {
      patch = { readings: [{ sensorId: p.sensorId, kind: 'presence', value: p.value, unit: null, source: 'backend', observedAt: data.observedAt }] };
    } else return false;
    this.sequence = data.sequence;
    this.snapshot = Object.freeze({ ...this.snapshot, ...patch, updatedAt: data.observedAt });
    this.listeners.forEach(fn => fn()); return true;
  }
  dispose() { this.disposed = true; this.listeners.clear(); }
}
