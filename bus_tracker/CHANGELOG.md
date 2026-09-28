# Changelog

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
