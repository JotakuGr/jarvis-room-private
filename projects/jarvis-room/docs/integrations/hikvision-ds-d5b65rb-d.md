# Hikvision DS-D5B65RB/D — planejamento offline

Estado: `planned`. O item `hikvision_board` é a lousa interativa de 65 polegadas.
O segundo monitor/TV continua um placeholder sem modelo confirmado.
Nenhum equipamento foi conectado ou controlado nesta sprint.

A ficha oficial do modelo exato lista RS-232, RJ45, HDMI IN/OUT e Touch-USB
(tabela de interfaces, página 3). A existência dessas portas não comprova
protocolo de controle funcional, comandos suportados ou retorno de estado.
Conferir etiqueta, revisão do equipamento e firmware antes da futura conexão.

## Trilha A — exibição e interação com um computador host

Planejar vídeo do computador por HDMI IN e, eventualmente, Touch-USB para
interação. Confirmar compatibilidade do host, cabos e permissões antes de testar.
Exibir a interface do J.A.R.V.I.S. não comprova controle de alimentação,
seleção de entrada ou outras funções internas da lousa.

## Trilha B — controle de funções do equipamento

Exigir documentação específica do protocolo, identificação do meio físico,
segurança, autorização institucional e confirmação confiável de estado.
Não há comando RS-232, baudrate, endereço de rede ou cliente de controle
implementado. `power_on`, `power_off`, `set_input`, `volume`, `touch` e
`screen_cast` permanecem negados. Alterar flags no JSON não habilita nada.

## Questões pendentes para a Sprint 3

- O equipamento está disponível para teste autorizado?
- Existe manual de controle RS-232 específico para DS-D5B65RB/D e sua revisão?
- Qual o firmware instalado e quais funções ele suporta?
- Haverá computador host conectado por HDMI e Touch-USB?
- Qual integração forneceria retorno real e confiável de estado?
- A conexão e eventual automação são permitidas pela universidade?

## Fontes primárias

- [Ficha oficial DS-D5B65RB/D](https://assets.hikvision.com/prd/normal/all/doc/m000065236/DS-D5B65RB_D_Datasheet_20251128.pdf), consultada em 17/10/2026.
- [Página do modelo exato](https://pro-av.hikvision.com/en/products/interactive-flat-panel-display/interactive-flat-panels/performance-series/ds-d5b65rb-d/): indisponível na ferramenta de consulta nesta coleta; a ficha oficial foi a evidência utilizada.
