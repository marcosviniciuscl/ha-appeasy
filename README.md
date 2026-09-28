# Apps do Marcos para Home Assistant

Coleção de **Apps** (antigos *add-ons*) para **Home Assistant OS** ou
**Supervised**. Cada App fica na sua própria pasta deste repositório, com
instalação e configuração independentes.

## Apps disponíveis

| App | Pasta | O que faz |
| --- | --- | --- |
| **YouTube para Telegram** | [`youtube-telegram/`](youtube-telegram/) | Baixa vídeo/áudio do YouTube pelo Telegram e entrega no chat (usa MinIO para arquivos grandes). |
| **Bus Tracker** | [`bus_tracker/`](bus_tracker/) | Ônibus ao vivo das cidades que usam o SIUMobile, com painel, avisos e rastreio no celular. |

A documentação completa de cada App está no `DOCS.md` da respectiva pasta (também
aparece na aba **Documentação** dentro do Home Assistant).

## Requisitos

- **Home Assistant OS** ou **Supervised** (são os que aceitam Apps).
- Internet no Home Assistant.

## Instalação

1. No Home Assistant, vá em **Configurações → Apps → Loja de Apps**
   (em versões antigas: **Add-ons → Loja de add-ons**).
2. Clique no menu **⋮ (três pontinhos)** → **Repositórios**.
3. Cole a URL abaixo e clique em **Adicionar**:

   ```
   https://github.com/marcosviniciuscl/ha-appeasy
   ```

4. Feche a janela e recarregue a página. Os Apps deste repositório vão aparecer
   na loja.
5. Abra o App desejado, clique em **Instalar** e configure conforme o `DOCS.md`
   dele.

## Atualizar um App

1. Vá em **Configurações → Apps → Loja de Apps** e clique em
   **Verificar atualizações** (ou recarregue a página).
2. Abra o App e clique em **Atualizar**.

Se o botão **Atualizar** não aparecer, use **Reconstruir (Rebuild)** na página
do App.

## Estrutura do repositório

```
.
├── repository.yaml        # metadados do repositório de Apps
├── bus_tracker/           # App de ônibus (SIUMobile)
│   ├── config.yaml        # opções e metadados do App
│   ├── Dockerfile
│   ├── DOCS.md
│   └── ...
└── youtube-telegram/      # App YouTube → Telegram
    ├── config.yaml
    ├── Dockerfile
    ├── DOCS.md
    └── ...
```

## Observações

- Os Apps precisam de internet para funcionar.
- Cada App guarda a configuração em `/data` e sobrevive a reinícios e
  atualizações.
