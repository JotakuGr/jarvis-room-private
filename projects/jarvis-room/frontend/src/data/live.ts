import type { PresentationSource } from '../contracts';
import { ReadOnlyEventSource } from './source';

export interface EventStream {
  onmessage: ((message: MessageEvent<string>) => void) | null;
  onerror: ((event: Event) => void) | null;
  close(): void;
}

/** Apenas GET SSE da mesma origem, sem áudio, tokens ou endpoints de comando. */
export class LiveSource implements PresentationSource {
  private receiver = new ReadOnlyEventSource();
  private stream: EventStream | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private watchdog: ReturnType<typeof setInterval> | null = null;
  private generation = 0;
  private active = false;
  private heartbeat = 0;
  private energy = 0;
  constructor(private factory: (url: string) => EventStream = url => new EventSource(url), private clock = Date.now) {}
  getSnapshot = () => this.receiver.getSnapshot();
  subscribe = (listener: () => void) => this.receiver.subscribe(listener);
  activate() {
    if (this.active) return;
    this.active = true; this.receiver.activate(); this.connect();
    this.watchdog = setInterval(() => {
      if (this.clock() - this.heartbeat > 8000 && this.stream) this.reconnect();
      if (this.clock() - this.energy > 500) this.receiver.silence();
    }, 250);
  }
  private connect() {
    if (!this.active) return;
    this.receiver.invalidate(this.generation === 0 ? 'connecting' : 'reconnecting'); this.heartbeat = this.clock();
    const generation = ++this.generation;
    try {
      const stream = this.factory('/api/presentation/events'); this.stream = stream;
      stream.onmessage = message => {
        if (!this.active || generation !== this.generation || message.data.length > 8192) return;
        try {
          const event = JSON.parse(message.data);
          if (event?.version !== 2) return;
          if (Math.abs(this.clock() - Date.parse(event.observedAt)) > (event.type === 'voice_amplitude' || event.type === 'playback_status' ? 1500 : 8000)
            && ['connection', 'heartbeat', 'playback_status', 'voice_amplitude'].includes(event.type)) return;
          if (!this.receiver.receive(event)) return;
          if (event.type === 'heartbeat' || event.type === 'connection') this.heartbeat = this.clock();
          if (event.type === 'voice_amplitude' || event.type === 'playback_status') this.energy = this.clock();
        } catch { /* Evento inválido não renova heartbeat nem altera dados. */ }
      };
      stream.onerror = () => { if (generation === this.generation) this.reconnect(); };
    } catch { this.reconnect(); }
  }
  private reconnect() {
    this.generation++; this.stream?.close(); this.stream = null;
    this.receiver.invalidate('reconnecting');
    if (this.retry !== null) clearTimeout(this.retry);
    if (this.active) this.retry = setTimeout(() => { this.retry = null; this.connect(); }, 1000);
  }
  dispose() {
    this.active = false; this.generation++; this.stream?.close(); this.stream = null;
    if (this.retry !== null) clearTimeout(this.retry);
    if (this.watchdog !== null) clearInterval(this.watchdog);
    this.retry = this.watchdog = null; this.receiver.invalidate(); this.receiver.dispose();
  }
}
