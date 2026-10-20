/** Presentation only. No credential, tool, script or authorization contracts. */
export const VOICE_STATES = ['IDLE', 'LISTENING', 'TRANSCRIBING', 'THINKING', 'RESPONDING', 'ERROR'] as const;
export type VoiceState = typeof VOICE_STATES[number];
export type VoiceAmplitude = number & { readonly __normalizedAmplitude: unique symbol };
export type DeviceStatus = 'planned' | 'unknown' | 'offline' | 'connected' | 'unavailable';
export type Origin = 'catalog' | 'demo' | 'backend';
export type Timestamp = string | null;
export type ServiceId = 'voice' | 'ollama' | 'llm' | 'stt' | 'tts' | 'home_assistant';
export interface PresentationPayloads {
  connection: { state: 'disconnected' | 'connecting' | 'connected' | 'reconnecting' };
  heartbeat: Record<string, never>;
  voice_state: { state: VoiceState };
  voice_amplitude: { amplitude: number };
  playback_status: { state: 'idle' | 'synthesizing' | 'playing' | 'unavailable' | 'error' };
  service_status: { id: ServiceId; status: DeviceStatus; detail: string };
  device_status: { id: string; status: DeviceStatus; state: 'on' | 'off' | 'unknown' | 'unavailable' | null };
  lab_observation: { entityId: 'input_boolean.jarvis_lab_light'; status: DeviceStatus; state: 'on' | 'off' | 'unknown' | 'unavailable' | null };
  conversation: { question: string; answer: string };
}
export type PresentationEventV2 = { [K in keyof PresentationPayloads]: {
  readonly version: 2; readonly source: 'backend'; readonly sessionId: string;
  readonly sequence: number; readonly observedAt: string; readonly type: K;
  readonly payload: Readonly<PresentationPayloads[K]>;
} }[keyof PresentationPayloads];
export interface ServiceStatus { readonly id: ServiceId; readonly label: string; readonly detail: string; readonly status: DeviceStatus; readonly source: Origin; readonly observedAt: Timestamp }
export interface ConnectionStatus { readonly state: 'disconnected' | 'connecting' | 'connected' | 'reconnecting'; readonly source: Origin; readonly receivedAt: Timestamp }
export interface SensorReading { readonly sensorId: string; readonly kind: 'presence' | 'temperature'; readonly value: boolean | number | null; readonly unit: '°C' | null; readonly source: Origin; readonly observedAt: Timestamp }
export interface RoomDevice {
  readonly id: string; readonly name: string; readonly group: 'monitores' | 'leds' | 'audio' | null;
  readonly category: 'display' | 'led_strip' | 'audio' | 'light' | 'climate' | 'presence_sensor';
  readonly manufacturer: string | null; readonly model: string | null;
  readonly integration: 'planned' | 'lab_existing'; readonly recordKind: string;
}
export interface RoomSceneStep { readonly id: string; readonly target_kind: 'group' | 'device'; readonly target_id: string; readonly action: 'turn_on' | 'turn_off'; readonly depends_on: readonly string[] }
export interface RoomScene { readonly id: string; readonly operation: 'activate' | 'deactivate'; readonly steps: readonly RoomSceneStep[] }
export interface DeviceObservation { readonly status: DeviceStatus; readonly state: 'on' | 'off' | 'unknown' | 'unavailable' | null; readonly source: Origin; readonly observedAt: Timestamp }
export interface PresentationSnapshot {
  readonly sessionId: string | null; readonly playback: 'idle' | 'synthesizing' | 'playing' | 'unavailable' | 'error';
  readonly labObservation: { entityId: 'input_boolean.jarvis_lab_light'; status: DeviceStatus; state: 'on' | 'off' | 'unknown' | 'unavailable' | null; observedAt: string } | null;
  readonly conversation: { question: string; answer: string; observedAt: string } | null;
  readonly mode: 'demo' | 'backend'; readonly voiceState: VoiceState; readonly amplitude: VoiceAmplitude;
  readonly connection: ConnectionStatus; readonly updatedAt: Timestamp;
  readonly devices: Readonly<Record<string, DeviceObservation>>; readonly services: readonly ServiceStatus[];
  readonly readings: readonly SensorReading[]; readonly speakingDemo: boolean;
}
export interface PresentationSource {
  getSnapshot(): PresentationSnapshot;
  subscribe(listener: () => void): () => void;
  dispose(): void;
}
export function amplitude(value: number): VoiceAmplitude {
  return (Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : 0) as VoiceAmplitude;
}
export function isVoiceState(value: unknown): value is VoiceState { return typeof value === 'string' && (VOICE_STATES as readonly string[]).includes(value); }
