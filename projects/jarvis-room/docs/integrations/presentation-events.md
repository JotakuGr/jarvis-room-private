# Contrato de apresentação somente leitura — Sprint 8

Este documento especifica a fronteira futura **antes de criar uma API Python**.
Não existe endpoint implementado ou presumido nesta sprint. O navegador não recebe
token HA, não importa controladores e não envia ações. `ReadOnlyEventSource.receive`
é um ponto de injeção local de eventos validados, não um cliente de rede.

## Envelope v1

```json
{
  "version": 1,
  "source": "backend",
  "sequence": 1,
  "type": "voice_state",
  "observedAt": "2026-10-20T12:00:00Z",
  "payload": { "state": "LISTENING" }
}
```

Todos os campos são obrigatórios; campos extras são rejeitados. `sequence` deve ser
inteiro seguro crescente; `observedAt` deve ter formato ISO com fuso e ser parseável.
Uma sequência não autentica o produtor: transporte e autenticação futuros precisarão
ser definidos e revisados separadamente. Não vincular essa fonte a um LLM.

| Tipo | Payload exato | Restrições |
| --- | --- | --- |
| `connection` | `{state}` | disconnected, connecting, connected, reconnecting |
| `voice_state` | `{state}` | IDLE, LISTENING, TRANSCRIBING, THINKING, RESPONDING, ERROR |
| `voice_amplitude` | `{amplitude}` | Número finito entre 0 e 1 |
| `device_status` | `{id, status, state}` | ID canônico; status permitido; on/off/unknown/unavailable/null |
| `service_status` | `{id, status}` | Seis IDs de serviço conhecidos |
| `sensor_reading` | `{sensorId, kind, value, unit}` | Apenas presença cadastrada; booleano/null; unidade null |

Todos os eventos, exceto conexão, exigem primeiro `connection=connected`.
Desconexão/reconexão limpa observações antigas, amplitude e estado de voz.
Planejados não podem ser promovidos a conectados por evento. Nenhum sensor de
temperatura foi cadastrado: não se aceita valor demonstrativo como medição real.
A futura publicação de temperatura exige cadastro e revisão do contrato.

Os snapshots contêm origem e timestamps; dados ausentes ficam null/desconhecidos.
Não há stale-time automático: o futuro transporte deve emitir desconexão ao perder
heartbeat e definir uma política de validade dos dados antes da integração real.
A UI atual ainda precisa homologar a apresentação dos sensores ao integrar a fonte.

## DEMO

`DemoSource` é independente da fonte futura e usa BroadcastChannel apenas entre
janelas da mesma origem. Estados modificados são rotulados DEMO, sem armazenamento.
Mensagens recebidas não podem executar ou autorizar operações. Trocar para fonte
futura descarta a fonte DEMO. A demonstração de fala gera amplitude matemática,
sem microfone, STT, TTS ou inferência. Sincronização real com TTS permanece pendente.
