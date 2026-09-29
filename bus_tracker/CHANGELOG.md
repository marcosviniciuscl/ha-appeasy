# Changelog

## 0.49.0

- **Selects funcionando no celular**: os campos de seleção (cidade, tipo de
  horário e "trajeto sem linha") agora abrem um **dropdown próprio, dentro da
  tela e legível** — o dropdown nativo aparecia invisível no tema escuro ou fora
  da tela no WebView.
- **Chips do mapa não voltam mais sozinhos**: ao remover/adicionar linhas em
  "O que exibir no mapa", a atualização automática não desfaz mais a seleção
  antes de salvar; aparece um aviso **"alterações não salvas"** e só o botão
  **Salvar exibição** aplica.
- **Desktop sem painel atrás**: nas abas que não são o Mapa, o painel translúcido
  (sombra/bordas) atrás dos cards foi removido — ficam só os cards da aba sobre o mapa.

## 0.48.1

- O indicador de **"no ponto"** agora é **estático** (verde, sem pulsar), para
  não poluir o mapa. O balão do ponto continua mostrando "você já está no ponto"
  e a animação de caminhada continua parando quando a pessoa chega.

## 0.48.0

- **Localização com idade**: o app passa a mostrar **há quanto tempo o Home
  Assistant atualizou** a localização da pessoa (no balão da pessoa no mapa e no
  log de diagnóstico). Se ficar parada por mais de 30 min, a Atividade avisa
  `⚠ localização parada` — ajuda a ver se o GPS/HA está realmente atualizando.
- **Pessoa no ponto**: quando a pessoa chega ao ponto de embarque, o mapa **para
  a animação de caminhada** e marca a pessoa em **verde com um anel pulsante** e
  o rótulo **"no ponto"** (o balão do ponto também diz "você já está no ponto").

## 0.47.0

- **O trajeto agora monitora o ônibus o tempo todo**, não só na janela do
  horário: assim que existe um ônibus **indo ao destino** e chegando perto do
  ponto de embarque, o app envia o aviso ao vivo com **distância/tempo do ônibus
  até o ponto**, **seu tempo a pé** e o **risco**. A janela do horário deixou de
  ser obrigatória para avisar (dentro dela, o ônibus escolhido continua sendo o
  do tipo de horário).
- O aviso acompanha o ônibus **até ele passar pelo ponto** (antes parava 200 m
  antes e encerrava).
- **Ônibus que sai do início da linha** (a parada de "SAIDA" perto de casa)
  voltou a ser considerado: o filtro de "já passou da parada" estava com o lado
  invertido e descartava ônibus que estavam **no/antes** do ponto.
- **Primeiro aviso do rastreio volta a alertar** (som/vibração). Antes o
  primeiro "ônibus a X km" chegava **silencioso** no iPhone (as atualizações
  seguintes é que devem ser silenciosas).
- O aviso **"🚌 Ônibus chegando!"** não é mais apagado logo em seguida: ao
  chegar/passar, o app mantém esse aviso na tela e para só a atualização do
  rastreio.
- O **ponto de embarque e o ônibus destacado** agora são sempre da **mesma
  linha** (antes, quando não havia ônibus no horário, o ponto podia ser de uma
  linha e o ônibus de outra).

## 0.46.0

- **Ponto de embarque não fica mais longe do que o necessário**: quando não há
  parada oficial perto de você, o trajeto passa a usar o **ponto do traçado onde
  o ônibus passa** (no sentido do destino), em vez de te mandar para a parada
  oficial mais próxima — que às vezes ficava a mais de 1 km. Exemplo real: o
  ônibus passa a ~190 m e o app mandava andar ~1,2 km até a parada.
- A **parada oficial** continua sendo preferida quando ela não fica muito mais
  longe que o ponto do traçado (o ônibus para de verdade nela).

## 0.45.0

- **Painéis do mapa no celular viram gavetas**: arraste o puxador **para baixo**
  para recolher (fica só o título, ocupando pouco da tela) e **para cima** para
  abrir. Um toque curto no puxador também alterna.
