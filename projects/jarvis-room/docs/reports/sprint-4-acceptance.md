# Relatório técnico — implementação da Sprint 4

Data: 18/10/2026 (America/Bahia).

**Status: implementação e regressão offline aprovadas; Sprint 4 não concluída.**
Homologação física explicitamente autorizada e revisão técnica final pendentes.

## Base e escopo

Repositório: `JotakuGr/jarvis-room-private`.
Branch: `feature/sprint4-samsung-ha-control`.
Base: `main`/`origin/main`, merge da Sprint 3 pelo PR #12, `1050e19a`.
A branch já existia limpa nessa base; foi preservada. A consulta autenticada
ao remoto confirmou a base atualizada antes da implementação.
Python 3.11.17, Ubuntu WSL. Baseline **261/261** aprovado.

O usuário confirmou que o HA permanece em `http://127.0.0.1:18123` e forneceu os
IDs da TV Samsung LH32BETBLGGXZD e dos scripts. Durante a implementação offline,
não usamos senha ou token real nem consultamos a instância. Na etapa posterior
de homologação somente leitura, os GETs reais foram autorizados e bem-sucedidos,
com correção do identificador de ligar conforme o adendo de 18/10/2026.

## S4.1–S4.9: arquivos, decisões, testes e commits

| Tarefa | Arquivos principais / decisão | Novos | Regressão | Commit |
| --- | --- | --- | --- | --- |
| S4.1 | `samsung_lab.json`, `samsung_inventory.py`, `samsung_contract.py`, teste; inventário exclusivo, IDs exatos | 8 | 269/269 | `3afc84f1` |
| S4.2 | `samsung_credentials.py` e teste; arquivo externo privado, sem links/hardlinks | 10 | 279/279 | `c3149c49` |
| S4.3 | `samsung_rest_client.py`, `samsung_fakes.py`, teste; GET/POST fixos, sem retry/redirect | 12 | 291/291 | `a05f8cc3` |
| S4.4 | `samsung_state.py` e teste; separação de envio, HA e confirmação física | 8 | 299/299 | `9e1ebd17` |
| S4.5 | `samsung_manual_policy.py` e teste; TTY, opt-in e permissão única de 60 s | 8 | 307/307 | `a5ed1765` |
| S4.6 | `samsung_audit.py` e teste; JSONL privado e eventos estritos | 8 | 315/315 | `81c38a84` |
| S4.7 | `samsung_control.py`, `samsung_lab_cli.py`, teste; orquestração manual e polling limitado | 12 + 1 na revisão final | 327/327; final 336/336 | `d2cc4e0a` + correção final |
| S4.8 | `test_sprint4_e2e.py`; sockets reais proibidos, falhas e isolamento | 8 | 335/335 | `bc41ee32` |
| S4.9 | ADR, procedimento, relatório, README e filtro de branch CI | 0 | 336/336 final | `2531b6d9`, `59325624` e complemento da revisão final |

O contrato/resultado foram complementados nas tarefas que introduzem suas
semânticas. Cada tarefa executou testes específicos e regressão completa.
Todos os testes executados passaram; nenhuma falha atual ou teste ignorado.
Total: **261 anteriores + 75 novos = 336 aprovados**.
A revisão final acrescentou um teste e recusou token/auditoria no mesmo caminho,
evitando que a abertura append do log corrompa o arquivo da credencial.
Os 335 testes da entrega inicial e o teste adicional estão aprovados.

Pendências das tarefas: S4.1/S4.3, revisar o conteúdo real dos scripts;
S4.2, manter o token privado provisionado pelo operador; S4.4, evidência física
independente; S4.5/S4.7, sessão manual autorizada; S4.6, política institucional
de retenção/proteção de auditoria; S4.8, prova física não substituída por fakes;
S4.9, revisão final e encerramento condicionados às evidências.

## Arquitetura implementada

```text
Operador → CLI Samsung → inventário → política manual + token privado
  → auditoria → controlador → REST Samsung → scripts exatos HA
  → GETs de estado → resultado sanitizado com confirmação física falsa

LLM / room_chat_cli / RoomControlGateway / cliente read-only Sprint 3
  → nenhuma ligação de execução à Samsung
```

Três entidades GET autorizadas:

- `media_player.samsung_bet_series_32_lh32betblggxzd`.
- `script.jarvis_ligar_samsung`.
- `script.jarvis_desligar_samsung`.

Único POST: `/api/services/script/turn_on`, corpo com somente o ID do script
escolhido por `turn_on`/`turn_off`. Um 404 não altera o identificador de ligar.
`script.turn_off` não é usado para desligar a TV. Não há serviço genérico,
comando de media player, URL dinâmica, argumentos de script ou estado POST.

## Análise de segurança e testes negativos

- Manifesto exato, versão inteira, JSON sem chaves duplicadas e flags que não
  habilitam LLM/execução padrão/confirmam fisicamente por edição de configuração.
- Destino fixo `127.0.0.1:18123`; HTTP remoto e HTTPS não homologado rejeitados.
  Nenhuma opção de certificado inseguro, proxy, redirect ou fallback externo.
- Bearer apenas no cabeçalho. Arquivo 0400/0600, dono atual, regular e externo,
  destino efetivamente aberto conferido; symlinks, hardlinks e FIFO recusados.
- Timeout finito e tamanho JSON limitado; schema de estado restrito e atributos
  descartados. Erros HTTP/JSON/TLS/timeout públicos são códigos sanitizados.
  O parser CLI também não repete argumentos desconhecidos que possam conter segredo.
- Opt-in não autentica pessoas. Terminal + frase exata e permissão única são
  proteção local preventiva, sem RBAC institucional ou confiança em texto de IA.
