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
sintético. As seções abaixo registram marcos históricos de cada sprint.
Estado atual: Sprint 6 integrada à `main` pelo PR #15 (`9ee93e94`);
Sprint 7 em `feature/sprint7-voice-interaction`, sem PR ou merge automático.
O catálogo e os planos novos não autorizam execução física coletiva.

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

### Sprint 6 — catálogo, grupos e cenas offline

- Catálogo canônico com nove registros e vínculo explícito dos seis IDs legados.
- TVs, lousa e telas pertencem a **monitores**. Não existe grupo separado de TVs.
  “TV Samsung”, “televisão Samsung” e “monitor Samsung” identificam o mesmo ID.
- Interface Jarvis e dashboard são papéis de exibição planejados, sem comprovar
  duas telas físicas adicionais. O placeholder anterior foi reaproveitado.
- Grupos `monitores`, `leds` e `audio`, resultados por ID e pendências explícitas.
- Apresentação: LEDs → monitores → áudio. Encerramento: áudio → monitores → LEDs.
  Computador host, sessão e serviços de segurança não são alvos.
- Planos tipados antes de execução, deduplicação, detecção de ciclos/dependências
  inválidas, falha parcial simulada e nenhum retry/rollback automático.
- Novos comandos ficam em preview, mesmo com `--enable-samsung`. As oito frases
  individuais da Samsung S5.11 preservam seu caminho autorizado; o novo alias
  “monitor Samsung” identifica a mesma tela, mas permanece offline nesta rota.
- **597/597 testes locais aprovados**: 494 anteriores + 103 novos. Nenhum acesso
  real ao HA, ação física ou inferência. Fake backend exclusivamente em testes.

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_session_cli
```

Na sessão: `Jarvis, ligue os monitores.`, `Jarvis, ativar modo apresentação.`,
`Desligue os LEDs.`, `Quais são os grupos da sala?`, `Liste os dispositivos da sala`
e `sair`. Para um plano JSON sem TTY/credenciais:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_orchestrator \
  'Jarvis, encerrar apresentação.'
```

Samsung mantém integração de laboratório existente; Hikvision, WS2815/WLED,
áudio e slots não recebem drivers físicos fictícios. Voz/microfone continuam
fora do escopo. As flags de confirmação física permanecem falsas.

[Catálogo](docs/integrations/room-device-catalog.md),
[grupos e comandos](docs/integrations/room-groups.md),
[cenas e dependências](docs/integrations/room-presentation-scenes.md),
[ADR-0004](docs/adr/0004-room-orchestration.md) e
[relatório Sprint 6](docs/reports/sprint-6-acceptance.md).

### Sprint 7 — voz local, planejamento físico offline

Marco original, preservado abaixo. Para a execução atual CUDA/residente/LLM,
consulte a consolidação ao final desta seção e o
[guia GPU/LLM](docs/integrations/voice-gpu-ollama.md).

- CLI `room_voice_cli.py`, estados tipados e janela com múltiplos turnos.
- Enter inicia a escuta; openWakeWord/ONNX CPU é opcional, com fallback manual.
  O modelo público detecta “hey Jarvis”; “Jarvis” isolado em português ainda
  depende de avaliação e possivelmente de modelo acústico próprio.
- Faster-Whisper CPU/int8/`pt`, com tiny/base locais e avaliador de WAVs.
- Kokoro CPU com vozes brasileiras `pm_santa`, `pm_alex` e `pf_dora`, velocidade,
  volume e saída configuráveis. Saída textual se o TTS estiver indisponível.
- Half-duplex: microfone/detector fechados durante TTS, buffers descartados,
  cooldown e rejeição suplementar de possível eco.
- Voz de terceiros e wake word não autenticam ninguém. Toda fala operacional,
  inclusive Samsung, usa **somente preview S6**, sem `OperatorTurn`, autorização
  de terminal ou cliente físico. Respostas do LLM não voltam ao parser.
- Conversa informativa opcional pelo adaptador local existente, sem ferramentas,
  com memória volátil limitada. Configuração própria, Ollama em localhost.
- **714/714 testes offline**: 597 anteriores + 117 novos. Hardware, rede,
  subprocessos e modelos reais bloqueados na suíte inteira.
- Diagnóstico local: WSLg presente, mas dependências de voz indisponíveis.
  Microfone/alto-falantes, acurácia tiny/base e naturalidade TTS ainda não
  homologados. Não houve captura, síntese, inferência ou ação física real.

Diagnóstico sem captura nem mudanças no sistema:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli --diagnose
```

Após instalar dependências e preparar modelos explicitamente:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-tiny" \
  --tts-model-dir "$HOME/.local/share/jarvis-room/models/kokoro" \
  --voice pm_santa --speed 1.0 --volume 0.7
```

