# Relatório técnico — Sprint 2 — J.A.R.V.I.S.

Data: 17/10/2026 (America/Bahia).

Status: homologação offline e revisão técnica externa do código aprovadas;
PR, CI e merge pendentes.

Branch: `feature/sprint2-home-assistant-offline`.
Repositório: `JotakuGr/jarvis-room-private`.

## Preparação e escopo

A árvore estava limpa. A branch da Sprint 2 já existia, ainda sem implementação;
foi reutilizada sem sobrescrever histórico. A `main` foi atualizada com
`git pull --ff-only origin main`, e a branch foi alinhada por fast-forward.
O merge da Sprint 1 está confirmado no histórico da `main` atualizada:
`b01401b1`, PR #10, `feature/jarvis-persona` → `main`.

Baseline confirmado: **139/139 testes aprovados**.
Todas as novas alterações ficam em `projects/jarvis-room/`.
Nenhuma instância real de Home Assistant, equipamento ou provedor de IA
foi utilizado nos testes. A consulta das fontes públicas e as operações Git
são atividades de documentação/publicação, externas às simulações.

## Tarefas, testes e commits

| Tarefa | Entrega | Novos testes | Regressão aprovada | Commit |
| --- | --- | --- | --- | --- |
| 2.1-A | Catálogo de seis dispositivos planejados e modelo Hikvision exato | 8/8 | 147/147 | `badcc7c7` |
| 2.1-B | Política determinística que nega todas as solicitações | 8/8 | 155/155 | `b72ad4e2` |
| 2.2-A | Contrato de transporte, implementação desabilitada e fake só em testes | 8/8 | 163/163 | `0a7a5a7d` |
| 2.2-B | Comparação de estados simulados sem confirmação física | 8/8 | 171/171 | `5b8460ec` |
| 2.3-A | Plano da lousa Hikvision e documentação de duas trilhas | 8/8 | 179/179 | `fd2d9564` |
| 2.3-B | Premissas WLED/WS2815 e pré-requisitos elétricos | 8/8 | 187/187 | `005b9ae3` |
| 2.4-A | E2E offline e inspeção sem tráfego externo | 8/8 | 195/195 | `d3ccda3b` |
| 2.5-A | Este relatório e atualização do README | 0 | 195/195 | Commit que contém este documento: `docs: registrar homologacao da sprint 2` |

Cada tarefa de implementação teve testes específicos, regressão completa e
`git diff --check` aprovados antes de seu commit.
Entrega original: **195/195 testes aprovados**, sem falhas ou erros,
com 56 novos testes e baseline de 139.

Após a correção do vínculo sintético:

- Baseline da Sprint 1: 139 testes
- Testes da Sprint 2: 58
- Total: **197/197 aprovados**

### Correção após revisão — vínculo da simulação

Após a homologação original de 195 testes, foi acrescentada a associação
exclusivamente sintética `room_main_lights → light.sala`. O verificador exige
esse vínculo antes de ler o transporte. Lousa, fitas LED, sensor de presença e
IDs desconhecidos não podem reutilizar o estado simulado da iluminação.

Foram adicionados dois testes: recusa dos dispositivos sem vínculo, sem
chamadas ao fake, e leitura única do vínculo válido. A regressão desta correção
confirmou **197/197 testes aprovados**, com **10/10** no verificador de estados.
O baseline continua em 139; o acréscimo acumulado passa de 56 para 58 testes.
Nenhuma integração física ou inferência real foi executada. As contagens de
195 e os commits da tabela acima registram a entrega original.

A correção do vínculo sintético foi publicada na branch
`feature/sprint2-home-assistant-offline`.

A revisão técnica externa do código foi aprovada.
Permanecem pendentes a validação de CI e o merge na `main`.

## Homologação final offline

