# Bus Tracker

Rastreia ônibus **ao vivo** das cidades que usam o sistema **SIUMobile**
(TACOM / CIT-Siu) e mostra tudo num **painel dentro do Home Assistant**, além de
enviar avisos de aproximação e conduzir um rastreio ao vivo no celular
(Live Activity no iPhone).

Funciona hoje com **Feira de Santana (BA)** e **Belo Horizonte (MG)**, e aceita
qualquer outra cidade que use o mesmo sistema por configuração manual.

## Como usar

1. Abra o App e vá na aba **Mapa** para ver os ônibus das linhas monitoradas.
2. Em **Ônibus**, escolha quais linhas e pessoas aparecem no mapa.
3. Em **Pessoas**, cadastre quem recebe avisos (celular + localização do HA).
4. Em **Avisos**, crie regras (linha, dias, horário) para receber notificação
   quando o ônibus estiver chegando.
5. Em **Ajustes**, calibre distância, tempo entre avisos e o fuso horário.

## Cidades

Você pode escolher a cidade **dentro do painel**, na aba **Ônibus → Cidade**.
A lista de linhas (e tudo o mais) passa a usar a cidade escolhida, e a seleção
fica salva. As opções do App abaixo servem apenas como valor inicial.

| Cidade | Valor de `cidade` |
| --- | --- |
| Feira de Santana (BA) | `feira_de_santana` |
| Belo Horizonte (MG) | `belo_horizonte` |

### Outra cidade (SIUMobile)

No painel, escolha **Outra cidade…** e preencha URL base, praça e pacote. As
opções abaixo do App fazem o mesmo (e valem como valor inicial):

| Opção | Para que serve |
| --- | --- |
| `api_base` | URL base da API, ex.: `http://xxx.siumobile.com.br:6060/siumobile-ws-v01/rest/ws` |
| `api_praca` | Código da praça usado nos endpoints V3 (ex.: `BHZ`; em Feira é `null`) |
| `app_package` | Pacote do app oficial, enviado no cabeçalho `X-Requested-With` (ex.: `com.tacom.siumobilebh`) |

> Use as ferramentas de desenvolvedor do navegador ou a captura de tráfego do
> app oficial para descobrir esses três valores.

## Opções

| Opção | Padrão | Descrição |
| --- | --- | --- |
| `cidade` | `feira_de_santana` | Cidade embutida (ver tabela acima). |
| `intervalo_segundos` | `30` | Intervalo entre leituras da API (5–300 s). |
| `linhas_monitoradas` | `[]` | Linhas extras monitoradas mesmo sem aviso configurado. |
| `api_base` | — | Sobrescreve a URL base (cidade não listada). |
| `api_praca` | — | Sobrescreve o código da praça. |
| `app_package` | — | Sobrescreve o pacote do app. |

Dentro do painel, a aba **Ajustes** ainda permite mudar:

- distância para avisar, tempo mínimo entre avisos e velocidade mínima p/ o ETA;
- intervalo de leitura e de atualização do rastreio;
- fuso horário e modo simulação (não envia notificações).

## Observações

- Os avisos usam o serviço `notify.mobile_app_*` do Home Assistant; instale o
  app do HA no celular para receber.
- Os veículos também são publicados como `device_tracker.bustracker_<veiculo>`.
- A configuração do painel fica salva em `/data/bus_tracker.json` e sobrevive a
  reinícios e atualizações.
- A API do SIUMobile é pública e sem autenticação; evite consultas agressivas.
