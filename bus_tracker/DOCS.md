# Bus Tracker

Rastreia ônibus **ao vivo** das cidades que usam o sistema **SIUMobile**
(TACOM / CIT-Siu) e mostra tudo num **painel dentro do Home Assistant**, além de
enviar avisos de aproximação e conduzir um rastreio ao vivo no celular
(Live Activity no iPhone).

Funciona hoje com **Feira de Santana (BA)** e **Belo Horizonte (MG)**, e aceita
qualquer outra cidade que use o mesmo sistema por configuração manual.

## Como usar

1. Abra o App e vá na aba **Mapa** para ver os ônibus das linhas monitoradas.
   **Toque em um ônibus** para ver a rota que ele faz (linha azul), as paradas e
   o tempo estimado até cada uma, além do sentido, destino e acessibilidade.
2. Em **Ônibus**, escolha quais linhas e pessoas aparecem no mapa.
3. Em **Pessoas**, cadastre quem recebe avisos (celular + localização do HA).
4. Em **Trajetos**, cadastre os ônibus que cada pessoa pega e os horários.
5. Em **Avisos**, crie regras (linha, dias, horário) para receber notificação
   quando o ônibus estiver chegando.
6. Em **Ajustes**, calibre distância, velocidade a pé, tempo entre avisos e fuso.

## Trajetos e caminhada

Na aba **Trajetos** você cadastra **quais ônibus cada pessoa pega**, em **quais
horários** e o **ponto de destino** (onde vai descer). É possível ter **vários
trajetos** por pessoa e **vários horários** por trajeto.

A linha **não é obrigatória**: dá para escolher **várias linhas** e, deixando
vazio, o app usa as **linhas monitoradas que passam pelo destino** (padrão) ou
descobre as **linhas da cidade** que atendem o destino (veja **Ajustes →
Comportamento → Trajeto sem linha escolhida**). O ponto de destino sai da lista
pesquisável ou é escolhido **direto no mapa** (botão *Escolher no mapa*): toque
no mapa para carregar as paradas num **raio configurável** (Ajustes → *Raio de
busca do destino no mapa*, padrão 3 km) e toque na parada desejada — só é aceito
um ponto que existe de verdade.

### O que o horário significa

Cada trajeto tem um **tipo de horário** (não obrigatório; padrão *passa no
ponto*):

| Tipo | O horário é… | O que o app faz |
| --- | --- | --- |
| **Passa no ponto** | a hora que o ônibus passa no seu ponto | destaca o ônibus que passa perto desse horário |
| **Fico livre** | a hora que você fica disponível | pega o **próximo ônibus** no ponto mais próximo depois disso |
| **Chegar no destino** | a hora que você quer chegar | acha o **melhor horário para sair** e o ônibus que ainda chega a tempo |

O ponto de embarque é sempre o **ponto mais próximo que o ônibus (indo ao
destino) atende** — a **parada oficial** mais perto ou, quando não há parada
oficial por perto, o **ponto do traçado onde o ônibus passa**. Ele não muda
enquanto você espera; quando o ônibus passa, o próximo que vier assume o
destaque. A parada oficial é preferida quando não fica muito mais longe que o
ponto do traçado.

Com isso o App calcula e mostra:

- o **ponto de embarque** (o ponto mais próximo **que fica no sentido do seu
  destino** — só entram itinerários que passam no destino e pontos antes dele,
  sejam paradas oficiais ou o ponto do traçado onde o ônibus passa) e a
  **distância** até ele;
- o **tempo a pé** calculado por **ruas** (OSRM) e a **linha da caminhada** no
  mapa, sempre até o **ponto de embarque**. Em **Ajustes → Casa** dá
  para cadastrar uma zona (por `zone.home` ou marcando no mapa), usada como
  origem quando a pessoa não tem localização no HA;
- o **ETA do ônibus** no ponto e o **tempo total** para conseguir pegá-lo;
- o **risco** de perder o ônibus: *dá tempo*, *corra* ou *pode perder*.

Perto do horário configurado, o App envia uma notificação para **sair a tempo**
e, depois, **atualizações em tempo real** com o tempo do ônibus, o seu tempo a
pé e o risco. O **rastreio ao vivo (Live Activity) começa automaticamente**
quando o ônibus cumpre as condições do trajeto e termina na chegada — não há
mais seleção manual. Os cálculos usam a posição real dos ônibus (SIUMobile) e a
sua localização no Home Assistant.

No mapa, quando um trajeto está **no horário**: o **ônibus** e o **ponto de
embarque** piscam em **azul**, a **rota** fica destacada e o **caminho até o
ponto** ganha animação de deslocamento.

## Cidades

Você escolhe a cidade **dentro do painel**, na aba **Ônibus → Cidade**. A lista
de linhas (e tudo o mais) passa a usar a cidade escolhida, e a seleção fica
salva.

| Cidade | Valor |
| --- | --- |
| Feira de Santana (BA) | `feira_de_santana` |
| Belo Horizonte (MG) | `belo_horizonte` |

### Outra cidade (SIUMobile)

No painel, escolha **Outra cidade…** e preencha URL base, praça e pacote.

| Campo | Para que serve |
| --- | --- |
| URL base | URL da API, ex.: `http://xxx.siumobile.com.br:6060/siumobile-ws-v01/rest/ws` |
| Praça | Código da praça usado nos endpoints V3 (ex.: `BHZ`; em Feira é `null`) |
| Pacote | Pacote do app oficial, enviado no cabeçalho `X-Requested-With` (ex.: `com.tacom.siumobilebh`) |

> Use as ferramentas de desenvolvedor do navegador ou a captura de tráfego do
> app oficial para descobrir esses três valores.

## Configuração

**Toda a configuração é feita dentro do painel** (aba **Ajustes**) — o App não
tem mais opções na tela de configuração do Home Assistant. Por lá você muda:

- cidade, e URL/praça/pacote para cidades não listadas;
- linhas e pessoas exibidas no mapa;
- trajetos, horários e pontos de destino;
- distância para avisar, tempos, velocidade a pé, fator de rota e margem;
- intervalo de leitura da API e de atualização do rastreio;
- raio de busca do destino no mapa, **distância máxima até o ponto de embarque**
  (trajetos mais longos que isso aparecem em cinza) e como tratar trajeto **sem
  linha escolhida**;
- fuso horário, casa/zona de referência e servidor OSRM;
- modo simulação (não envia notificações).

A configuração fica salva em `/data/bus_tracker.json` e sobrevive a reinícios e
atualizações.

## Observações

- Os avisos usam o serviço `notify.mobile_app_*` do Home Assistant; instale o
  app do HA no celular para receber.
- Os veículos também são publicados como `device_tracker.bustracker_<veiculo>`.
- A configuração do painel fica salva em `/data/bus_tracker.json` e sobrevive a
  reinícios e atualizações.
- A API do SIUMobile é pública e sem autenticação; evite consultas agressivas.
