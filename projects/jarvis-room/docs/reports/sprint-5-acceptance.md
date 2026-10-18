# Relatório técnico — Sprint 5: Samsung por texto

Data: 18/10/2026 (America/Bahia).
Status: implementação offline pronta para revisão; homologação física da nova
interface pendente. Não é reconhecimento de voz. Nenhum PR/merge automático.

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
| S5.9 | Este relatório, guia de integração, README e ADR | Regressão anterior preservada | 441/441 | Commit que contém a documentação | Revisão técnica final |
| S5.10 | Filtro do workflow, publicação e evidências CI | Suíte offline completa | Local 441/441; CI consultado após push | Commit de CI/publicação e complemento de evidência | Conferir SHA/workflow efetivos |

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
- Tokens reais lidos/criados: **0**.
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
precisa incluir Sprint 5, preservando os gatilhos anteriores. Sem Docker,
credenciais ou endpoints reais no job. A execução remota será consultada no
SHA publicado e registrada em complemento, separadamente da regressão local.

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
- [ ] Conferir CI do SHA final publicado e limpeza do Git na entrega.
- [ ] Revisão técnica externa e decisão humana sobre abertura do PR.
- [ ] Homologação física específica das novas interfaces.

A implementação offline está pronta para revisão quando o CI final for aprovado.
Homologação física/produção e abertura de PR permanecem pendentes de decisão
humana. Nenhuma ação física, PR ou merge será executado automaticamente.
