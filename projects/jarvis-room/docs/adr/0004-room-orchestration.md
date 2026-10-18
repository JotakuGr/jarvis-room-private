# ADR-0004 — Catálogo e orquestração offline da sala

Data: 18/10/2026. Status: implementação offline validada; CI e revisão externa pendentes.

## Base verificada — S6.1

Branch existente e limpa: `feature/sprint6-room-orchestration`, HEAD `421565ed`.
O commit é o merge do PR #14 da Sprint 5 na main; contém
`f7bfbe190a5e3ad8957266553fad3c9f7caf63ff` e tem árvore idêntica a essa base.
Não é necessário rebase ou substituir a branch. Baseline executado: 494/494.
Main não será modificada. A afirmação inicial de que Sprint 5 ainda precisa de
merge foi superada pela evidência do histórico local; o relatório distinguirá
essa evidência da confirmação remota. `git ls-remote origin` confirmou depois
que main e a branch remota da Sprint 6 estavam em `421565ed` antes da publicação.
A API do GitHub confirmou `merged=true` no PR #14 e o mesmo merge SHA.

Foram inspecionados sessão, interpretador/adaptador/política/controlador Samsung,
roteador, dispatcher, safe entrypoint, inventário de capacidades, política de
automação e catálogo HA. Lidos capabilities.json, home_assistant_devices.json,
samsung_lab.json e wled_zones.json. Seus contratos e arquivos serão preservados.

## Decisões

- TV, lousa e telas pertencem a `monitores`. Sem grupo físico `televisores`.
- Catálogo novo não habilita hardware: `execution_available=false` para o
  orquestrador. Somente Samsung referencia a entidade fixa já cadastrada.
- Papéis de interface e dashboard não provam duas telas físicas adicionais.
  O placeholder `second_display_placeholder` será reaproveitado como slot lógico
  de dashboard a confirmar, sem afirmar identidade física. O slot Jarvis também
  é um papel planejado; atribuições a equipamentos dependem de inventário real.
- IDs legados são associados explicitamente, sem apagar inventários anteriores.
  Luz principal, ar-condicionado e presença continuam inventariados, sem criar
  grupos novos. Sensor não ganha capacidade de ligar/desligar.
- Novas intenções produzem planos offline. Backend de simulação é uma interface
  separada, injetada exclusivamente nos testes; não há cliente físico novo.
- Cenas resolvem grupos, deduplicam alvos, ordenam dependências e rejeitam ciclos
  ou ações contraditórias. Resultados individuais não ocultam falhas parciais.
- Nenhum retry ou rollback automático, nem desligamento do computador host,
  sessão, serviços ou controlador. Sem preparação fictícia de áudio: somente
  uma capacidade futura de ligar/desligar o sistema, com integração pendente.
- As oito frases Samsung antigas mantêm a rota autorizada S5.11. Novos aliases,
  grupos e cenas ficam em preview mesmo com `--enable-samsung`. Não se reescreve
  texto para fabricar uma intenção/autorização Samsung.
- Saída do LLM nunca é reprocessada como intenção. Autorizações Samsung não são
  escopo de sala. A futura autorização coletiva deverá enumerar cada alvo e ação,
  expirar, ser consumida e exigir a política real de cada integração.

## Limites

Planejamento não atesta disponibilidade, potência elétrica, protocolo, estado HA
ou confirmação física. Flags `action_verified` e `physical_action_verified`
permanecem falsas inclusive em simulações bem-sucedidas. Voz fora do escopo.
Os relatórios finais registrarão contagens reais, CI e pendências de homologação.

## Implementação e validação

Criados catálogo e compatibilidade, resolução de grupos, intenções, planos com
dependências, orquestrador de simulação e apresentação de resultados. A sessão
acrescenta somente um ramo offline depois das oito frases Samsung originais.
Nenhuma modificação na política, controlador, REST, token ou auditoria Samsung,
gateway, cliente read-only, roteador/dispatcher/safe entrypoint antigos.

Baseline 494 preservado; 103 novos testes; regressão 597/597. A mesma suíte passou
com conexões reais proibidas; fixtures novas impedem criar sockets. Fake backend
restrito a tests/, relógio virtual para tempo de simulação. Nenhum HA real,
comando físico ou inferência nesta implementação. Relatório e CI:
[aceitação Sprint 6](../reports/sprint-6-acceptance.md).