- **Tocar no mapa recolhe o card** no celular (em vez de fechá-lo), mantendo a
  rota/ônibus selecionado — toque de novo para fechar de vez.
- **Ao abrir um ônibus** o painel volta a aparecer inteiro, mesmo se estiver
  recolhido.
- **Layout do mapa**: os contadores de ônibus/pessoas ficam no **canto superior
  esquerdo** e os **botões de controle em uma única coluna** no lado direito
  (no celular também), deixando o mapa mais livre.

## 0.44.0

- **Linha do tempo das paradas**: ao selecionar um ônibus, o painel mostra
  **todas as paradas** até o fim — as que **já passaram** (apagadas) e as que
  **faltam**, com a **próxima destacada** ("próximo"). Rola com **barra
  invisível** para ver tudo.
- **Clicar numa parada realça ela no mapa** (centraliza e põe um anel pulsante).

## 0.43.1

- O **destaque prefere o ônibus que dá tempo** (você chega no ponto antes dele).
  Antes podia ficar em vermelho ("perdeu") mostrando um ônibus atrasado mesmo
  havendo outro que dava tempo. Se nenhum der tempo, não destaca.
- Para o tipo **passa no ponto** sem horário no dia, destaca o próximo ônibus
  que dá tempo (em vez de não destacar nada).
- Diagnóstico agora mostra **de onde veio a localização** usada (GPS da pessoa ou
  a casa) — ajuda a entender quando o ponto mais próximo parece longe.

## 0.43.0

- **Tipo de horário no trajeto**: ao criar/editar você escolhe o que o horário
  informado significa:
  - **Passa no ponto** (padrão): o ônibus passa no seu ponto naquele horário.
  - **Fico livre**: você fica disponível naquele horário — o app pega o **próximo
    ônibus** no ponto mais próximo depois disso.
  - **Chegar no destino**: você quer chegar no destino naquele horário — o app
    acha o **melhor horário para sair** (o ônibus que ainda chega a tempo).
- O **destaque do ônibus** só aparece quando faz sentido para o tipo escolhido.
- No painel o trajeto mostra o tipo e, no caso de "chegar", **quando sair** e
  **quando chega**.

## 0.42.0

- **Ponto de encontro fixo**: é sempre a parada válida **mais próxima** (não muda
  conforme o ônibus anda). O que muda é o ônibus: quando o atual passa, o
  **próximo que passar** naquele ponto assume o destaque e a cor.
- O trajeto continua aparecendo mesmo **sem ônibus indo agora** (mostra o ponto
  e espera o próximo).
- **Notificação live** (Live Activity) com **cor pelo risco**: verde (dá tempo),
  laranja (corra) e vermelho (não dá mais). Mostra a **distância/tempo do ônibus
  até o ponto** e a **distância/tempo de você até o ponto** (atualizados conforme
  você anda).

## 0.41.0

- **Ponto de embarque correto**: a parada agora é casada pelo **itinerário** do
  ônibus (não por projeção geométrica). Antes podia escolher uma parada de rua
  paralela onde o ônibus não para; agora é sempre um ponto em que o ônibus que
  vai ao destino realmente para.
- Escolhe a **parada mais próxima que tenha um ônibus indo ao destino** (se
  nenhuma tiver ônibus agora, mostra a mais próxima ainda).
- **Destaque em verde**: o ônibus e o ponto ficam verdes; ficam **laranja** em
  "corra" e **vermelho** quando não dá mais tempo.
- A rota destacada mostra só o **trecho do ônibus até o seu ponto** (não o
  itinerário inteiro).
- Anel pulsante do ônibus **centralizado**.

## 0.40.0

- **Destaque independe do horário**: o **próximo ônibus** que passa no ponto indo
  ao destino fica destacado sempre que existir (antes só destacava dentro da
  janela de horário, por isso "não aparecia"). A janela agora controla apenas os
  avisos/rastreio automático.
