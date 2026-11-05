# MEMORY — especificação da memória

Este arquivo documenta o formato inicial; não contém dados de moradores.
A memória operacional deve ser persistida em `/data`, com migração de esquema,
exportação e exclusão pela interface.

## Camadas

| Camada | Exemplo | Regra |
| --- | --- | --- |
| Preferências confirmadas | horário de silêncio, nome de cômodo | editável; origem e data visíveis |
| Identidade e configuração | nome do assistente, forma de tratamento | escolhida na primeira execução; alterável |
| Perguntas pendentes | presença, alertas, consumo normal | contexto, adiamento e recusa persistidos |
| Rotinas aprendidas | luz da varanda costuma apagar às 23h | evidência mínima configurável; expira sem reforço |
| Eventos | porta abriu às 02h quando modo ausente | retenção limitada; dados mínimos |
| Propostas | automação sugerida, aprovada ou rejeitada | histórico e justificativa auditáveis |
| Resumo contextual | último estado relevante para conversa | curto, revisável e descartável |

Cada registro precisa de `id`, `tipo`, `conteudo`, `origem`, `criado_em`,
`atualizado_em`, `expira_em` quando aplicável, `confianca` quando inferido e
`confirmado_pelo_usuario`. Não registre segredos, biometria, identidade
inferida por câmera ou transcrição integral por padrão. Estabeleça períodos
de retenção configuráveis e uma opção de apagar tudo.

Perguntas graduais precisam registrar `pergunta_id`, `estado` (pendente,
respondida, adiada ou recusada), `proxima_oportunidade` e escopo da resposta.
Uma recusa deve ser respeitada; o usuário pode reabrir a configuração pela UI.

O contexto enviado a um LLM deve ser selecionado por relevância e permissão;
nunca despeje toda a memória ou o estado completo da casa no prompt.
