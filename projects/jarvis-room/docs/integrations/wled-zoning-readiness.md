# WLED — prontidão e zonas lógicas ainda não energizadas

As premissas da Sprint 2 são preservadas: WS2815, 12 V, 100 m,
60 LEDs/m, total declarativo de 6.000 LEDs, ESP32 e WLED.
Não há controlador conectado nem instalação confirmada.

## Inventário lógico preliminar

| Referência lógica | Limites e associação física |
| --- | --- |
| Perímetro (`led_perimeter`) | Região candidata do planejamento; segmentos e limites ainda não definidos. |
| Demais zonas | A definir no projeto elétrico e de hardware, sem dispositivos associados. |

Essas referências não estabelecem quantidade final de zonas, fontes,
controladores, saídas ou comprimentos individuais. `zones_count` permanece null.

## Pendências que precisam de evidência

- Potência por metro e corrente por LED, com condições reais de ensaio.
- Identificação do produto/lote, comprimentos dos trechos e topologia.
- Localização e quantidade das fontes e controladores.
- Seções e trajetos dos cabos, proteção por circuito e fusíveis.
- Pontos de injeção, quedas de tensão, aterramento e referência de sinal.
- Número de ESP32, quantidade de saídas e taxa de atualização viável.

Potência total e quantidade de fontes permanecem null.
`power_design_verified=false` e `physical_control_enabled=false`.
Nenhum valor é preenchido por suposição; alterações de JSON que aleguem
dimensionamento concluído são recusadas nesta sprint.

Antes de energizar qualquer trecho, exigir dimensionamento e revisão por
profissional habilitado. Não há chamada WLED, alimentação, automação ou
projeto executivo implementado. Ver os
[pré-requisitos elétricos da Sprint 2](wled-electrical-prerequisites.md).
