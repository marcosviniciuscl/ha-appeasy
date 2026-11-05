# Prompt mestre — implementar HA Concierge

Você é um agente de engenharia responsável por **entregar um App funcional e
instalável para Home Assistant OS/Supervised** neste repositório. O projeto se
chama **HA Concierge**. Leia `ha-concierge/AGENTS.md` e `.agents/*.md`, inspecione
os Apps existentes e implemente o produto até os critérios de aceite abaixo.
Não termine com uma proposta, um mockup ou um esqueleto: entregue código,
interface, documentação, testes e instruções de instalação. Resolva decisões
com bom julgamento; só peça dados da instalação do usuário quando forem
indispensáveis. Não use nomes ou identidade visual de personagens de ficção.

## Objetivo

Criar um assistente residencial proativo que observe **somente** entidades
selecionadas do Home Assistant, perceba padrões e anomalias, contextualize
eventos com presença e horário, converse sobre o estado da casa, sugira ações
e aprenda preferências com feedback. Deve aceitar sensores de energia, água,
gás, portas, janelas, movimento, clima, presença e câmeras quando disponíveis.
Deve ser útil também em casas sem câmeras ou medidores. Não prometa detecção
infalível nem substituição de dispositivos de segurança.

## Entrega e estrutura

- Crie o App em `ha-concierge/` com `config.yaml`, `Dockerfile`, inicialização,
  backend, frontend, `DOCS.md`, `CHANGELOG.md`, ícone e logo próprios, testes e
  arquivos de dependência fixados em versões. Use `/data` para estado e
  segredos. Ajuste o `README.md` do repositório após o App estar instalável.
- Ofereça UI via Ingress, sem porta pública por padrão, com caminhos de assets,
  APIs e WebSocket funcionando sob prefixo de Ingress. Siga os requisitos de
  segurança do Home Assistant; use o menor acesso do Supervisor necessário.
- A arquitetura deve separar: cliente Home Assistant, ingestão de eventos,
  regras/anomalias, orquestração do agente, provedores LLM/visão, memória,
  política de ações, notificações, API e frontend. Use fila assíncrona ou
  equivalente para tarefas caras, com cancelamento, backoff e limites.
- Escolha stack que rode em `amd64` e `aarch64` sem complexidade desnecessária.
  Documente a escolha. Não dependa de serviço proprietário obrigatório.

## Integração com Home Assistant

- Na primeira execução, faça uma descoberta **somente de leitura** do Home
  Assistant: inventário de áreas, dispositivos, entidades e seus estados.
  Consulte histórico recente de forma limitada e paginada para mostrar o que
  teve atividade, quando ocorreu a última leitura válida e quais sensores
  oferecem dados suficientes para uma análise inicial. Descobrir e resumir
  não equivale a habilitar monitoramento contínuo.
- Gere um retrato inicial em linguagem simples: quantos cômodos/áreas estão
  cadastrados, quais estão sem entidades, principais tipos de sensores,
  câmeras e medidores disponíveis, entidades ativas, indisponíveis ou sem
  atualização recente, e quais informações ainda não existem. Use as **áreas
  cadastradas** como base para a contagem de cômodos e diga quando não for
  possível inferir o número real de cômodos. Não invente nomes nem quantidades.
- Defina "ativa" na interface com critério claro (estado válido e atualização
  dentro de janela configurável); diferencie isso de entidade apenas habilitada
  no HA. Mostre hora e origem do dado, inclusive quando o histórico estiver
  indisponível. Limite volume de consultas para não sobrecarregar o Recorder.
- Descubra entidades, áreas e dispositivos e permita buscar, filtrar e marcar
  individualmente o que será monitorado. Mostre domínio, área, estado, última
  atualização e disponibilidade. Nenhuma entidade é monitorada antes de ser
  habilitada pelo usuário.
- Use APIs oficiais do Home Assistant para estados, eventos, histórico quando
  apropriado e chamadas de serviços. Reconecte após falha e retome sem perder
  configuração. Trate `unknown`, `unavailable`, reinício e mudanças de ID.
- Configure presença por entidades selecionadas e um modo manual opcional.
  Indique sempre o motivo do modo casa/ausente e incerteza. Não inferir que
  ninguém está em casa apenas pela falta de movimento.
- Para energia, água e gás, suporte unidades e classes do HA, leituras
  cumulativas ou instantâneas, resets de medidor e ausência de dados. Gere
  tendências, consumo atípico e possíveis vazamentos com limiares editáveis.
