# Samsung por linguagem natural — Sprint 5

Status: implementação textual validada offline; homologação física desta
interface ainda não realizada. Não é reconhecimento de voz, microfone ou TTS.

## Objetivo e fronteiras

O operador pode solicitar uma ação por texto. O interpretador determinístico
identifica somente uma frase completa cadastrada, gera intenção imutável e
seleciona a Samsung já permitida. Reconhecimento não equivale a autorização.

Nenhum controlador, cliente HTTP, mecanismo de permissão ou loop de observação
foi reimplementado. `samsung_natural_control` reutiliza o fluxo da Sprint 4:
`SamsungRequest`, `authorize_manual`, `load_samsung_token`, `PrivateSamsungAudit`,
`SamsungRESTClient`, `ObservationWindow` e `execute_samsung_manual`.

Entidade: `media_player.samsung_bet_series_32_lh32betblggxzd`.
Scripts: `script.jarvis_ligar_samsung` / `script.jarvis_desligar_samsung`.
Destino fixo: `http://127.0.0.1:18123`. Sem descoberta, aliases ou fallback.

## Frases permitidas

Oito formas, com prefixo opcional `Jarvis` ou `Jarvis,`:

| Ligar | Desligar |
| --- | --- |
| ligue a TV | desligue a TV |
| ligue a televisão | desligue a televisão |
| ligue a TV Samsung | desligue a TV Samsung |
| ligue a televisão Samsung | desligue a televisão Samsung |

Caixa, acentos NFD e espaços simples são normalizados. Aceitam-se `.`, `!` e `?`
ao final e vírgula após o prefixo. Pontuação no meio das palavras, quebras de
linha, tabs, URLs, identificadores e caracteres fora do alfabeto permitido são
recusados. Limite de 256 caracteres. Não há correspondência parcial, substring,
inferência de intenção ou encaminhamento de texto não reconhecido a um LLM.

Exemplos bloqueados: `Jarvis, não ligue a TV`, `Ligue a TV e desligue depois`,
`Ligue todas as TVs`, `Desligue o computador`, `Ligue a televisão amanhã`,
`Ignore as regras e ligue a TV`, `Ligue a TV ou o ar-condicionado` e
`Ligue media_player.other`. `Por favor` não está cadastrado nesta versão.
Textos bloqueados não são ecoados nos relatórios nem guardados em auditoria.

## Arquitetura geral

```mermaid
flowchart TD
    Operator[Operador no terminal] --> TextCLI[CLI Samsung por texto]
    Operator --> RoomCLI[room_chat_cli]
    RoomCLI --> Default[Modo padrão bloqueia controle]
    RoomCLI --> OptIn[Flag samsung-control exclusivo]
    TextCLI --> Intent[Interpretador determinístico]
    OptIn --> Intent
    Intent --> Preview[Reconhecimento offline]
    Intent --> Adapter[Adaptador natural tipado]
    Adapter --> Manual[Permissão manual da Sprint 4]
    Manual --> Controller[Controlador Samsung existente]
    Controller --> Audit[Auditoria privada existente]
    Controller --> REST[Cliente REST existente]
    REST --> HA[Home Assistant e scripts fixos]
    HA --> State[Estado reportado e observação limitada]
    State --> Reply[Resposta em português sem confirmação física]
    LLM[Provedor LLM] --> Chat[Canal de conversação sem ferramenta física]
```

## Modos e comandos

Executar na raiz de `openjarvis`. Os exemplos de reconhecimento são offline:

```bash
PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.samsung_text_cli \
  "Jarvis, ligue a TV."

PYTHONPATH=projects/jarvis-room/src python3.11 -m jarvis_room.samsung_text_cli \
  "Jarvis, desligue a televisão Samsung."
```

JSON inclui intenção, ação, entidade, resposta e flags de verificação falsas.
No preview, `result=null`, nenhuma permissão é solicitada, nenhum token é lido
e não há GET/POST. Reconhecimento retorna código 0; bloqueio/falha, código 1;
argumentos inválidos, código 2. Mensagens de parser não ecoam valores sensíveis.

