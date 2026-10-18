# Catálogo unificado da sala — Sprint 6

O catálogo canônico é `config/room_devices.json`; o carregador é
`jarvis_room.room_device_registry`. É um inventário declarativo offline,
não uma descoberta de hardware ou uma autorização de execução.

## Equipamentos e papéis

| ID | Cadastro | Grupo | Integração / identidade |
| --- | --- | --- | --- |
| `samsung_lab_tv` | Samsung LH32BETBLGGXZD | monitores | Laboratório existente; dispositivo identificado |
| `hikvision_board` | Hikvision DS-D5B65RB/D | monitores | Planejada; protocolo físico não verificado |
| `jarvis_interface_display` | Slot da interface Jarvis | monitores | Papel planejado, equipamento a confirmar |
| `second_display_placeholder` | Slot do dashboard | monitores | Papel planejado; reaproveita placeholder anterior |
| `led_perimeter` | WS2815 12 V, perímetro | leds | Planejada; ESP32/WLED futuros |
| `room_audio` | Sistema de alto-falantes | audio | Modelo/interface não confirmados |
| `room_main_lights` | Iluminação principal | Sem grupo canônico nesta sprint | Planejada |
| `air_conditioner` | Ar-condicionado | Sem grupo canônico nesta sprint | Planejada |
| `presence_sensor` | Presença | Sem grupo de atuação | Somente capacidade declarativa de leitura |

TV, televisão e monitor Samsung são aliases de **um** cadastro e uma entidade.
Toda tela cadastrada pertence a `monitores`. Não existe grupo `televisores`.

Os quatro registros de exibição não comprovam quatro equipamentos físicos
adicionais ou disponíveis. Interface e dashboard são funções visuais; podem
futuramente compartilhar equipamentos já inventariados. O placeholder anterior
foi reaproveitado como slot lógico do dashboard, sem comprovar essa atribuição
física. Resolver a identidade de cada slot antes de qualquer integração coletiva;
não adicionar novas TVs reais por inferência sobre a quantidade de funções.

WS2815: 100 m × 60 LEDs/m = 6.000 LEDs **declarados**, não instalação confirmada.
Tensão nominal de 12 V. O carregador confere as premissas com `wled_zones.json`;
ESP32, WLED e dimensionamento continuam sujeitos ao plano anterior. Potência,
fontes, circuitos, cabos, fusíveis e pontos de injeção não foram inventados.
Áudio não recebe entidade, endereço, comando de preparo ou driver fictício.

## Contrato e validações

Cada registro contém ID, nome, aliases completos (com artigo), grupo, categoria,
fabricante/modelo opcionais, capacidades, adaptador, referência de entidade,
status da integração, disponibilidade, exigência de autorização, tipo do registro,
IDs legados e premissas. São rejeitados:

- Versão diferente do inteiro 1, booleano como versão, campos desconhecidos,
  JSON duplicado, tipos inválidos, listas vazias e IDs inválidos/duplicados.
- Aliases conflitantes após normalização, aliases de grupos e campos de URL/token.
- Grupo de tela diferente de `monitores`; grupo separado de TVs.
- Capacidade de atuação para presença, capacidades desconhecidas ou duplicadas.
- Entidades/adaptadores físicos inventados; somente a Samsung possui a referência
  exata existente e o rótulo `lab_existing`.
- Elevar `execution_available` por JSON. Esse campo é sempre falso no orquestrador,
  inclusive para Samsung: a rota manual S5.11 é separada e mantém sua política.
- Declarar papéis de exibição como equipamentos identificados, elevar premissas
  elétricas ou duplicar os modelos Samsung/Hikvision conhecidos sob outro ID.

`capabilities` descreve o contrato planejado; não comprova integração ou estado.
`read_state` não habilita um novo GET. A leitura operacional real Samsung continua
no controlador anterior; os estados do backend novo são rotulados como simulação.
Novos monitores podem ser planejados com ID e aliases únicos e grupo `monitores`;
uma nova integração física exige evidência, revisão de código e autorização.

## Compatibilidade

Os inventários `home_assistant_devices.json`, `capabilities.json`,
`samsung_lab.json` e `wled_zones.json` não foram alterados. A função
`legacy_catalog_links()` confere os seis IDs legados, sem referências desconhecidas,
sem omissões e preservando categoria e fabricante/modelo conhecidos. A categoria
legada `interactive_display` é traduzida explicitamente para `display`. Sensores
não podem ser reclassificados como áudio/tela para fabricar atuação. O placeholder mantém
seu ID. Não há migração destrutiva nem substituição silenciosa de consultas antigas.
Os novos comandos de inventário usam o catálogo unificado; a consulta declarativa
antiga de capacidades mantém o contrato das Sprints 1–5.

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.room_device_registry
```

Esse relatório não requer Home Assistant, credenciais, Docker ou Ollama.
`physical_control_enabled=false` e `live_state_queried=false` permanecem falsos.

Decisão: [ADR-0004](../adr/0004-room-orchestration.md).
Grupos e interfaces: [guia de grupos](room-groups.md).
