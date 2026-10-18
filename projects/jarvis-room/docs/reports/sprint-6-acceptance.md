# Relatório técnico — Sprint 6 — orquestração da Sala Temática

Data: 18/10/2026, America/Bahia.
Status: implementação offline publicada e aprovada localmente e em CI.
Revisão externa e homologação física coletiva permanecem pendentes.

## Base e ambiente

- Repositório: `JotakuGr/jarvis-room-private`.
- Branch: `feature/sprint6-room-orchestration`, já existente e limpa no início.
- Base solicitada: `f7bfbe190a5e3ad8957266553fad3c9f7caf63ff` (S5.11).
- HEAD inicial/main: `421565ed6da303c875a15a896b4d31477843a8d2`.
- Base solicitada é ancestral de HEAD; a comparação das árvores não apresenta
  diferença. Não houve rebase, sobrescrita ou mudança de main.
- [PR #14 da Sprint 5](https://github.com/JotakuGr/jarvis-room-private/pull/14):
  GitHub API confirmou `merged=true` e merge SHA `421565ed...`.
- `git ls-remote origin`: main e feature estavam nesse mesmo SHA antes do push.
- A instrução inicial de documentar Sprint 5 como pendente foi superada por essa
  evidência: a Sprint 5 já está integrada. A Sprint 6 não teve PR/merge automático.
- Ambiente: Ubuntu WSL, Python **3.11.17**. Sem depender de HA, Docker ou Ollama.
- Baseline real, antes das alterações: **494/494 aprovados**.

Inspecionados sessão contínua; intenção/adaptador/política/controlador Samsung;
roteador, dispatcher, safe entrypoint, inventário de capacidades, política de
automação e catálogo HA. Lidos os quatro JSONs solicitados. Seus testes e
contratos anteriores foram preservados.

## Tarefas e commits

| ID | Entrega e arquivos principais | Testes novos / acumulado | Resultado | Commit | Pendência |
| --- | --- | --- | --- | --- | --- |
| S6.1 | Revisão, baseline e `docs/adr/0004-room-orchestration.md` | 0 / 494 | Aprovado | `f09023bf` | Revisão da ADR |
| S6.2 | `config/room_devices.json`, `room_device_registry.py`, `room_text.py`, fixture e testes | 16 / 510 | Aprovado | `98e6b444` | Identidade física dos slots |
| S6.3 | `room_groups.py`, `test_room_groups.py` | 10 / 520 | Aprovado | `bc9cebe8` | Homologar grupos antes de execução real |
| S6.4 | `room_intent.py`, `test_room_intent.py` | 15 / 535 | Aprovado | `a514f776` | Aliases físicos novos continuam offline |
| S6.5 | `config/room_scenes.json`, `room_scenes.py`, testes | 14 / 549 | Aprovado | `3160d80e` | Sequência física precisa de revisão específica |
| S6.6 | `room_orchestrator.py`, `room_simulation_fakes.py`, testes | 16 / 565 | Aprovado | `01703185` | Drivers físicos futuros não implementados |
| S6.7 | `room_responses.py`, `room_session_cli.py`, testes de sessão | 15 / 580 | Aprovado | `0cd8c10d` | Prova física não executada |
| S6.8 | Isolamento do escopo Samsung, declaração futura por alvo e ação; validações negativas | Compartilha S6.6/S6.7/S6.9 | Aprovado | `01703185`, `0cd8c10d`, `a916339c` | Autorização coletiva real adiada |
| S6.9 | `test_sprint6_e2e.py`, reforço das validações e erros sanitizados; revisão da categoria legada | 17 / 597 | Aprovado | `a916339c`, `11fb11c2` | Revisão externa |
| S6.10 | Três guias, relatório, README, ADR e filtro do workflow | 0 / 597 | Local e CI aprovados | `1b559023` + complemento documental de evidência | Decisão humana sobre PR |

Total real: **494 anteriores + 103 novos = 597/597**. Nenhuma alteração nos
arquivos de testes anteriores, nenhum teste removido e nenhum skip registrado.

## Arquivos e arquitetura final

Sete módulos novos de produção:

- `src/jarvis_room/room_text.py`: normalização restrita.
- `src/jarvis_room/room_device_registry.py`: catálogo e compatibilidade explícita.
- `src/jarvis_room/room_groups.py`: grupos canônicos e todos os membros.
- `src/jarvis_room/room_intent.py`: intenção individual, grupo ou cena.
- `src/jarvis_room/room_scenes.py`: plano tipado e dependências.
- `src/jarvis_room/room_orchestrator.py`: preview e contrato de simulação.
- `src/jarvis_room/room_responses.py`: apresentação de planos e inventário.

`room_session_cli.py` recebeu somente um ramo offline depois do caminho Samsung
original e um aviso de modo. Os módulos de autorização, controle, REST,
credenciais, auditoria e observação Samsung **não foram modificados**. Gateway,
read-only, roteador, dispatcher e safe entrypoint também não foram ampliados.

Criados dois JSONs novos, sete módulos de testes e duas fixtures de teste.
Testes novos: `test_room_device_registry.py`, `test_room_groups.py`,
`test_room_intent.py`, `test_room_scenes.py`, `test_room_orchestrator.py`,
`test_room_orchestration_session.py` e `test_sprint6_e2e.py`. Fixtures:
`room_test_support.py` e `room_simulation_fakes.py`, exclusivamente em `tests/`.
Documentação nova: ADR-0004, três guias e este relatório. README atualizado;
workflow recebeu somente a branch Sprint 6 no filtro de push. Demais permissões,
gatilhos, versões e comando de testes do workflow foram preservados.

Fluxo: entrada direta do operador → intenção determinística → catálogo/grupo/cena
→ plano validado → preview sem backend ou fake injetado nos testes → resultados
por alvo e eventos mínimos → resposta sem confirmação física.

O orquestrador reconstitui o plano antes de chamar qualquer backend. O contrato
novo aceita somente backend identificado como simulação, método `simulate_step`
e observação tipada com estados restritos. Não importa drivers, clientes HTTP,
OpenJarvis ou transportes de execução física. JSON não instancia adaptadores.

## Catálogo e compatibilidade

| ID | Grupo | Situação |
| --- | --- | --- |
| `samsung_lab_tv` | monitores | Samsung LH32BETBLGGXZD; integração de laboratório existente |
| `hikvision_board` | monitores | DS-D5B65RB/D; integração/protocolo pendentes |
| `jarvis_interface_display` | monitores | Papel de interface; equipamento a confirmar |
| `second_display_placeholder` | monitores | Papel de dashboard; placeholder reaproveitado sem comprovação física |
| `led_perimeter` | leds | WS2815 12 V; 100 m × 60 LEDs/m declarados; ESP32/WLED futuros |
| `room_audio` | audio | Modelo e método físico não confirmados |
| `room_main_lights` | Sem grupo canônico | Iluminação planejada preservada |
| `air_conditioner` | Sem grupo canônico | Climatização planejada preservada |
| `presence_sensor` | Sem grupo de atuação | Somente capacidade declarativa de leitura |

TV e monitor são o mesmo domínio lógico. Samsung não foi duplicada por aliases.
Não há grupo físico `televisores`. Os quatro registros de exibição incluem dois
papéis e não comprovam quatro equipamentos físicos distintos/disponíveis.
Confirmar suas identidades antes de integração coletiva. Não foram inventados
IPs, entidades de equipamentos planejados, protocolo serial, WLED ou dados elétricos.

Os inventários anteriores permanecem byte a byte preservados. Os seis IDs de
`home_assistant_devices.json` têm vínculo único e explícito no catálogo novo,
validado por `legacy_catalog_links()`. Categoria e fabricante/modelo conhecidos são conferidos.
`capabilities.json`, `samsung_lab.json` e `wled_zones.json` continuam com seus
contratos originais. `execution_available=false` diz respeito ao orquestrador,
inclusive para Samsung; não remove sua integração manual individual S5.11.

## Intenções e cenas disponíveis

Exemplos: “Ligue o monitor Samsung”, “Ligue o monitor Jarvis”, “Desligue o monitor
do dashboard”, “Ligue os LEDs do perímetro”, “Ligue os monitores”, “Ligue todas
as TVs”, “Desligue as luzes LED”, “Ligue o sistema de áudio”, “Desligue os
alto-falantes”, “Ative o modo apresentação”, “Encerrar apresentação”.

Aliases de grupo não criam dispositivos. “Todas as TVs” resolve para monitores;
“alto-falantes” resolve para audio, atualmente com um cadastro do sistema.
Normalização aprovada de acentos, caixa, prefixo Jarvis e pontuação simples;
sem correspondência parcial. Negações, condições, múltiplas ações livres,
agendamento, injeção, URLs/serviços e alvos desconhecidos são bloqueados.

Apresentação: LEDs → quatro registros de monitores → áudio. Encerramento:
áudio → monitores → LEDs. Host, sessão e serviços não são alvos. Não há comando
inventado de preparação do áudio, somente requisito futuro e capacidade de ligar.

Cada cena expande alvos, deduplica IDs, valida referências e ordena dependências.
Ciclos antes/depois da expansão são recusados. Falha de um alvo bloqueia seus
dependentes e preserva resultados dos independentes; todos aparecem no relatório.
`simulated_partial` não declara cena inteira bem-sucedida. Não há retry/rollback.

## Segurança e auditoria

- Novos comandos só têm preview na sessão e CLI de planos; não há flag coletiva
  de execução física, token, URL ou backend selecionável por argumento.
- As oito frases Samsung anteriores seguem sua rota S5.11, com terminal,
  opt-in, autorização única, token/log externos, allowlists, um POST e observação.
- Novo alias “monitor Samsung” é reconhecido como o mesmo ID, mas fica offline.
  Não há reescrita de entrada para fabricar autorização Samsung.
- `FutureAuthorizationScope` enumera alvos/ações, sempre não autorizado. Não é
  credencial aceita pelo controlador; permissão Samsung não autoriza outros alvos.
- LLM só recebe perguntas informativas permitidas. Sua saída nunca é analisada
  novamente como comando, plano ou autorização; nenhum atuador é ferramenta do modelo.
- Backend fake existe só em testes. Ausência de backend significa preview;
  respostas simuladas não são `ToolReceipt` e não confirmam estado físico.
- Resultados/eventos novos são mínimos, sanitizados e em memória, sem diálogos,
  tokens ou detalhes internos de erros. Auditoria física persistente anterior
  continua no mesmo controlador, sem duplicação de registros.
- `action_verified=false` e `physical_action_verified=false` permanecem invariantes.
- Preservados encerramento/revogação da sessão, read-only e gateway restritivos.

As barreiras são da aplicação, não isolamento contra Python malicioso no mesmo
processo. Metadados de backend não comprovam autenticidade. Autorizações reais
por grupo/cena exigirão escopo de cada alvo, políticas, validade, revogação,
consumo e comprovação de integração em sprint posterior.

## Validação e comandos reproduzíveis

Regressão padrão: **597/597**, zero falhas, erros ou skips. Mesma suíte:
**597/597** com `socket.connect`, `connect_ex` e `create_connection` proibidos
após descoberta. Fixtures novas proíbem criar sockets e usam apenas arquivos
temporários, REST falso, backend em memória e relógio virtual.

Cobertura inclui catálogo inválido/duplicado, aliases conflitantes, sensores,
novos monitores planejados, todos os atuadores on/off simulados, todos os grupos,
cenas, ordem/ciclos, falhas parciais, backend indisponível, estado não confirmado,
ausência de retry/rollback, adulteração de plano/observação, isolamento do LLM,
escopo Samsung, CLI, cancelamento e saída sem processar turnos posteriores.

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v
git diff --check
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_device_registry
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_orchestrator \
  'Jarvis, ativar modo apresentação.'
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_session_cli
```

Exercitado também um terminal informativo real: grupo monitores, modo apresentação,
LEDs, consulta ao inventário, identidade e sair. Sem `--enable-samsung`, `--llm`
ou credenciais. CLI de planos gerou seis alvos e `offline_preview/plan_ready`,
com flag física falsa. Não foi declarada homologação física por esses testes.

Logs locais não versionados: `/tmp/jarvis-s6-baseline.log`,
`/tmp/jarvis-s6-tests.log`, `/tmp/jarvis-s6-network-blocked.log` e logs específicos.
Prévia local: `/tmp/jarvis-s6-presentation.json`. Sem volumes, tokens ou auditorias
privadas staged. `git diff --check` aprovado.

Chamadas reais HA GET/POST: **0**. Ações físicas: **0**. Inferências LLM: **0**.
Credenciais reais HA lidas/criadas: **0**. PR/merge da Sprint 6: **não**.

Na revisão final, foi reforçado o vínculo da categoria dos IDs legados:
reclassificar `presence_sensor` como áudio com capacidades de ligar/desligar
é rejeitado, assim como alterar sua lista de capacidades sem reclassificação.
Apenas a tradução declarada `interactive_display → display` é permitida.
O cenário adicional foi incluído no teste existente, sem alterar a contagem.
Regressão padrão e com conexões proibidas foram repetidas: **597/597**.

## Documentação e CI

- [Catálogo e compatibilidade](../integrations/room-device-catalog.md).
- [Grupos, comandos e fronteira S5.11](../integrations/room-groups.md).
- [Cenas, falha parcial e autorização futura](../integrations/room-presentation-scenes.md).
- [ADR-0004](../adr/0004-room-orchestration.md) e README do subprojeto.
- Diagramas Mermaid: arquitetura, fluxo individual/coletivo e falha parcial.
- Workflow: `JARVIS Room offline unittest`, Python 3.11, `contents: read`;
  execução somente de unittest offline, sem Docker, segredos ou dispositivos.
- Push da implementação e correção concluído na feature; árvore limpa e
  sincronizada em `11fb11c2fb3e54124b5fa1a6e0cdd450aa291f6a`.
- [Workflow 39178156636](https://github.com/JotakuGr/jarvis-room-private/actions/runs/39178156636),
  conferido pela API do GitHub para esse SHA: **completed/success**.
- Job `unittest-offline`, ID `117825037853`: **completed/success**.
- Este complemento registra essa evidência já verificada. Seu SHA documental
  final também terá push, CI e estado Git conferidos na entrega.

Commits da Sprint 6, sem reescrever histórico compartilhado:

1. `f09023bf` — S6.1, base e decisão arquitetural.
2. `98e6b444` — S6.2, catálogo e compatibilidade.
3. `bc9cebe8` — S6.3, grupos lógicos.
4. `a514f776` — S6.4, intenções da sala.
5. `3160d80e` — S6.5, cenas e planos.
6. `01703185` — S6.6, orquestrador e simulação.
7. `0cd8c10d` — S6.7/S6.8, sessão e isolamento de autorização.
8. `a916339c` — S6.9, E2E e validações.
9. `1b559023` — S6.10, documentação, diagramas e filtro de CI.
10. `11fb11c2` — revisão final da categoria legada e cenário negativo.

O complemento documental de evidência segue esses commits no histórico da
branch; seu SHA e a execução final de CI são informados na entrega.

## Pendências e prontidão

Implementação offline pronta para revisão técnica externa, com publicação e CI
aprovados. A aceitação para hardware coletivo permanece explicitamente adiada:

- Atribuir equipamentos reais aos papéis Jarvis/dashboard sem duplicar Samsung
  ou Hikvision; não presumir equipamento extra pelo número de funções visuais.
- Verificar disponibilidade, firmware, protocolo/retorno de estado e permissão
  institucional da Hikvision; nenhuma serial/rede foi implementada.
- Dimensionar WS2815, fontes, circuitos, cabos, fusíveis, injeção, quedas e sinal,
  com profissional habilitado. Não presumir um ESP32 suficiente para 100 m.
- Identificar áudio, método de acionamento, preparo e estados verificáveis.
- Homologar novas frases/aliases, grupos, cenas e autorização específica por alvo.
- Revisão técnica externa; decisão humana para PR e posterior CI/merge.
- Voz e microfone continuam fora do escopo e não herdam autorização textual.

Não há mudança pendente de hardware exigida para validar a implementação offline.
Não se afirma sala automatizada, cena física funcional ou confirmação independente.
