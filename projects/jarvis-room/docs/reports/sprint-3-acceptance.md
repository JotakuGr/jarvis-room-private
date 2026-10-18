# Relatório técnico — Sprint 3

Data: 17/10/2026 (America/Bahia).

Status: implementação e homologação offline aprovadas; prova operacional do
LAB e revisão técnica externa pendentes. Não certifica integração real.

Branch: `feature/sprint3-ha-laboratorio-readonly`.
Repositório: `JotakuGr/jarvis-room-private`.

## Base e ambiente

Árvore limpa antes do início. A branch já existia sem tarefas iniciadas e foi
reutilizada sem sobrescrever histórico. `main` foi atualizada com
`git pull --ff-only origin main`; PR #11 confirmado no merge `e96ef916`.
Baseline local: **197/197 aprovados**.

Ambiente: Ubuntu WSL, Python 3.11.17, Docker Desktop Engine 29.5.3 e
Compose v5.1.4. A coleta inicial mostrou aproximadamente 11 GiB de RAM total,
8,3 GiB disponível e 4 GiB de swap livre. O Docker declarou 12.492.374.016
bytes disponíveis ao daemon. A postergação do LAB não é atribuída a falta
de RAM nessa coleta: é uma pendência de compatibilidade e operação supervisionada.

## Commits e regressão por tarefa

| Tarefa | Entrega | Testes novos | Regressão aprovada | Commit |
| --- | --- | --- | --- | --- |
| 3.1-A | Manifesto estrito e Compose restrito | 8/8 | 205/205 | `bf6e8142` |
| 3.1-B | Cliente exclusivamente GET, desabilitado por padrão | 8/8 | 213/213 | `c711f9ce` |
| 3.2-A | Interpretação sanitizada de estados LAB | 8/8 | 221/221 | `c6530792` |
| 3.2-B | Vínculo do helper virtual | 8/8 | 229/229 | `a0e1c14d` |
| 3.3-A | CLI independente com opt-in e token privado | 8/8 | 237/237 | `362292da` |
| 3.3-B | Prontidão Hikvision sem controle presumido | 8/8 | 245/245 | `de7379d5` |
| 3.4-A | Prontidão elétrica/lógica WLED | 8/8 | 253/253 | `a2063c35` |
| 3.4-B | E2E offline e fronteiras arquiteturais | 8/8 | 261/261 | `65b5a572` |
| 3.5-A | Workflow, README e este relatório | 0 | 261/261 | Commit que contém este documento |

Cada tarefa teve testes específicos e regressão completa antes do commit.
Total local confirmado: **197 anteriores + 64 novos = 261/261**, sem erros.
Não foram necessários testes extras fora dos 64 planejados.

## Arquivos

- `lab/home-assistant/compose.yaml` e `config/ha_lab_manifest.json`.
- `ha_lab_manifest.py`, `ha_lab_readonly_client.py`, `ha_lab_state.py`,
  `ha_lab_bindings.py`, `ha_lab_cli.py` e seus testes.
- `config/ha_lab_entities.json` com helper virtual restrito.
- `config/hikvision_lab_readiness.json`, `hikvision_readiness.py`, teste e checklist.
- `config/wled_lab_readiness.json`, `wled_readiness.py`, teste e pré-requisitos.
- `tests/test_sprint3_e2e.py`, `tests/ha_lab_http_fakes.py` e documentação de fronteiras.
- Validação estrita aninhada compartilhada em `_offline_json.py`.
- README do subprojeto e workflow próprio de unittest, preservando os demais.

As alterações ficam em `projects/jarvis-room/`, exceto o workflow explicitamente
solicitado. Não houve alteração de `room_chat_cli.py` ou registro do cliente
no gateway/LLM.

## Docker e laboratório opcional

`docker compose -f projects/jarvis-room/lab/home-assistant/compose.yaml config`
foi aprovado. A renderização confirma `host_ip: 127.0.0.1`, porta publicada
18123 e destino 8123, sem `privileged` e sem rede host. O teste estático confere
o conteúdo completo do Compose sem dependência YAML adicional.

Home Assistant Container inicializado nesta execução: **não**.
`docker compose ... ps --format json` não apresentou contêineres desse projeto.
URL reservada: `http://127.0.0.1:18123`, sem token.