- Corrigido o **padrão de dias** do trajeto: era ter–sáb (excluía a segunda);
  agora é **seg–sex**.
- A janela de horário tolera o mesmo tempo **depois** do horário (antes eram só
  5 min), então o trajeto continua ativo enquanto o ônibus chega.
- Diagnóstico passa a dizer **por que** está fora do horário (dia da semana ou
  próximo horário).

## 0.39.0

- **Limite de caminhada configurável** (Ajustes → *Distância máxima até o ponto
  de embarque*, padrão 2 km).
- Trajetos cujo ponto de embarque fica **além do limite** aparecem em **cinza**
  ("longe"), no mapa e na lista, sem destaque de ônibus — informando a distância
  e o limite. Se houver um ponto dentro do limite, ele é preferido.

## 0.38.0

- **Ponto de embarque fixo**: a parada não muda mais conforme o ônibus anda
  (antes o ponto "pulava" para a parada à frente do veículo). Agora ele é
  calculado só pela **sua localização + destino** e permanece o mesmo.
- **Destaque é o próximo ônibus** a passar nesse ponto (menor ETA), não mais o
  ponto recalculado na frente do ônibus.
- Destaque mais visível: anel **azul pulsante**, rótulo azul e o ônibus
  destacado fica **por cima** dos demais.
- Se um trajeto está no horário e **não há** ônibus indo ao ponto, isso aparece
  no log de **Atividade** (com o modo diagnóstico detalhado).

## 0.37.0

- **Ponto de embarque no sentido do destino**: agora só entram paradas de
  itinerários que **passam no destino** e que ficam **antes** dele. Antes o app
  podia mandar você para uma parada onde passam ônibus que **não** vão ao seu
  destino (direção contrária).
- **Destaque é o próximo ônibus**: o veículo e a rota em destaque são o **próximo
  ônibus que vai passar na sua parada** indo para o destino.
- **Logs de diagnóstico**: novo botão **Copiar logs** em Ajustes → Atividade e um
  switch **Log detalhado dos trajetos** mostrando destino, direções, parada
  escolhida, ônibus e motivo quando nada é encontrado.

## 0.36.0

- **Configuração só no painel**: removidas todas as opções do App no Home
  Assistant; cidade, intervalos, linhas e demais ajustes ficam na aba Ajustes.
- **Botões do mapa no canto** também no mobile (grade 2×3 no canto superior
  direito, em vez de uma faixa no meio da tela).
- **Rota com animação no sentido do ônibus** ao selecionar o veículo (tracinhos
  em movimento na direção do trajeto).
- Clicar no mapa **volta para a aba Mapa e fecha os painéis** abertos.
- **Destaque do trajeto ativo** agora marca **todos os ônibus candidatos** da
  linha (não só o melhor), além do ponto de embarque e da rota.
- Escondida a **barra de rolagem** dos cards/painéis.
- Explicação na interface das opções de **Trajeto sem linha escolhida**
  (monitoradas x cidade).

## 0.35.0

- **Criar trajeto por uma parada da rota**: ao tocar no ônibus, cada parada do
  painel e do mapa tem um botão **+ trajeto** que abre o cadastro já com aquela
  linha e aquele ponto como destino.
- **Busca de destino no mapa** agora junta as paradas próximas do toque com as
  paradas das **linhas monitoradas dentro do raio** — como a API ignora o raio
  pedido, antes vinham só ~7 pontos; agora vêm todos os das linhas monitoradas.
- **Indicador de carregamento global**: barra no topo e um selo *carregando…* no
  topo para **todas as requisições** (API e imagens do mapa).

## 0.34.1

- Corrigido o **ponto de embarque**: agora ele é a parada **sobre o traçado que o
  ônibus percorre** (mesma lógica do ETA), em vez da lista genérica de paradas da
  linha — que muitas vezes apontava para uma parada distante/fora da rota.
- Cache de `paradasProximas` (10 min) para não sobrecarregar a API ao varrer o
  traçado.

## 0.34.0

