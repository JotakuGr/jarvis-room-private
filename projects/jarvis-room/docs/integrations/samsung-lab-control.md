# Samsung LH32BETBLGGXZD — procedimento de laboratório supervisionado

Status: código e testes simulados disponíveis; homologação física pendente.
Os comandos de execução abaixo são instruções para uma sessão futura com
autorização explícita do responsável. Não foram executados nesta implementação.

## Inventário e contratos

| Finalidade | Identificador autorizado |
| --- | --- |
| TV | `media_player.samsung_bet_series_32_lh32betblggxzd` |
| Ligar | `script.script_jarvis_ligar_samsung` |
| Desligar | `script.jarvis_desligar_samsung` |
| Destino | `http://127.0.0.1:18123` |
| Serviço | `POST /api/services/script/turn_on` |

O corpo do POST contém somente `entity_id` do script selecionado. Não há
volume, entrada, toggle, media_player.turn_on, template, variável de script ou
endpoint arbitrário. O script de desligar é iniciado com `script.turn_on`.

O script de ligar mantém o ID com `script.script_...` informado pelo usuário.
Se um GET exato retornar 404, interromper. Não trocar para
`script.jarvis_ligar_samsung` por suposição. Conferir o ID efetivo na interface
e submeter eventual mudança de allowlist/inventário/testes à revisão.

Referências oficiais: [REST](https://contributors.home-assistant.io/core/internals/rest-api/)
e [scripts](https://www.home-assistant.io/integrations/script/). O estado de
execução de um script não representa o estado de energia da TV.

## Fluxo e módulos

```text
Operador em terminal → samsung_lab_cli
  → inventário estrito + arquivo privado de token
  → política manual (opt-in, frase, permissão única de 60 s)
  → auditoria privada → samsung_control → samsung_rest_client
  → GET script selecionado / GET TV / revalidação script / POST script
  → até 3 GETs da TV → resultado sanitizado, confirmação física=false
```

O módulo `samsung_control` não importa LLM, gateway ou cliente read-only.
O cliente da Sprint 3 continua apenas GET do helper virtual. Nada nesta
implementação conecta o LLM à Samsung ou habilita outros equipamentos.

## Preparação humana obrigatória

1. Obter autorização explícita para a sessão física, identificar o responsável
   presente e confirmar que a ação não interrompe aula ou uso de terceiros.
2. Confirmar instância/porta, TV/modelo, IDs exatos e conteúdo dos dois scripts
   na interface do HA. Verificar que eles só afetam a Samsung desejada e que
   não possuem variáveis, automações indiretas ou efeitos adicionais imprevistos.
3. Identificar TV e observador independente; registrar estado visual inicial.
   Não aceitar resposta do LLM ou `media_player.state` como observação física.
4. Gerar token temporário exclusivo, guardar em arquivo privado fora de qualquer
   checkout Git, dono atual, 0400/0600. O diretório pode ser criado com modo 700:
   `install -d -m 700 "$HOME/.config/jarvis-room"`.
   Preencher o arquivo com editor local; não colar o token no chat, comando,
   histórico, relatório ou CI. Usar arquivo Linux/WSL, não volume Windows sem
   permissões Unix confiáveis. O cliente recusa links e arquivos com hardlinks.
5. Reservar arquivo JSONL externo para auditoria, diferente do arquivo de token.
   A CLI recusa usar o token como destino de auditoria. Não commitar o token ou log.
   Nenhum onboarding, token ou script é criado automaticamente por este código.

## Comandos manuais para a sessão autorizada

Na raiz do repositório, diagnóstico offline (nenhuma rede):

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.samsung_lab_cli
```

Somente após autorizar a leitura real e preparar o arquivo privado:

```bash
JARVIS_SAMSUNG_LAB_READ=1 PYTHONPATH=projects/jarvis-room/src \
python3.11 -m jarvis_room.samsung_lab_cli --read \
  --token-file "$HOME/.config/jarvis-room/samsung-ha.token"
```

Esse comando consulta a TV e os dois scripts por GET. Não lista entidades nem
atributos privados. Presença de script não valida seu conteúdo.

Somente após autorização explícita para cada teste físico:

```bash
JARVIS_SAMSUNG_LAB_CONTROL=1 PYTHONPATH=projects/jarvis-room/src \
python3.11 -m jarvis_room.samsung_lab_cli --execute turn_on \
  --token-file "$HOME/.config/jarvis-room/samsung-ha.token" \
  --audit-file "$HOME/.config/jarvis-room/samsung-audit.jsonl"
```

Digitar `LIGAR SAMSUNG` no terminal interativo. Para desligar, após autorização
separada, trocar somente `turn_on` por `turn_off` e digitar `DESLIGAR SAMSUNG`.
Não existe `--yes`, opt-in de LLM ou execução não interativa.

## Interpretação e registro da homologação

- `command_delivery=accepted` / `command_sent=true`: HA aceitou o POST e retornou
  JSON do serviço. Não significa fim do script ou energia física confirmada.
- `command_delivery=unknown` / `command_sent=null`: resultado de entrega incerto;
  não repetir nem inverter a ação automaticamente. Inspecionar a TV e o HA.
- `reported_target_match`: estado do GET compatível; ligar considera on, idle,
  playing ou paused; desligar considera apenas off. Standby/buffering não provam
  o alvo. Unknown/unavailable não confirmam o estado.
- `state_transition_observed`: diferença entre dois estados HA disponíveis;
  não comprova causalidade ou mudança física. Timestamps HA podem ser antigos.
- `physical_action_verified=false` e `independent_physical_confirmation=not_collected`
  permanecem assim: este software não dispõe de sensor/observador independente.
- `audit_complete=false`: auditoria falhou; preservar a distinção de envio e
  interromper a sessão. Não alegar que uma ação aceita deixou de ser executada.
- Código de saída zero indica caminho técnico aceito e estado HA compatível,
  nunca homologação física. Códigos 1/2 representam falha/bloqueio/argumentos.

Registrar em documento humano separado: autorização, data/hora, operador,
observador, IDs/revisão dos scripts, ação, estados HA, evidência visual ou
medição independente e divergências. Não alterar um JSON para afirmar sucesso.
Revogar o token temporário ao terminar e conservar auditoria em local privado.

## Limitações e critérios de parada

Loopback não é isolamento total; processos locais e um token HA com privilégios
amplos são fronteiras de confiança. Destinos HTTP de rede e HTTPS não homologado
são bloqueados; não usar proxy, túnel ou desativar validação TLS para contornar.

Parar em 401/403, 404 de script, redirect, falha TLS, resposta inválida, ausência
de auditoria, resultado incerto, dispositivo diferente ou efeito inesperado.
Se houver divergência física, não reenviar para tentar obter um relatório verde.
O gateway original continua recusando `media_player.*`.
