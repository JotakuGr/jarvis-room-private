# Relatório técnico — Sprint 7 — comunicação por voz

Data: 19/10/2026, America/Bahia.
Status: implementação publicada e aprovada offline/local/CI;
homologação acústica humana pendente.
Nenhuma permissão física adicional. Nenhum PR ou merge automático.

## Base e entrega incremental

- Repositório: `JotakuGr/jarvis-room-private`.
- Branch: `feature/sprint7-voice-interaction`, criada de `origin/main` após fetch.
- Base/main confirmada: `9ee93e94e10d96f83bf6dfb62ffef52a53722344`, merge do
  [PR #15](https://github.com/JotakuGr/jarvis-room-private/pull/15).
- Árvore inicial limpa; a branch anterior não tinha alterações e foi preservada.
- `de891a36`: sessão, diagnóstico, captura, STT/TTS/wake locais e roteamento.
- `06930c86`: regressão offline bloqueada e avaliador tiny/base.
- `e00f2cc8`: isolamento de configuração OpenJarvis/Ollama e prontidão de áudio.
- A documentação/CI e a consolidação de evidências têm commits próprios,
  consultáveis com `git log main..feature/sprint7-voice-interaction --oneline`.

## Ambiente e diagnóstico efetivamente executado

Ubuntu **24.04.5 LTS**, WSL2 kernel `6.18.54.1-microsoft-standard-WSL2`,
Python **3.11.17**, cerca de 15,2 GiB de RAM total e 12,9 GiB disponível na
inspeção (valores momentâneos, não reserva). Não foi presumido CUDA/GTX 750.

`room_voice_cli --diagnose` executado com Python 3.11 e com `.venv/bin/python`:

| Inspeção | Resultado observado |
| --- | --- |
| Diretório WSLg e socket `/mnt/wslg/PulseServer` | Presentes |
| Acesso ao socket de áudio | Leitura/escrita permitidas ao processo |
| `PULSE_SERVER` | Configurada; valor não precisa ser exposto |
| `/dev/snd` | Ausente; isso não exclui áudio via WSLg |
| PortAudio/Pulse/ALSA no `ldconfig -p` | Nenhuma entrada correspondente encontrada |
| sounddevice/soundfile/Faster-Whisper/CTranslate2/Kokoro/openWakeWord/ONNX Runtime | Não instalados nos intérpretes inspecionados |
| NumPy | Presente em `.venv`, ausente no Python usado inicialmente |
| pactl/arecord/aplay/espeak-ng | Ausentes do PATH |
| Dispositivos de entrada/saída | Não enumerados porque sounddevice não está instalado |
| Captura, reprodução ou mudanças de sistema | Nenhuma |

Não se conclui que o computador não possui microfone/alto-falantes. O ambiente
Python atual ainda não pode acessá-los. Não foram instalados pacotes nativos,
alteradas permissões/rotas ou baixados modelos automaticamente.

## Implementação e fronteiras

Contratos e limites em `voice_contract.py`; captura PCM/WAV e reprodução em
`voice_audio.py`; processos supervisionados em `voice_backends.py`; backends
OpenJarvis reutilizados em `voice_worker.py`; roteamento em `voice_router.py`;
máquina de estados em `voice_session.py`; entrada em `room_voice_cli.py`.
`voice_benchmark.py` mede WAVs locais de avaliação humana, separadamente do CI.

Uma ativação abre janela absoluta de 45 s/até oito turnos. Captura até 15 s,
silêncio inicial 4 s/final 1,2 s, timeout de operações até 60 s. Cancelamento,
resultados tardios, modelos ausentes e hardware bloqueado têm caminhos limitados.
Processos são encerrados e aguardados, inclusive em Ctrl+C. O aviso de microfone
pronto só é emitido após a abertura do stream, sem confundir carga com escuta.

STT: backend Faster-Whisper existente, CPU/int8 com fallback de compatibilidade
existente, idioma `pt`, modelo local completo obrigatório. TTS: backend Kokoro
existente em CPU, pipeline brasileiro e voz local explícita, sem default inglês.
Wake: openWakeWord 0.6.0, três ONNX locais, score/energia e frames consecutivos;
não usa busca textual sobre ASR contínuo.

O candidato público de ativação é **“hey Jarvis”**. “Jarvis” isolado em
português brasileiro ainda não tem comprovação de qualidade; a interface aceita
um ONNX acústico específico via `--wake-model`, sem presumir que esse modelo
já existe. Fallback manual permanece disponível.

Todo controle por voz vai a `respond_to_room_operator` → intenção/catálogo/
grupos/cenas/orquestrador/respostas S6 em preview. Isso inclui os oito comandos
Samsung S5.11, mesmo com autorização habilitada em outro terminal. Nenhum
`OperatorTurn`, cliente HA ou sessão executora é construído por voz.

Ollama informativo usa o adaptador existente e sua política de recursos. O
worker tem configuração temporária própria, destino `127.0.0.1:11434`, sem
proxies, MCP, ferramentas ou telemetria persistente. Contexto de até quatro
pares/1800 caracteres, prompt até 3800 e resposta armazenada até 700; apagado
ao fechar a janela. O agente permanece `simple`, `tools=[]`, `context=False`.
Resposta do modelo só é exibida/falada, nunca analisada como novo comando.

Half-duplex: streams e filas de entrada terminam antes do TTS; cooldown padrão
0,8 s e stream novo em seguida. Proteção suplementar descarta frases contidas
nas duas respostas faladas recentes. Não há cancelamento por voz durante TTS;
Ctrl+C continua disponível. Wake word não autentica locutor e não impede replay
de terceiros. A segurança física vem da ausência de qualquer rota executora.

## Verificações locais

Baseline executada antes de implementar: **597/597**, 1,892 s.
Regressão final: **714/714**, sendo **597 preservados + 117 novos**.
O tempo local observado foi aproximadamente 2,4 s, sem medições acústicas.

```bash
python3.11 projects/jarvis-room/scripts/run_offline_tests.py
git diff --check
.venv/bin/ruff check projects/jarvis-room/src/jarvis_room/voice_*.py \
  projects/jarvis-room/src/jarvis_room/room_voice_cli.py \
  projects/jarvis-room/tests/voice_fakes.py \
  projects/jarvis-room/tests/test_voice_*.py \
  projects/jarvis-room/scripts/run_offline_tests.py
```

Todos aprovados. Help das duas CLIs e diagnóstico passivo executados.
Os 597 testes pertencem à Sala Temática; não se alega execução da suíte inteira
upstream do OpenJarvis com integrações externas.

A suíte bloqueia sockets, subprocessos reais e importação de modelos/backends
de hardware; só aceita seus substitutos explícitos. Abrange WAV sintético,
formato inválido/cortado, silêncio, impulsos separados, overflow, dispositivo
ausente, reprodução interrompida, relógio virtual, deadlines, resultado tardio,
Ctrl+C/EOF, wake/false wake, vários turnos, buffers descartados, eco de comandos,
LLM que devolve comandos, memória limitada e comandos individuais/coletivos/cenas.

O teste de interrupção encontrou e corrigiu limpeza de processo na inicialização
do prazo. Não foram feitos acessos reais a Home Assistant, comandos físicos,
inferências, downloads, gravações ou reprodução durante testes automatizados.
Fixtures senoidais e backends falsos comprovam contratos, não acurácia do Whisper,
qualidade perceptiva do Kokoro ou desempenho real do detector.

## CI e publicação

Workflow `JARVIS Room offline unittest` atualizado para a branch S7, com Python
3.11, sem instalar extras e bloqueando acesso real a áudio/rede/modelos. Mudanças
em `src/openjarvis/speech/**` também disparam essa regressão. Checkout de duas
revisões permite `git diff --check HEAD^ HEAD` em clone raso.

Primeiro push concluído. [CI aprovado, execução 39334983464](https://github.com/JotakuGr/jarvis-room-private/actions/runs/39334983464)
na revisão `6511fa01e0fb00d74100740be3eaf4e132842555`. Job `unittest-offline`
aprovado, incluindo **714 testes em 2,215 s** e `git diff --check HEAD^ HEAD`,
conforme log remoto consultado. Encerramento em 19/10/2026 às 19:26:52
(America/Bahia; 22:26:52 UTC). O commit posterior consolida somente este
relatório e também é enviado para nova execução do mesmo workflow; seu SHA e
link final são informados na entrega. Nenhum PR ou merge foi criado.

## Critérios de aceite e pendências

| Critério | Resultado disponível | Pendência humana |
| --- | --- | --- |
| 1. Captura quando há áudio | Implementada; WAV e falhas com fakes aprovados | Instalar dependências e validar microfone real |
| 2. Português com qualidade avaliada | CPU/int8/pt testados por contrato; avaliador tiny/base pronto | WER, intenção, memória e latência em WAVs brasileiros reais |
| 3. Detectar Jarvis e fallback | Detector acústico ONNX e Enter testados | “Jarvis” isolado/sotaques; modelo público é “hey Jarvis” |
| 4. Sessão conversacional | Estados, turnos, janela, cancelamento e memória aprovados offline | Fluidez com hardware e Ollama reais |
| 5. Individuais, grupos e cenas | Exemplos exigidos e Samsung reconhecidos em planejamento | Nenhuma execução física nesta sprint |
| 6. Resposta falada em português | Interface Kokoro brasileira e fallback testados | Instalação, audição e seleção final de naturalidade |
| 7. Não reutilizar voz própria | Half-duplex/buffers/cooldown/eco aprovados com fakes | Eco e reverberação na sala real |
| 8. Sem acionamento por transcrição | Rota exclusivamente offline; LLM não chama parser | Preservar essa fronteira na homologação |
| 9. Preservar controles/testes | 597 anteriores aprovados; nenhuma alteração nas permissões físicas | Nenhuma |
| 10. CI e relatório | Relatório presente; CI aprovado com 714 testes e whitespace | Nenhuma pendência de CI nesta revisão |

Não declarar homologação integral nem conclusão dos critérios acústicos sem
essas evidências humanas. Roteiro e limiares de avaliação em
[instalação e homologação](../integrations/voice-interaction.md); decisões em
[ADR-0005](../adr/0005-local-voice-session.md).

## Comandos de inicialização

Disponível agora, sem modelos nem captura:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli --diagnose
```

Após a instalação e preparação explícita dos assets locais:

```bash
PYTHONPATH=projects/jarvis-room/src:src .venv/bin/python -m jarvis_room.room_voice_cli \
  --stt-model-dir "$HOME/.local/share/jarvis-room/models/whisper-tiny" \
  --tts-model-dir "$HOME/.local/share/jarvis-room/models/kokoro" \
  --voice pm_santa --speed 1.0 --volume 0.7 \
  --wake-model-dir "$HOME/.local/share/jarvis-room/models/wake" \
  --llm
```

Enter é usado automaticamente quando não há detector. Omitir flags opcionais
mantém o fallback manual/textual. `sair`, EOF e Ctrl+C encerram a sessão.
