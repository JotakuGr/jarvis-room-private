import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { LiveSource, type EventStream } from './live';
import { ReadOnlyEventSource, DemoSource } from './source';

const sid = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
const event = (sequence: number, type: string, payload: object, sessionId = sid) => ({ version: 2, source: 'backend', sessionId, sequence, type, observedAt: new Date().toISOString(), payload });
const connected = () => { const source = new ReadOnlyEventSource(); source.receive(event(1, 'connection', { state: 'connected' })); return source; };
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date('2026-10-20T15:00:00Z')); });
afterEach(() => { vi.useRealTimers(); });

describe('v2 presentation contract', () => {
  it('requires valid session identifiers and connected handshake', () => {
    const source = new ReadOnlyEventSource();
    expect(source.receive(event(1, 'voice_state', { state: 'LISTENING' }))).toBe(false);
    expect(source.receive(event(1, 'connection', { state: 'connected' }, 'invalid'))).toBe(false);
  });
  it('rejects invalid calendar timestamps rather than accepting Date.parse normalization', () => {
    const source = connected();
    for (const observedAt of ['2026-02-30T12:00:00Z', '2026-04-31T12:00:00Z', '2026-01-01T24:00:00Z', '0000-01-01T12:00:00Z']) {
      expect(source.receive({ ...event(2, 'heartbeat', {}), observedAt })).toBe(false);
    }
    expect(source.receive({ ...event(2, 'heartbeat', {}), observedAt: '2024-02-29T12:00:00.123456+03:00' })).toBe(true);
  });
  it('discards stale sequence values within a session', () => {
    const source = connected();
    expect(source.receive(event(10, 'voice_state', { state: 'THINKING' }))).toBe(true);
    expect(source.receive(event(9, 'voice_state', { state: 'IDLE' }))).toBe(false);
  });
  it('resets on a new epoch and rejects the retired session', () => {
    const source = connected();
    source.receive(event(10, 'voice_state', { state: 'THINKING' }));
    expect(source.receive(event(1, 'connection', { state: 'connected' }, other))).toBe(true);
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    expect(source.receive(event(11, 'voice_state', { state: 'ERROR' }))).toBe(false);
  });
  it('rejects energy before real playback and clears energy after stop', () => {
    const source = connected();
    expect(source.receive(event(2, 'voice_amplitude', { amplitude: .7 }))).toBe(false);
    source.receive(event(2, 'playback_status', { state: 'playing' }));
    source.receive(event(3, 'voice_amplitude', { amplitude: .7 }));
    expect(source.getSnapshot().amplitude).toBe(.7);
    source.receive(event(4, 'playback_status', { state: 'error' }));
    expect(source.getSnapshot().amplitude).toBe(0);
  });
  it('shows safe model health metadata and rejects secret fields', () => {
    const source = connected();
    expect(source.receive(event(2, 'service_status', { id: 'llm', status: 'connected', detail: 'qwen3.5:4b' }))).toBe(true);
    expect(source.getSnapshot().services.find(s => s.id === 'llm')?.detail).toBe('qwen3.5:4b');
    expect(source.receive(event(3, 'service_status', { id: 'llm', status: 'connected', detail: 'qwen3.5:4b', token: 'never' }))).toBe(false);
  });
  it('keeps virtual helper observation separate from the canonical physical catalog', () => {
    const source = connected();
    expect(source.receive(event(2, 'lab_observation', { entityId: 'input_boolean.jarvis_lab_light', state: 'on', status: 'connected' }))).toBe(true);
    expect(source.getSnapshot().labObservation?.state).toBe('on');
    expect(source.getSnapshot().devices.room_main_lights.status).toBe('planned');
    expect(source.receive(event(3, 'sensor_reading', { sensorId: 'presence_sensor', kind: 'presence', value: true, unit: null }))).toBe(false);
    expect(source.receive(event(3, 'lab_observation', { entityId: 'switch.tv', state: 'on', status: 'connected' }))).toBe(false);
  });
  it('accepts bounded opt-in conversation as text without executing model contents', () => {
    const source = connected();
    expect(source.receive(event(2, 'conversation', { question: 'Como?', answer: 'Ligue os monitores.' }))).toBe(true);
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    expect(source.getSnapshot().devices.samsung_lab_tv.status).toBe('unknown');
    expect(source.receive(event(3, 'conversation', { question: 'x'.repeat(257), answer: 'x' }))).toBe(false);
  });
  it('disconnection removes conversation, helper, health and amplitude', () => {
    const source = connected();
    source.receive(event(2, 'conversation', { question: 'Como?', answer: 'Informação.' }));
    source.invalidate('reconnecting');
    expect(source.getSnapshot().conversation).toBeNull();
    expect(source.getSnapshot().services.every(s => s.status === 'unknown')).toBe(true);
    expect(source.getSnapshot().amplitude).toBe(0);
  });
});

