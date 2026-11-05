# HA Concierge — documentação

## Instalação

Instale este App pela loja de Apps do repositório AppEasy em Home Assistant
OS ou Supervised. Abra a interface pelo botão **Abrir interface web**. O App
usa Ingress; não publica porta externa por padrão. A API do Home Assistant é
acessada pelo token fornecido pelo Supervisor.

Se o App não aparecer após uma atualização do repositório, abra **Configurações
→ Apps → Loja de Apps**, use o menu **⋮ → Verificar atualizações** (ou
recarregue a loja) e atualize a página do navegador. Confirme que o repositório
`https://github.com/marcosviniciuscl/ha-appeasy` está cadastrado. Se continuar
ausente, consulte os logs do Supervisor para ver se o `config.yaml` foi
rejeitado; envie a mensagem de erro para diagnóstico.

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

## Sugestões

O painel analisa os tipos, estados e classes das entidades descobertas e
mostra sugestões do que pode ser feito: selecionar sensores de segurança,
configurar presença, acompanhar medidores, revisar câmeras com consentimento,
observar rotinas de luzes, verificar baterias baixas e revisar entidades
indisponíveis. As sugestões usam apenas dados locais do inventário, não enviam
nada a provedores e se atualizam após mudanças de seleção, presença, câmeras,
avisos ou propostas. O Assistente também responde a perguntas como
“quais sugestões você tem?” usando essa mesma lista.

## Modelos de linguagem

O modo local sem LLM funciona sem chave. Para modelos externos, preencha a
chave desejada na aba **Configuração** do App no Home Assistant, depois escolha
provedor e modelo dentro do painel. Chaves disponíveis: OpenAI, Anthropic,
Gemini, OpenRouter e endpoint compatível com OpenAI. Para Ollama, informe `ollama_url` nas
opções do App; o endereço deve resolver para rede privada ou loopback. O
endpoint compatível deve ser HTTPS público. IDs de modelos variam com o
provedor; caso o padrão deixe de existir, informe um ID atual.

Para **OpenRouter**, preencha `openrouter_api_key` nas opções do App e selecione
`openrouter` no painel. O modelo inicial é `openrouter/auto`, mas você pode
informar um ID específico no formato `provedor/modelo`. Para análise de câmera,
o modelo escolhido precisa aceitar imagens; confirme a capacidade na página
do modelo no OpenRouter antes de habilitar o envio. Chamadas podem ser cobradas
conforme o modelo roteado; o limite do App conta chamadas, não valores em dinheiro.

Ao selecionar um provedor, o painel consulta seu catálogo e mostra os modelos
em uma lista filtrável. OpenRouter, OpenAI, Anthropic, Gemini e endpoints
compatíveis usam seus endpoints de catálogo. Ollama lista os modelos presentes
no servidor informado; para Ollama Cloud, essa lista depende do servidor/API
configurado e pode exigir que os modelos tenham sido habilitados ou baixados.
Se não houver chave, a API estiver indisponível ou o endpoint não oferecer
listagem, o painel informa isso, mantém o modelo padrão e permite digitar um
ID manualmente.

O painel envia ao modelo apenas estados das entidades selecionadas e alguns
alertas recentes, além da pergunta. O modelo responde em texto e não tem
ferramentas para controlar a casa. O limite diário de chamadas é ajustável;
uma tentativa conta para o limite mesmo que o provedor falhe. Chaves não são
expostas à interface nem aos logs do App. Os segredos nas opções do Supervisor
seguem a proteção de armazenamento do próprio Home Assistant.

## Depuração

Para investigar respostas vazias, falhas de conexão ou catálogos de modelos
indisponíveis, ative `debug: true` nas opções do App e reinicie-o. Os logs do
App passam a registrar provedor, modelo, tamanho da pergunta e da resposta,
status HTTP e mensagens de erro retornadas pelo provedor. Chaves de API,
cabeçalhos de autenticação, imagens e o conteúdo completo do contexto não são
gravados. Desative `debug` depois de coletar os logs. Em desenvolvimento local,
use `CONCIERGE_DEBUG=1 python3 ha-concierge/app.py`.

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

## Interface

O painel é uma aplicação Vue 3 construída com PrimeVue v4. O resultado do
build é gerado em `web/` e servido pelo próprio backend, sem CDN externo. A
interface inclui tema claro/escuro, navegação lateral em desktop e menu
retrátil em telas pequenas. Os dados continuam vindo apenas de `/api/*` sob o
prefixo do Ingress.

## Desenvolvimento

O painel tem código-fonte em `ui/`. O build é feito durante a construção da
imagem: o Dockerfile compila `ui/` em um estágio Node e copia o resultado para
a imagem final. Assim, a instalação e a atualização do App no Home Assistant
sempre usam o código-fonte atual, e o dispositivo executa apenas Python.
`ha-concierge/web/` é gerado no build e não é versionado.

Para testar o painel fora do Docker, gere-o manualmente:

```bash
cd ha-concierge/ui
npm ci
npm run build
```

Esse comando cria `ha-concierge/web/` apenas na sua máquina; não é necessário
rodá-lo antes de commits ou para instalar o App.

Execute `pytest -q ha-concierge/tests` na raiz do repositório. Para iniciar
fora do Home Assistant, defina `CONCIERGE_DATA`, `CONCIERGE_DEV=1`, `HA_BASE`,
`HA_WS` e `HA_TOKEN`; então execute `python3 ha-concierge/app.py`. O painel
escuta em 8099. Use uma instância de teste do Home Assistant.
