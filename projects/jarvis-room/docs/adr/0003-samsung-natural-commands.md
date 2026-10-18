# ADR-0003 — Linguagem natural determinística e controle manual Samsung

Status: implementação offline validada; homologação física da nova interface pendente.
Data: 18/10/2026.

## Revisão inicial — S5.1

Branch: `feature/sprint5-samsung-natural-commands`, limpa e baseada em
`origin/main` atualizada, merge PR #13, `b9627949`. Não modificar `main`.
Baseline executado: **356/356**, Python 3.11.17, Ubuntu WSL.

Foram inspecionados os módulos de roteamento/conversação (`command_router`,
`response_dispatcher`, `safe_entrypoint`, `room_chat_cli`, `room_assistant`,
`conversation_adapter`, `provider_chat_adapter`), todos os nove módulos de
controle/credenciais/auditoria/observação Samsung e `config/samsung_lab.json`.
A regressão inclui os testes Samsung, E2E e bloqueios de LLM das Sprints 1–4.

## Decisão original — S5.1–S5.10

Usar frases completas cadastradas em um interpretador próprio, sem LLM ou
efeitos colaterais. Não ampliar o normalizador do roteador antigo: apagar sinais
arbitrários pode transformar texto inválido em comando; a nova camada só aceita
letras, espaços e pontuação simples explicitamente permitida.

Uma intenção reconhecida não é autorização. O adaptador novo reutilizará
`SamsungRequest`, `authorize_manual`, `load_samsung_token`, `PrivateSamsungAudit`,
`SamsungRESTClient`, `ObservationWindow` e `execute_samsung_manual`. Nenhum
cliente HTTP, permissão ou loop de observação será reimplementado.

CLI independente: reconhecimento offline por padrão, execução somente com
`--execute`. Interface conversacional: caminho manual explícito separado,
incompatível com `--llm`, `--experimental-chat` e seleção de provedor; deve ser
tratado antes de construir qualquer adaptador de conversação.

Preservar `command_router`, `response_dispatcher` e `safe_entrypoint` em seus
contratos atuais. Uma frase Samsung no caminho padrão continuará bloqueada.
O gateway não receberá `media_player.*`, o cliente read-only não ganhará POST
e nenhum provedor de LLM terá acesso ao adaptador de execução.

## Confiança e limites das CLIs por ação

Opt-in, terminal, frase exata, permissão única com validade, token externo e
auditoria permanecem obrigatórios. São barreiras locais, não autenticação
institucional nem isolamento contra código Python malicioso do mesmo usuário.

O interpretador não fornece origem autenticada de texto. Frases aceitas só
podem alcançar execução por uma interface de operador explicitamente habilitada;
texto de resposta de um modelo nunca é recirculado para essa interface.

Uma resposta HTTP e um estado HA não comprovam execução física independente.
`action_verified=false` e `physical_action_verified=false` serão preservados.
Os acionamentos anteriores da Sprint 4 não homologam a nova interface textual.
Microfone, reconhecimento de voz e TTS permanecem fora desta sprint.

## Implementação e validação original

`samsung_text_cli` oferece preview e `--execute`; `room_chat_cli` tem o caminho
exclusivo `--samsung-control`, sem construir provedor LLM nesse ramo. As duas
interfaces compartilham interpretador, adaptador, respostas e auditoria existente.
O parser recusa abreviações e evita eco de valores sensíveis em erros automáticos;
mensagens explícitas anteriores permanecem compatíveis com os testes existentes.

Regressão: 441/441, incluindo 85 testes novos. O controlador/cliente/permissão da
Sprint 4 permanecem intactos. Um erro ao fechar a auditoria no adaptador preserva
o resultado conhecido do controlador. Nenhum comando HA real foi executado.

Diagramas, procedimentos e riscos: [guia](../integrations/samsung-natural-commands.md).
Evidências e tarefas: [relatório](../reports/sprint-5-acceptance.md).

## Extensão S5.11 — autorização de sessão textual

O operador pode habilitar uma sessão com `room_session_cli --enable-samsung`.
Essa escolha autoriza ligar/desligar a Samsung durante a sessão digitada no
terminal, sem pedir novamente `LIGAR SAMSUNG` ou `DESLIGAR SAMSUNG` a cada ação.
Não se utiliza `authorize_manual` para esse caminho, nem se simulam entradas,
respostas ou TTY em produção. As CLIs anteriores mantêm sua política original.

`SamsungTextSession` captura os objetos stdin/stdout, PID e thread proprietária,
exige TTY e lê cada turno com `input`. `OperatorTurn` é imutável e só é emitido
nessa leitura. A intenção exata deve corresponder ao turno ativo. A sessão emite
um `SessionPermit`, limitado à ação e à Samsung fixa, com 60 s para consumo,
uso único e revogação ao terminar o turno ou a sessão. Não se pode emitir uma
segunda permissão para o mesmo turno. Perda/troca do terminal revoga a sessão.
Nenhuma API recebe uma string externa para convertê-la em turno autorizado.

O controlador existente passa a usar um seletor fechado de capacidades:
`consume_control_permit` aceita apenas o tipo exato `ManualPermit` ou
`SessionPermit`. A função antiga `consume_manual_permit` continua recusando
qualquer outro tipo. POST, preflight, observação, estado, auditoria e credenciais
da Sprint 4 não foram reimplementados. `SamsungSessionControl`, no adaptador
natural, mantém cliente e auditoria privados no contexto da sessão; inicializá-lo
não realiza GET ou POST. Erro de auditoria encerra a sessão executora.

Nesta nova CLI, `--enable-samsung` é o opt-in de controle; não se exige também
`JARVIS_SAMSUNG_LAB_CONTROL`. Essa variável e a confirmação exata continuam
obrigatórias nas CLIs antigas. Token externo 0400/0600 e JSONL externo 0600,
destino/scripts fixos e um POST sem retry permanecem obrigatórios.

`--llm` pode coexistir com o controle **somente nesta sessão**. O ramo de comando
usa exclusivamente o turno original; o ramo informativo usa catálogo ou provedor
existente, com configuração restritiva e política de memória. A saída do LLM é
exibida como experimental, nunca passa pelo interpretador ou pela autorização.
O provedor não recebe referências à sessão, permissões, cliente ou auditoria.
Conversas não habilitam, renovam ou ampliam a autorização. Não há ferramentas
físicas no modelo. Os contratos antigos de `room_chat_cli` não mudaram.

`sair`, EOF, Ctrl+C e exceções revogam permissões pendentes e fecham o log.
Se Ctrl+C ocorrer durante envio/observação, o controlador registra o resultado
conhecido ou incerto, sem repetir POST, e o loop termina. O JSONL usa os mesmos
eventos e request IDs do controlador, sem duplicação ou registro de diálogos.

Consequências: depois do opt-in inicial, cada frase completa aceita tem efeito
operacional sem outra pergunta; exige maior cuidado do operador com o terminal.
Não há autenticação institucional, proteção contra Python malicioso no mesmo
processo ou garantia de que texto colado no terminal foi digitado tecla a tecla.
A aplicação não oferece ingestão de arquivo/log, voz ou execução de respostas
do modelo. Permissão de sessão não se aplica automaticamente a microfone/TTS.

Validação S5.11: **494/494** (441 anteriores + 53 novos), REST fake e relógio
virtual, sem HA real ou inferência. `action_verified=false` e
`physical_action_verified=false` permanecem invariantes. Homologação física da
sessão e revisão técnica externa continuam pendentes.