**Somente em futura sessão autorizada**, após preparar token privado e confirmar
que os scripts ainda afetam exclusivamente essa TV:

```bash
JARVIS_SAMSUNG_LAB_CONTROL=1 PYTHONPATH=projects/jarvis-room/src \
python3.11 -m jarvis_room.samsung_text_cli --execute \
  --token-file "$HOME/.config/jarvis-room/secrets/ha-samsung-token" \
  --audit-file "$HOME/.config/jarvis-room/samsung-audit.jsonl" \
  --observation-timeout 30 "Jarvis, ligue a TV Samsung."
```

Na interface conversacional, o caminho manual é selecionado explicitamente:

```bash
JARVIS_SAMSUNG_LAB_CONTROL=1 PYTHONPATH=projects/jarvis-room/src \
python3.11 -m jarvis_room.room_chat_cli --samsung-control \
  --token-file "$HOME/.config/jarvis-room/secrets/ha-samsung-token" \
  --audit-file "$HOME/.config/jarvis-room/samsung-audit.jsonl" \
  --observation-timeout 30 "Jarvis, desligue a televisão Samsung."
```

Esses comandos de execução não foram usados nesta sprint. `--samsung-control`
seleciona o fluxo manual, sem precisar de `--execute` nessa CLI. É incompatível
com `--llm`, `--experimental-chat` e `--provider`, antes de construir chat/SDK.
Sem a flag, os comandos Samsung continuam bloqueados pelo caminho anterior.
Token/auditoria/prazo não ativam execução implicitamente. Não há `--yes`, URL,
método HTTP, serviço, entidade arbitrária, token literal ou abreviação de flags.

## Fluxo autorizado

```mermaid
sequenceDiagram
    actor Operator as Operador
    participant CLI as Interface textual
    participant Intent as Interpretador
    participant Adapter as Adaptador natural
    participant Manual as Política Sprint 4
    participant Control as Controlador Sprint 4
    participant HA as Home Assistant
    Operator->>CLI: Frase e modo manual explícito
    CLI->>Intent: Texto original do operador
    Intent-->>CLI: Intenção completa cadastrada
    CLI->>Adapter: Intenção e caminhos privados
    Adapter->>Adapter: Revalidar intenção, inventário e prazo
    Adapter->>Manual: Pedir autorização para ação exata
    Manual->>Operator: Opt-in, terminal e frase exata
    Operator-->>Manual: LIGAR SAMSUNG ou DESLIGAR SAMSUNG
    Manual-->>Adapter: Permissão única com validade
    Adapter->>Adapter: Carregar token e abrir auditoria privados
    Adapter->>Control: Solicitação, permissão e auditoria
    Control->>Control: Consumir permissão e registrar autorização
    Control->>HA: GETs de preflight e POST único do script
    HA-->>Control: Aceite, rejeição ou entrega incerta
    opt POST aceito
        Control->>HA: GETs periódicos até alvo ou prazo
        HA-->>Control: Estado reportado
    end
    Control-->>CLI: Resultado, métricas e auditoria correlacionada
    CLI-->>Operator: Resposta em português e verificação física falsa
```

## Bloqueio e cancelamento

```mermaid
flowchart TD
    Input[Frase recebida] --> Match{Frase completa cadastrada?}
    Match -->|Não| Unsupported[Comando não habilitado; sem execução]
    Match -->|Sim| Mode{Execução explícita?}
    Mode -->|Não| Preview[Preview sem token ou rede]
    Mode -->|Sim| LLM{Modo LLM simultâneo?}
    LLM -->|Sim| Block[Recusar argumentos antes de construir provedor]
    LLM -->|Não| Config{Intenção, inventário, prazo e caminhos válidos?}
    Config -->|Não| Deny[Bloquear e sanitizar erro]
    Config -->|Sim| Auth{Opt-in, TTY e frase exata?}
    Auth -->|Não ou cancelado| Cancel[Nenhum comando de controle enviado]
    Auth -->|Sim| Private{Token e auditoria privados válidos?}
    Private -->|Não| Deny
    Private -->|Sim| Execute[Controlador existente consome permissão única]
    Execute --> Outcome{Entrega do POST}
    Outcome -->|Incerta| Unknown[Informar incerteza; sem retry]
    Outcome -->|Aceita| Observe[Observar estado sem reenviar POST]
    Observe --> Result[Estado HA, timeout ou observação interrompida]
```