- Câmeras: seleção explícita, captura sob demanda ou disparada por evento
  relevante, cooldown e limite diário. Analise imagens somente com provedor
  visual configurado e consentimento específico para envio externo. Exiba
  motivo da captura; faça retenção mínima e evite armazenar imagens por padrão.

## Inteligência, memória e custos

- Implemente adaptadores para **OpenAI, Anthropic, Google Gemini, Ollama local**
  e um endpoint compatível com OpenAI. Se algum provedor não oferecer visão ou
  ferramentas, exponha a limitação com clareza. IDs de modelo e capacidades
  devem ser configuráveis; não prenda o produto a nomes de modelos atuais.
- Permita modelo distinto para chat, análise de evento e visão; chave por
  provedor, teste de conexão, fallback configurável, limite de gasto/chamadas,
  estatísticas de uso e desligamento imediato. Segredos devem ser protegidos
  em repouso com mecanismo documentado e nunca sair nos logs/API/UI.
- Reduza chamadas: regras locais primeiro, deduplicação, debounce, resumo de
  contexto, cache com prazo, lote de eventos e análise visual só quando
  necessária. Um problema crítico conhecido por regra local deve gerar alerta
  mesmo se o LLM estiver indisponível.
- Use `SOUL.md`, `AGENT.md` e `MEMORY.md` como modelos conceituais. Crie cópias
  operacionais editáveis em `/data` ou estrutura equivalente, versionada por
  esquema. Mostre na UI o que foi aprendido, por quê, quando e como apagar.
  Só consolide preferência pessoal após confirmação ou evidência suficiente
  definida e visível. Feedback de falso positivo deve reduzir recorrência.
- Proteja contra injeção de prompt em nomes/atributos de entidade, respostas
  do modelo e conteúdo de imagem. Saída estruturada é validada no backend.

## Automações e ações

- Detecte rotinas repetidas com critérios transparentes (quantidade de
  ocorrências, estabilidade de horário/contexto, exceções, economia estimada).
  Ofereça **proposta** de automação com gatilho, condições, ação, entidades,
  motivo, risco, economia esperada, simulação e forma de desfazer.
- A criação e ativação de automação no Home Assistant dependem de aprovação
  explícita na interface. Não use arquivo YAML do usuário sem necessidade;
  escolha mecanismo oficial suportado e teste ciclo completo. Evite propostas
  duplicadas e respeite rejeições.
- Ações diretas também passam por política de permissão por entidade e
  serviço. Padrão: leitura e notificações; alterações físicas exigem opt-in.
  Ações críticas (fechadura, alarme, portão, gás, energia geral) exigem
  confirmação humana por padrão. Registre auditoria de proposta, aprovação,
  execução, resultado e reversão, sem segredos.

## Interface

Construa uma interface responsiva, moderna e discreta, com qualidade de
produto residencial, **sem visual genérico de chatbot/IA**: tipografia clara,
hierarquia forte, paleta sóbria, microinterações contidas, bom contraste e
acessibilidade por teclado. Português brasileiro completo; prepare i18n.
Não use emojis como ícones principais nem painéis repletos de brilho neon.

### Primeira execução e aprendizado gradual

Na primeira abertura, apresente uma recepção curta e pergunte **como o
assistente deve ser chamado**, com **Concierge** preenchido como nome padrão.
Permita aceitar o padrão em um toque e trocar depois. Pergunte opcionalmente
como deve chamar a pessoa, sem bloquear o uso se ela pular. Salve as escolhas
em `/data` e reflita o nome na interface e nas notificações.

Em seguida, execute a descoberta inicial e mostre o retrato da casa com
contagens e exemplos reais, dados recentes e suas datas, além de lacunas. Dê
ao usuário a oportunidade de corrigir nomes de áreas e selecionar os primeiros
grupos/entidades para monitorar. Peça apenas as permissões indispensáveis para
começar. Provedor de LLM, câmeras, notificações, presença e poderes de ação
podem ser configurados depois, quando a função for relevante. A configuração
inicial deve poder ser retomada sem perder respostas.

Depois do início, faça perguntas contextuais **uma por vez**, em momentos
apropriados e com opções "agora não" e "não perguntar novamente". Exemplos:
qual sensor representa presença, o que é um consumo normal, se um alerta foi
útil, se determinada rotina deve virar automação. Não interrompa um alerta
urgente para perguntar preferências. Registre resposta, origem, data,
consentimento e escopo; evite perguntar de novo o que já foi respondido e
permita revisão e exclusão na tela de Memória. Inferências de rotina devem
ser apresentadas como hipótese antes de virarem preferência confirmada.

Telas necessárias:

