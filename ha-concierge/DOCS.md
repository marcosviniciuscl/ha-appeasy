# HA Concierge — documentação

## Instalação

Instale este App pela loja de Apps do repositório AppEasy em Home Assistant
OS ou Supervised. Abra a interface pelo botão **Abrir interface web**. O App
usa Ingress; não publica porta externa por padrão. A API do Home Assistant é
acessada pelo token fornecido pelo Supervisor.

## Primeira execução

Escolha o nome do assistente, ou mantenha **Concierge**. O nome do morador é
opcional. O App consulta estados, áreas, dispositivos e até 20 sensores com
histórico das últimas 24 horas. A descoberta não ativa monitoramento. O painel
mostra a contagem de **áreas cadastradas**, que pode ser diferente da quantidade
de cômodos físicos. Uma entidade é marcada como ativa quando tem estado válido
e atualização nas últimas duas horas.

Vá a **Monitoramento** e selecione as entidades desejadas. Depois configure
presença em **Configurações**, escolhendo uma ou mais entidades `person`,
`device_tracker` ou `binary_sensor`. Um modo manual casa/ausente também está
disponível. Sem presença válida, o modo fica desconhecido e alertas baseados
em ausência não são gerados. Um sensor de movimento desligado não é prova de
ausência; o modo automático só conclui ausência com pessoas/rastreadores
selecionados em `not_home`/`away`.

## Alertas e automações

O App consulta estados a cada 15 segundos. Detecta abertura de porta ou janela
durante ausência, acionamento de sensores de gás/fumaça/umidade/problema e
leituras de energia, água ou gás muito acima da mediana local, após pelo menos
oito amostras. Leituras inválidas ou indisponíveis são ignoradas. A análise de
medidores cumulativos usa a diferença entre amostras, tratando reset como zero.
Alertas não substituem alarmes ou verificação humana.

Quando uma luz ou interruptor muda para o mesmo estado em três dias, perto
do mesmo horário, pode surgir uma proposta de rotina diária. A tela mostra
horário, serviço e entidade antes da aprovação. A rotina roda **dentro deste
App** enquanto ele estiver ativo. Pode ser rejeitada ou desativada; não grava
YAML nem cria uma automação nativa no Home Assistant. A execução só alcança
entidades ainda selecionadas.

Marcar um alerta não crítico como falso positivo o dispensa, registra o
feedback na memória e silencia essa entidade por 24 horas. Alertas críticos
não são silenciados por esse mecanismo.
Em Configurações, você pode habilitar notificações persistentes do Home
Assistant para alertas. Por padrão elas ficam desligadas.

## Modelos de linguagem

O modo local sem LLM funciona sem chave. Para modelos externos, preencha a
chave desejada na aba **Configuração** do App no Home Assistant, depois escolha
provedor e modelo dentro do painel. Chaves disponíveis: OpenAI, Anthropic,
Gemini e endpoint compatível com OpenAI. Para Ollama, informe `ollama_url` nas
opções do App; o endereço deve resolver para rede privada ou loopback. O
endpoint compatível deve ser HTTPS público. IDs de modelos variam com o
provedor; caso o padrão deixe de existir, informe um ID atual.

O painel envia ao modelo apenas estados das entidades selecionadas e alguns
alertas recentes, além da pergunta. O modelo responde em texto e não tem
ferramentas para controlar a casa. O limite diário de chamadas é ajustável;
uma tentativa conta para o limite mesmo que o provedor falhe. Chaves não são
expostas à interface nem aos logs do App. Os segredos nas opções do Supervisor
seguem a proteção de armazenamento do próprio Home Assistant.

## Câmeras e privacidade

Selecione uma câmera em Monitoramento, habilite-a em Configurações e autorize
explicitamente o envio de imagem ao provedor. Cada análise exige confirmação
no momento da captura, com intervalo mínimo de cinco minutos por câmera.
As imagens não são gravadas em `/data`; uma descrição curta entra no registro
de atividade. Existe uma permissão adicional para analisar automaticamente
uma imagem quando um alerta de abertura ou segurança ocorrer na **mesma área**
da câmera. Isso não ativa vídeo contínuo.

O banco SQLite local fica em `/data/concierge.db`. Ele contém configurações,
amostras por até 30 dias, eventos, memórias e propostas. Os arquivos
`SOUL.md`, `AGENT.md` e `MEMORY.md` ficam em `/data/identity`; este último é
gerado a partir da memória do banco. A tela Memória permite esquecer itens,
exportar respostas e apagar todos os registros de memória. Para excluir também
eventos e configurações, pare o App e remova seu diretório `/data` pelo
mecanismo de gerenciamento do Supervisor.

## Desenvolvimento

Execute `pytest -q ha-concierge/tests` na raiz do repositório. Para iniciar
fora do Home Assistant, defina `CONCIERGE_DATA`, `CONCIERGE_DEV=1`, `HA_BASE`,
`HA_WS` e `HA_TOKEN`; então execute `python3 ha-concierge/app.py`. O painel
escuta em 8099. Use uma instância de teste do Home Assistant.
