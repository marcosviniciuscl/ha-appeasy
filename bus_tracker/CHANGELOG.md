# Changelog

## 3.0.1

- `linhas_monitoradas` agora é um campo de texto com as linhas separadas por
  vírgula. Contorna o bug da UI do HA que não mostra os botões de
  adicionar/remover em opções do tipo lista.

## 3.0.0

- App renomeado de "VIA Feira Tracker" para **Bus Tracker** (`slug: bus_tracker`).
- Agora é **genérico**: qualquer cidade que use o sistema SIUMobile. Inclui
  **Feira de Santana (BA)** e **Belo Horizonte (MG)** na lista, com opção de
  informar URL base, praça e pacote manualmente para outras cidades.
- Novo App dentro do repositório multi-App `ha-appeasy`.
