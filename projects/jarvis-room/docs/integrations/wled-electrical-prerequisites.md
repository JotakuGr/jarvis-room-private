# WLED / ESP32 / WS2815 — pré-requisitos antes da instalação

Estado: `planned`. WS2815, tensão nominal de 12 V, 100 m e 60 LEDs/m
são premissas informadas pelo projeto, não características medidas de uma
instalação existente. O produto declarativo é 6.000 LEDs; isso não define
potência, fontes, controladores, alimentação ou taxa de atualização.

## Dados que precisam ser obtidos

- Potência real da fita por metro ou corrente por LED no branco, com condições
  de medição e identificação do produto/lote.
- Comprimentos individuais e distribuição física das zonas.
- Quedas de tensão admissíveis e medidas nos percursos relevantes.
- Topologia de alimentação e de sinal, distâncias e conectores.
- Bitolas/seções, materiais, capacidade e trajeto dos cabos.
- Fusíveis e demais proteções por trecho, dimensionados para os circuitos reais.
- Pontos e circuitos de injeção de alimentação, sem interligação indevida de fontes.
- Número e capacidade de fontes e controladores, com suas limitações documentadas.
- Aterramento, referência de sinal, isolamento e compatibilidade das interfaces.
- Separação e proteção entre rede elétrica e circuitos de baixa tensão.

O projeto elétrico e a instalação exigem validação por profissional habilitado.
Nenhum valor de potência total, proteção, seção de cabo ou quantidade de fontes
foi definido nesta sprint. Esses parâmetros dependem dos dados acima.

## Capacidade de processamento e integração

Um único ESP32 não é considerado suficiente para os 100 m: quantidade de saídas,
distribuição dos LEDs e taxa de atualização deverão ser validadas no projeto.
Nenhum firmware foi instalado ou controlador acessado por estes módulos.
Todos os comandos `on`, `off`, `color`, `brightness` e `effect` são recusados.

A integração WLED com Home Assistant fica para sprint futura, após segurança
elétrica, autorização e testes controlados com retorno real de estado.
Alterar flags do JSON não habilita execução.

## Referências de preparação

As orientações oficiais destacam cuidados de alimentação, cabos, fusíveis
e queda de tensão; não substituem o dimensionamento da instalação universitária:
[início do WLED](https://kno.wled.ge/basics/getting-started/) e
[orientações de cabeamento](https://kno.wled.ge/advanced/wiring/), consultadas em 17/10/2026.
