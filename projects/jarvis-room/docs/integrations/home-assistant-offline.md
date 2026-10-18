# Home Assistant — contrato offline da Sprint 2

Nenhuma instância real foi contatada. Não há cliente HTTP nem credenciais.
`DisabledHATransport` recusa todas as chamadas. O fake existe somente em
`tests/ha_fakes.py`, registra chamadas em memória e não modifica dispositivos.
`light.sala` é um identificador sintético restrito à allowlist da simulação.
Uma resposta do fake não autentica conexão ou estado físico.

O vínculo `room_main_lights → light.sala` é exclusivamente sintético e não
comprova dispositivo real. O verificador exige essa associação antes de ler
o transporte: outros dispositivos, inclusive a lousa, as fitas LED e o sensor
de presença, retornam `simulated_error` sem qualquer chamada ao fake.
Mesmo um `simulated_match` mantém `physical_action_verified=False`.

## Endpoints futuros, sem implementação nesta sprint

- `POST /api/services/<domain>/<service>`: solicitar uma ação.
- `GET /api/states/<entity_id>`: consultar o estado informado pela integração.
- `POST /api/states/<entity_id>`: altera a representação de estado no Home
  Assistant; não envia comando ao dispositivo e não comprova execução física.

Uma futura implementação precisará de autorização, associação real de entidades,
tratamento de falhas e retorno confiável. O contrato atual não configura nenhum
destino de rede ou mecanismo de autenticação.

Fonte: [REST API oficial do Home Assistant](https://contributors.home-assistant.io/core/internals/rest-api/),
consultada em 17/10/2026.