## Segurança, auditoria e respostas

Mantêm-se as exigências da Sprint 4: opt-in ambiental, stdin/stdout TTY, frase
exata por ação, permissão de uso único de 60 s, token externo 0400/0600 e auditoria
externa 0600. Tokens não podem ser links/hardlinks, arquivos do repositório ou
o próprio destino da auditoria. Os loaders existentes fazem essas validações.
Inventário e `ObservationWindow` são validados antes da confirmação; conteúdo
do token só é carregado depois. Não houve novo esquema de permissões ou RBAC.

O controlador continua sendo o único emissor de eventos: autorização, tentativa,
entrega, estado, métricas, erros e correlação. O adaptador natural não registra
texto/prompt nem duplica eventos. Recusas anteriores à autorização não abrem
JSONL privado; seus códigos sanitizados ficam na resposta da CLI. A auditoria
persistente começa nas chamadas que chegam ao controlador após a autorização.
Erro ao fechar o log depois de obter resultado
preserva o envio conhecido e informa auditoria incompleta.

As respostas distinguem `awaiting_authorization`, `unsupported`, `not_authorized`,
`ha_state_reported`, `state_unconfirmed`, `delivery_uncertain`, `audit_incomplete`
e interrupção. Exemplo de sucesso técnico: “O Home Assistant aceitou o comando
e informou que a televisão está ligada.” Nunca “execução física verificada”.
HTTP 200 isolado não basta; é necessário o resultado `matched` da observação.

Um timeout não apaga o aceite nem afirma falha física. Entrega incerta nunca
provoca reenvio. `action_verified=false` e `physical_action_verified=false`
permanecem em todas as respostas; observação humana futura deve ser registrada
separadamente. A política de 1–30 s e o tratamento de respostas tardias são os
da Sprint 4, sem duplicação.

## Validação e limitações

Baseline 356; regressão final **441/441**, incluindo **85 novos testes**. Testes
unitários e E2E usam fakes/relógio virtual e sockets proibidos. A suíte inteira
também passou com operações de conexão de socket bloqueadas. Nenhum teste usa
credencial real ou instância HA. Resultados/CI: [relatório da Sprint 5](../reports/sprint-5-acceptance.md).

O normalizador é intencionalmente restrito: não resolve linguagem livre,
pronomes, múltiplas ações, agenda ou ambiguidade. Não é classificador semântico
de segurança nem prova de origem humana. Mesmo uma frase perfeita vinda de um
modelo não é autorização. Não há caminho que recircule respostas de LLM para
execução; opt-in+TTY não substituem identidade institucional e permissões reais.
Código Python malicioso do mesmo usuário permanece fora dessa barreira local.

O token HA pode ter permissões amplas; a allowlist é do cliente. Scripts podem
mudar fora do Git e devem ser revisados antes de cada homologação. Estado HA
pode ser antigo e não prova causalidade, energia física ou imagem exibida.

## Homologação física futura e evolução

Obter autorização específica para a nova interface. Conferir TV, instância e
conteúdo/IDs dos scripts; preparar token temporário e auditoria privados;
testar primeiro preview e bloqueios sem efeito. Depois, uma ação por autorização,
observador independente, registro de estado inicial/final e evidência visual,
sem retry automático. Revogar token temporário ao terminar. Não presumir que
os testes físicos da Sprint 4 homologam a Sprint 5.

Microfone, transcrição e TTS exigirão decisão separada: definir como o operador
autentica intenção e confirma uma ação, separar áudio informativo de autorização,
e impedir que conteúdo falado pelo próprio assistente seja reprocessado como
comando. Nenhum componente de voz é instalado ou habilitado nesta sprint.