- Auditoria privada append/fsync antes de tentar POST. Se falha antes, bloqueia;
  se falha após aceite, preserva envio e informa auditoria incompleta.
- POST ambíguo resulta em envio desconhecido, sem repetição automática. Falha de
  GET posterior não transforma um POST aceito em alegação de não execução.
- E2E usam fake HTTP e bloqueiam sockets reais; testam isolamento das Sprints 1–3.
  Estados de fakes não viram `ToolReceipt` nem `SimulatedActionResult` de sucesso físico.

Não há certificação de segurança contra Python arbitrário do mesmo usuário,
token exfiltrado por outro processo ou alterações dos scripts fora do Git.
Auditoria local não é assinada ou inviolável. Token HA não é intrinsecamente
restrito aos métodos que este cliente implementa. Loopback não é isolamento total.

## Verificações locais e CI

```bash
set -o pipefail
PYTHONPATH=projects/jarvis-room/src python3.11 -m unittest discover \
  -s projects/jarvis-room/tests -p 'test_*.py' -v \
  2>&1 | tee /tmp/jarvis-sprint4-tests.log
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.samsung_lab_cli
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_chat_cli 'Ligue a TV Samsung'
git diff --check
```

Regressão offline final: **336/336**, log temporário fora do Git. CLI Samsung padrão
retorna inventário offline e execução desabilitada. CLI de conversação recusa
controle Samsung, `acao_verificada=false`. Nenhum arquivo das Sprints 1–3 foi
modificado, exceto README e filtro de branch do workflow de testes existente.

O workflow mantém Python 3.11, `contents: read`, somente unittest offline,
sem Docker, credenciais operacionais, LLM ou acesso a equipamentos. Foi incluído
o gatilho de push para a branch da Sprint 4, preservando os gatilhos anteriores.
Regressão local e CI são evidências distintas. Consultar a execução do commit
publicado no [workflow da branch](https://github.com/JotakuGr/jarvis-room-private/actions/workflows/jarvis-room-unittest.yml?query=branch%3Afeature%2Fsprint4-samsung-ha-control).

Evidência remota verificada pela API do GitHub: [execução 39151019940](https://github.com/JotakuGr/jarvis-room-private/actions/runs/39151019940),
SHA `2531b6d9908b0bf7d27e9f0784d3244dfaa1d939`, workflow
`JARVIS Room offline unittest`, job `unittest-offline`: **completed/success**.
Este complemento apenas registra a evidência do commit de implementação;
não constitui aprovação de um futuro PR. O complemento documental `59325624`
também foi aprovado na [execução 39151105771](https://github.com/JotakuGr/jarvis-room-private/actions/runs/39151105771).
A correção final do caminho de auditoria será conferida novamente no CI do
seu SHA publicado; seu resultado será informado na entrega final.

## Homologação física — ainda não realizada

Procedimento detalhado: [Samsung no laboratório](../integrations/samsung-lab-control.md).
Exigir autorização explícita separada, responsável presente, revisão de script
e dispositivo, leitura inicial autorizada, um teste por ação e observador
independente da TV. Guardar resultado humano separado, sem token ou log privado.

Nenhum GET/POST real foi realizado durante a implementação offline. Na etapa
posterior, GETs reais autorizados validaram a leitura da TV e a presença dos
scripts; o token privado foi usado pela CLI sem exibição ou versionamento.
Nenhum POST real foi executado pelo Python.
**Ações físicas: 0. Inferências LLM: 0. Merge: não realizado.**
Não foi feita mudança no Docker, na instância HA, nos scripts ou na TV.
Nenhum PR é aberto automaticamente antes da revisão externa solicitada.

## Checklist para revisão do Pull Request

- [x] Base main após merge PR #12; branch exclusiva; commits identificados por tarefa.
- [x] Inventário Samsung separado e IDs exatos, sem assumir renomeações.
- [x] Cliente read-only/gateway/router existentes preservados e cobertos pelos testes.
- [x] Destino/métodos/payload fixos; credenciais privadas; erro e auditoria sanitizados.
- [x] Sem retries de POST, execução por LLM ou confirmação física falsa.
- [x] 336 testes locais aprovados, incluindo negativos e E2E sem sockets.
- [x] CI do commit de implementação publicado aprovado, com SHA/run registrados.
- [ ] Conferir os checks do futuro PR e da sua revisão final.
- [x] Confirmar por GET real o ID operacional de ligar e a presença das três entidades.
- [ ] Revisar os conteúdos reais dos scripts na interface.
- [ ] Autorizar e executar homologação física, coletar evidência independente.
- [ ] Revisão técnica final, tratar achados e decidir abertura/merge do PR.
- [ ] Declarar Sprint 4 concluída somente após homologação e revisão final.

Referências: [ADR-0002](../adr/0002-samsung-manual-control.md),
[REST oficial](https://contributors.home-assistant.io/core/internals/rest-api/),
[scripts oficiais](https://www.home-assistant.io/integrations/script/).

## Adendo — Validação da API real em 18/10/2026

- A primeira leitura apresentou `not_found`.
- O script de ligar antigo retornou HTTP 404.
- O identificador `script.jarvis_ligar_samsung`
  retornou HTTP 200.
- A TV e o script de desligar retornaram HTTP 200.
- Inventário, contrato e teste negativo corrigidos.
- Regressão local: 336/336 testes aprovados.
- `git diff --check`: aprovado.
- GET real autorizado: bem-sucedido.
- Estado informado pela Samsung: `off`.
- POST real pelo Python: não executado.
- Homologação física pelo Python: pendente.
- Confirmação física independente: não coletada.
