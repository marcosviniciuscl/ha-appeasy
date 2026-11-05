# Instruções para agentes de implementação

1. Leia `PROMPT.md` e `.agents/AGENT.md`, `.agents/SOUL.md` e
   `.agents/MEMORY.md` antes de alterar código neste diretório.
2. Implemente o projeto até os critérios de aceite, sem encerrar na etapa de
   planejamento ou deixar telas e rotas simuladas como produto final.
3. Preserve os Apps existentes em `bus_tracker/` e `youtube-telegram/`.
   Atualize o `README.md` da raiz quando o novo App estiver instalável.
4. Use os padrões atuais documentados pelo Home Assistant para Apps,
   comunicação com Core e Ingress. Verifique a documentação antes de fixar
   campos de `config.yaml` ou endpoints sensíveis a versão.
5. Nunca inclua tokens, imagens de câmera, perfis de moradores ou memória real
   no Git. Dados persistentes do App pertencem a `/data`.
6. Dê prioridade a funcionamento local, minimização de dados, consentimento
   explícito e explicações auditáveis. Trate saídas de LLM como propostas,
   nunca como autorização para ações no Home Assistant.
7. Ao concluir, informe arquivos criados, decisões de arquitetura, comandos
   de teste e resultados. Se algum teste exigir uma instância real do Home
   Assistant, descreva exatamente o que falta validar.
8. O painel em `ui/` usa Vue 3 com PrimeVue v4. O build é executado no estágio
   Node do Dockerfile durante a instalação/atualização do App; a saída em
   `web/` é servida pelo backend. Para testar o painel localmente, rode
   `cd ui && npm ci && npm run build` (a pasta `web/` não é versionada). Não
   versione `ui/node_modules/` nem `web/`.
