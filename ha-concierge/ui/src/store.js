import { reactive } from 'vue'
import { api } from './api'
import { notify } from './toast'

export const navItems = [
  { key: 'overview', label: 'Visão geral', icon: 'pi pi-home' },
  { key: 'monitor', label: 'Monitoramento', icon: 'pi pi-shield' },
  { key: 'activity', label: 'Atividade', icon: 'pi pi-chart-line' },
  { key: 'assistant', label: 'Assistente', icon: 'pi pi-comments' },
  { key: 'automations', label: 'Automações', icon: 'pi pi-bolt' },
  { key: 'memory', label: 'Memória', icon: 'pi pi-book' },
  { key: 'settings', label: 'Configurações', icon: 'pi pi-cog' },
]

export const state = reactive({
  boot: null,
  inv: null,
  events: [],
  memories: [],
  proposals: [],
  availableModels: [],
  modelMeta: null,
  modelsLoading: false,
  page: 'overview',
  chat: [],
  chatBusy: false,
  loading: true,
  fatal: '',
})

export function go(page) {
  state.page = page
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function perform(action, success, detail) {
  try {
    const result = await action()
    if (success) notify('success', success, detail)
    return result
  } catch (error) {
    notify('error', 'Não foi possível concluir', error.message)
    throw error
  }
}

export async function load() {
  state.loading = true
  state.fatal = ''
  try {
    const [boot, inv, events, memories, proposals] = await Promise.all([
      api('bootstrap'),
      api('inventory'),
      api('events'),
      api('memories'),
      api('proposals'),
    ])
    Object.assign(state, { boot, inv, events, memories, proposals })
  } catch (error) {
    state.fatal = error.message
  } finally {
    state.loading = false
  }
}

export async function reloadBoot() {
  state.boot = await api('bootstrap')
  return state.boot
}

export async function refresh(kind) {
  state[kind] = await api(kind)
  return state[kind]
}

export async function saveProfile(payload, message = 'Nome salvo.') {
  return perform(async () => {
    state.boot.profile = await api('profile', payload)
    return state.boot.profile
  }, message)
}

export async function completeOnboarding(payload) {
  return perform(async () => {
    state.boot.profile = await api('profile', { ...payload, onboarded: true })
    return state.boot.profile
  }, 'Casa descoberta.', 'Escolha em Monitoramento o que deve ser acompanhado.')
}

export async function saveSelection(selected) {
  return perform(async () => {
    await api('select', { selected })
    await reloadBoot()
  }, 'Seleção salva.', `${selected.length} entidades monitoradas.`)
}

export async function savePresence(payload) {
  return perform(async () => {
    await api('presence', payload)
    await reloadBoot()
  }, 'Presença configurada.')
}

export async function answerQuestion(action, value) {
  return perform(async () => {
    await api('question', {
      id: state.boot?.question?.id || 'presence',
      action,
      value,
    })
    await reloadBoot()
  }, 'Resposta registrada.')
}

export async function loadModels(provider) {
  state.modelsLoading = true
  state.modelMeta = null
  try {
    const result = await api(`models?provider=${encodeURIComponent(provider)}`)
    state.availableModels = result.models || []
    state.modelMeta = result
  } catch (error) {
    state.availableModels = []
    state.modelMeta = { source: 'error', message: error.message }
  } finally {
    state.modelsLoading = false
  }
}

export async function saveProvider(payload) {
  return perform(async () => {
    await api('settings', {
      provider: payload.provider,
      model: payload.model || '',
      daily_ai_limit: Number(payload.daily_ai_limit),
    })
    await reloadBoot()
  }, 'Provedor salvo.')
}

export async function saveNotifications(enabled) {
  return perform(async () => {
    await api('notifications', { enabled })
    await reloadBoot()
  }, 'Avisos configurados.')
}

export async function saveCameras(payload) {
  return perform(async () => {
    await api('cameras', payload)
    await reloadBoot()
  }, 'Permissões de câmera salvas.')
}

export async function dismissEvent(event) {
  return perform(async () => {
    await api('dismiss', { id: Number(event.id) })
    await refresh('events')
  }, 'Alerta dispensado.')
}

export async function markFalsePositive(event) {
  return perform(async () => {
    await api('feedback', { id: Number(event.id) })
    await refresh('events')
    await refresh('memories')
  }, 'Feedback salvo.', 'Alerta silenciado por 24 horas.')
}

export async function addMemory(content) {
  return perform(async () => {
    await api('memory', { content })
    await refresh('memories')
  }, 'Preferência salva.')
}

export async function forgetMemory(memory) {
  return perform(async () => {
    await api('forget', { id: Number(memory.id) })
    await refresh('memories')
  }, 'Preferência esquecida.')
}

export async function clearMemories() {
  return perform(async () => {
    await api('memory/clear', { confirm: 'APAGAR MEMÓRIA' })
    await refresh('memories')
    await reloadBoot()
  }, 'Memória apagada.')
}

export async function exportMemories() {
  try {
    const data = await api('memory/export')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'ha-concierge-memory.json'
    link.click()
    URL.revokeObjectURL(url)
    notify('success', 'Memória exportada.')
  } catch (error) {
    notify('error', 'Não foi possível exportar', error.message)
  }
}

export async function decideProposal(proposal, status) {
  return perform(async () => {
    await api('proposal', { id: Number(proposal.id), status })
    await refresh('proposals')
  }, 'Decisão registrada.')
}

export async function sendChat(message) {
  state.chat.push({ mine: true, text: message })
  state.chatBusy = true
  try {
    const result = await api('chat', { message })
    const answer = typeof result.answer === 'string' ? result.answer.trim() : ''
    state.chat.push(
      answer
        ? { mine: false, text: answer }
        : {
            mine: false,
            text: 'O provedor retornou uma resposta vazia. Ative o modo debug nos logs do App e verifique o modelo configurado.',
            error: true,
          },
    )
  } catch (error) {
    state.chat.push({ mine: false, text: error.message, error: true })
  } finally {
    state.chatBusy = false
  }
}

export async function analyzeCamera(entityId) {
  return perform(async () => {
    const result = await api('camera/analyze', { entity_id: entityId })
    return result.answer
  }, 'Análise concluída.')
}
