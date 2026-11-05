# HA Concierge

App de monitoramento residencial para Home Assistant OS/Supervised. O painel
funciona por Ingress; dados e memória ficam em `/data`.

## O que já funciona

- Primeira execução: escolha do nome (padrão **Concierge**) e retrato das áreas,
  entidades ativas, indisponíveis e leituras recentes.
- Seleção explícita das entidades monitoradas; presença automática por
  entidades escolhidas ou modo manual.
- Alertas locais de abertura durante ausência, sensores de segurança e
  consumo acima de uma mediana recente; linha do tempo e feedback.
- Conversa local sobre áreas, presença e alertas. Adaptadores opcionais para
  OpenAI, Anthropic, Gemini, OpenRouter, Ollama e API compatível com OpenAI.
- Análise de câmera por pedido explícito; análise após alerta de segurança na
  mesma área somente com autorização adicional. Intervalo mínimo de cinco minutos.
- Preferências locais e propostas de rotina diária para luzes e interruptores.
  A execução é gerenciada pelo App depois da aprovação.

## Instalação e uso

Veja [DOCS.md](DOCS.md). O [PROMPT.md](PROMPT.md) documenta a visão completa
do produto e os critérios de expansão. Os arquivos em `.agents/` orientam o
desenvolvimento e **não contêm dados de moradores**.

## Limites atuais

A versão 0.1.0 usa amostragem REST a cada 15 segundos. Rotinas aprovadas são
executadas pelo próprio App e não aparecem como entidades de automação nativas
do Home Assistant. A análise de câmeras por evento exige opt-in. O limite de IA é por número
de chamadas, não por custo monetário. Consulte `DOCS.md` antes de usar alertas
como apoio para decisões de segurança.
