# Memória Institucional — Sala Temática

## Projeto

Nome: J.A.R.V.I.S. — Sala Temática Inteligente.

Objetivo: integrar inteligência artificial local, dispositivos IoT, automações e interfaces em uma sala universitária.

## Arquitetura

- OpenJarvis: agente de inteligência artificial.
- Ollama: execução local dos modelos de linguagem.
- Home Assistant: automação e estado dos dispositivos.
- MCP e tool calling: comunicação entre agentes e serviços.
- ESP32, ESPHome e WLED: controle IoT e LEDs.
- Frigate: visão computacional planejada.

## Interfaces

Monitor 1:
Interface visual do J.A.R.V.I.S., com estados IDLE, OUVINDO, PENSANDO, EXECUTANDO e FALANDO.

Monitor 2:
Dashboard com temperatura, umidade, iluminação, LEDs, ar-condicionado, televisores, sensores, presença e estado dos serviços.

## Automação planejada

A sala utilizará zonas de presença para ativar progressivamente dispositivos.

Comandos determinísticos serão executados pelo Home Assistant.
Decisões conversacionais serão interpretadas pelo OpenJarvis.

## Estado atual

O ambiente de desenvolvimento utiliza Windows, WSL2 e Ubuntu.

OpenJarvis e Ollama foram instalados e validados.

O modelo leve é temporário e possui limitações de qualidade.

A integração física com Home Assistant e dispositivos ainda não foi validada.

Não considere equipamentos físicos controláveis até existir integração funcional e confirmação das ferramentas.
