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

O desenvolvimento da Sprint 2 ocorre em
`feature/sprint2-home-assistant-offline`, criada a partir da `main` atualizada.
A branch deve passar por revisão técnica e PR antes de ser integrada à `main`.
Não haverá merge automático nem início da Sprint 3 antes dessa revisão.

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

Foram aprovados **195 testes locais**: baseline 139 e 56 novos testes offline.
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
