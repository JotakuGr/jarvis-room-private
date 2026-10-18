# J.A.R.V.I.S. — Sala Temática

Projeto de desenvolvimento de um assistente inteligente local para uma sala
temática universitária.

## Objetivo

Integrar inteligência artificial local, automação, interfaces gráficas,
comandos de voz, sensores e dispositivos IoT em uma experiência inspirada
no conceito J.A.R.V.I.S.

## Arquitetura planejada

- OpenJarvis — agente e orquestração
- Ollama — inferência local
- Home Assistant — automação da sala
- MCP — integração entre IA e ferramentas
- Faster-Whisper — reconhecimento de voz
- TTS local — síntese de voz
- ESP32 / ESPHome / WLED — dispositivos IoT
- Frigate — visão computacional e presença

## Interfaces

### Monitor 1

Interface visual e interativa do J.A.R.V.I.S.

Estados planejados:

- IDLE
- OUVINDO
- PENSANDO
- EXECUTANDO
- FALANDO
- ERRO

### Monitor 2

Dashboard operacional contendo:

- temperatura;
- umidade;
- ar-condicionado;
- luzes;
- LEDs;
- televisores;
- presença;
- sensores;
- status dos serviços.

## Ambiente de desenvolvimento

Desenvolvimento:

Windows + WSL2 + Ubuntu.

Produção futura:

Linux nativo.

## Estado atual

A fundação da Sprint 1 foi integrada à `main` pelo PR #10.
O repositório Git é a subpasta `openjarvis` do workspace `jarvis-room`.
As customizações permanecem em `projects/jarvis-room/`.

A Sprint 2 foi integrada à `main` pelo PR #11, incluindo a correção do vínculo
sintético. A Sprint 3 é desenvolvida em `feature/sprint3-ha-laboratorio-readonly`,
a partir dessa `main`. Não haverá merge automático nem início da Sprint 4
antes de revisão externa, PR, validação de CI e merge da Sprint 3.

### Sprint 2 — planejamento e simulações offline

- Seis dispositivos lógicos cadastrados como `planned`, sem entidades reais.
- Hikvision **DS-D5B65RB/D** cadastrada com interfaces documentadas; nenhum
  protocolo serial ou de rede verificado e nenhum controle realizado.
- Segunda tela/TV apenas como placeholder, sem modelo confirmado.
- WLED/ESP32 e WS2815 de 12 V planejados: os 100 m a 60 LEDs/m são premissas,
  não instalação confirmada. Potência e distribuição elétrica ainda pendentes.
- Política de automação sempre negativa; `actor_id` não autentica usuários.
- Transporte real desabilitado; fake exclusivamente em testes.
- Resultados `simulated_match` verificam somente consistência de valores
  simulados e sempre mantêm `physical_action_verified=False`.
- CLI da Sprint 1 preservada: identidade pelo catálogo e controle físico negado.

**Home Assistant não está conectado. Não há estados reais de LEDs, confirmação
de equipamentos ou autorização de controle físico.**

Foram aprovados **197 testes locais**: baseline 139, 56 novos testes offline
da implementação original e dois testes da correção do vínculo sintético.
O modelo `jarvis-dev-lite` permanece experimental; esta sprint não executa
inferência nem certifica modelo para produção. Modelos maiores serão avaliados
em ambiente apropriado e na máquina definitiva da Sala Temática.

Para repetir as verificações sem Home Assistant ou LLM:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.home_assistant_catalog
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_chat_cli 'Ligue a luz da sala'
```

Detalhes: [homologação da Sprint 2](docs/reports/sprint-2-acceptance.md),
[contrato Home Assistant](docs/integrations/home-assistant-offline.md),
[plano Hikvision](docs/integrations/hikvision-ds-d5b65rb-d.md) e
[pré-requisitos elétricos WLED](docs/integrations/wled-electrical-prerequisites.md).

### Sprint 3 — laboratório read-only, offline por padrão

Foram aprovados **261 testes locais**: os 197 anteriores e 64 novos testes.

- Manifesto restrito e Compose de laboratório com porta publicada somente em
  `127.0.0.1:18123`, volume nomeado, bridge e sem privilégios.
- Cliente GET desabilitado por padrão, destino fixo, sem proxies ou redirects,
  com timeout e tamanho de resposta limitados. Nenhum POST/serviço implementado.
- Helper previsto: `input_boolean.jarvis_lab_light`, diferente de `light.sala`.
  Sua criação e ID efetivo ainda não foram confirmados em uma instância real.
- `ha_lab_cli` independente: offline sem token. Para leitura opcional, exigir
  `--read-lab`, `JARVIS_HA_LAB_READ=1` e token obtido por entrada oculta ou
  arquivo privado fora do repositório. Nunca passar token em comando ou CI.
- Estado informativo e sanitizado, sempre `physical_action_verified=false`.
  Nenhuma conexão ao LLM ou ao gateway de controle físico.
- Checklists Hikvision e WLED mantêm protocolo, autorização e dimensionamento
  elétrico como não comprovados, sem habilitar equipamentos.

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.ha_lab_cli
docker compose -f projects/jarvis-room/lab/home-assistant/compose.yaml config
```

O Compose foi validado, mas a subida foi adiada por compatibilidade operacional
do Docker Desktop. Não houve onboarding, token real, helper criado ou GET real
ao HA. A tag `stable` ainda não foi baixada; versão/digest devem ser registrados
quando o laboratório for efetivamente homologado.

Loopback não garante isolamento total de rede. O token HA não é
intrinsecamente read-only; a restrição é do cliente. Preservar o volume com
`down` sem `-v` e criar backup privado antes de atualizações.

