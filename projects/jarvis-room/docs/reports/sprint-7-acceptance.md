# Relatório técnico — Sprint 7 — comunicação por voz

Data: 19/10/2026, America/Bahia.
Status: implementação publicada e aprovada offline/local/CI;
homologação acústica humana pendente.
Nenhuma permissão física adicional. Nenhum PR ou merge automático.

Este documento preserva os resultados históricos da S7 e da correção S7.1.
A evolução CUDA/residente/LLM/TTS, o inventário atualizado e as novas evidências
estão no [relatório de consolidação](sprint-7-consolidation.md).
Use os comandos atuais do [guia GPU/LLM](../integrations/voice-gpu-ollama.md);
os exemplos de inicialização abaixo registram a configuração da entrega original.

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

## Sprint 7.1 — correção de comandos naturais em português brasileiro

### Causa e escopo

O operador informou um teste com Faster-Whisper Large-v3 Turbo,
CTranslate2/CUDA FP16 no ambiente Ryzen 7 7800X3D/RTX 4070 12 GB:
idioma `pt`, transcrição `Jarvis, liga os monitores`, tempo de 0,38 s e
intenção bloqueada como `unsupported_command`. São evidências fornecidas
pelo operador, não medições ou homologação reproduzidas nesta correção.

A causa estava na lista de verbos do parser determinístico: a revisão da
Sprint 7 aceitava apenas `ligue` e `desligue`. A normalização preserva
`liga`/`desliga`, por isso uma transcrição semanticamente correta não
encontrava verbo autorizado. Não era necessário criar outro interpretador,
alterar o reconhecimento de fala nem delegar comandos físicos ao LLM.

Na inspeção inicial, a alteração local já continha as duas variantes novas;
ela foi preservada e consolidada com testes, documentação e formatação Ruff.
A única mudança funcional em relação à revisão S7 é a inclusão explícita de
`("liga ", "turn_on")` e `("desliga ", "turn_off")` junto às duas formas
existentes. Uma comparação de AST, removendo somente essas duas entradas,
confirmou equivalência ao código anterior; as demais alterações do parser
são comentário e formatação.

### Arquivos modificados

- `src/jarvis_room/room_intent.py`: quatro formas explícitas, com o mesmo
  parser e a mesma correspondência completa de grupos/aliases e capacidades.
- `tests/test_room_natural_variants.py`: 20 testes novos, reutilizando
  `OfflineVoiceTest`, WAVs, microfone, STT/TTS falsos e relógio virtual existentes.
- `docs/integrations/voice-interaction.md`: formas aceitas e limites textuais.
- `README.md` da Sala Temática: comportamento e resultado da regressão S7.1.
- Este relatório: diagnóstico, exemplos, verificações e pendências da correção.

Os caminhos acima são relativos a `projects/jarvis-room/`. Foram inspecionados
também `room_text.py`, `room_device_registry.py`, `room_responses.py`,
`voice_router.py` e os testes existentes. Suas implementações não precisaram
de alteração. CUDA, Whisper e sintetizador de voz permaneceram intactos.

### Exemplos antes e depois

Comparação executada offline com o parser original da revisão S7 e o parser
atual, usando somente os arquivos locais do catálogo:

| Frase | Antes (S7) | Depois (S7.1) |
| --- | --- | --- |
| `Jarvis, liga os monitores` | `blocked / unsupported_command` | `group_control / turn_on / monitores` |
| `Jarvis, desliga os monitores` | `blocked / unsupported_command` | `group_control / turn_off / monitores` |
| `Jarvis, ligue os monitores.` | `group_control / turn_on / monitores` | Mesmo resultado |

As formas com/sem vocativo, `liga`/`ligue` e `desliga`/`desligue` produzem os
mesmos campos semânticos. O campo `phrase` continua guardando a frase
normalizada, incluindo o verbo recebido; não houve canonicalização adicional.
Grupos `monitores`, `leds` e `audio` e todos os aliases individuais existentes
com capacidade de ligar/desligar foram cobertos. Nenhum alias foi inventado.

### Segurança e integração

A exigência de alvo completo continua bloqueando `não liga`, `não desliga`,
`liga os monitores e desliga os LEDs`, dispositivos desconhecidos, ações
condicionais/agendadas, verbos parciais e frases incompletas. `desliga` não é
interpretado como `liga`; o espaço no prefixo e o alvo completo são exigidos.
Sensores continuam sem capacidade de ligar/desligar.

`respond_to_room_operator()` e `VoiceRouter` processam as novas formas pelo
mesmo caminho S6, sem chamar o LLM. O orquestrador retorna `offline_preview`,
`action_verified=False` e `physical_action_verified=False`; não há estado
físico observado. As respostas dizem que o comando foi reconhecido/planejado
e que nenhum comando físico foi enviado.

As oito frases autorizáveis Samsung S4/S5.11 não foram ampliadas: o parser
Samsung continua rejeitando `liga a TV Samsung`/`desliga a TV Samsung`, embora
o parser da sala possa preparar seus planos offline. Não se criam tokens,
clientes Home Assistant, permissões ou `OperatorTurn` a partir da voz.

### Testes e verificações

Baseline preservada: **714/714**. Resultado S7.1: **734/734**, com **20 novos
testes** e seus subcasos. O runner bloqueia acesso real a hardware, rede,
subprocessos e modelos, como na Sprint 7.

Cobertura adicionada: ligar/desligar com/sem Jarvis; pontuação, caixa,
acentos e espaços; grupos e aliases individuais cadastrados; distinção de
ações; negação; múltiplas ações, condições e horários; alvos desconhecidos;
frases incompletas; prefixos parciais e caracteres proibidos; capacidades de
sensores; preservação do parser Samsung; respostas em preview; VoiceRouter
sem LLM; sessão com transcrições simuladas válidas e inválidas, sem execução.

Comandos executados e aprovados na raiz do repositório:

```bash
python3.11 projects/jarvis-room/scripts/run_offline_tests.py
git diff --check
.venv/bin/ruff check projects/jarvis-room/src/jarvis_room/room_intent.py \
  projects/jarvis-room/tests/test_room_natural_variants.py
```

Esta correção não afirma nova execução remota do CI; a evidência remota da
Sprint 7 original permanece registrada acima. Nenhum PR ou merge foi realizado.

### Limitações e pendências

As variantes são uma lista explícita, não compreensão irrestrita do português.
Infinitivos como `ligar`, sinônimos não cadastrados e nomes fora dos aliases
continuam bloqueados. Não há fuzzy matching nem correspondência parcial.
Erros do STT em verbo, negação ou alvo podem resultar em bloqueio ou em outro
plano reconhecido; esta mudança não avalia ou corrige acurácia acústica.

Não foram chamados microfone, GPU, Ollama, Home Assistant ou dispositivos
físicos na regressão. Não houve inferência real nem homologação acústica
adicional. Avaliações de áudio, desempenho do modelo e melhorias CUDA/TTS
continuam separadas, sob supervisão humana e sem ampliar controle físico.
