# Contrato de apresentação — v2 / Sprint 9

Backend implementado em `jarvis_room.presentation_server`, SSE somente leitura
no loopback. Publicação exclusiva por socket Unix privado do mesmo UID.
[Arquitetura, comandos e segurança](voice-frontend-integration.md).

## Envelope atual

```json
{
  "version": 2,
  "source": "backend",
  "sessionId": "11111111-1111-4111-8111-111111111111",
  "sequence": 1,
  "type": "voice_state",
  "observedAt": "2026-10-20T15:00:00Z",
  "payload": { "state": "LISTENING" }
}
```

Campos exatos, sem extras; versão inteira 2, origem backend, UUID canônico,
sequência inteira segura não negativa/crescente por época e timestamp ISO com
fuso. Payloads são validados em Python e TypeScript. Na rede LIVE aceita-se
apenas v2; o receptor isolado conserva v1 para os testes/contratos anteriores.

`sessionId` identifica a época da apresentação. A sessão de voz possui UUID
próprio no handshake Unix; cada conexão de produtor cria uma época nova no
backend, mesmo se o processo de voz estiver reconectando. Isso impede rollback
para estados da conexão anterior. Não representa identidade do operador.

| Tipo | Payload exato | Restrições |
| --- | --- | --- |
| `connection` | `{state}` | disconnected, connecting, connected, reconnecting |
| `heartbeat` | `{}` | Renova validade do transporte, não de medidas físicas |
| `voice_state` | `{state}` | Seis estados reais S7 |
| `playback_status` | `{state}` | idle, synthesizing, playing, unavailable, error |
| `voice_amplitude` | `{amplitude}` | Número finito 0–1; positivo só durante playing |
| `service_status` | `{id,status,detail}` | IDs voice/ollama/llm/stt/tts/home_assistant, status conhecido, detalhe até 128 caracteres imprimíveis |
| `device_status` | `{id,status,state}` | ID canônico; planejados não são promovidos por apresentação |
| `lab_observation` | `{entityId,status,state}` | Entidade exata input_boolean.jarvis_lab_light; auxiliar virtual |
| `conversation` | `{question,answer}` | Opt-in Python; até 256/700 caracteres imprimíveis |

Status: planned, unknown, offline, connected, unavailable. Estado observado:
on, off, unknown, unavailable ou null. Observação de laboratório não conectada
só admite null/unavailable. Não há payload v2 para sensor físico: nenhum sensor
foi observado nesta integração. Não existem campos de token, áudio, ferramentas,
comandos, autorização ou confirmação física.

## Transporte, validade e privacidade

- GET `/events` no backend; navegador usa somente `/api/presentation/events`
  no proxy Vite. SSE envia `data: JSON` seguido de linha vazia, sem áudio bruto.
- Primeiro evento precisa ser conexão; mesma época rejeita sequências antigas
  ou repetidas. Nova época só começa por conexão válida e limpa o snapshot.
- Heartbeat 2 s; ausência por 8 s desconecta/invalida no frontend. Reconexão
  automática após 1 s recebe o último snapshot em ordem; não reproduz histórico
  de ações. Dados DEMO nunca entram na fonte LIVE.
- Energia expira sem progresso, é zerada em stop/erro/desconexão e não é
  reaproveitada quando seu timestamp está atrasado. Ver limites no guia.
- Um produtor Unix por vez, com lease e heartbeat. UID/permissões autenticam o
  processo local, não o operador ou a realidade de um equipamento.
- Handshake Unix exato `{version:2, sessionId, model}` (model null se a conversa
  estiver desabilitada); mensagens seguintes `{type,payload}`. O backend cria
  época, sequência e timestamp, sem aceitar esses valores do produtor.
- Conversa desabilitada por padrão. `--share-conversation` autoriza publicação
  informativa; Monitor 2 exige também seleção de exibição. Só último par volátil,
  sem armazenamento persistente, HTML executável ou reinterpretação como comando.
- Status de serviço conserva horário da observação; pacote/modelo instalado não
  comprova inferência, naturalidade, dispositivo disponível ou execução física.

## Histórico — contrato da Sprint 8 (v1)

O trecho abaixo preserva a especificação original; o transporte atual e suas
políticas de validade estão definidos na v2 acima.


Este documento especifica a fronteira futura **antes de criar uma API Python**.
Não existe endpoint implementado ou presumido nesta sprint. O navegador não recebe
token HA, não importa controladores e não envia ações. `ReadOnlyEventSource.receive`
é um ponto de injeção local de eventos validados, não um cliente de rede.

### Envelope v1

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

### DEMO

`DemoSource` é independente da fonte futura e usa BroadcastChannel apenas entre
janelas da mesma origem. Estados modificados são rotulados DEMO, sem armazenamento.
Mensagens recebidas não podem executar ou autorizar operações. Trocar para fonte
futura descarta a fonte DEMO. A demonstração de fala gera amplitude matemática,
sem microfone, STT, TTS ou inferência. Sincronização real com TTS permanece pendente.