Pressione Enter e aguarde `Microfone pronto. Pode falar.`. Fale o pedido,
faça uma pausa e comece cada novo pedido com Jarvis, inclusive na janela ativa
(regra atual S9.1).
`sair`, EOF ou Ctrl+C encerram. `--wake-model-dir` habilita o detector
experimental; `--llm` habilita somente perguntas informativas pelo Ollama local.

Regressão completa da Sala Temática, sem dependências de áudio:

```bash
python3.11 projects/jarvis-room/scripts/run_offline_tests.py
git diff --check
```

[Instalação, diagnóstico e homologação](docs/integrations/voice-interaction.md),
[ADR-0005](docs/adr/0005-local-voice-session.md) e
[relatório Sprint 7](docs/reports/sprint-7-acceptance.md).

### Sprint 7.1 — variantes naturais em português brasileiro

O parser existente agora aceita explicitamente `liga`/`ligue` como `turn_on`
e `desliga`/`desligue` como `turn_off`, mantendo vocativo opcional e a
normalização existente. Assim, `Jarvis, liga os monitores` produz
`group_control / turn_on / monitores`, em vez de `unsupported_command`.
Os mesmos verbos funcionam com os grupos e aliases individuais cadastrados.

Os alvos continuam exigindo correspondência completa. Negação, comandos
compostos, alvos desconhecidos e frases incompletas permanecem bloqueados.
Todos os comandos por voz continuam em **planejamento offline**, inclusive
Samsung; suas autorizações de terminal não foram ampliadas.

**734/734 testes offline aprovados: baseline 714 + 20 novos**, com Ruff e
`git diff --check` aprovados. Nenhuma mudança em CUDA, modelo Whisper ou TTS,
nenhum acionamento físico e nenhuma homologação acústica adicional nesta tarefa.
O teste real de transcrição relatado pelo operador motivou a correção; não
foi repetido durante a regressão automatizada.

Detalhes e limitações no [relatório da Sprint 7, seção S7.1](docs/reports/sprint-7-acceptance.md).

### Consolidação Sprint 7 — STT residente e conversa local

- STT com diretório local, CPU/int8 ou CUDA/float16 explícito e validação real
  de compatibilidade. Modelo carregado uma vez por sessão, separado do microfone.
- Captura e reprodução PortAudio em processos próprios; STT/TTS residentes
  por pipes privados limitados, com timeout, cancelamento e encerramento.
- Parser e os 20 testes S7.1 preservados. Voz mantém todos os planos em
  `offline_preview`; não cria `OperatorTurn` ou autorização Samsung.
- Ollama selecionável por nome instalado; modelo preferido da sessão:
  `qwen3.5:4b`, instalado após autorização explícita do operador.
  Perguntas e acompanhamentos naturais com histórico volátil limitado, sem
  ferramentas físicas nem reinterpretação da resposta como comando.
- Kokoro brasileiro CPU residente opcional, voz masculina candidata `pm_santa`;
  faltam Kokoro/Torch e pesos/vozes locais para síntese real. Fallback textual.
- Wake word mantém Enter como fallback; faltam pacote/ONNX e avaliação de
  “Jarvis” isolado. Modelo público “hey Jarvis” não comprova esse vocativo.
- **830/830 testes offline: 734 preservados + 96 novos**. Ruff, whitespace e
  CI aprovados. Mais 11 testes upstream de fala aprovados separadamente.
- RTX 4070: carga isolada do Turbo comprovada em CUDA/FP16 (1,58 s de modelo,
  2,13 s incluindo início do worker). Não representa latência de conversa.
  Não houve nova captura, transcrição, geração LLM, síntese ou reprodução real.

Para a homologação posterior de STT e LLM, ainda com saída textual:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16 \
  --llm --llm-model qwen3.5:4b --tts-backend none --metrics
