# Fronteira futura — automações físicas supervisionadas

Documento de preparação da Sprint 9. **Não há executor novo implementado.**
Voz, LLM, SSE e dashboard continuam sem autoridade física. As cenas permanecem
`offline_preview`. Wake word, reconhecimento de fala, clique e texto de LLM
não autenticam operador nem constituem confirmação/autorização.

O inventário permanece em `config/room_devices.json` e as sequências em
`config/room_scenes.json`. Não criar listas paralelas de equipamentos/entidades.
O auxiliar `input_boolean.jarvis_lab_light` é uma observação virtual de laboratório,
não estado da iluminação física nem evidência de integração Samsung atual.

| Alvo já cadastrado | Fronteira disponível | Evidência ainda necessária para futura execução |
| --- | --- | --- |
| Samsung | Histórico e contratos S4/S5.11 preservados; apresentação sem consulta atual | Inventário HA atual, vínculo exato, identidade/autorizações e verificação física independente |
| Hikvision DS-D5B65RB/D | Planejamento | Protocolo/interface real, integração e teste supervisionado |
| WLED / WS2815 | Planejamento | Projeto elétrico/distribuição, hardware e integração autorizada |
| Ar-condicionado | Planejamento | Modelo, interface, instalação e confirmação independente |
| Áudio | Planejamento | Interface do amplificador/dispositivo e estado verificável |
| Cenas | Grafo declarativo canônico | Integração e autorização formal de cada alvo; política de falha parcial |

## Contratos a revisar numa sprint própria

1. **Identidade do operador:** autenticação por canal confiável, fora de áudio,
   LLM e navegador de apresentação; identidade vinculada a sessão autorizada.
2. **Pedido tipado:** ID único, alvo canônico, capacidade permitida, ação única,
   versão do plano, origem e prazo. Texto livre não chega a um transporte físico.
3. **Autorização explícita:** aprovação humana vinculada ao pedido/plano exatos,
   sem reusar autorizações de outro terminal, sessão ou turno. Negação, ambiguidade,
   contexto e resultado de LLM não são fontes de autorização.
4. **Precondições:** entidade observada/revalidada, endereço permitido, credencial
   fora do Git/UI, integração homologada, condições elétricas e operacionais
   atendidas. Não inferir que a entidade histórica está instalada no HA atual.
5. **Execução isolada:** serviço/adapter privilegiado separado da apresentação e
   do agente informativo. Exigir revisão específica antes de criar qualquer POST,
   controlador ou ferramenta. Os contratos físicos Samsung anteriores continuam
   exclusivos do seu caminho autorizado.
6. **Prevenção de repetição:** nonce/ID consumível, TTL curto, uma operação por alvo,
   registro de pedidos já consumidos e ausência de retry/replay automático após
   timeout. Reconexão de SSE ou repetição acústica não pode disparar operações.
7. **Resultado verificável:** distinguir envio, resposta HA e estado observado de
   confirmação física independente. Um auxiliar virtual ou retorno HTTP 200 não
   comprova que o equipamento mudou. Não confirmar sucesso sem evidência exigida.
8. **Auditoria mínima:** metadados do pedido/aprovação/resultado, tempos, identidade
   verificada e motivo; sem tokens, áudio bruto ou diálogos pessoais. Falha parcial
   em cenas não implica rollback, repetição ou nova autorização automática.
9. **Revogação e parada:** cancelamento/expiração descarta entradas pendentes;
   encerramento não deixa processos executores órfãos. Intertravamentos precisam
   ser validados no hardware, não simulados como confirmação física.

Homologação futura deve demonstrar tanto o caso autorizado quanto bloqueios de
identidade ausente, autorização vencida, plano alterado, pedido duplicado,
mudança de vínculo, timeout e estado divergente. Nenhuma dessas capacidades é
exposta pelo backend SSE da Sprint 9 ou pelos controles DEMO/LIVE.
