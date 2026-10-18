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

## Decisão

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

## Confiança e limites

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

## Implementação e validação

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
