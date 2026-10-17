# ADR-0001 — Estratégia de inferência do J.A.R.V.I.S.

Status: Proposta para validação
Projeto: J.A.R.V.I.S. — Sala Temática
Sprint: 1

## 1. Contexto

O projeto utiliza OpenJarvis, Ollama e módulos próprios
para conversação e controle determinístico.

O modelo experimental atual é jarvis-dev-lite:latest,
baseado em Qwen3.5 0.8B, executado em CPU.

O ambiente WSL possui aproximadamente 3,8 GiB de RAM.

## 2. Evidências existentes

Modelo frio:

- Tempo do cliente: 26,77 s
- Cobertura lexical MQTT: 0%
- Revisão humana: incorreta

Modelo pré-carregado:

- Tempo do cliente: 6,00 s
- Cobertura lexical MQTT: 33,33%
- Revisão humana: incorreta

A residência do modelo reduziu a latência observada,
mas consumiu aproximadamente 1,46 GiB adicionais de RAM.

As observações não constituem benchmark representativo
de outros modelos nem medição estatística de desempenho.

## 3. Decisão arquitetural

Adotar arquitetura híbrida, implementada gradualmente.

### Camada A — Respostas verificadas

Responsável por:

- Identidade do assistente
- Informações cadastradas da sala
- Consulta declarativa ao inventário
- Outras respostas revisadas e aprovadas

Não necessita de inferência.

### Camada B — Conversação local experimental

Responsável por perguntas informativas abertas.

Utiliza:

- OpenJarvis
- Ollama
- Política preventiva de memória
- Ferramentas físicas desabilitadas

As respostas são identificadas como não verificadas.

O modelo atual permanece restrito ao desenvolvimento.

### Camada C — Provedor remoto futuro

Permitirá avaliar modelos de maior capacidade.

Restrições:

- Integração ainda não implementada
- Habilitação explícita
- Provedor configurado pelo operador
- Credenciais fora do repositório
- Política de privacidade e envio de dados
- Sem ferramentas físicas por padrão
- Sem fallback automático para a nuvem

Nenhuma requisição remota será realizada nesta fase.

### Camada D — Controle físico

Responsável exclusivamente por:

- Validação de identidade e permissões
- Identificação dos dispositivos
- Validação das ações permitidas
- Comunicação com backend confiável
- Recebimento de confirmações verificáveis

Texto gerado por IA não comprova execução de comandos.

Home Assistant e dispositivos físicos permanecem
desabilitados até integração, autorização e testes.

## 4. Critérios para aceitar um modelo

A avaliação futura deverá considerar:

1. Correção factual revisada por humanos.
2. Adequação ao português brasileiro.
3. Ausência de falsas alegações de execução física.
4. Cumprimento de instruções e formatos.
5. Tempo de resposta e velocidade de geração.
6. Consumo de RAM, swap e estabilidade.
7. Comportamento diante de pedidos não autorizados.
8. Privacidade e disponibilidade do provedor.

Os quatro casos de avaliação atuais são insuficientes
para certificar um modelo para produção.

## 5. Metas de experiência

- Respostas verificadas: manter caminho rápido sem IA.
- Conversação: buscar baixa latência para uso por voz.
- Controle físico: exigir confirmação de backend confiável.
- Falhas de provedor: manter catálogo e gateway disponíveis.

Valores finais de latência ainda serão definidos
e medidos no hardware de implantação.

## 6. Decisões explicitamente adiadas

- Seleção do modelo definitivo.
- Integração com um serviço remoto de IA.
- Implementação de voz em tempo real.
- Autorização de ações físicas.
- Ferramentas de Home Assistant.
- Política de memória para hardware definitivo.

## 7. Próximos passos

1. Formalizar contrato de provedores de conversação.
2. Preservar roteamento determinístico existente.
3. Criar simuladores para avaliar provedores sem inferência.
4. Expandir casos técnicos e de segurança.
5. Avaliar modelos candidatos em ambiente apropriado.
6. Integrar Home Assistant em ambiente controlado.

## 8. Restrições de segurança

Nenhum provedor de IA possui autorização implícita
para executar ferramentas ou modificar dispositivos.

A autorização de operações físicas deve ocorrer fora
do modelo de linguagem, em serviço confiável.

Nenhum resultado lexical é considerado prova suficiente
de correção factual.
