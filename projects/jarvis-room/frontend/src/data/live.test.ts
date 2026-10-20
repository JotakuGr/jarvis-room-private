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
});
