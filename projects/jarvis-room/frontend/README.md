# J.A.R.V.I.S. — frontend dual-monitor

Aplicação independente do frontend original do OpenJarvis. A Sprint 8 adiciona
apresentação gráfica; não adiciona caminhos de controle físico.

## Executar

Requisitos verificados: Node 24.21.0, npm 11.19.0. Use Node 24 e npm 11.

```bash
cd projects/jarvis-room/frontend
npm ci
npm run dev
```

Abra duas janelas, no computador que executa o servidor:

- http://127.0.0.1:5174/monitor/1 — sala virtual e holograma.
- http://127.0.0.1:5174/monitor/2 — dashboard declarativo.

O servidor escuta apenas no loopback, com porta fixa e sem proxy de backend.
Não exponha o servidor de desenvolvimento à rede. Para distribuição, `npm run
build` gera **somente** `frontend/dist`; `npm run preview` permite inspecioná-lo
localmente. As rotas exigem fallback para `index.html` em outro servidor estático.
Não há alteração no frontend original em `/frontend`.

## Usar a demonstração

O botão **Controles**, ou a tecla **D**, abre o painel recolhível. Selecione um dos
seis estados de voz, ajuste amplitude entre 0 e 1 ou use **Demonstrar resposta**.
A demonstração dura oito segundos e retorna a IDLE. Não produz som nem usa TTS.
Há seletores de qualidade, status demonstrativo da Samsung e conexão simulada.
A marca DEMO permanece visível; o catálogo inicia sem telemetria inventada.

As duas janelas da mesma origem compartilham apenas apresentação DEMO por
BroadcastChannel em memória. Não há persistência, microfone, inferência ou HA.
O Monitor 1 possui botão de tela cheia e atalho para abrir o dashboard.
No Monitor 2, as cenas abrem uma prévia ordenada de seis equipamentos, sem ação.

O seletor **Adaptador futuro** usa um receptor sem transporte. Ele NÃO abre
WebSocket, HTTP ou conexão Python. Sem integração futura, mostra ausência de fonte.
O contrato está em [presentation-events.md](../docs/integrations/presentation-events.md).

## Verificar

```bash
npm run typecheck
npm test
npm run build
```

Os testes Vitest não abrem rede nem inicializam WebGL. São 34 testes de contratos,
catálogo, cenas, fontes de dados, animação, orçamento de pixels e descarte de recursos.

Quatro cenários Playwright foram preparados, mas ainda precisam ser executados no
ambiente com Chromium e bibliotecas do navegador disponíveis:

```bash
npx playwright install chromium
# Em Ubuntu sem bibliotecas do navegador, preparar dependências conforme o Playwright.
npm run test:e2e
```

Esses cenários usam fallback sem GPU, movimento reduzido e bloqueiam requisições fora
de `127.0.0.1:5174`. Não certificam a renderização WebGL nem fidelidade visual.

## Desempenho e limites

- Geometrias e materiais compartilhados; animação com delta time e suavização.
- 550/1.300/2.100 partículas nos perfis econômico/equilibrado/alto.
- Orçamento de pixels: 0,9/1,9/2,8 milhões; DPR máximo 1,5.
- Pós-processamento limitado a 30/40/45 apresentações por segundo; o ciclo R3F
  ainda pode atualizar a animação na frequência do navegador.
- Aba oculta: `frameloop=never`; movimento reduzido: `frameloop=demand`.
- Sem WebGL: alternativa SVG identificada como compatibilidade.
- Three.js é carregado sob demanda no Monitor 1. O chunk possui cerca de 941 kB
  minificados / 250 kB gzip; o build avisa que excede 500 kB.
- Não houve benchmark de GPU. Qualidade, consumo e fluidez em dois monitores devem
  ser homologados no equipamento da Sala Temática.

As imagens originais não são publicadas. O ambiente derivado da referência está
em `public/assets/lab-environment.png`; veja a [proveniência](public/assets/PROVENANCE.md).
O holograma é procedural, e o vídeo de referência não é reproduzido pela aplicação.
