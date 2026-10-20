# Comunicação por voz — instalação e homologação

Implementação local da Sprint 7. Nenhuma permissão física adicional.
Arquitetura inicial: [ADR-0005](../adr/0005-local-voice-session.md);
evolução residente: [ADR-0006](../adr/0006-resident-voice-workers.md).
Execução atual com RTX 4070, Ollama e TTS opcional:
[guia GPU/LLM](voice-gpu-ollama.md).
Resultados: [histórico S7/S7.1](../reports/sprint-7-acceptance.md) e
[consolidação](../reports/sprint-7-consolidation.md).

## Diagnóstico passivo

Da raiz `openjarvis`, com Python 3.11:

```bash
PYTHONPATH=projects/jarvis-room/src:src python3.11 -m jarvis_room.room_voice_cli --diagnose
```

Enumera dependências, WSLg, acesso ao socket de áudio, `/dev/snd`, PortAudio,
host APIs, índices e canais de dispositivos. Não abre stream, grava, reproduz,
baixa modelo, inicia Ollama/HA ou altera configurações. A enumeração é
supervisionada por processo de até 10 s. Encontrar dispositivo não comprova
captura/reprodução; ausência de pacote não comprova ausência de hardware.

No WSL2, áudio normalmente usa WSLg/PulseAudio, não `/dev/snd` direto. Verifique
no Windows o dispositivo de entrada/saída selecionado, volume/mudo e permissão
de microfone para aplicativos de desktop. Valide a gravação primeiro no Windows
com o operador presente. Confira WSLg e a variável `PULSE_SERVER` já fornecida
pela sessão. `pactl info` e `pactl list short sources`/`sinks`, se instalados,
ajudam a inspecionar roteamento. Não selecione fontes `monitor`/loopback como
microfone: elas capturam a reprodução do computador.

Não executar `chmod 777`, instalar servidor PulseAudio alternativo ou editar
configurações Windows/WSL automaticamente. Grupo `audio` e `/dev/snd` podem
ser relevantes em Linux nativo; não são pré-requisitos gerais de WSLg. Reinício,
`wsl --update` e alterações de privacidade ficam sob controle do operador.

## Dependências opcionais

Os comandos desta seção **instalam pacotes e acessam a internet**. Não são
executados pelo diagnóstico nem pelo CI. Instalação e resolução completa dos
pacotes de voz ainda precisam ser validadas no ambiente de homologação.

Se faltarem bibliotecas nativas, instalar de forma supervisionada no Ubuntu:

```bash
sudo apt-get install libportaudio2 libsndfile1 espeak-ng pulseaudio-utils
```

`pulseaudio-utils` fornece inspeção, não implica iniciar outro servidor.
Usando o ambiente `.venv` do projeto e `uv`:

```bash
uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r projects/jarvis-room/config/requirements-voice.txt
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli --diagnose
```

STT e wake word não precisam de Torch; ele é utilizado pelo Kokoro. TTS e
wake word usam CPU; STT aceita CPU ou CUDA explícita. A RTX 4070 atual foi
inspecionada, sem presumir CUDA em outras máquinas. Não instalar os extras
`full` de openWakeWord nem trocar o índice de todos os pacotes pelo de Torch.
Os intervalos do arquivo são requisitos candidatos, não lock homologado.
Registre versões efetivamente resolvidas antes da avaliação humana.

## Preparação explícita dos modelos

Baixe uma vez, conscientemente, em diretório privado fora do Git. Este script
acessa Hugging Face/GitHub; só deve ser executado durante a preparação humana.
Pesos públicos de wake word possuem licença própria: verificar condições de
uso antes de produção. Registre revisões e SHA256 dos arquivos baixados.

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from urllib.request import urlretrieve
from huggingface_hub import snapshot_download

root = Path.home() / '.local/share/jarvis-room/models'
for size in ('tiny', 'base'):
    snapshot_download(f'Systran/faster-whisper-{size}',
                      local_dir=str(root / f'whisper-{size}'))
snapshot_download('hexgrad/Kokoro-82M', local_dir=str(root / 'kokoro'),
                  allow_patterns=['config.json', 'kokoro-v1_0.pth',
                                  'voices/pm_santa.pt', 'voices/pm_alex.pt',
                                  'voices/pf_dora.pt'])
wake = root / 'wake'
wake.mkdir(parents=True, exist_ok=True)
for name in ('hey_jarvis_v0.1.onnx', 'melspectrogram.onnx', 'embedding_model.onnx'):
    urlretrieve('https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/'
                + name, wake / name)
