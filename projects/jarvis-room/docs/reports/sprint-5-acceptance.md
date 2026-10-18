# Relatório técnico — Sprint 5: Samsung por texto

Data: 18/10/2026 (America/Bahia).
Status: S5.1–S5.10 validadas offline e em CI; extensão S5.11 validada localmente,
CI da extensão em verificação. Homologação física das novas interfaces e revisão
técnica externa pendentes. Não é reconhecimento de voz. Nenhum PR/merge automático.

As seções S5.1–S5.10 abaixo preservam a entrega original de 441 testes. A extensão
S5.11, suas alterações de autorização e a regressão de 494 testes estão registradas
no adendo final deste documento.

## Base, ambiente e revisão S5.1

Repositório: `JotakuGr/jarvis-room-private`.
Branch: `feature/sprint5-samsung-natural-commands`.
Base remota confirmada por fetch: `b9627949`, merge da Sprint 4 pelo PR #13.
A branch já existia limpa nessa base e foi preservada. `main` não foi modificada
e não houve reescrita de histórico. Python 3.11.17, Ubuntu WSL.

Baseline real: **356/356**. Revisados todos os módulos solicitados de conversação,
roteamento, controle Samsung, loaders, auditoria, observação, configuração e os
testes de segurança/E2E existentes. Decisão: preservar os contratos anteriores
e integrar somente um novo caminho explícito na CLI conversacional.

## Tarefas, arquivos e resultados

S5.6 precedeu S5.4/S5.5 para que as duas interfaces compartilhassem a apresentação.

| ID | Objetivo e arquivos criados/modificados | Testes relacionados | Resultado local | Commit | Pendência |
| --- | --- | --- | --- | --- | --- |
| S5.1 | Revisão/base; `docs/adr/0003-samsung-natural-commands.md` | Baseline Sprints 1–4 | 356/356 | `3d8ebafa` | Revisão externa da decisão |
| S5.2 | `samsung_natural_intent.py`, `test_samsung_natural_intent.py` | 13 novos | 369/369 | `c9d0158a` | Ampliar frases só por revisão |
| S5.3 | `samsung_natural_control.py`, `samsung_natural_fakes.py`, `test_samsung_natural_control.py` | 15 novos | 384/384 | `16af5b01` | Homologação física da interface |
| S5.4 | `samsung_text_cli.py`, `test_samsung_text_cli.py` | 12 novos | 409/409 | `27ad1ab6` | Sessão manual real autorizada |
| S5.5 | `room_chat_cli.py`, `test_room_samsung_optin.py` | 11 novos | 420/420 | `53d8b22a` | Revisão do opt-in explícito |
| S5.6 | `samsung_natural_responses.py`, `test_samsung_natural_responses.py` | 13 novos | 397/397 | `7f0df4fc` | Evidência física futura separada |
| S5.7 | Reforço do adaptador e `test_samsung_natural_security.py` | 9 novos | 429/429 | `f4d66658` | Identidade institucional fora do escopo |
| S5.8 | `test_sprint5_e2e.py` | 12 novos | 441/441 | `239607b7` | Não substitui homologação física |
| S5.9 | Este relatório, guia de integração, README e ADR | Regressão anterior preservada | 441/441 | `e0aeea73` | Revisão técnica final |
| S5.10 | Filtro do workflow, publicação e evidências CI | Suíte offline completa | Local 441/441; CI aprovado | `494875b6` e complemento documental de evidência | Conferir checks do futuro PR |

Total: **356 anteriores + 85 novos = 441 aprovados**. Nenhum teste falhou ou foi
ignorado nas execuções registradas. Os testes anteriores não foram editados.
Além do comando padrão, a suíte inteira passou com `socket.connect`,
`connect_ex` e `create_connection` bloqueados, após a descoberta dos testes.
Fixtures das novas integrações proíbem criação de sockets e usam HTTP/tempo
simulados. Token e JSONL dos testes são temporários e contêm apenas dados fictícios.

