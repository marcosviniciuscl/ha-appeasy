# Changelog

## 0.3.0

- Adiciona sugestões determinísticas baseadas nas entidades descobertas, com
  prioridade, motivo e ação para monitoramento, presença, segurança, consumo,
  câmeras, rotinas, baterias e entidades indisponíveis.
- Exibe as sugestões no painel e permite abrir diretamente a tela ou aba
  relacionada.
- Inclui as sugestões nas respostas locais do Assistente e no contexto enviado
  ao provedor de linguagem.

## 0.2.1

- Corrige o espaçamento do menu lateral e o fundo do breadcrumb.
- Troca a lista de modelos pelo Select pesquisável do PrimeVue, com opções
  legíveis por nome e identificador.
- Corrige o scroll automático da conversa no Assistente.
- Detecta respostas vazias dos provedores e exibe um erro claro em vez de
  bolha vazia.
- Adiciona o modo `debug` nas opções do App, com logs de provedor, modelo,
  tempos, status HTTP e erros, sem registrar chaves.

## 0.2.0

- Interface reconstruída em Vue 3 com PrimeVue v4, com tema claro/escuro,
  navegação responsiva em Drawer e componentes acessíveis.
- Novas telas: painel com métricas e tabelas, monitoramento com busca e
  paginação, linha do tempo de atividade, configurações em abas, listas
  filtráveis de modelos e diálogos de confirmação/análise.
- Build estático do painel servido pelo backend Python conservando o Ingress e
  a política de segurança de conteúdo.

## 0.1.3

- Carrega o catálogo de modelos do provedor selecionado e permite filtrar por
  nome ou identificador na configuração.

## 0.1.2

- Adicionado OpenRouter como provedor de chat e análise visual, com chave
  própria e modelo configurável.

## 0.1.1

- Exibe o App também em instalações nas quais o estágio experimental é
  filtrado pela loja.

## 0.1.0

- App instalável via Ingress e painel responsivo.
- Descoberta inicial de áreas, estados e histórico recente.
- Seleção de entidades, presença e alertas locais.
- Chat local e adaptadores de modelos remotos/opcionais.
- Memória, feedback, análise manual de câmera e propostas de rotinas.
- Análise visual automática opcional por alerta na mesma área, notificações
  persistentes opcionais e exportação/exclusão de memória.
