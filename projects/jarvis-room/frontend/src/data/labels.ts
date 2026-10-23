import type { ConnectionStatus, DeviceStatus, PresentationSnapshot, ServiceId } from '../contracts';

export const connectionLabel: Record<ConnectionStatus['state'], string> = {
  connected: 'Conectado', disconnected: 'Desconectado',
  connecting: 'Conectando', reconnecting: 'Desconectado · reconectando',
};
export const playbackLabel: Record<PresentationSnapshot['playback'], string> = {
  idle: 'Sem reprodução ativa', synthesizing: 'Síntese em andamento; saída ainda inativa',
  playing: 'Reprodução real do TTS', unavailable: 'Saída ainda não observada / indisponível',
  error: 'Falha na reprodução',
};
export function serviceLabel(id: ServiceId, status: DeviceStatus): string {
  if (status === 'connected') return 'Observado';
  if (status === 'unknown') return id === 'llm' ? 'Uso não observado' : 'Não observado';
  return { planned: 'Planejado', offline: 'Offline', unavailable: 'Indisponível' }[status];
}
