# Voz residente, RTX 4070 e Ollama local

Guia operacional da consolidação S7. Estado e medições:
[relatório técnico](../reports/sprint-7-consolidation.md).
Arquitetura: [ADR-0006](../adr/0006-resident-voice-workers.md).
Comportamento atual: [vocativo obrigatório e pm_alex S9.1](jarvis-wake-persona.md).
Instalação de áudio/WSLg: [guia de voz](voice-interaction.md).
Todos os comandos partem da raiz `openjarvis`, com o ambiente virtual existente:

```bash
export PYTHONPATH=projects/jarvis-room/src:src
```

## Diagnóstico que não grava nem faz inferência

```bash
.venv/bin/python -m jarvis_room.room_voice_cli --diagnose
.venv/bin/python -m jarvis_room.room_voice_cli --diagnose-gpu
.venv/bin/python -m jarvis_room.room_voice_cli --diagnose-ollama --llm-model qwen3.5:4b
.venv/bin/python -m jarvis_room.room_voice_cli --diagnose-stt \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16
```

STT diagnóstico importa CTranslate2 para consultar capacidades, mas não carrega
pesos. Ollama diagnóstico faz somente GET local de versão, inventário e
processos. GPU diagnóstico consulta memória global via `nvidia-smi`.
Áudio diagnóstico só enumera dispositivos; encontrar `pulse` não comprova
abertura nem qualidade. Para assets preparados, adicione `--tts-model-dir` e
`--wake-model-dir` ao diagnóstico. Ele não inicializa esses modelos.

No ambiente inspecionado: entrada/saída `pulse`, índice 0; não fixe esse índice
em outras máquinas. Não use fontes monitor/loopback. No WSLg, inspecione o
dispositivo Windows e `pactl list short sources`/`pactl list short sinks` antes
de mudar rotas. Esta entrega não altera Windows, permissões ou serviços.

## STT CUDA: somente carregar e liberar

Este comando é ativo: aloca memória/carrega o modelo, mas não abre microfone,
transcreve, sintetiza ou consulta LLM. Execute separadamente dos diagnósticos:

```bash
.venv/bin/python -m jarvis_room.room_voice_cli --stt-check --metrics \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16 --stt-gpu-index 0
```

O resultado separa `initialization_seconds` (construção/carregamento do backend)
de `worker_initialization_seconds` (spawn/imports e inicialização). RAM é pico
RSS do worker em KiB; snapshots VRAM são de toda a GPU, não só deste processo.
Sem CUDA, use modelo adequado ao equipamento com `--stt-device cpu
--stt-compute-type int8`; não há presunção de NVIDIA nem fallback silencioso.

