# YouTube para Telegram

Recebe links do YouTube pelo Telegram, baixa o vídeo/áudio e devolve no chat.
Arquivos acima do limite do Telegram vão para o MinIO e são entregues por um
link temporário.

## Requisitos

- Home Assistant **OS** ou **Supervised**.
- Um **bot no Telegram** (grátis) — veja o passo 1 abaixo.
- Internet no Home Assistant.
- Opcional: um servidor **MinIO** para arquivos grandes.

## Instalação

### 1. Crie seu bot no Telegram

1. Abra o [@BotFather](https://t.me/BotFather) e envie `/newbot`.
2. Escolha um nome e um usuário para o bot.
3. Copie o **token** que ele te envia (algo como `123456789:AA...`).

### 2. Descubra o seu ID do Telegram

Fale com o [@userinfobot](https://t.me/userinfobot) e copie o campo `Id`.
É com ele que você libera o acesso ao seu bot (ou use `/id` no próprio bot).

### 3. Adicione o repositório no Home Assistant

1. Vá em **Configurações → Apps → Loja de Apps** (em versões antigas:
   **Add-ons → Loja de add-ons**).
2. Clique no menu **⋮ (três pontinhos)** → **Repositórios**.
3. Cole a URL e clique em **Adicionar**:

   ```
   https://github.com/marcosviniciuscl/ha-appeasy
   ```

### 4. Instale e configure

1. Abra o App **YouTube para Telegram** e clique em **Instalar**.
2. Na aba **Configuração**, preencha pelo menos:

   ```yaml
   telegram_token: "SEU_TOKEN_DO_BOTFATHER"
   usuarios_autorizados:
     - SEU_ID
   ```

   Clique no **+** para liberar mais de uma pessoa.

3. Clique em **Salvar** e depois em **Iniciar**.
4. No Telegram, mande `/start` para o seu bot e envie um link do YouTube.

## Uso

- Mande um link (`youtube.com`, `youtu.be`, Shorts, etc.) para o bot.
- O bot mostra o título, a duração e **2 opções de vídeo + 2 de áudio**.
- Clique na opção; o progresso aparece na própria mensagem.
- O arquivo final é enviado no chat (até o limite) ou vira um link do MinIO.
- `/id` mostra seu ID (use em `usuarios_autorizados`).
- `/start` e `/help` mostram o resumo.

## Opções

### Telegram
| Opção | Descrição |
| --- | --- |
| `telegram_token` | Token do bot (BotFather). **Obrigatório.** |
| `usuarios_autorizados` | Lista de IDs que podem usar o bot (use o **+** para adicionar vários). Vazio = todos. |
| `aceitar_grupos` | Se `true`, também responde em grupos. |

### YouTube
| Opção | Padrão | Descrição |
| --- | --- | --- |
| `youtube.ativo` | `true` | Liga/desliga o download. |
| `youtube.altura_maxima` | `1080` | Qualidade máxima oferecida (144–2160). |
| `youtube.duracao_maxima_min` | `120` | Duração máxima do vídeo, em minutos. |
| `youtube.mp3_bitrate_kbps` | `192` | Bitrate do MP3 (64–320). |
| `youtube.cookies` | — | Caminho de um `cookies.txt` (opcional). |

Sem a opção, o bot procura cookies em `/data/cookies.txt` e
`/share/youtube-cookies.txt`.

### Envio pelo Telegram
| Opção | Padrão | Descrição |
| --- | --- | --- |
| `telegram.tamanho_maximo_mb` | `50` | Limite do Bot API. Acima disso, usa o MinIO. |

### MinIO
| Opção | Padrão | Descrição |
| --- | --- | --- |
| `minio.ativo` | `false` | Liga o uso do MinIO. |
| `minio.endpoint` | — | `https://minio.exemplo.com[:porta]`. |
| `minio.access_key` | — | Chave de acesso. |
| `minio.secret_key` | — | Chave secreta. |
| `minio.bucket` | `youtube-telegram` | Bucket (criado se não existir). |
| `minio.secure` | `true` | Usa HTTPS. |
| `minio.regiao` | — | Região S3 (MinIO aceita `us-east-1`). |
| `minio.url_expira_min` | `60` | Validade do link pré-assinado, em minutos. |
| `minio.apagar_apos_min` | `70` | Apaga o objeto após X minutos (ou no botão). |

### Log
| Opção | Padrão | Descrição |
| --- | --- | --- |
| `log.nivel` | `INFO` | `DEBUG`, `INFO`, `WARNING` ou `ERROR`. |

Os logs saem no log do App (aba **Log**) e também em
`/data/youtube-telegram.log`.

## Arquivos grandes (MinIO)

O Telegram só deixa bots enviarem arquivos de até **50 MB**. Para arquivos
maiores, ative o MinIO em **Configuração**:

```yaml
minio:
  ativo: true
  endpoint: "https://minio.seudominio.com"
  access_key: "SUA_ACCESS_KEY"
  secret_key: "SUA_SECRET_KEY"
  bucket: "youtube-telegram"
  secure: true
  url_expira_min: 60
  apagar_apos_min: 70
```

Como funciona:

1. O arquivo é enviado ao seu MinIO.
2. O bot manda um **link temporário** junto com um botão
   **“🗑 Já baixei — apagar agora”**.
3. O arquivo é apagado quando você toca no botão ou, no mais tardar, depois de
   `apagar_apos_min` minutos.

O bucket é criado automaticamente se não existir e pode continuar **privado** —
o link é assinado e temporário.

## Quando o YouTube pede verificação

Se o download falhar com a mensagem *“Sign in to confirm you're not a bot”*,
exporte os cookies do seu navegador para um arquivo no formato **Netscape
(cookies.txt)** e coloque em um destes locais:

- `/share/youtube-cookies.txt` (recomendado), ou
- `/data/cookies.txt`, ou
- aponte o caminho na opção `youtube.cookies`.

Uma extensão de navegador como *Get cookies.txt* ajuda a exportar o arquivo.

## Problemas comuns

| Situação | O que fazer |
| --- | --- |
| O bot não responde | Confira o `telegram_token` e veja o **Log** do App. |
| “Não autorizado” | Adicione seu ID em `usuarios_autorizados` (use `/id` para ver). |
| “Passa do limite do Telegram” e o MinIO está desligado | Ative o MinIO ou escolha uma qualidade/áudio menor. |
| “Sign in to confirm you're not a bot” | Configure os cookies (seção acima). |
| Vídeo longo é recusado | Ajuste `youtube.duracao_maxima_min`. |

## Observações

- Os arquivos baixados ficam em `/tmp` dentro do container e são apagados ao
  final de cada download.
- O bot respeita o limite de upload do Telegram (50 MB). Não há como enviar
  arquivos maiores pelo Bot API — por isso o MinIO.
- Para usar um bucket privado, nada mais é preciso: os links são pré-assinados.
