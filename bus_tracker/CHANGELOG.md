# Changelog

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