1. **Visão geral**: estado da casa, modo de presença, alertas, eventos recentes,
   consumo resumido e o que merece atenção.
2. **Monitoramento**: seleção de entidades por área/tipo, detalhes, regras,
   limiares e estado da coleta.
3. **Atividade**: linha do tempo filtrável com evidências, gravidade, origem e
   ações tomadas; controles para falso positivo.
4. **Assistente**: conversa contextual com referências a entidades e horários,
   explicação de limites e ações propostas com confirmação explícita.
5. **Automações**: sugestões, simulação, aprovar/rejeitar, ativas e histórico.
6. **Memória**: preferências e rotinas aprendidas; editar, confirmar, esquecer,
   exportar e apagar tudo.
7. **Configurações**: provedores/modelos, orçamento, privacidade/câmeras,
   notificações, permissões, retenção e diagnóstico de conexão.

Inclua estados vazios úteis, carregamento, falhas recuperáveis e explicação de
por que um alerta foi emitido. Não exponha streams ou snapshots de câmera em
miniaturas sem habilitação explícita.

## Segurança e privacidade

- Configuração inicial progressiva: nome do assistente, retrato da casa e
  seleção inicial de entidades; demais preferências e permissões são pedidas
  quando necessárias, com opção de adiar. O produto funciona em modo básico
  sem LLM e sem envio de dados para nuvem.
- Dados locais por padrão; fluxo de dados para cada provedor explicado na UI.
  Granularidade por entidade/câmera, retenção e consentimento revogável.
- Proteja endpoint Ingress, valide entrada, limite chamadas, evite SSRF em URL
  de provedor e não permita que o navegador acesse credenciais do Supervisor.
  Faça backup/restauração da base sem segredos em texto puro.
- Separe observação, recomendação e execução. Toda ação deve ser auditável.
  Alertas de fumaça, vazamento ou intrusão devem recomendar verificação e
  não apresentar certeza indevida.

## Testes e critérios de aceite

Crie testes de unidade para normalização, regras, presença, limites de custo,
memória e política de ação; testes de integração com HA e LLM simulados; e um
fluxo de UI automatizado ou reproduzível. Use fixtures de eventos sintéticos,
sem dados pessoais. Execute lint, testes e build da UI/container quando o
ambiente permitir. Documente comandos e resultados.

O trabalho só está concluído quando for possível demonstrar:

1. Instalação do App pelo repositório e abertura do painel por Ingress.
2. Primeira execução pergunta o nome do assistente com "Concierge" como padrão,
   descobre áreas e entidades, resume dados recentes com timestamps e lacunas,
   e distingue descoberta de monitoramento. Seleções e respostas persistem
   após reinício.
3. Alerta local para porta aberta em modo ausente e para consumo anômalo,
   inclusive sem LLM; sem alerta quando dado estiver indisponível.
4. Câmera desabilitada sem captura; habilitada analisa apenas no evento
   permitido, respeitando cooldown e escolha de envio à nuvem.
5. Troca entre provedor remoto e Ollama, com falha/fallback visível e limite
   de gasto impedindo nova chamada.
6. Preferência aprendida explicável, corrigível e apagável.
7. Rotina repetida gera proposta de automação; nenhuma é criada ou ativada
   antes da aprovação; rejeição e reversão funcionam.
8. Uma saída maliciosa do modelo ou nome de entidade não consegue chamar
   serviço fora da allowlist.
9. UI utilizável em celular e desktop, com estados de erro e vazios.
10. Nenhum segredo, imagem ou dado pessoal em Git, logs ou respostas de API.
11. Uma pergunta posterior pode ser adiada ou recusada; a resposta salva pode
    ser vista, corrigida e apagada sem reaparecer indevidamente.

## Modo de execução

Trabalhe em etapas completas: infraestrutura do App e conexão HA; persistência
e seleção de entidades; regras e alertas; provedores; memória; automações;
frontend; testes e documentação. A cada etapa, integre ao produto real. Não
deixe TODOs que substituam requisitos centrais. No fim, apresente resumo do
que funciona, como instalar, como testar e qualquer limite que dependa de
uma instância real do Home Assistant ou credenciais do usuário.

## Referências oficiais a conferir durante a implementação

- [Desenvolvimento de Apps](https://developers.home-assistant.io/docs/apps/)
- [Apresentação e Ingress](https://developers.home-assistant.io/docs/apps/presentation/)
- [API REST](https://developers.home-assistant.io/docs/api/rest/)
- [API WebSocket](https://developers.home-assistant.io/docs/api/websocket/)
