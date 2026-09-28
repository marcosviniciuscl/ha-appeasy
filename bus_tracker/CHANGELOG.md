# Changelog

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