```

Pressione Enter e aguarde a abertura efetiva do microfone. A janela permite
vários turnos (até 300 s, 30 s de inatividade e 20 tentativas de captura),
reutilizando STT entre ativações. `Jarvis, limpar contexto` descarta a conversa por voz;
Ctrl+C encerra. Controle físico permanece desabilitado.

[Diagnósticos, instalação e comandos atuais](docs/integrations/voice-gpu-ollama.md),
[arquitetura e fluxogramas](docs/adr/0006-resident-voice-workers.md) e
[relatório consolidado para revisão](docs/reports/sprint-7-consolidation.md).
Homologação de LLM real e qualidade acústica permanecem pendentes.

A seleção posterior do Qwen 3.5 4B mantém as fronteiras da consolidação.
Regressão após essa troca: **831/831 testes offline**. O modelo menor foi
preservado e pode ser escolhido explicitamente por `--llm-model`; não há
fallback automático nem download durante a sessão.

### Sprint 8 — frontend dual-monitor independente

Implementação local em [`frontend/`](frontend/README.md), preservando o frontend
original OpenJarvis. Monitor 1: sala virtual da referência aprovada e holograma
dourado procedural com seis estados oficiais. Monitor 2: nove registros do catálogo,
serviços desconhecidos, cenas em prévia e dados DEMO identificados.

```bash
cd projects/jarvis-room/frontend
npm ci
npm run dev
```

Abra `http://127.0.0.1:5174/monitor/1` e `http://127.0.0.1:5174/monitor/2` em janelas
separadas. Sem acesso ao Home Assistant, microfone, TTS real ou controle físico.
Build, testes e pendências estão no [relatório da Sprint 8](docs/reports/sprint-8-acceptance.md).

### Sprint 9 — sessão de voz conectada às telas

- Estados reais S7 publicados por socket Unix privado e distribuídos por SSE
  em loopback. DEMO e LIVE separados, heartbeat, reconexão e limpeza de dados.
- Cena e fundo S8 preservados. Energia do holograma vem do PCM na reprodução
  real do TTS, com suavização, relógio DAC e retorno a zero em falha/cancelamento.
- Ollama/Qwen 3.5 4B reutilizados, sem ferramentas físicas. Conversa no Monitor 2
  somente com opt-in da CLI e opção de exibição; sem entrada de comandos no navegador.
- GET HA opcional e restrito ao auxiliar virtual; tokens apenas no backend,
  sem presumir entidades Samsung antigas. Catálogo/cenas canônicos preservados.
- Kokoro/Torch e assets brasileiros ausentes no ambiente auditado: infraestrutura
  pronta e testada com fakes, síntese/audição reais ainda pendentes.
- **885 testes Python**, **50 TypeScript** e **6 E2E** aprovados; build, Ruff e
  whitespace aprovados. Não há homologação real de voz/GPU/HA nesta entrega.

Backend, da raiz do repositório:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.presentation_server
```

Frontend: `cd projects/jarvis-room/frontend` e `npm run dev`. Abra as duas rotas
5174 acima e selecione LIVE em cada janela. Em outro terminal, na homologação
autorizada, execute a sessão S7 com `--presentation`; um único processo de voz
alimenta os dois monitores. Sem sessão, os serviços de voz ficam indisponíveis.

[Comandos completos e diagnóstico](docs/integrations/voice-frontend-integration.md),
[contrato v2](docs/integrations/presentation-events.md),
[controles futuros supervisionados](docs/integrations/supervised-physical-automation.md) e
[relatório da Sprint 9](docs/reports/sprint-9-acceptance.md).
Sem comandos de push, PR ou merge pelo agente. O relatório distingue a revisão
publicada externamente dos complementos locais. Controle físico por voz/UI permanece bloqueado.


### Sprint 9.1 — vocativo obrigatório, persona e pm_alex

Cada solicitação de voz exige **Jarvis no início**. Fala sem o nome ou com o
nome no meio é descartada antes do roteador, LLM, TTS e publicação da conversa.
`Jarvis` isolado responde **“Sim, senhor. Em que posso ajudá-lo?”**, sem Ollama,
e volta à espera. Não há dispensa de vocativo nos turnos seguintes.

Padrão da aplicação: **pm_alex**, velocidade **0,92**, volume **0,5**, Kokoro
CPU brasileiro. O texto escrito continua J.A.R.V.I.S.; só a preparação da
fala transforma o nome em Jarvis. pm_santa continua selecionável. Persona
original calma, técnica e educada; sem imitação/clonagem ou confirmação física.

`--continuous-experimental` habilita VAD de energia + o único STT residente,
sem Enter por chamada. É uma alternativa experimental com gaps e consumo a
medir, não detector acústico homologado de Jarvis isolado. Ctrl+C desliga o
microfone e libera recursos. Durante espera passiva, o holograma fica IDLE;
amp real apenas durante reprodução PCM. Não mudou a cena visual ou o SSE.

Kokoro/Torch e assets locais estão agora presentes; o operador relata sucesso
anterior de STT/LLM/TTS/frontend no Lief. A nova voz e a escuta experimental
aguardam homologação específica. Sem inferência, áudio ou equipamentos reais
na regressão: **920 Python**, **52 frontend**, **6 E2E** aprovados.

[Comandos completos no Lief, comparação de vozes e testes de falsos positivos](docs/integrations/jarvis-wake-persona.md).
[Relatório da Sprint 9.1](docs/reports/sprint-9-1-acceptance.md).
Controle físico continua em planejamento offline. Sem push, merge ou PR automático.