- **Destino só por ponto existente**: ao tocar no mapa, o app carrega as paradas
  num **raio configurável** (Ajustes → *Raio de busca do destino no mapa*,
  padrão 3 km) e você toca na parada desejada; não dá mais para salvar uma
  coordenada solta — o destino é sempre um ponto real.
- **Topo enxuto**: removido o cabeçalho com nome do app e linhas; ficaram só o
  **horário** e o status **online/offline**.

## 0.33.0

- **Trajetos sem linha obrigatória**: dá para escolher **várias linhas**
  (multiselect) ou deixar vazio. Sem linha, o app usa as **linhas monitoradas
  que passam pelo destino** (padrão) ou **descobre as linhas da cidade** que
  atendem o destino — configurável em **Ajustes → Comportamento**.
- **Destino direto no mapa**: botão **Escolher no mapa** no cadastro do trajeto;
  toque no ponto desejado (ou em qualquer lugar) para definir onde descer.
- **Rastreio automático**: acabou a seleção manual de "Rastrear". A **Live
  Activity** começa sozinha quando o ônibus cumpre as condições do trajeto e
  encerra na chegada/expiração. A lista em Ajustes virou **Rastreios
  automáticos** (só acompanhamento).
- **Modais com ícones**: popups do ônibus/ponto e o painel da linha ficaram mais
  bonitos, com ícones de veículo, relógio, destino, acessibilidade e paradas.
- Corrigido o **toque/pan do mapa**: os traçados das linhas não capturam mais o
  gesto (touch-action) quando estão exibidos.
- **Ajustes → Comportamento** agora com as opções **uma embaixo da outra**.
- Corrigido o **empilhamento do mapa**: os painéis de informação (rota do ônibus,
  trajetos e pontos) não ficam mais atrás dos panes do Leaflet.

## 0.32.0

- **Mapa em tela cheia**: no mapa o topo virou um leve degradê (sem barra sólida)
  e o menu inferior flutuante ficou mais colado na base da tela.
- Corrigida a **animação da caminhada** e o **brilho da rota** (as classes do
  Leaflet não eram aplicadas quando o traçado não era interativo).
- Trajeto **no horário** agora destaca de verdade: o **ônibus** e o **ponto de
  embarque mais próximo** piscam em **azul**, a **rota** fica azul animada e o
  **caminho até o ponto** ganha animação de deslocamento. O ônibus do trajeto
  aparece no mapa mesmo que a linha não esteja selecionada.

## 0.31.0

- Trajetos agora usam **ponto de destino** (onde a pessoa vai descer) em vez de
  ida/volta. O cálculo (embarque, tempo a pé, ônibus e risco) continua igual.
- UI reformulada: **menu inferior flutuante e arredondado** (só ícones no
  celular), **switches**, ícones nos títulos, foco nos campos e espaçamentos
  melhores.
- Campo de **destino pesquisável**, com as paradas da linha escolhida.

## 0.30.0

- Removida a aba **Avisos** (os trajetos cobrem os avisos).
- Lista de **trajetos agrupada por pessoa**.
- Corrigido o **gesto** no mapa: as rotas desenhadas não capturam mais o toque.
- Menu do celular só com **ícones**; topo mais compacto (hora do ciclo minúscula).
- **Modal estilo Uber**: painel sobe de baixo sem tomar a tela e o mapa continua
  visível.
- Notificação **ao vivo** mais enxuta (só ícone/cor).
- Quando o trajeto está no horário, o **ônibus pisca** e a **rota dele fica azul
  em destaque**; a **caminhada até o ponto** ganhou animação de deslocamento.

## 0.29.0

- **Zoom por gesto** (pinça) e por duplo toque no mapa, além de botões +/−.
- **Interface mobile** mais enxuta: usa a altura toda, botões/menus menores.
- **Campos de linha/pessoa/celular/local** agora são pesquisáveis (datalist).
- **Zona da casa**: cadastre a casa por entidade do HA (`zone.home`) ou marcando
  no mapa; os trajetos passam a saber o que é **ida** e **volta**.
