# J.A.R.V.I.S. — frontend dual-monitor

Aplicação independente do frontend original do OpenJarvis. A Sprint 8 adiciona
apresentação gráfica; não adiciona caminhos de controle físico.

## Executar

Requisitos atuais verificados: Node 24.22.0, npm 11.19.1. Use Node 24 e npm 11.

```bash
cd projects/jarvis-room/frontend
npm ci
npm run dev
```

Abra duas janelas, no computador que executa o servidor:

- http://127.0.0.1:5174/monitor/1 — sala virtual e holograma.
- http://127.0.0.1:5174/monitor/2 — dashboard declarativo.

O servidor escuta apenas no loopback, com porta fixa e proxy apenas de
`/api/presentation/events` para SSE em `127.0.0.1:8765/events`. Nenhuma API
HA, Ollama ou publicação fica acessível pelo proxy.
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

## Fonte LIVE — Sprint 9

No seletor, **LIVE · backend local somente leitura** abre SSE de mesma origem.
Inicie `jarvis_room.presentation_server` e uma única CLI de voz S7 com
`--presentation`; as duas telas compartilham os eventos, sem duplicar modelos.
Backend ausente/perda de heartbeat limpa estado, energia e observações antigas.
DEMO permanece separado e não publica estados falsos na fonte LIVE.

O holograma existente recebe energia calculada do PCM durante a reprodução
efetiva do TTS, não durante síntese. Dependências/assets Kokoro estão ausentes
na inspeção atual; o modo textual mostra indisponibilidade de áudio e energia zero.
Sem `--share-conversation` não é enviado conteúdo de conversa ao dashboard.
Home Assistant é lido somente pelo backend com opt-in e token privado, nunca pelo
navegador; o auxiliar virtual não comprova estado de iluminação física.

[Inicialização, diagnóstico e homologação completos](../docs/integrations/voice-frontend-integration.md).
[Contrato de eventos](../docs/integrations/presentation-events.md).

## Verificar

```bash
npm run typecheck
npm test
npm run build
```

Os testes Vitest não abrem rede nem inicializam WebGL. São **50 testes** de
contratos, catálogo, cenas, fontes DEMO/LIVE, reconexão/heartbeat, animação e recursos.

**Seis cenários Playwright aprovados** na Sprint 9, com Chromium/bibliotecas
temporários em `/tmp`, serviços falsos e GPU desativada. Para preparar um ambiente
de teste explicitamente (não necessário à execução normal da UI):

```bash
npx playwright install chromium
# Em Ubuntu sem bibliotecas do navegador, preparar dependências conforme o Playwright.
npm run test:e2e
```

Esses cenários usam fallback sem GPU, movimento reduzido e bloqueiam requisições fora
de `127.0.0.1:5174`. Não certificam a renderização WebGL nem fidelidade visual.
O guia completo registra a opção sem instalação de pacotes no sistema usada nesta
entrega. Os imports 3D têm pré-bundle explícito e cache próprio para evitar HTTP 504
durante o carregamento tardio da cena.

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