Detalhes: [relatório da Sprint 3](docs/reports/sprint-3-acceptance.md),
[fronteiras do laboratório](docs/integrations/ha-lab-architecture.md),
[checklist Hikvision](docs/integrations/hikvision-lab-checklist.md) e
[prontidão WLED](docs/integrations/wled-zoning-readiness.md).

### Sprint 4 — Samsung em laboratório físico, aguardando revisão final

Implementação separada para a Samsung **LH32BETBLGGXZD**, na branch
`feature/sprint4-samsung-ha-control`, derivada da `main` após o merge da Sprint 3
(PR #12). A Sprint 4 **não está encerrada**: os dois acionamentos autorizados
foram observados pelo operador; falta consolidar a homologação e a revisão final.

- Inventário exclusivo `config/samsung_lab.json`; não altera o catálogo planejado
  nem os helpers virtuais das Sprints 2/3.
- Destino fixo local, GET da TV/scripts e POST somente dos dois scripts fornecidos
  pelo operador. IDs renomeados não são presumidos ou descobertos por fallback.
- CLI independente `python3.11 -m jarvis_room.samsung_lab_cli`: offline por padrão;
  execução manual exige opt-in, terminal, frase exata, token privado e auditoria.
- Nenhuma ferramenta de LLM recebe esse cliente. `RoomControlGateway` e o cliente
  read-only da Sprint 3 permanecem intactos.
- Estado reportado pelo HA, comando aceito e confirmação física são distintos;
  `physical_action_verified` permanece falso.
- Observação após aceite: prazo configurável de 1 a 30 s, GETs periódicos sem
  reenvio do POST, encerramento antecipado e métricas no resultado/auditoria.
  Timeout significa estado não confirmado no prazo; confirmação física segue falsa.
- **356/356 testes locais**: 261 anteriores preservados e 95 novos simulados.
  A janela revisada recebeu 20 testes adicionais, sem novos acionamentos reais.
  A sessão anterior teve dois POSTs autorizados, com observação visual do operador
  para ligar e desligar; nenhuma inferência foi executada.

[Procedimento de homologação Samsung](docs/integrations/samsung-lab-control.md),
[decisão arquitetural](docs/adr/0002-samsung-manual-control.md) e
[relatório de aceitação](docs/reports/sprint-4-acceptance.md).

### Sprint 5 — comandos Samsung por texto, sem LLM na execução

A Sprint 4 foi integrada à `main` pelo PR #13. A Sprint 5 é desenvolvida em
`feature/sprint5-samsung-natural-commands`, baseada nessa `main`, com baseline
de 356 testes. A nova interface textual ainda não possui homologação física.

- Oito frases completas cadastradas: ligue/desligue a TV/televisão, com Samsung
  opcional; prefixo Jarvis, caixa, acentuação e pontuação simples normalizados.
- Negação, múltiplas ações, condições, horários, entidades/URLs arbitrárias e
  dispositivos desconhecidos são bloqueados. Nenhuma correspondência parcial.
- `samsung_text_cli` reconhece offline por padrão, sem token ou rede. `--execute`
  reutiliza integralmente autorização, token, auditoria e controlador da Sprint 4.
- `room_chat_cli --samsung-control` seleciona o mesmo fluxo manual e é incompatível
  com LLM/provedor. Sem essa flag, o comportamento anterior continua bloqueado.
- Respostas distinguem reconhecimento, autorização, aceite, estado HA, timeout e
  entrega incerta; flags de verificação permanecem falsas. Nenhum retry de POST.
- S5.1–S5.10: **441/441 testes aprovados**: 356 anteriores e 85 novos. Nenhum acionamento,
  acesso real ao HA ou inferência nesta sprint. Isto é texto, não voz.

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.samsung_text_cli \
  "Jarvis, ligue a TV Samsung."
```

[Guia e diagramas](docs/integrations/samsung-natural-commands.md),
[ADR-0003](docs/adr/0003-samsung-natural-commands.md) e
[relatório da Sprint 5](docs/reports/sprint-5-acceptance.md).

### S5.11 — sessão textual contínua

Regressão local: **494/494**, incluindo os 441 anteriores e 53 testes novos.
Nenhum acesso real ao HA, acionamento físico ou inferência foi executado nesta
implementação. A nova sessão ainda exige homologação física supervisionada.

Sessão informativa, com catálogo local e controle desabilitado:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_session_cli
```

Para uma futura sessão autorizada de controle, no terminal local interativo:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_session_cli \
  --enable-samsung \
  --token-file "$HOME/.config/jarvis-room/secrets/ha-samsung-token" \
  --audit-file "$HOME/.config/jarvis-room/samsung-audit.jsonl" \
  --observation-timeout 30
```

Digite `Jarvis, ligue a TV.` ou `Jarvis, desligue a televisão Samsung.`.
`--enable-samsung` autoriza esses comandos durante a sessão, **sem segunda
confirmação por ação**. `sair`, EOF ou Ctrl+C encerram a autorização.
Não há opção de ler comandos de arquivo ou de argumentos. Ambas as sessões
exigem stdin/stdout TTY. As CLIs antigas mantêm a confirmação por ação e seu
opt-in ambiental; a nova sessão usa a flag explícita como opt-in próprio.

`--llm` é opcional para perguntas informativas experimentais, com o provedor
local e a política de memória existentes. Respostas do modelo são apenas
exibidas como não verificadas, sem ferramentas físicas ou redirecionamento.
Nenhuma frase de conversa habilita controle. As flags de verificação física
permanecem falsas; uma resposta de sucesso exige estado correspondente do HA
dentro do prazo. Texto contínuo não implementa voz nem memória entre inferências.

[Modos, arquitetura e homologação da sessão](docs/integrations/samsung-natural-commands.md#s511--sessão-textual-contínua).
