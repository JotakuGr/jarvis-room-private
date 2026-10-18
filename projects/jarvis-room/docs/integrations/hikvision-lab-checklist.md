# Prontidão da Hikvision DS-D5B65RB/D — Sprint 3

`hikvision_board` continua `planned`. Esta checklist não habilita operações.
Nenhum equipamento foi acessado para preenchê-la.

## Trilha A — interface no computador host

Planejar HDMI para exibir a interface e Touch-USB para eventual interação.
Computador host, cabos e compatibilidade ainda são desconhecidos.
Exibir interface ou receber toque não comprova controle da alimentação ou de
funções internas. Os dois monitores lógicos do J.A.R.V.I.S. (interface e
dashboard) não precisam corresponder a duas TVs físicas. O segundo display
físico continua sem identificação confirmada.

## Trilha B — funções do equipamento

Permanecem não comprovados: posse/disponibilidade da lousa, etiqueta e revisão,
firmware, documentação RS-232, comandos, retorno de estado, acesso à rede e
autorização institucional. O protocolo e `control_verified` permanecem falsos.
Alterar somente o JSON para alegar validação é recusado nesta sprint.

Antes de uma futura conexão, obter evidências e autorização específicas para
cada item. Não foram implementados serial, TCP, Wake-on-LAN, IR, chaveamento
elétrico ou automação. Ver também o [plano da Sprint 2](hikvision-ds-d5b65rb-d.md)
e suas fontes oficiais do modelo exato.
