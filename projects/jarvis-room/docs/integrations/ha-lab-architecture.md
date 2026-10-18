# Home Assistant LAB — fronteiras da Sprint 3

## Fronteira informativa: GET da instância de laboratório

O manifesto permite somente `http://127.0.0.1:18123`, bridge, sem privilégios,
sem dispositivos reais e com cliente desabilitado por padrão.
O Compose publica exclusivamente `127.0.0.1:18123:8123` e utiliza volume nomeado.
Não montar configurações de produção, dispositivos USB, D-Bus ou credenciais.

`ha_lab_cli` → manifesto e vínculo virtual → opt-in e token privado → cliente
GET → interpretação de estado sanitizado → relatório informativo.

Sem `--read-lab`, há apenas `read_disabled`, sem token nem I/O de rede.
Com `--read-lab`, o operador também precisa definir `JARVIS_HA_LAB_READ=1`.
O token é obtido por `getpass` em terminal com entrada oculta ou por
`--token-file` em arquivo regular fora do repositório, de propriedade do usuário,
com permissões 0400/0600. Não usar token na linha de comando, histórico, CI,
relatórios ou variáveis ambientais de credenciais.

Há somente `GET /api/` e `GET /api/states/<helper-allowlisted>`.
Não existem POST, chamadas de serviço, atualização de estado ou helpers de
método HTTP genérico. Redirecionamentos são recusados, proxies são desabilitados,
há timeout limitado e leitura de JSON limitada a bytes. Não há retries infinitos.

O helper previsto é `input_boolean.jarvis_lab_light`. Ele é diferente da
entidade simulada `light.sala` da Sprint 2. Se o laboratório for instalado,
criar manualmente o Toggle Helper sem automações/dispositivos e conferir seu
ID efetivo com a configuração antes de qualquer leitura. Nomes alternativos
precisam manter o prefixo virtual restrito `input_boolean.jarvis_lab_`.
O JSON não comprova criação nem ausência de automações: isso requer inspeção
do operador na instância de laboratório.

## Fronteira física: fora do escopo

Informações do LAB não são execução física. `HALabState` não vira `ToolReceipt`
ou `SimulatedActionResult` e mantém `physical_action_verified=false`.
A origem `home_assistant_lab` é rótulo descritivo, não autenticação.
Nenhum cliente foi instalado no gateway nem exposto ao LLM.
`room_chat_cli` permanece inalterada, com comandos físicos recusados.
Hikvision e WLED continuam planejados e sem execução real.

## Limites de acesso e credenciais

Loopback limita a publicação da porta, mas não prova isolamento total:
processos locais e caminhos de rede do contêiner exigem avaliação própria.
Bridge não bloqueia toda saída de rede. Não declarar acesso externo bloqueado
em execução sem uma prova operacional que vá além da renderização do Compose.

Um token do Home Assistant pode autorizar operações mutáveis fora deste cliente.
Ele não se torna intrinsecamente read-only. Credenciais do LAB devem ser
independentes das futuras de produção; usar token temporário e revogá-lo quando
não for mais necessário. Nunca aceitar integrações descobertas automaticamente,
importar backups de produção ou adicionar equipamentos reais nesta prova.

## Operação opcional e pendente

A documentação oficial atual de [Home Assistant Container](https://www.home-assistant.io/installation/linux#install-home-assistant-container)
orienta Docker Engine e declara Docker Desktop não suportado. O ambiente
disponível usa Docker Desktop; a inicialização foi adiada por compatibilidade
operacional, não por falha dos testes offline. Não houve onboarding, criação
de helper, token real, leitura autenticada ou download da imagem nesta execução.

Antes de instalar sob supervisão, validar o runtime, executar `docker compose
config`, registrar versão efetiva e digest da tag mutável `stable` e verificar
os recursos. Depois criar usuário exclusivo do LAB com senha forte e o helper
virtual, sem associá-lo a qualquer automação/dispositivo.

Encerrar rotineiramente com `docker compose ... down`, sem `-v`.
`down -v` apaga o volume e não deve ser usado para encerramento normal.
Não versionar o volume; criar backup privado antes de atualizações.
Versão/digest e provas GET reais permanecem pendentes até essa instalação.

Referência de endpoints: [REST API oficial](https://contributors.home-assistant.io/core/internals/rest-api/).
Fontes consultadas em 17/10/2026; não foram acessadas instâncias de dispositivos.
