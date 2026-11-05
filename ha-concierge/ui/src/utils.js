export const pageTitle = {
  overview: 'Visão geral',
  monitor: 'Monitoramento',
  activity: 'Atividade',
  assistant: 'Assistente',
  automations: 'Automações',
  memory: 'Memória',
  settings: 'Configurações',
}

export const providerNames = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  openrouter: 'OpenRouter',
  ollama: 'Ollama',
  compatible: 'API compatível',
}

export function formatDate(value) {
  if (!value) return 'sem registro'
  const date = new Date(typeof value === 'number' ? value * 1000 : value)
  if (Number.isNaN(date.getTime())) return 'sem registro'
  return date.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

export function eventSeverity(event) {
  if (event.severity === 'critical') return 'danger'
  if (event.severity === 'warning') return 'warn'
  return 'secondary'
}

export function eventIcon(event) {
  if (event.severity === 'critical') return 'pi pi-exclamation-octagon'
  if (event.severity === 'warning') return 'pi pi-exclamation-triangle'
  return 'pi pi-info-circle'
}

export function stateSeverity(entity) {
  if (entity.active) return 'success'
  if (entity.available) return 'warn'
  return 'danger'
}

export function stateLabel(entity) {
  if (entity.active) return 'Ativa'
  if (entity.available) return 'Sem atualização recente'
  return 'Indisponível'
}

export function proposalSeverity(status) {
  if (status === 'approved') return 'success'
  if (status === 'pending') return 'warn'
  if (status === 'rejected') return 'danger'
  return 'secondary'
}

export function proposalLabel(status) {
  return {
    pending: 'Aguardando aprovação',
    approved: 'Aprovada',
    rejected: 'Rejeitada',
    disabled: 'Desativada',
  }[status] || status
}
