# ADR-0005 — Voz local com planejamento físico offline

Data: 2026-10-19. Base: `9ee93e94`, merge do PR #15.
Status: implementado e testado offline; homologação acústica pendente.

## Decisão

A voz usa uma CLI própria e contratos tipados. Não é uma fonte de
`OperatorTurn`, não constrói `SamsungTextSession` e não recebe seus tokens,
auditoria, flags ou permissões. Todo comando individual, coletivo ou de cena
passa por `respond_to_room_operator`, que reutiliza o parser, catálogo,
grupos, cenas e orquestrador da Sprint 6 em `offline_preview`.

Perguntas informativas explicitamente habilitadas podem usar
`RegistryChatAdapter` → OpenJarvis → Ollama, preservando a política de memória
da Sprint 1. O agente existente usa `tools=[]`, `context=False` e modelo local
`jarvis-dev-lite:latest`. Texto gerado nunca é entrada do interpretador.
Uma resposta do modelo não comprova nem autoriza ações.

O worker usa configuração OpenJarvis temporária própria: Ollama fixo em
`http://127.0.0.1:11434`, proxies removidos, MCP/ferramentas/analytics/traces e
telemetria desabilitados. Não importa a configuração ou arquivos de memória
da sessão de terminal. Eventuais arquivos internos de segurança do SDK ficam
no diretório temporário privado, removido ao terminar, inclusive em timeout.
O Ollama já em execução tem sua própria política de retenção e recursos;
não se muda sua configuração nesta sprint.

## Áudio e backends

- Push-to-talk por Enter é o padrão. Um botão externo pode chamar `activate()`;
  não foi adicionada interface gráfica nem driver de botão nesta sprint.
- Captura PCM16 mono 16 kHz, fila de oito frames de 80 ms, duração limitada,
  energia mínima e silêncio final. Excesso de fila/overflow invalida o áudio.
  Frase cortada pelo limite é rejeitada, sem interpretação parcial.
- Reutilização de `_rms` e `_frames_to_wav` de `openjarvis.speech.voice_io`.
  O gravador original não oferece dispositivo, cancelamento ou timeout de
  leitura bloqueada; `play_wav` também não oferece volume/cancelamento e aceita
  PCM inválido como fallback. Adaptadores específicos cobrem essas lacunas.
- Faster-Whisper existente, com diretório local obrigatório, `cpu`, `int8`
  com resolução de compatibilidade existente e idioma `pt`. Não existe código
  Whisper separado `pt-BR`.
- openWakeWord 0.6.0/ONNX CPU escolhido como backend acústico experimental:
  sem chave de API, sem STT contínuo, assets locais explícitos, dois frames
  consecutivos com score ≥ 0,6 e RMS > 500. Cada espera dura no máximo 30 s
  mais inicialização limitada pelo supervisor. Não se usa detector textual.
- O modelo público `hey_jarvis_v0.1` foi treinado para **“hey Jarvis”**, não
  comprova ativação por **“Jarvis” isolado em português brasileiro**. Um
  modelo acústico Jarvis próprio pode ser passado por `--wake-model` com os
  mesmos extratores locais. Reconhecimento do vocativo isolado permanece
  critério de homologação, com possível necessidade de treinar modelo.
- Kokoro existente com `lang_code='p'`, modelo/config e tensor de voz locais,
  CPU obrigatório. Candidata inicial `pm_santa`; alternativas `pm_alex` e
  `pf_dora`. A escolha de naturalidade final exige ouvintes brasileiros.
  Não se chama `health()` do backend, pois ele testa o pipeline inglês.

A avaliação documental favoreceu openWakeWord pela execução CPU e interface
acústica aberta. Porcupine exigiria credencial/licenciamento adicionais;
ASR contínuo com busca de texto ampliaria uso de recursos e falsos positivos.
Não foram feitos benchmarks comparativos desses detectores nesta máquina.

## Máquina de estados e prazos

`IDLE` → `LISTENING` → `TRANSCRIBING` → `THINKING` → `RESPONDING`.
O ciclo pode retornar a `LISTENING` na mesma janela; não requer novo vocativo.
Silêncio, limite, cancelamento ou fim da janela retornam a `IDLE`. Falhas de
captura, STT ou LLM passam por `ERROR` e fecham a janela. TTS indisponível
preserva a resposta textual. Ctrl+C/EOF encerram e limpam recursos.

Janela absoluta padrão de 45 s, máximo de oito turnos, captura de até 15 s,
silêncio inicial de 4 s, silêncio final de 1,2 s e operações de até 60 s.
STT/LLM recebem o menor prazo entre operação e janela restante. Resultado
que chega após a janela é descartado. Uma resposta TTS já iniciada pode
terminar após a janela, respeitando seu próprio timeout; não abre nova captura.

Cada operação nativa roda em um processo descartável supervisionado. Isso
inclui abertura de PortAudio, inferência, wake word e reprodução, permitindo
encerramento do grupo de processos em timeout/Ctrl+C e evitando acumular
modelos de STT/TTS na memória. Há custo de recarga a cada turno; a avaliação
mede esse custo, sem alegar latência de modelo residente. Threads e filas de
captura não sobrevivem ao processo. Nenhum áudio/transcrição é persistido
automaticamente. Os temporários privados de IPC são fechados ao finalizar.

Contexto volátil apenas informativo: até quatro pares, 1800 caracteres totais,
resposta armazenada até 700 caracteres e prompt até 3800 (abaixo do contrato
4096 existente). Some ao fechar a janela/sessão. Comandos não entram na memória.

## Política acústica e limites

Half-duplex: não existe stream de entrada durante síntese ou reprodução.
O stream e toda a fila de wake word/captura são fechados antes da próxima
operação. Após TTS, inclusive falha parcial, espera-se 0,8 s sem captura;
o próximo stream é novo. É vedado barge-in por voz durante a resposta;
Ctrl+C continua disponível. Duas respostas faladas recentes têm normalização
limitada para descartar possível eco tardio; essa comparação pode rejeitar
repetições legítimas e é suplementar ao isolamento, não autenticação.

Ruído pode produzir falsos positivos; silêncio não é enviado ao STT e frases
ambíguas não ganham interpretação parcial. Wake word, RMS, idioma e botão não
autenticam pessoas. Uma gravação de terceiros pode ativar a conversa ou gerar
um preview: **a barreira física é a inexistência de rota executora**. Não se
promete resistência a replay acústico nem reconhecimento de locutor.
Fones e posicionamento do microfone devem ser avaliados na homologação.

Variáveis `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, telemetria desabilitada
e `CUDA_VISIBLE_DEVICES=''` são impostas aos workers. Caminhos locais são
validados antes de carregar modelos. Isso bloqueia downloads Hugging Face,
mas não é sandbox de rede para código de terceiros. O worker informativo
usa apenas o Ollama local conforme a arquitetura existente. Os testes têm
bloqueios adicionais de rede/imports/processos.

## Referências primárias consultadas

- [Faster-Whisper: CPU/int8, diretórios locais e idioma](https://github.com/SYSTRAN/faster-whisper).
- [openWakeWord: API e limiares acústicos](https://github.com/dscripka/openWakeWord).
- [Assets do openWakeWord 0.6.0](https://github.com/dscripka/openWakeWord/blob/v0.6.0/openwakeword/__init__.py).
- [Vozes brasileiras do Kokoro](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).
- [KModel: config e pesos locais](https://github.com/hexgrad/kokoro/blob/main/kokoro/model.py).
- [WSLg: suporte a áudio e requisitos Windows/WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps).