A [documentação oficial atual do Container](https://www.home-assistant.io/installation/linux#install-home-assistant-container)
orienta Docker Engine e declara Docker Desktop não suportado. Por isso a
inicialização opcional foi adiada por compatibilidade operacional, em vez de
declarar uma instalação não testada como concluída.

Imagem declarada: `ghcr.io/home-assistant/home-assistant:stable`.
Não houve pull. `docker image inspect` informou ausência dessa imagem local;
portanto versão efetiva e digest permanecem **não determinados** e deverão
ser registrados na homologação operacional antes de atualizações.

Publicação externa de porta: restrita a loopback no Compose renderizado.
Não foi feita prova em runtime de bloqueio de acesso externo. Loopback não
isola todos os processos locais e bridge não bloqueia toda saída de rede.

Não houve onboarding, descoberta aceita, importação de backup, adição de
integração real ou criação de volume por esta execução. Antes de futura
instalação: usuário exclusivo do LAB, senha forte, verificação de runtime,
recursos e digest. Encerrar com `down`, nunca `down -v` rotineiramente.
Guardar o volume fora do Git e criar backup privado antes de atualizar.

## Helper, token e provas GET

Helper configurado: `input_boolean.jarvis_lab_light`, associado somente a
`room_main_lights`, `kind=virtual_helper`, `physical=false`, `read_only=true`.
Ele não é a entidade de simulação `light.sala`.

Helper criado na interface e ID efetivo confirmado: **não**, pendente da
instalação supervisionada. A configuração não comprova sua existência nem
ausência de automações; o operador deverá confrontá-la com a instância real.

Tokens reais gerados, lidos ou versionados: **nenhum**.
Os testes usam apenas valores fictícios, identificados como não credenciais.
O cliente envia token somente em `Authorization: Bearer`, sem incluí-lo em
URLs, relatórios ou mensagens de erro. A CLI exige opt-in ambiental e entrada
oculta em terminal ou arquivo externo de propriedade do usuário, 0400/0600.

Provas contra Home Assistant real: **nenhuma**.
Provas com HTTP fake em memória:

- `GET /api/`: 200 simulado e falhas 401/403/404/503, timeout e redirect.
- `GET /api/states/input_boolean.jarvis_lab_light`: 200 simulado, on/off e
  interpretação de respostas inválidas, entidade divergente e dados privados.

Relatórios descartam atributos/contexto e detalhes internos de erros.
Proxy desabilitado, redirects recusados, timeout finito e tamanho JSON limitado.
POST, chamadas de serviço ou atualização de estado pelo J.A.R.V.I.S.: **0**.

Um token HA pode ter permissões amplas fora deste código: ele não é
intrinsecamente read-only. Credenciais do LAB são independentes das futuras
de produção; revogar o token temporário quando não for mais necessário.

## Ausência de controle físico e inferência

- `HALabReadOnlyClient` não oferece POST, `call_service`, `perform_and_verify`,
  `set_state` ou método HTTP genérico.
- `HALabState` mantém origem descritiva e confirmação física não configurável;
  não vira `ToolReceipt` nem `SimulatedActionResult`.
- `RoomControlGateway()` padrão segue recusando comandos.
- A CLI anterior mantém identidade pelo catálogo e bloqueio físico; o LLM não
  foi chamado para comandos físicos.
- Execuções físicas: **0**. Inferências LLM: **0**.
- `ollama ps`: nenhum modelo residente na coleta de homologação.

## Hikvision e WLED

Hikvision: **DS-D5B65RB/D**, `hikvision_board`, `planned`.
Disponibilidade, etiqueta/revisão, firmware, host e cabos desconhecidos.
Protocolo RS-232, comandos, retorno de estado, acesso à rede e permissão
institucional não comprovados. Exibição HDMI/Touch-USB é independente de
controle do equipamento. Nenhuma interface física foi acionada.
O segundo display físico permanece não identificado; os dois monitores
lógicos do J.A.R.V.I.S. não implicam duas TVs.

WLED: WS2815 12 V, 100 m, 60 LEDs/m e 6.000 LEDs declarados, ESP32 e WLED,
sem controlador conectado. Permanecem null: potência, corrente, lote, trechos,
localização de fontes, cabos, proteções, fusíveis, injeções, quedas de tensão,
referência de sinal, número de ESP32, taxa de atualização e quantidade de fontes.
Zonas são referências lógicas, sem limites ou número final definidos.
Nenhuma energização antes de projeto e revisão por profissional habilitado.

## Homologação local e CI

```bash
set -o pipefail
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v \
  2>&1 | tee /tmp/jarvis-sprint3-tests.log
git diff --check
git status -sb
ollama ps
```

O log é local e não versionado. Suíte local: **261/261 aprovada**.
`git diff --check`: sem erros. Os 197 testes da Sprint 2 continuam passando.

Não havia workflow equivalente para o subprojeto. Foi criado
`.github/workflows/jarvis-room-unittest.yml`: Python 3.11, somente unittest
offline, `permissions: contents: read`, sem Docker, credenciais operacionais
ou acesso a equipamentos. Os workflows existentes foram preservados.

A execução remota é distinta da regressão local; sua evidência fica no
[histórico do workflow desta branch](https://github.com/JotakuGr/jarvis-room-private/actions/workflows/jarvis-room-unittest.yml?query=branch%3Afeature%2Fsprint3-ha-laboratorio-readonly).
Não se presume êxito de CI apenas porque os testes locais passaram, nem
aprovação de checks de um PR que ainda não foi aberto.

## Publicação e revisão externa

Um commit por tarefa, publicado na branch privada da Sprint 3.
Nenhum envio ao upstream oficial do OpenJarvis, merge automático ou início
da Sprint 4. Apresentar branch, commits e evidências para revisão técnica;
após os achados, abrir PR para `main`, conferir CI e só então fazer merge.

## Pendências, problemas e riscos

- Instalação opcional adiada: validar runtime e executar onboarding do LAB.
- Registrar versão/digest, criar helper e confirmar ID real sem automações.
- Prova GET autenticada, senha e token temporário: não executados nesta rodada.
- Restrição de porta verificada estaticamente, sem certificação de isolamento
  completo da rede ou de privilégios read-only intrínsecos do token.
- Nenhum teste local falhou; a evidência de CI é consultada separadamente.
- Revisão técnica externa, PR/CI e merge antes de iniciar a Sprint 4.

Referências: [arquitetura do LAB](../integrations/ha-lab-architecture.md),
[checklist Hikvision](../integrations/hikvision-lab-checklist.md),
[prontidão WLED](../integrations/wled-zoning-readiness.md) e
[API oficial HA](https://contributors.home-assistant.io/core/internals/rest-api/).