## Arquitetura e inventário

O inventário, a entidade e os scripts da Sprint 4 permanecem intactos:

- TV: `media_player.samsung_bet_series_32_lh32betblggxzd`.
- Ligar: `script.jarvis_ligar_samsung`.
- Desligar: `script.jarvis_desligar_samsung`.
- Destino fixo: `http://127.0.0.1:18123`.

Frase do operador → interpretador determinístico → intenção imutável → adaptador
natural → autorização/credenciais/auditoria/controlador da Sprint 4 → REST fake
nos testes → resultado e resposta natural sanitizada. O adaptador não cria novo
transporte, loop de observação ou emissor de eventos.

Foram criados quatro módulos de produção, sete arquivos de testes e um fixture
compartilhado. O único módulo anterior de produção modificado é `room_chat_cli`;
os módulos Samsung da Sprint 4, gateway, cliente read-only, roteador, dispatcher,
safe entrypoint, provedores e configurações não foram alterados.

Guia e três diagramas Mermaid GitHub: [Samsung por linguagem natural](../integrations/samsung-natural-commands.md).
Decisão: [ADR-0003](../adr/0003-samsung-natural-commands.md).

## Frases e interfaces

Oito formas completas: ligue/desligue × TV/televisão × com/sem Samsung,
com prefixo Jarvis opcional, caixa/acentos normalizados e pontuação simples.
Exemplos: “Jarvis, ligue a TV.” e “Jarvis, desligue a televisão Samsung.”
Negação, condição, múltiplas ações, horário futuro, prompt injection, URLs,
serviços/entidades arbitrários e equipamento desconhecido são bloqueados.

CLI independente: preview offline sem token/rede; `--execute` habilita somente
o pedido de autorização manual. A CLI conversacional exige `--samsung-control`,
incompatível com `--llm`, `--experimental-chat` e `--provider` antes de construir
um provedor. Sem a flag, o comportamento de bloqueio anterior é preservado.
Flags não aceitam abreviação; erros automáticos de parser não ecoam valores,
preservando os diagnósticos explícitos já testados das interfaces anteriores.

## Segurança e evidências negativas

- Intenção não é autorização: revalidar frase, ação e entidade antes da política
  existente; objetos/string/dicts não substituem uma intenção válida.
- Opt-in, stdin/stdout TTY, frase exata, validade e consumo único mantidos.
- Loader e auditoria da Sprint 4 recusam token inseguro, symlink/hardlink, arquivo
  no repositório, permissões inválidas e token/log no mesmo caminho.
- Apenas um POST por autorização; nenhuma repetição automática ou fallback.
  Scripts ausentes e erros HTTP preservam os bloqueios.
- Um emissor de auditoria: correlação única, autorização, tentativa, entrega,
  estado e métricas. Nenhum prompt, resposta do modelo ou credencial é registrado.
  Bloqueios anteriores à autorização não abrem JSONL privado; retornam códigos
  sanitizados pela interface. A auditoria persistente começa no controlador.
- Erro ao fechar auditoria depois do resultado preserva o aceite e informa log
  incompleto. Erros internos/credenciais não aparecem em respostas ou relatórios.
- HTTP 200 isolado, estado tardio e timeout não geram falsa conclusão física.
  Entrega incerta fica explícita, sem declarar que nada foi enviado.
- `action_verified=false` e `physical_action_verified=false` em todas as respostas.
- LLM não recebe ferramenta física; seu texto nunca é reencaminhado à execução.
- Gateway original recusa media_player e o cliente read-only não ganhou POST.

As proteções são locais, não RBAC institucional ou defesa contra Python malicioso
do mesmo usuário. Token HA pode ter poderes amplos; scripts podem mudar fora do
Git. O estado HA não é sensor independente nem prova causalidade.

## Execuções desta sprint

