# Sprint 8 — Implementação local e passagem para validação visual

Data: 20/10/2026. Branch: `feature/sprint8-dual-monitor-ui`.
Base confirmada: `6483b89dd59d836eb7494d71995a8a48f1cbc96c` (main / Sprint 7).
Status: código preparado para continuação e revisão; homologação visual pendente.
O operador solicitou o commit local para continuar os trabalhos na faculdade.
Sem push, PR, merge ou CI remoto executados nesta entrega.

## Implementação

| Fase | Arquivos principais | Resultado local |
| --- | --- | --- |
| Fundação | frontend/package.json, lock, vite.config.ts, tsconfig.json, index.html, src/main.tsx | React independente, duas rotas, loopback 5174 |
| Sala virtual | public/assets/lab-environment.png, src/pages/MonitorOne.tsx, src/styles.css | Ambiente híbrido derivado da imagem aprovada |
| Holograma | src/scene/hologram.ts, Scene.tsx, motion.ts | Núcleo, camadas fragmentadas, anéis independentes, partículas, filamentos, bloom |
| Estados | src/contracts.ts, state.tsx, components/DemoPanel.tsx | Seis estados, interpolação, amplitude 0–1, fala sintética de oito segundos |
| Dashboard | src/pages/MonitorTwo.tsx, src/data/catalog.ts | Nove IDs canônicos, seções de equipamentos/serviços e duas prévias de cena |
| Integração | src/data/source.ts, docs/integrations/presentation-events.md | DEMO entre janelas; receptor futuro sem transporte |
| Qualidade | três arquivos *.test.ts, tests/monitors.spec.ts, documentação | 34 testes leves aprovados; quatro E2E preparados, não executados |

Todas as rotas de código acima ficam em `projects/jarvis-room/frontend`.
O frontend OpenJarvis, inventários originais e módulos Python não foram modificados.
Não há dependências novas para o Python.

## Evidências verificadas

- Node 24.21.0 e npm 11.19.0.
- `npm run typecheck`: aprovado.
- `npm test`: **34/34**, três arquivos Vitest; sem rede/WebGL.
- `npm run build`: aprovado, com aviso de chunk Three.js acima de 500 kB.
- `python3.11 projects/jarvis-room/scripts/run_offline_tests.py`: **831/831**.
  O runner bloqueia sockets, subprocessos de hardware e imports de inferência.
- `git diff --check`: aprovado antes do commit.
- Inferências, captura de voz e acionamentos físicos nesta implementação: **zero**.
- Build não certifica fidelidade visual, fluidez, integração TTS ou dispositivos.

## Dependências

React/React DOM 19.3.0; Three.js 0.186.1; React Three Fiber 9.8.2.
Vite 8.3.1; TypeScript 7.0.2; Vitest 5.0.2; Playwright 1.64.1 (testes de UI preparados).
Lockfile incluído. Não há Drei, Recharts, biblioteca de chat ou fontes externas.

## Fronteiras de segurança

Sem tokens no navegador, endpoints HA, clientes de controle ou proxy para Python.
Cenas são somente prévias. Serviços iniciam desconhecidos e oito equipamentos
continuam planejados. Samsung com integração de laboratório não aparece conectada
sem observação; alterações DEMO são rotuladas como simulação.

O servidor usa loopback, `strictPort`, filesystem allowlist com somente os dois
JSONs canônicos fora do frontend, CORS desabilitado e Permissions-Policy que bloqueia
microfone/câmera/geolocalização. CSP restringe origem e permite o WebSocket de HMR
local; não é um canal de automação. Nenhuma API Python foi criada.

Eventos rejeitam campos desconhecidos, comandos, IDs arbitrários, sequências antigas,
amplitudes fora do intervalo e elevação de planejados. Isso não autentica um backend:
a futura conexão requer projeto e revisão separados.

## Referências e limites visuais

PNG aprovado examinado antes de implementar. Vídeo examinado por metadados e quadros
amostrados, sem reproduzir áudio. O asset derivado remove o holograma e os textos da
sala para receber animação procedural; [proveniência](../../frontend/public/assets/PROVENANCE.md)
registra hashes e instrução de edição imagegen.

Sala usa backplate estático: preserva perspectiva e iluminação, mas não fornece
parallax da arquitetura. A edição não é pixel a pixel. A esfera usa shaders e
geometria animada; não reproduz MP4. Velocidade, densidade, escala, reflexos e bloom
ainda precisam de comparação visual direta no navegador com a referência aprovada.
Não foram produzidas capturas homologadas 1920×1080.

Tentativa de captura no Chromium encontrou bibliotecas ausentes (`libnspr4`, `libnss3`,
`libasound`). Isso não foi resolvido alterando o sistema doméstico. Quatro testes de
navegador estão preparados; sua execução e validação visual ficam pendentes.

DPR e quantidade de partículas são limitados por perfil. Aba oculta pausa o render;
movimento reduzido utiliza atualização sob demanda; WebGL indisponível oferece SVG
identificado. Nenhum benchmark de GPU foi feito. Build gera cerca de 253 kB de JS
principal e 941 kB do chunk de cena (250 kB gzip), carregado sob demanda no Monitor 1.

## Continuação na faculdade

1. Instalar com `npm ci` na pasta do frontend e abrir ambas as rotas em janelas.
2. Preparar Chromium/bibliotecas e executar `npm run test:e2e` (fallback sem GPU).
3. Comparar Monitor 1 em 1920×1080 com o PNG e movimento do MP4; ajustar e capturar.
4. Conferir seis estados, amplitude, retorno a IDLE, erro, aba oculta e movimento reduzido.
5. Validar layout em 1080p/1440p/4K, tela cheia e duas telas no hardware de implantação.
6. Testar consumo e fluidez moderadamente no equipamento da Sala, sem supor resultados.
7. Revisar segurança e preparar PR manualmente; CI ainda não executado nesta branch.
8. Projetar transporte read-only, política de obsolescência e sincronização TTS em etapa futura.

O compromisso desta entrega é preservar o trabalho em commit local verificável.
A Sprint 8 não está declarada homologada visualmente ou integrada ao backend.