As bibliotecas instaladas em `.venv` são descobertas pelo supervisor e passadas
ao ambiente do worker antes de iniciar CUDA. Não exporte `LD_LIBRARY_PATH` em
cada sessão. Se faltar biblioteca, registre o diagnóstico e prepare o ambiente
explicitamente; não há instalação automática.
[Faster-Whisper](https://github.com/SYSTRAN/faster-whisper) documenta CUDA 12,
cuBLAS e cuDNN 9 para versões atuais do CTranslate2; capacidades são consultadas
no runtime conforme [CTranslate2](https://opennmt.net/CTranslate2/hardware_support.html).

## Homologação STT e comandos sem LLM/TTS

Este comando abre microfone depois de Enter, mantendo o STT carregado:

```bash
.venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16 --stt-beam-size 1 \
  --tts-backend none --metrics
```

Espere `Microfone pronto. Comece com Jarvis.`. Diga `Jarvis, liga os monitores`,
depois `Jarvis, desliga os LEDs` e `Jarvis, ativar modo apresentação`.
São planos offline; nenhum equipamento deve mudar. Cada fala exige Jarvis,
inclusive na janela ativa.
Teste também negação, alvo desconhecido, comando composto, silêncio e Ctrl+C.
Silêncio tenta outra captura dentro dos limites; ao voltar ao prompt, Enter
abre outra janela e reutiliza o mesmo modelo residente.

Parâmetros opcionais: `--stt-room-terms` fornece vocabulário linguístico da sala;
`--stt-vad` habilita VAD do Faster-Whisper; `--stt-beam-size` aceita 1–5.
Idioma fixo `pt`, `condition_on_previous_text=False`. Compare as opções com
corpus consentido antes de escolher: nenhuma delas corrige automaticamente
`liga` para `desliga` ou concede autorização. Não há evidência nova de WER.

Limites CLI: janela 1–300 s (padrão 300), inatividade 1–120 s (padrão 30),
captura 1–30 s (padrão 15), operação 1–120 s (padrão 60), inicialização
maior que zero até 300 s (padrão 120), até 20 tentativas por ativação.
O limite efetivo é o menor prazo aplicável. Uma resposta TTS já iniciada pode
terminar após a janela, respeitando seu timeout; nenhuma nova captura é aberta.

## Ollama: inventário e conversa supervisionada

Na inspeção histórica da consolidação foi encontrado **somente `qwen3.5:0.8b`**
no endpoint fixo
`http://127.0.0.1:11434`. A presença no inventário não mede qualidade de resposta.
`jarvis-dev-lite:latest` não estava instalado. Não houve `ollama pull` nem
seleção automática substituta naquela inspeção. A sessão agora prefere
`qwen3.5:4b` quando `--llm` é habilitado, conforme solicitação do operador.
O modelo precisa estar instalado; se estiver ausente, a CLI recusa iniciar a
conversa e não substitui pelo 0.8B. Downloads continuam fora da sessão e exigem
autorização explícita. Repita o diagnóstico para conferir o inventário atual.
[Inventário Ollama](https://docs.ollama.com/api/tags).
[Tag Qwen 3.5 4B](https://ollama.com/library/qwen3.5:4b).

Após autorização explícita do operador, `ollama pull qwen3.5:4b` concluiu com
verificação SHA256. O inventário local agora contém o 4B e o 0.8B preservado.
4B: 3.324.173.934 bytes, GGUF Q4_K_M, metadados 4.2B, digest
`d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04`.
O diagnóstico confirmou `llm_selected=qwen3.5:4b` e a política existente de
4 GiB aceitou o pacote. Isso não mede VRAM nem valida respostas reais.
Contexto da sessão permanece 4096 tokens e saída 192 por padrão; não adotamos
automaticamente o contexto máximo anunciado pelo modelo. Não houve inferência.

Primeiro teste apenas texto, sem STT, microfone ou TTS:

```bash
.venv/bin/python -m jarvis_room.room_voice_cli --text-chat \
  --llm --llm-model qwen3.5:4b \
  --llm-max-tokens 192 --llm-context-tokens 4096 --operation-seconds 60
```

Teste `Jarvis, como você está?`, `O que você consegue fazer?`,
`Me explique o funcionamento da sala`, `Qual é a função do Home Assistant?`,
`Pode explicar isso de outra forma?` e `E como isso funciona?`.
`Jarvis, limpar contexto` apaga o histórico por voz; `Jarvis, sair`,
EOF e Ctrl+C encerram (no chat textual, os comandos continuam sem vocativo).
Converse em seguida por voz, ainda sem TTS:

```bash
.venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16 \
  --llm --llm-model qwen3.5:4b --tts-backend none --metrics
```

O agente OpenJarvis existente tem `tools=[]`, `context=False`; destino local,
configuração temporária, sem MCP/telemetria. Comandos conhecidos continuam
no parser determinístico, sem LLM. Comandos desconhecidos não são executados.
Uma resposta gerada, mesmo contendo `ligue os monitores`, nunca vira comando.
Afirmações conhecidas de execução física são suprimidas; fatos informativos
continuam sujeitos a erros de modelo e devem ser avaliados pelo operador.

Histórico de até quatro pares/1800 caracteres, prompt 3800, resposta armazenada
700; tokens saída 32–512, contexto 2048–8192. Memória volátil, sem arquivos de
conversa. Contexto vencido por inatividade é descartado na próxima ativação;
cancelar/fechar também limpa. Modelos maiores que 4 GiB de pesos são recusados
pela configuração padrão; tamanho em disco não equivale ao uso de VRAM.

A política existente exige ao menos 2 GiB de RAM disponível e 2 GiB de swap
livre. Não reserva memória. Consulte GPU antes/durante/depois e registre OOM ou
evicção do Ollama. Não inicie várias sessões pesadas para contornar limites.
Timeout LLM fecha o cliente e exige reiniciar a sessão antes de nova inferência;
não implica interromper a geração já iniciada no serviço externo. Não alteramos
parâmetros globais nem retenção do Ollama.

## TTS brasileiro opcional: preparação e estado atual

Na auditoria histórica S7, Kokoro/Torch e pesos/vozes **não estavam instalados**.
Na conferência S9.1, Kokoro/Torch CPU e assets pm_alex/pm_santa estão presentes;
a nova voz padrão pm_alex/0,92/0,5 ainda requer audição.
`espeak-ng` está presente. O operador relata sucesso de síntese/reprodução S9
no Lief, posterior à auditoria original. Isso não homologa a nova voz S9.1.
Para outras máquinas, consulte o [guia de instalação](voice-interaction.md).
Não executar os comandos de download dessa preparação durante testes offline.

Os candidatos brasileiros são `pm_santa` (masculina),
`pm_alex` (padrão masculino desde S9.1) e `pf_dora` (feminina), `lang_code='p'`/espeak `pt-br`.
A lista do autor confirma idioma/vozes, mas não garante naturalidade:
[Kokoro VOICES](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md).
[Modelo Kokoro-82M: Apache 2.0](https://huggingface.co/hexgrad/Kokoro-82M).
Piper é alternativa futura, sem backend adicionado nesta entrega;
[implementação atual](https://github.com/OHF-Voice/piper1-gpl) usa GPL-3.0 e
cada voz exigiria verificar sua própria licença, idioma e arquivos.

Com assets locais preparados, execute a sessão completa (manual por Enter):

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16 \
  --llm --llm-model qwen3.5:4b \
  --tts-backend kokoro \
  --tts-model-dir "$HOME/.local/share/jarvis-room/models/kokoro" \
  --voice pm_alex --speed 0.92 --volume 0.5
```

TTS usa CPU, inicialização preguiçosa e modelo residente;
reprodução roda separadamente. Saída validada PCM16 mono 24 kHz/até 30 s.
Velocidade 0,5–2, volume 0–1. Falha de dependência, síntese, formato ou saída
preserva texto. Não há captura durante TTS; cooldown padrão 0,8 s, configurável
0,3–5 s. Não há interrupção por voz; Ctrl+C funciona.

Avaliar em etapa posterior: naturalidade/inteligibilidade, J.A.R.V.I.S., LEDs,
Samsung, Hikvision, WLED, números e negações; ritmo e volume; carga inicial,
sínteses seguintes, latência total, eco e conversa com vários turnos. Começar
com fones, depois alto-falantes na posição real. Comparar as três vozes antes
da escolha final. Não declarar semelhança à voz dos filmes sem audição.

## Wake word: fallback pronto, modelo isolado pendente

Não há pacote openWakeWord nem ONNX local nesta inspeção. Enter funciona.
O modelo público é **“hey Jarvis”**, não “Jarvis” isolado. O código mantém
limiar/RMS/frames consecutivos, CPU e até seis ativações por minuto; não mede
taxa real de falsos positivos. Exige três ONNX locais e um arquivo de registro
de procedência/licença com `--wake-license-file`. Esse registro não substitui
uma revisão humana da licença nem valida a origem criptograficamente.

[openWakeWord](https://github.com/dscripka/openWakeWord) declara código
Apache 2.0 e modelos pré-treinados CC BY-NC-SA 4.0. Antes de usar, verificar
também as condições dos extratores e do modelo escolhido. Não há download
normal da sessão. Após essa preparação, adicione:

```bash
--wake-model-dir "$HOME/.local/share/jarvis-room/models/wake" \
--wake-model hey_jarvis_v0.1.onnx \
--wake-license-file "$HOME/.local/share/jarvis-room/models/wake/PROVENANCE.txt"
```

Arquivos ausentes/licença não registrada/falha em runtime ativam Enter.
Após despertar, aguarde o microfone abrir: áudio dito junto ao vocativo pode
ser descartado ao trocar streams. Teste silêncio, ruído, sotaques brasileiros,
TV e terceiros; meça falsas ativações/hora e acertos. “Jarvis” isolado requer
modelo e avaliação próprios. Detector não autentica e não permite execução.

## Avaliação com WAVs e observabilidade

Prepare manifesto privado com até 100 WAVs consentidos PCM16 mono 16 kHz,
até 30 s cada. Exemplo e avaliação antiga tiny/base no guia de voz. Para medir
o residente, sem microfone:

```bash
.venv/bin/python -m jarvis_room.voice_benchmark \
  --manifest "$HOME/.local/share/jarvis-room/avaliacao/corpus.json" \
  --resident-model-dir "$HOME/.local/share/jarvis-room/models/whisper-large-v3-turbo" \
  --stt-device cuda --stt-compute-type float16 --stt-beam-size 1
```

Separa inicialização, primeira transcrição e seguintes, request/inferência,
WER e pico RSS. O JSON deliberado do benchmark contém transcrições: mantenha
privado. `--metrics` da sessão oficial fornece somente saúde/tempos/códigos,
sem texto ou áudio. O terminal da conversa naturalmente exibe suas respostas;
não redirecione a sessão para arquivos pessoais inadvertidamente.

```bash
python3.11 projects/jarvis-room/scripts/run_offline_tests.py
git diff --check
```

Esses são testes automatizados offline, com fakes/mocks. Não executam nenhum
dos testes humanos acima nem usam GPU, modelos reais, rede ou dispositivos.