print('Modelos preparados explicitamente em', root)
PY
```

Na sessão, não há fallback para nomes remotos: o diretório STT deve conter
`model.bin`, `config.json`, `tokenizer.json` e os demais arquivos do snapshot;
Kokoro exige config, pesos e voz; wake word exige os três ONNX e registro
local de procedência/licenças. O script acima não cria esse registro: revise
as condições e prepare `PROVENANCE.txt` antes de habilitar o detector.
Pacotes ou
assets incompletos resultam em erro/fallback, sem tentativa de download.

## Inicialização real

Push-to-talk/manual (Enter), com saída textual se não houver TTS:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-tiny"
```

Voz bidirecional com detector acústico experimental e Ollama informativo:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-tiny" \
  --tts-model-dir "$HOME/.local/share/jarvis-room/models/kokoro" \
  --voice pm_santa --speed 1.0 --volume 0.7 \
  --wake-model-dir "$HOME/.local/share/jarvis-room/models/wake" \
  --wake-license-file "$HOME/.local/share/jarvis-room/models/wake/PROVENANCE.txt" \
  --llm --llm-model qwen3.5:4b
```

Adicionar `--input-device N --output-device M` com os índices do diagnóstico.
Omitir `--llm` mantém perguntas conhecidas e planos sem inferência. O modelo
Ollama selecionado deve estar previamente disponível e continua sujeito à
política local de memória; o comando não baixa/puxa modelo. O inventário
histórico da consolidação continha `qwen3.5:0.8b`, não `jarvis-dev-lite:latest`.
O modelo preferido agora é `qwen3.5:4b`, que exige instalação local.
Use `--diagnose-ollama` para conferir e selecione o nome exato com `--llm-model`.
O worker conecta exclusivamente a `127.0.0.1:11434`, com configuração temporária
sem MCP, ferramentas, telemetria ou memória persistente. Não herda
`OLLAMA_HOST`, proxies ou a configuração OpenJarvis do terminal. O processo
Ollama externo mantém sua própria configuração de GPU/retenção de memória.

No modo manual, pressione Enter e aguarde `Microfone pronto. Pode falar.`;
esse aviso confirma abertura do stream, após a inicialização do processo.
Fale uma frase
completa e faça uma pausa de 1,2 s. É um botão de início, não gravação enquanto
a tecla está pressionada. No modo acústico, diga **“hey Jarvis”**, faça uma
pausa e aguarde `Microfone pronto. Pode falar.` antes do pedido.
Uma frase dita junto à wake word
pode ser descartada ao fechar o stream do detector. O vocativo **“Jarvis”
isolado** ainda precisa ser homologado/modelado; não há garantia do modelo
público para essa forma ou sotaques brasileiros.

Na janela seguinte, não precisa repetir o vocativo:

- `Jarvis, ligue os monitores.`
- `Desligue os monitores.`
- `Ligue os LEDs.`
- `Desligue os alto-falantes.`
- `Ativar modo apresentação.`
- `Encerrar apresentação.`
- `Ligue a TV Samsung.` (também somente planejamento offline por voz).
- `Quem é você?` ou `Explique como funciona o som.`

Desde a correção S7.1, `liga`/`ligue` e `desliga`/`desligue` são formas
explicitamente equivalentes para ações e alvos cadastrados. Por exemplo,
`Jarvis, liga os monitores`, `Ligue os monitores.`, `Desliga os LEDs.` e
`Liga o sistema de áudio.` geram os respectivos planos offline. Mantêm-se
caixa, acentuação, pontuação simples, vocativo opcional e espaços já permitidos.
O alvo completo precisa ser um alias cadastrado: negações, múltiplas ações,
frases incompletas e alvos desconhecidos continuam bloqueados. A mudança
não amplia o parser autorizado da Samsung nem concede execução física por voz.
Ela corrige uma limitação textual; não corrige erros de transcrição ou
homologa microfone, CUDA, modelo Whisper, wake word ou TTS.

`cancelar`/`pare` fecham a janela; `sair`/`encerrar sessão` encerram a CLI.
Ctrl+C/EOF encerram em qualquer etapa. Durante TTS não há escuta nem barge-in.
Silêncio inicial permite outra tentativa dentro da janela/inatividade;
falha de captura/STT ou timeout fecha a janela e exige nova ativação. O modelo
STT residente é reutilizado até fechar a sessão ou falhar. Sem detector/asset,
usa Enter; se o detector falhar durante execução, também muda para Enter.
Não há flags `--execute`, `--enable-samsung`, token ou auditoria executora.

Limites configuráveis: `--active-seconds` (1–300, padrão 300),
`--inactivity-seconds` (1–300, padrão 30), `--capture-seconds` (1–30),
`--operation-seconds` (1–120), `--wake-seconds` (1–60), `--max-turns` (1–20),
`--cooldown-seconds` (0,3–5), `--silence-threshold` (1–32767),
`--wake-threshold` (0,1–1). Números CLI usam ponto decimal. O prazo de captura
tem tolerância de inicialização de processo de até 5 s; o supervisor mata
PortAudio bloqueado. STT e LLM não utilizam transcrições fora da janela.

STT CUDA, carga isolada, benchmark residente e seleção de LLM estão no
[guia GPU/LLM](voice-gpu-ollama.md). A inicialização do STT tem prazo separado
e antecede a janela ativa. A CLI mantém contexto informativo curto entre
ativações próximas; a próxima ativação descarta o contexto vencido. Comandos,
`limpar contexto`, cancelamento e encerramento não criam memória permanente.

## Testes automatizados offline

```bash
python3.11 projects/jarvis-room/scripts/run_offline_tests.py
git diff --check
```

A regressão inteira da Sala Temática usa somente stdlib, sem instalar extras.
Bloqueia sockets, processos reais e importação de backends de áudio/modelos;
os testes que exercitam esses contratos injetam fakes explicitamente. Testa
WAV PCM sintético, silêncio, impulsos, corte, overflow, stream ausente,
timeout, teclado, múltiplos turnos, estados, eco, wake word falsa, LLM que
responde com comando e os oito comandos Samsung anteriores em preview.
WAV senoidal e transcrição simulada não medem acurácia de reconhecimento.

## Avaliação supervisionada separada

Só começar com operador presente e dispositivos de áudio realmente acessíveis.
Nenhum teste desta seção está no CI e nenhum deve habilitar controle físico.

1. Registrar Windows/WSL/Ubuntu/Python, versões dos pacotes, dispositivo e rota
   selecionados, revisões/hashes dos modelos, RAM livre e volume. Não usar fonte
   monitor/loopback. Começar com fones e volume baixo.
2. Validar Enter com `tiny` em CPU, silêncio, cancelamento, falha de microfone,
   EOF e Ctrl+C durante captura/STT/TTS. Conferir liberação do dispositivo.
3. Preparar WAVs consentidos PCM16 mono 16 kHz (≤ 30 s), fora do repositório,
   com brasileiros de sotaques distintos: os seis pedidos acima, Samsung,
   perguntas informativas, negação, frases incompletas e ruído/terceiros.
   Não versionar gravações pessoais.
4. Comparar tiny/base usando o mesmo corpus e os recursos medidos abaixo;
   repetir pelo menos três vezes e registrar mediana/p95, WER e taxa de
   intenção correta, incluindo trocas perigosas de ligar/desligar. Os workers
   do modo tiny/base medem carga + inferência; o novo modo `--resident-model-dir`
   separa carga, primeira inferência e inferências seguintes.
5. Ouvir `pm_santa`, `pm_alex`, `pf_dora` com nomes, LEDs, monitores, negações,
   números e frases da persona. Registrar inteligibilidade (palavras entendidas),
   naturalidade e preferência de pelo menos dois falantes brasileiros; não
   declarar a voz homologada apenas porque produz um WAV.
6. Medir ativação por “hey Jarvis” e “Jarvis” isolado em múltiplas distâncias,
   silêncio, conversas/TV e gravações (taxa de acerto, falsas ativações/hora e
   latência). Ajustar limiar somente com corpus separado de validação. Para
   “Jarvis” sem qualidade suficiente, manter Enter e treinar/avaliar um modelo
   acústico específico, sem trocar por correspondência textual contínua.
7. Repetir respostas TTS com alto-falantes e microfone na posição final.
   Verificar ausência de captura durante `[RESPONDING]`, intervalo sem escuta,
   filas novas e rejeição de eco tardio. Aumentar cooldown/fones se necessário.
   Áudio de terceiros pode ativar a interface; nunca pode executar dispositivos.
8. Registrar aceite/reprovação de cada critério, configuração final e pendências
   no relatório S7. As proteções físicas não dependem do resultado acústico.

Manifesto local de avaliação (caminhos relativos ao próprio manifesto):

```json
[
  {"wav": "monitores.wav", "expected": "Jarvis, ligue os monitores."},
  {"wav": "leds.wav", "expected": "Desligue os LEDs."}
]
```

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.voice_benchmark \
  --manifest "$HOME/.local/share/jarvis-room/avaliacao/corpus.json" \
  --tiny-dir "$HOME/.local/share/jarvis-room/models/whisper-tiny" \
  --base-dir "$HOME/.local/share/jarvis-room/models/whisper-base"
```

O JSON de resultado contém transcrições e deve permanecer privado. Informa
WER normalizada (sem pontuação/acentos/vocativo), tempo por amostra,
pico RSS do processo em KiB (Linux) e correspondência de alvo/ação/cena. Não
executa planos. Contexto da sessão não entra na avaliação. Até 100 amostras e
manifesto de até 64 KiB. A qualidade de TTS e wake word é registrada pelo
operador, não inferida das métricas do STT.
