# ADR-0002 — Controle Samsung exclusivo de laboratório e operador

Status: implementação, leitura real e acionamentos autorizados registrados;
janela revisada validada por simulação; aceitação consolidada e revisão final pendentes.
Data: 18/10/2026. Complementa a ADR-0001 sem liberar ferramentas ao LLM.

## Contexto e decisão

O operador informou a TV Samsung LH32BETBLGGXZD, a entidade
`media_player.samsung_bet_series_32_lh32betblggxzd` e dois scripts homologados:
`script.jarvis_ligar_samsung` e `script.jarvis_desligar_samsung`.
O endereço confirmado é `http://127.0.0.1:18123`.
Em 18/10/2026, consultas GET reais confirmaram a existência da TV e dos dois
scripts com os identificadores operacionais acima. Essa leitura não verifica
o conteúdo dos scripts nem substitui inspeção ou confirmação física independente.

Criar inventário e cliente próprios, separados do helper virtual e dos planos
da Sprint 2. O cliente read-only da Sprint 3 e `RoomControlGateway` não mudam.
O catálogo original permanece planejado; não associar a Samsung ao placeholder
de segundo display nem confundir monitores lógicos com equipamentos físicos.

## Fronteiras

1. `room_chat_cli` e todos os provedores: nenhuma referência ao controlador Samsung.
2. CLI Samsung sem flags: inventário offline, sem token ou sockets.
3. Leitura: opt-in próprio, token privado e três GETs fixos.
4. Execução: opt-in distinto, TTY, frase exata, permissão de uso único por
   ação com validade de 60 s e auditoria privada antes da tentativa.
5. Transporte: um único POST `script.turn_on`, direcionado ao script da ação;
   desligar a TV também inicia um script via esse serviço, nunca `script.turn_off`.
6. Resultado: aceite HTTP, estado HA e observação física independente separados.

Não há integração da Samsung ao gateway genérico, descoberta automática de
scripts, fallback para scripts renomeados, ferramenta de LLM ou comando livre.
Um GET de script prova presença e estado de execução, não conteúdo, autorização
institucional ou homologação de seus efeitos. `script.state=off` não é TV desligada.

## Destinos e credenciais

Somente o loopback/porta confirmados são aceitos em código e inventário.
HTTP de LAN/WAN e todos os endpoints HTTPS ainda não homologados são recusados.
Não há parâmetro CLI de URL ou opção para desativar validação TLS. Um futuro
destino HTTPS exigirá allowlist revisada e validação de certificado/hostname;
não reutilizar token por redirecionamento. Proxies e redirects estão desabilitados.

Token: arquivo externo Linux/WSL 0400/0600, proprietário atual, regular, sem
links/hardlinks, com tamanho e caracteres limitados. Nunca usar senha de usuário,
token em argumento, variável de CI ou campo do inventário. Token HA pode ter
privilégios amplos: as restrições são deste cliente, não permissões intrínsecas
do token. Credenciais futuras de produção devem permanecer independentes.

## Evidência e falhas

Não converter respostas HA ou fakes em `ToolReceipt` ou confirmação física.
`physical_action_verified` permanece falso, inclusive quando o estado coincide.
O estado pode estar em cache e já coincidir antes do comando; não demonstra
causalidade, atualização do painel ou funcionamento físico.

Se o POST perde a resposta ou retorna conteúdo inválido/erro ambíguo, registrar
`command_delivery=unknown`, `command_sent=null`, sem retry. Falha de leitura ou
auditoria após aceite preserva `command_sent=true` e expõe a falha separadamente.
Não tentar desfazer ou repetir automaticamente uma operação incerta.

GETs limitados aos três IDs; timeout de I/O padrão 5 s (máximo 8 s), JSON até
32 KiB (máximo 64 KiB). Após aceite, observar por prazo monotônico configurável
de 1 a 30 s (padrão 30), com GET imediato e intervalos de 2 s. Cada GET recebe
timeout limitado ao menor valor entre seu limite HTTP e o orçamento restante.
Encerrar assim que o HA informar o alvo dentro do prazo; nunca reenviar o POST.
Resposta tardia não produz resultado `matched`. Timeout de socket e gravação de
auditoria não são prazo absoluto de toda a sessão; uma chamada em curso pode
exceder o orçamento, e sua duração real é registrada. O prazo não inclui POST
ou preflight. Expiração da permissão não cancela um POST já enviado.

O resultado e o evento `observation_finished` registram quantidade de tentativas
GET, tempo monotônico, prazo e resultado. Campos novos são aditivos; registros
anteriores sem essas métricas continuam históricos. `state_observation_timeout`
significa que o estado não foi confirmado dentro do prazo, sem inferir falha
física. Indisponibilidade transitória permite novos GETs dentro do orçamento;
401/403, 404, redirect e JSON inválido interrompem a observação. Cancelamento
preserva o aceite já recebido. Um POST incerto não inicia polling automático.

Auditoria JSONL externa 0600, append e fsync, sem texto livre ou credenciais.
Falta de auditoria anterior à tentativa bloqueia o POST. Eventos não são
assinados nem resistentes a adulteração por um usuário com acesso ao arquivo.

## Limites de confiança e pendências

TTY, opt-in e frase são controles preventivos locais, não autenticação
institucional, RBAC ou defesa contra Python malicioso executado pelo mesmo
usuário. Permissão não pode ser fornecida por texto/modelo ou JSON. Scripts HA
podem ser alterados fora deste repositório: revisar conteúdo antes de cada prova.

Dois acionamentos foram autorizados e observados visualmente pelo operador em
18/10/2026, com evidências no relatório. A nova janela foi validada somente por
simulação, sem repetir esses acionamentos. Aceitação consolidada, revisão técnica
final e PR/CI são condições de encerramento da Sprint 4.