Comandos executados a partir da raiz `openjarvis`:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v \
  2>&1 | tee /tmp/jarvis-sprint2-tests.log
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.home_assistant_catalog
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_chat_cli 'Ligue a luz da sala'
```

O pipeline de testes usa `pipefail`, para que falhas não sejam escondidas por
`tee`. O log local não é adicionado ao Git.

- Catálogo: `mode=offline`, seis itens `planned`, todos sem entidade real;
  `home_assistant_connected=false` e `physical_control_enabled=false`.
- CLI: `canal=control; acao_verificada=false`, seguida de
  “Não executei esse comando. O controle deste dispositivo ainda não está disponível.”
- Identidade: resposta J.A.R.V.I.S. do catálogo preservada nos E2E.
- Modo experimental: comando físico recusado antes de chamar o adaptador de IA.
- Inferências reais executadas: **0**.
- Execuções físicas: **0**.
- `ollama ps`: nenhuma linha de modelo residente na verificação final.
- Credenciais operacionais registradas: **nenhuma**.

## Hikvision

Modelo exato: **Hikvision DS-D5B65RB/D**, item `hikvision_board`.
Interfaces documentadas: RS-232, RJ45, HDMI IN/OUT e Touch-USB.
A ficha oficial do modelo foi consultada; a página de produto não retornou
conteúdo utilizável pela ferramenta de pesquisa nesta coleta.

Trilha A: exibir a interface em HDMI e avaliar Touch-USB com computador host.
Trilha B: futura automação de funções mediante protocolo específico,
autorização institucional, meio apropriado e retorno confiável de estado.
A trilha A não comprova a trilha B.

Protocolo de controle verificado: **não**.
Controle remoto ou serial realizado: **não**.
Todos os comandos previstos permanecem negados, inclusive após tentativas
de alteração manual das flags no JSON, que tornam o plano inválido.

## Home Assistant, simulação e política

Instância real contatada: **não**. Entidades reais verificadas: **não**.
`light.sala` pertence somente à allowlist sintética dos testes.
`DisabledHATransport` não cria sockets e recusa leitura e ação.
`FakeHATransport` existe somente em `tests/ha_fakes.py`, registra chamadas
em memória e não altera dispositivos nem a tabela de estados ao pedir ações.

`actor_id` é metadado não autenticado. Nenhuma role ou permissão operacional
fictícia foi criada. As decisões seguem negativas para todos os seis itens.

`simulated_match` significa consistência entre dois valores inventados no teste.
Todos os resultados mantêm `physical_action_verified=false`, sem parâmetro para
alterá-lo no construtor. Não há conversão para `ToolReceipt` de sucesso.
Um resultado simulado apresentado indevidamente como recibo foi rejeitado
pelo gateway em teste; o gateway padrão do runtime continua sem backend.
Isso não certifica autenticidade de futuras ferramentas externas.

## WLED e WS2815

Premissas: WS2815, 12 V nominais, 100 m, 60 LEDs/m, ESP32 e WLED.
Os 6.000 LEDs são contagem declarativa, sem instalação confirmada.
Potência total, quantidade de fontes/controladores, proteção, cabos e injeções
não foram dimensionados. As medições e a validação por profissional habilitado
continuam pendentes. Não se presume que um único ESP32 seja suficiente.
Os comandos `on`, `off`, `color`, `brightness` e `effect` são negados.

## Problemas encontrados e limites

- Nenhum erro nos testes finais ou nos checks de whitespace.
- A branch de preparação já existia; reutilizada limpa, sem commit de segurança
  desnecessário e sem perda de alterações.
- A ficha oficial PDF substituiu a página indisponível como fonte das interfaces.
- A primeira consulta final `ollama ps` não foi executada porque a revisão
  automática de permissão expirou. A repetição autorizada teve sucesso e
  confirmou ausência de modelos residentes.
- Os testes novos não fazem I/O de rede; patches de sockets/processos e inspeção
  de imports exercitam a ausência de transporte externo nos novos módulos.
- Os fakes não certificam integração real, segurança elétrica, estado físico
  ou qualidade factual de um modelo de IA.

## Publicação e revisão

As implementações das oito tarefas e a correção do vínculo sintético estão
publicadas em `origin/feature/sprint2-home-assistant-offline`.
A revisão técnica externa do código foi aprovada, conforme confirmação do responsável.
Nenhuma alteração foi enviada ao `upstream` oficial do OpenJarvis.

Não fazer merge automaticamente. Permanecem pendentes a abertura de PR para
`main`, a validação de CI e o merge.
Somente depois dessa etapa deve começar a Sprint 3.

## Decisões pendentes para a Sprint 3

- Disponibilidade, etiqueta, revisão e firmware da lousa.
- Manual RS-232 específico, funções suportadas e retorno de estado.
- Computador host, conexões HDMI/Touch-USB e autorização da universidade.
- Instância Home Assistant de testes e associação de entidades reais.
- Identidade autenticada, permissões, execução confiável e auditoria operacional.
- Medições elétricas WS2815, topologia de zonas e capacidade dos controladores.
- PR, validação de CI e merge da Sprint 2 antes de nova integração.

## Fontes

- [REST API oficial do Home Assistant](https://contributors.home-assistant.io/core/internals/rest-api/).
- [Ficha oficial da Hikvision DS-D5B65RB/D](https://assets.hikvision.com/prd/normal/all/doc/m000065236/DS-D5B65RB_D_Datasheet_20251128.pdf), tabela de interfaces, página 3.
- [WLED: preparação](https://kno.wled.ge/basics/getting-started/) e [cabeamento](https://kno.wled.ge/advanced/wiring/).

As fontes foram consultadas para documentação, sem conexão a instalações reais.
