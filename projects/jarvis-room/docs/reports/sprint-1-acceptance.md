# Relatório de encerramento — Sprint 1

Projeto: J.A.R.V.I.S. — Sala Temática

Status: Homologação técnica aprovada no escopo da Sprint 1

Data da validação: 17/10/2026 (America/Bahia)

## Objetivo

Construir a fundação do assistente, com conversação
experimental, roteamento determinístico e separação
entre respostas de IA e comandos de controle físico.

## Entregas

- Ambiente de desenvolvimento configurado.
- Persona do J.A.R.V.I.S.
- Catálogo de respostas verificadas.
- Roteamento determinístico.
- Gateway de controle simulado.
- Contrato e registro de provedores de conversação.
- Adaptador local OpenJarvis.
- Seleção explícita de provedores.
- Política preventiva de memória.
- Auditoria offline da qualidade.
- Diagnóstico e observabilidade.

## Validação

Testes automatizados: 139/139 confirmados nesta execução.
Regressão final: APROVADA — 139 testes executados, sem erros ou falhas.
Controle físico real: desabilitado.
Provedores remotos: bloqueados.
Inferência real nesta homologação: não executada.

Comando utilizado para a regressão:

```bash
PYTHONPATH=projects/jarvis-room/src \
python3.11 -m unittest discover \
  -s projects/jarvis-room/tests \
  -p "test_*.py" -v
```

### CLI

| Cenário | Resultado confirmado |
| --- | --- |
| `Quem é você?` | `canal=conversation; acao_verificada=false`; identidade do catálogo e ausência de controle físico informadas. |
| `Ligue a luz da sala` | `canal=control; acao_verificada=false`; comando não executado, dispositivo indisponível. |
| Mesmo comando com `--llm --experimental-chat --provider openjarvis-local` | `canal=blocked; acao_verificada=false`; modo experimental aceita somente perguntas informativas habilitadas. |

### Diagnóstico offline

Relatório gerado e conferido com `python3.11 -m json.tool`:
`/tmp/jarvis-sprint1-final.json`.
Esse arquivo é um artefato temporário local; seus resultados estão registrados abaixo.

```json
{
  "schema_version": 1,
  "mode": "offline",
  "provider_id": "openjarvis-local",
  "configuration_valid": true,
  "local_enabled": true,
  "remote_provider_allowed": false,
  "resource_minimum_met": false,
  "status": "resources_blocked",
  "action_verified": false,
  "inference_executed_by_diagnostic": false
}
```

O resultado `resources_blocked` é aceito nesta homologação:
a Sprint 1 não certifica inferência neste hardware.
`ollama ps` não apresentou modelos residentes.

### Versionamento das implementações

Branch validada: `feature/jarvis-persona`.

Commit validado: `c567e427ef4532b34197411f24f674dcec20590c`
(`feat: adicionar diagnostico e observabilidade de provedores`).

A consulta direta à branch remota com `git ls-remote` confirmou o mesmo commit em
`origin`, no repositório `JotakuGr/jarvis-room-private`.
Nenhum push foi executado nesta homologação.

A árvore de trabalho estava limpa antes da criação deste relatório.
Este documento é a única alteração produzida na homologação e aguarda
versionamento; essa pendência documental está explicitamente justificada.

## Limitações conhecidas

O modelo local experimental apresentou erros factuais
nas avaliações anteriores.

O hardware atual não demonstrou condições adequadas
para manter a inferência local disponível de forma
confiável.

Os testes simulados não certificam integração física
nem qualidade factual de um modelo em produção.

## Critérios para encerramento

- Regressão final aprovada: atendido, 139/139 testes.
- Comandos físicos recusados como esperado: atendido nos modos normal e experimental.
- Configuração remota bloqueada: atendido pelos testes e diagnóstico offline.
- Diagnóstico offline válido: atendido, sem inferência e com configuração válida.
- Implementações publicadas no repositório: atendido, commit remoto confirmado.
- Nenhuma alteração pendente sem justificativa: atendido; somente este relatório
  recém-criado aguarda versionamento, conforme registrado acima.

## Resultado final

HOMOLOGAÇÃO TÉCNICA APROVADA para a fundação do J.A.R.V.I.S. na Sprint 1.

O resultado aprova o escopo implementado e as proteções verificadas,
sem certificar controle físico real ou modelo de IA para produção.
O versionamento deste relatório permanece como pendência documental justificada.