- Chamadas HA reais: **0**.
- Ações físicas reais: **0**.
- Tokens reais do HA lidos/criados: **0**.
- Inferências LLM: **0**.
- Modificações em scripts/contêineres/dispositivos: **0**.
- PR aberto ou merge: **não**.

Validações manuais executadas apenas em preview/bloqueio: CLI natural reconhece
“Jarvis, ligue a televisão Samsung”; room CLI padrão continua bloqueando “Ligue
a TV”; identidade cadastrada permanece funcionando. Nenhum flag de execução
real foi usado. Os dois acionamentos humanos anteriores pertencem à Sprint 4.

## Comandos e CI

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v
git diff --check
```

Log local: `/tmp/jarvis-sprint5-tests.log`, não versionado. Workflow existente
mantém Python 3.11 e `permissions: contents: read`; somente o filtro da branch
foi ampliado para incluir Sprint 5, preservando os gatilhos anteriores. Sem Docker,
credenciais ou endpoints reais no job.

Evidência remota verificada pela API do GitHub:

- SHA da implementação: `494875b693091df7f7bca28b2832d65f47cd48a0`.
- [Execução 39161550741](https://github.com/JotakuGr/jarvis-room-private/actions/runs/39161550741).
- Workflow: `JARVIS Room offline unittest`; job `unittest-offline`.
- Resultado: **completed/success**. Regressão local e CI foram verificados separadamente.

Todos os commits foram publicados na feature, sem reescrever histórico. A árvore
estava limpa e sincronizada após o push da implementação. Este complemento
apenas registra a evidência; o CI do SHA documental final também será conferido
e informado na entrega, sem criar PR ou merge.

## Homologação física futura, voz e prontidão de PR

Obter autorização específica para as novas interfaces; revisar scripts reais;
testar primeiro preview e cancelamento; preparar token/auditoria privados e
observador; depois uma ação por confirmação e evidência visual documentada.
Não presumir que a homologação da Sprint 4 valida a Sprint 5. Microfone e TTS
dependem de outra decisão de autorização e prevenção de realimentação de áudio.

Checklist para revisão:

- [x] Base PR #13 e 356 testes confirmados; trabalho exclusivo na feature.
- [x] Correspondência completa, sem LLM/efeitos no reconhecimento.
- [x] Reuso do controlador, política e auditoria; sem POST duplicado.
- [x] Interfaces opt-in incompatíveis com inferência e default bloqueado.
- [x] 441 testes locais, inclusive negativos e E2E com sockets bloqueados.
- [x] Documentação, Mermaid e limitações; nenhuma credencial/log privado staged.
- [x] CI da implementação publicado aprovado, com SHA e execução registrados.
- [x] Git limpo e sincronizado após publicar a implementação; reconferido na entrega.
- [ ] Revisão técnica externa e decisão humana sobre abertura do PR.
- [ ] Homologação física específica das novas interfaces.

A implementação offline está pronta para revisão; o CI da implementação foi aprovado.
Homologação física/produção e abertura de PR permanecem pendentes de decisão
humana. Nenhuma ação física, PR ou merge será executado automaticamente.

## Adendo — S5.11: sessão textual contínua (18/10/2026)

Status: implementação e testes offline aprovados; CI em verificação;
homologação física específica da sessão e revisão externa pendentes.

### Base e escopo

Início na branch limpa e sincronizada `feature/sprint5-samsung-natural-commands`,
SHA `cd9f610781cc89811b07d470e7daca535696616d`. Baseline executado novamente:
**441/441** em Ubuntu WSL, Python 3.11.17. Não houve troca/modificação da main,
PR ou merge, alteração de scripts HA, token real lido ou acesso à instância real.

Inspecionados roteamento, dispatcher, safe entrypoint, room/chat CLIs, provedores,
adaptador natural e módulos de contrato, autorização, REST, credenciais,
auditoria, controle, estado e observação Samsung. A política manual estrita não
foi substituída por entradas simuladas: criou-se uma capacidade própria de sessão.

### Tarefas, arquivos e evidências

| ID | Entrega / arquivos | Evidência de testes | Resultado | Commit | Pendência |
| --- | --- | --- | --- | --- | --- |
| S5.11.1 | `room_session_cli.py`: loop digitado, vários turnos, sair/EOF/Ctrl+C | `test_room_session_cli.py` | Aprovado offline | `977f3ce8` | Homologação supervisionada |
| S5.11.2 | Flag `--enable-samsung`, TTY e arquivos privados obrigatórios no modo executor | Default bloqueado, entrada não TTY, parâmetros inválidos, startup sem HTTP | Aprovado | `977f3ce8` | Validar operação humana no equipamento |
| S5.11.3 | `samsung_session_policy.py`, `samsung_authorization.py`, alteração mínima de `samsung_control.py` | 18 testes da política: vínculo, expiração, replay, origem e revogação | Aprovado | `1ea6e6b1` + reforço em `977f3ce8` | Revisão da fronteira local |
| S5.11.4 | `SamsungSessionControl` em `samsung_natural_control.py`; mesmo controlador REST/auditoria | On/off, um POST por turno, atraso, timeout, entrega incerta | Aprovado simulado | `977f3ce8` | Nenhum teste físico novo |
| S5.11.5 | Catálogo e provedor local opcional; configuração/memória preservadas; saída nunca redistribuída | Injeção na resposta LLM sem chamada ao controlador; comando não chega ao modelo | Aprovado simulado | `977f3ce8` | Sem inferência real nesta implementação |
| S5.11.6 | Token/log externos, permissões, allowlists e flags falsas; erro de log encerra sessão | Falha de token, log antes/depois do POST e fechamento, 401/403, redirect | Aprovado | `977f3ce8` | Identidade institucional fora do escopo |
| S5.11.7 | `test_samsung_session_policy.py`, `test_room_session_cli.py` | 53 novos; regressão padrão e conexões proibidas | 494/494 | `1ea6e6b1`, `977f3ce8` | CI registrado após publicação |
| S5.11.8 | README, ADR-0003, guia de integração e este adendo | Revisão de documentação e `git diff --check` | Aprovado localmente | Commit documental S5.11 no histórico da branch | Revisão técnica e homologação física |

### Arquitetura e mudança de autorização

O interpretador e o adaptador Samsung da Sprint 5 são reutilizados. A execução
continua no `execute_samsung_manual` da Sprint 4, com um único POST aos scripts
fixos e GETs de observação por até 30 s. Nenhuma alteração no cliente REST,
cliente read-only, gateway, scripts, entidade, inventário ou provedor existente.
São três novos módulos de produção, dois módulos anteriores modificados, dois
arquivos de testes e quatro documentos atualizados.

`SamsungTextSession` lê somente o stdin TTY original; cria `OperatorTurn` imutável.
O turno ativo e a intenção determinística vinculam `SessionPermit`, de uso único,
expirando em 60 s e revogado ao terminar o turno/sessão. PID/thread e TTY são
revalidados no consumo; perda/troca de terminal revoga a sessão. O controlador
aceita apenas os tipos exatos de permissão manual ou de sessão. O método antigo
de consumo manual continua estrito e recusando uma permissão de sessão.

As CLIs antigas mantêm opt-in ambiental e confirmação exata por ação. A nova
CLI usa exclusivamente `--enable-samsung` como escolha inicial de autorização,
sem repetir a confirmação; nenhuma mensagem pode ativá-la. Token e JSONL são
validados antes do loop executor e reutilizados até fechar o contexto. Inicializar
e sair não realiza rede. Em falha de auditoria não se aceita outro comando.

IA é opcional com `--llm`. O provedor local é selecionado pela configuração
restritiva existente; a política de memória e `tools=[]` permanecem. Não recebe
sessão, cliente, permissões ou auditoria. Respostas são apenas exibidas como não
verificadas, nunca interpretadas como comando. Perguntas cadastradas continuam
sem inferência. Não há histórico conversacional persistido ou voz implementada.

### Testes e resultados reais

- Baseline S5.1–S5.10: **441/441** novamente aprovado.
- Política de sessão: **18** novos testes.
- CLI, segurança e E2E de sessão: **35** novos testes.
- Regressão completa: **494/494**, zero falhas/erros/skips.
- Regressão com `socket.connect`, `connect_ex` e `create_connection` proibidos:
  **494/494**, após descoberta dos testes.
- Integrações novas proíbem também criar socket, usam REST fake e relógio virtual.
- Identidade, tentativa de ligar bloqueada e `sair` exercitados em um terminal
  informativo real, sem `--enable-samsung`, sem `--llm` e sem credenciais.
- Nenhuma confirmação repetida: teste on/off usa somente três leituras do
  operador (ligar, desligar, sair), ambiente sem opt-in manual e falha se tentar
  chamar `authorize_manual`. Exatamente dois POSTs falsos, um por ação, dois IDs
  correlacionados, sem eventos duplicados.
- Estado tardio `on` após 4 s simulados encerra observação; timeout de 6 s registra
  três consultas e não afirma falha física; entrega incerta faz só um POST falso.
- Ctrl+C durante POST é tratado como entrega incerta, sem retry, e encerra sessão.
- `action_verified=false` nos objetos de resposta Samsung; estado e auditoria
  mantêm `physical_action_verified=false`. Observação visual é evidência separada.

Comando reproduzível:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v
git diff --check
```