- **Deslocamento por ruas** (OSRM) no lugar da linha reta, com fallback.
- **Tempo a pé até a parada mais próxima** da linha (não mais o ponto do traço):
  o ETA do ônibus passa a ser calculado para a parada onde a pessoa embarca.
- Marcador de **pessoa** e da **casa** no mapa (em vez de um círculo simples).

## 0.28.0

- **Trajetos**: nova aba para cadastrar quais ônibus cada pessoa pega e os
  horários (ida/volta), com vários horários por trajeto e por pessoa.
- **Mapa** mostra onde estão as pessoas cadastradas, a distância até o ponto, o
  **tempo a pé** e a linha de caminhada até a parada, o ETA do ônibus e o
  **tempo total** para conseguir pegá-lo.
- **Risco de perder o ônibus** calculado em tempo real (dá tempo / corra / pode
  perder), com notificação para **sair de casa a tempo** e atualização ao vivo.
- Ajustes novos: velocidade a pé, fator de rota, margem de embarque e janela de
  aviso de saída.

## 0.27.0

- **Desktop**: o mapa também ocupa a tela toda e as opções abrem num painel
  lateral ao lado de uma trilha de navegação vertical (sem barra inferior).
- Ícones **SVG** no lugar dos emojis (navegação, ações do mapa e topo).
- Quando um ônibus é selecionado, a rota e as **informações de cada ponto**
  aparecem num painel lateral sobre o mapa (desktop) ou em bottom sheet (mobile).
- Visual mais moderno: painéis com desfoque (glass), cantos e sombras suaves.

## 0.26.0

- **Interface mobile**: mapa em tela cheia, barra de navegação inferior e
  painéis deslizantes (bottom sheets) para a rota e os pontos de embarque.
- Mesmo no desktop o mapa ocupa a tela toda, mantendo os botões.
- **Ícone de ônibus** no mapa em vez do quadrado laranja.
- A rota selecionada **não pisca mais** ao atualizar (só troca quando os dados
  novos chegam).

## 0.25.0

- Ao **tocar num ônibus no mapa**, o painel desenha a **rota do itinerário**
  (linha azul), mostra as paradas e o **tempo estimado** até cada uma.
- Detalhes extraídos da API: sentido/apelido da linha, destino, previsão
  ("X Minutos" ou "SAÍDA: HH:MM"), acessibilidade e rumo do veículo.
- Novos endpoints internos da API SIUMobile: paradas por itinerário
  (com coordenadas) e previsões por parada.

## 0.24.4

- Agora dá para **escolher a cidade pelo painel**; a lista de linhas passa a
  refletir a cidade selecionada (e a escolha fica salva).
- Notificações de aviso e de rastreio ao vivo ajustadas para funcionar tanto no
  **Android** quanto no **iPhone** (Live Activity/Live Update e botões de ação).
- Versão renumerada para abaixo de 1.

## 3.0.3

- Remove arquiteturas obsoletas (`armv7`, `armhf`, `i386`): agora só `aarch64` e
  `amd64`.
- Troca o tipo de mapa legado `addon_config` por `app_config`.
- Remove o `build.yaml` (não é mais usado) e usa a imagem base explícita no
  Dockerfile.

## 3.0.2

- `linhas_monitoradas` volta a ser uma lista com botão de adicionar (formato
  `["str?"]`), que a UI do HA renderiza corretamente.

## 3.0.1

- Ajuste interno ao ler `linhas_monitoradas`.

## 3.0.0

- App renomeado de "VIA Feira Tracker" para **Bus Tracker** (`slug: bus_tracker`).
- Agora é **genérico**: qualquer cidade que use o sistema SIUMobile. Inclui
  **Feira de Santana (BA)** e **Belo Horizonte (MG)** na lista, com opção de
  informar URL base, praça e pacote manualmente para outras cidades.
- Novo App dentro do repositório multi-App `ha-appeasy`.
