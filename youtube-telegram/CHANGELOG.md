# Changelog

## 1.0.5

- `usuarios_autorizados` agora é um campo de texto com IDs separados por vírgula.
  Contorna o bug da UI do HA que não mostra os botões de adicionar/remover em
  opções do tipo lista.

## 1.0.4

- Repositório passa a ser multi-App; nomenclatura "add-on" trocada por "App".
- Aponta as URLs para o novo repositório (`ha-appeasy`).

## 1.0.3

- Corrige o erro `Query is too old` no botão **Apagar agora**: o callback agora é
  respondido antes do delete bloqueante no MinIO.
- Adiciona timeouts de conexão/leitura no cliente do MinIO (evita travas longas).
- Registra um handler de erros (sem tracebacks para erros esperados do Telegram).

## 1.0.2

- O áudio do YouTube agora é sempre salvo em **MP3** (duas opções: bitrate
  configurado e 128 kbps), o formato preferido do Holyrics.
- O vídeo continua sendo salvo sempre em **MP4**.

## 1.0.1

- Corrige o build do Dockerfile: `run.sh` agora é executado de `/app/run.sh`.
- Re-declara os `ARG` após o `FROM` (remove o warning de `BUILD_VERSION`).
- Aponta as URLs para o repositório real do add-on.

## 1.0.0

- Versão inicial.
- Recebe links do YouTube pelo Telegram e oferece 2 opções de vídeo + 2 de áudio.
- Progresso do download/conversão na mesma mensagem.
- Envio direto no chat até o limite do Telegram (padrão 50 MB).
- Acima do limite, envia para o MinIO e entrega link pré-assinado temporário.
- Apaga o objeto do MinIO automaticamente (ou pelo botão) e faz limpeza periódica.