Logs locais não versionados: `/tmp/jarvis-s511-baseline.log`,
`/tmp/jarvis-s511-tests.log`, `/tmp/jarvis-s511-network-blocked.log`.
Chamadas HA reais, execuções físicas e inferências LLM nesta extensão: **0**.
Auditorias e tokens reais não foram lidos, criados ou versionados.

### CI e publicação S5.11

Workflow existente já cobre esta branch. Nenhuma alteração de gatilho, permissões
ou segredos foi necessária: Python 3.11, `contents: read`, somente unittest offline.
Commits da implementação: `1ea6e6b1` e `977f3ce8`. Evidência remota será registrada
depois do push, distinguindo o resultado local do GitHub Actions.

### Homologação e riscos pendentes

Comandos reais de inicialização, diferença entre os três modos, diagrama da
sessão e procedimento supervisionado estão no [guia](../integrations/samsung-natural-commands.md#s511--sessão-textual-contínua).

- [x] 441 testes preservados e 53 novos aprovados offline.
- [x] Default desabilitado; opção explícita, TTY e arquivos privados.
- [x] Sem confirmação repetida, replay ou POST automático adicional.
- [x] Sem controle por resposta de LLM, gateway genérico, read-only ou voz.
- [x] Revogação em saída normal, EOF, Ctrl+C, troca/perda de terminal e erro.
- [x] Documentação da mudança de autorização e riscos.
- [ ] CI S5.11 confirmado com SHA e URL.
- [ ] Revisão técnica externa e decisão humana sobre PR.
- [ ] Homologação física específica da sessão textual habilitada.

Após opt-in, cada comando exato tem efeito operacional sem uma nova pergunta.
O operador deve guardar o terminal e não colar instruções de origem externa.
TTY não autentica identidade nem distingue colagem de digitação; código Python
malicioso no mesmo processo está fora desta fronteira. Não há API de ingestão
de arquivos/logs, microfone ou ferramentas físicas. O token HA continua amplo,
e scripts podem mudar fora do Git. Estado HA não prova causalidade ou observação
física independente. Nenhuma ação real foi executada para fechar esse requisito.

A extensão está implementada e validada offline. Não declarar homologação física
nem encerramento definitivo da Sprint 5 antes da revisão e prova supervisionada.
Nenhum PR será aberto ou merge realizado automaticamente.