describe('LIVE SSE lifecycle with fake transport', () => {
  function live() {
    const streams: EventStream[] = [];
    const factory = vi.fn((url: string) => { expect(url).toBe('/api/presentation/events'); const stream: EventStream = { onmessage: null, onerror: null, close: vi.fn() }; streams.push(stream); return stream; });
    const source = new LiveSource(factory);
    source.activate();
    const send = (value: unknown, index = streams.length - 1) => streams[index].onmessage?.(new MessageEvent('message', { data: JSON.stringify(value) }));
    return { source, streams, factory, send };
  }
  it('opens one GET stream and sets connected only after a valid handshake', () => {
    const { source, factory, send } = live();
    expect(source.getSnapshot().connection.state).toBe('connecting');
    send(event(1, 'connection', { state: 'connected' }));
    expect(source.getSnapshot().connection.state).toBe('connected');
    source.activate(); expect(factory).toHaveBeenCalledOnce(); source.dispose();
  });
  it('reconnects automatically with cleared data after error', () => {
    const { source, streams, factory, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'voice_state', { state: 'THINKING' }));
    streams[0].onerror?.(new Event('error'));
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    expect(source.getSnapshot().connection.state).toBe('reconnecting');
    vi.advanceTimersByTime(1000); expect(factory).toHaveBeenCalledTimes(2);
    send(event(3, 'voice_state', { state: 'ERROR' }), 0);
    expect(source.getSnapshot().voiceState).toBe('IDLE'); source.dispose();
  });
  it('accepts current snapshots from the same epoch after reconnect', () => {
    const { source, streams, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'voice_state', { state: 'THINKING' }));
    streams[0].onerror?.(new Event('error')); vi.advanceTimersByTime(1000);
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'voice_state', { state: 'THINKING' }));
    expect(source.getSnapshot().voiceState).toBe('THINKING'); source.dispose();
  });
  it('expires missing heartbeat even if events keep arriving', () => {
    const { source, streams, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    vi.advanceTimersByTime(8250);
    expect(streams[0].close).toHaveBeenCalled();
    expect(source.getSnapshot().connection.state).toBe('reconnecting'); source.dispose();
  });
  it('uses valid heartbeat without retaining invalid or old-schema events', () => {
    const { source, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    vi.advanceTimersByTime(5000); send(event(2, 'heartbeat', {}));
    send({ ...event(3, 'voice_state', { state: 'ERROR' }), version: 1 });
    vi.advanceTimersByTime(4000); expect(source.getSnapshot().connection.state).toBe('connected');
    expect(source.getSnapshot().voiceState).toBe('IDLE'); source.dispose();
  });
  it('rejects stale amplitude and zeroes energy when progress stops', () => {
    const { source, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'playback_status', { state: 'playing' }));
    send({ ...event(3, 'voice_amplitude', { amplitude: .9 }), observedAt: '2026-10-19T12:00:00Z' });
    expect(source.getSnapshot().amplitude).toBe(0);
    send(event(3, 'voice_amplitude', { amplitude: .6 }));
    expect(source.getSnapshot().amplitude).toBe(.6);
    vi.advanceTimersByTime(750); expect(source.getSnapshot().amplitude).toBe(0); source.dispose();
  });
  it('dispose closes transport and timers and blocks late events', () => {
    const { source, streams, factory, send } = live();
    source.dispose(); send(event(1, 'connection', { state: 'connected' }));
    vi.advanceTimersByTime(20000); expect(factory).toHaveBeenCalledOnce();
    expect(source.getSnapshot().connection.state).toBe('disconnected');
    expect(streams[0].close).toHaveBeenCalled(); expect(vi.getTimerCount()).toBe(0);
  });
  it('keeps DEMO completely independent of LIVE', () => {
    const { source, send } = live(); const demo = new DemoSource();
    demo.setVoiceState('RESPONDING'); demo.setAmplitude(.9);
    send(event(1, 'connection', { state: 'connected' }));
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    expect(source.getSnapshot().amplitude).toBe(0); demo.dispose(); source.dispose();
  });
  it('keeps passive waiting idle and animates a greeting only with playback energy', () => {
    const { source, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'service_status', { id: 'voice', status: 'connected', detail: 'Microfone aberto; espera por Jarvis' }));
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    send(event(3, 'voice_state', { state: 'RESPONDING' }));
    send(event(4, 'playback_status', { state: 'synthesizing' }));
    expect(source.getSnapshot().amplitude).toBe(0);
    send(event(5, 'playback_status', { state: 'playing' }));
    send(event(6, 'voice_amplitude', { amplitude: .35 }));
    expect(source.getSnapshot().amplitude).toBe(.35);
    send(event(7, 'voice_amplitude', { amplitude: 0 }));
    send(event(8, 'playback_status', { state: 'idle' }));
    send(event(9, 'voice_state', { state: 'IDLE' }));
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    expect(source.getSnapshot().amplitude).toBe(0);
    expect(source.getSnapshot().conversation).toBeNull(); source.dispose();
  });
  it('zeros greeting energy immediately when the backend disconnects', () => {
    const { source, streams, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'voice_state', { state: 'RESPONDING' }));
    send(event(3, 'playback_status', { state: 'playing' }));
    send(event(4, 'voice_amplitude', { amplitude: .7 }));
    streams[0].onerror?.(new Event('error'));
    expect(source.getSnapshot().amplitude).toBe(0);
    expect(source.getSnapshot().voiceState).toBe('IDLE');
    expect(source.getSnapshot().connection.state).toBe('reconnecting'); source.dispose();
  });
  it('rejects a stale or future heartbeat instead of extending the lease', () => {
    const { source, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    vi.advanceTimersByTime(7000);
    send({ ...event(2, 'heartbeat', {}), observedAt: '2026-10-19T12:00:00Z' });
    send({ ...event(3, 'heartbeat', {}), observedAt: '2026-10-22T12:00:00Z' });
    vi.advanceTimersByTime(1250);
    expect(source.getSnapshot().connection.state).toBe('reconnecting'); source.dispose();
  });
  it('rejects an old playing status and a stale connection handshake', () => {
    const { source, send } = live();
    send({ ...event(1, 'connection', { state: 'connected' }), observedAt: '2026-10-19T12:00:00Z' });
    expect(source.getSnapshot().connection.state).toBe('connecting');
    send(event(1, 'connection', { state: 'connected' }));
    send({ ...event(2, 'playback_status', { state: 'playing' }), observedAt: '2026-10-19T12:00:00Z' });
    send(event(3, 'voice_amplitude', { amplitude: .8 }));
    expect(source.getSnapshot().amplitude).toBe(0); source.dispose();
  });
  it('recovers on a new backend epoch without reloading or retaining old data', () => {
    const { source, streams, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'conversation', { question: 'Como?', answer: 'Anterior.' }));
    send(event(3, 'voice_state', { state: 'THINKING' }));
    streams[0].onerror?.(new Event('error')); vi.advanceTimersByTime(1000);
    send(event(1, 'connection', { state: 'connected' }, other));
    send(event(2, 'voice_state', { state: 'LISTENING' }, other));
    send(event(9, 'voice_state', { state: 'ERROR' }, sid));
    expect(source.getSnapshot().sessionId).toBe(other);
    expect(source.getSnapshot().voiceState).toBe('LISTENING');
    expect(source.getSnapshot().conversation).toBeNull(); source.dispose();
  });
  it('keeps reconnecting visible while a replacement stream waits for handshake', () => {
    const { source, streams } = live();
    streams[0].onerror?.(new Event('error')); vi.advanceTimersByTime(1000);
    expect(source.getSnapshot().connection.state).toBe('reconnecting'); source.dispose();
  });
  it('zeroes playback immediately on ERROR and rejects energy until recovery', () => {
    const { source, send } = live();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'playback_status', { state: 'playing' }));
    send(event(3, 'voice_amplitude', { amplitude: .8 }));
    send(event(4, 'voice_state', { state: 'ERROR' }));
    expect(source.getSnapshot().amplitude).toBe(0);
    expect(source.getSnapshot().playback).toBe('error');
    send(event(5, 'playback_status', { state: 'playing' }));
    send(event(6, 'voice_amplitude', { amplitude: .7 }));
    expect(source.getSnapshot().amplitude).toBe(0); source.dispose();
  });
  it('does not change LIVE data when an explicit DEMO source broadcasts', () => {
    const { source, send } = live(); const demo = new DemoSource();
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'voice_state', { state: 'LISTENING' }));
    demo.setDeviceStatus('samsung_lab_tv', 'connected'); demo.demonstrateSpeech();
    vi.advanceTimersByTime(100);
    expect(source.getSnapshot().voiceState).toBe('LISTENING');
    expect(source.getSnapshot().devices.samsung_lab_tv.status).toBe('unknown');
    expect(source.getSnapshot().amplitude).toBe(0); demo.dispose(); source.dispose();
  });
  it('does not claim a model is loaded before observing backend metadata', () => {
    const { source, send } = live();
    expect(source.getSnapshot().services.find(s => s.id === 'llm')?.detail).not.toContain('qwen');
    send(event(1, 'connection', { state: 'connected' }));
    send(event(2, 'service_status', { id: 'llm', status: 'unknown', detail: 'qwen3.5:4b · instalado; sem resposta observada' }));
    expect(source.getSnapshot().services.find(s => s.id === 'llm')?.status).toBe('unknown');
    send(event(3, 'service_status', { id: 'llm', status: 'connected', detail: 'qwen3.5:4b · resposta gerada nesta sessão' }));
    expect(source.getSnapshot().services.find(s => s.id === 'llm')?.status).toBe('connected'); source.dispose();
  });
});
