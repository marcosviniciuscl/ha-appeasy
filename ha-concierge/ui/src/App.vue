<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Button from 'primevue/button'
import Breadcrumb from 'primevue/breadcrumb'
import Drawer from 'primevue/drawer'
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import Tag from 'primevue/tag'
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
import { useToast } from 'primevue/usetoast'
import SidebarContent from './components/SidebarContent.vue'
import OnboardingDialog from './components/OnboardingDialog.vue'
import OverviewView from './views/OverviewView.vue'
import MonitorView from './views/MonitorView.vue'
import ActivityView from './views/ActivityView.vue'
import AssistantView from './views/AssistantView.vue'
import AutomationsView from './views/AutomationsView.vue'
import MemoryView from './views/MemoryView.vue'
import SettingsView from './views/SettingsView.vue'
import { load, state } from './store'
import { toast } from './toast'
import { pageTitle, providerNames } from './utils'

const toastService = useToast()
toast.add = toastService.add
toast.remove = toastService.remove

const views = {
  overview: OverviewView,
  monitor: MonitorView,
  activity: ActivityView,
  assistant: AssistantView,
  automations: AutomationsView,
  memory: MemoryView,
  settings: SettingsView,
}

const currentView = computed(() => views[state.page] || OverviewView)
const breadcrumbHome = { icon: 'pi pi-home', command: () => (state.page = 'overview') }
const breadcrumb = computed(() => [{ label: pageTitle[state.page] || 'Visão geral' }])

const mobile = ref(false)
const navOpen = ref(false)
const dark = ref(localStorage.getItem('concierge-theme') === 'dark')
const clock = ref('')
let media
let timer

function updateClock() {
  clock.value = new Date().toLocaleString('pt-BR', {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function onMediaChange(event) {
  mobile.value = event.matches
  if (!event.matches) navOpen.value = false
}

watch(
  dark,
  (value) => {
    document.documentElement.classList.toggle('app-dark', value)
    localStorage.setItem('concierge-theme', value ? 'dark' : 'light')
  },
  { immediate: true },
)

const connectionSeverity = computed(() => (state.boot?.connection_error ? 'danger' : 'success'))
const connectionLabel = computed(() =>
  state.boot?.connection_error ? 'Home Assistant indisponível' : 'Home Assistant conectado',
)
const providerLabel = computed(() => {
  const provider = state.boot?.provider || 'local'
  return provider === 'local' ? 'Sem LLM externa' : providerNames[provider] || provider
})

onMounted(() => {
  media = window.matchMedia('(max-width: 820px)')
  mobile.value = media.matches
  media.addEventListener('change', onMediaChange)
  updateClock()
  timer = window.setInterval(updateClock, 30000)
  load()
})

onBeforeUnmount(() => {
  media?.removeEventListener('change', onMediaChange)
  window.clearInterval(timer)
})

function toggleTheme() {
  dark.value = !dark.value
}
</script>

<template>
  <div class="app-shell">
    <aside v-if="!mobile" class="app-sidebar">
      <SidebarContent />
    </aside>

    <main class="app-main">
      <div class="app-topbar">
        <div class="toolbar">
          <Button
            v-if="mobile"
            icon="pi pi-bars"
            text
            rounded
            aria-label="Abrir menu"
            @click="navOpen = true"
          />
          <Breadcrumb :home="breadcrumbHome" :model="breadcrumb" />
        </div>
        <div class="topbar-end">
          <Tag
            v-if="state.boot"
            :severity="connectionSeverity"
            :value="connectionLabel"
            :icon="state.boot.connection_error ? 'pi pi-exclamation-circle' : 'pi pi-check-circle'"
          />
          <span class="clock">{{ clock }}</span>
          <Button
            :icon="dark ? 'pi pi-sun' : 'pi pi-moon'"
            text
            rounded
            :aria-label="dark ? 'Usar tema claro' : 'Usar tema escuro'"
            v-tooltip.bottom="dark ? 'Tema claro' : 'Tema escuro'"
            @click="toggleTheme"
          />
        </div>
      </div>

      <div class="app-content">
        <Message v-if="state.fatal" severity="error" :closable="false">
          {{ state.fatal }}. Verifique a conexão com o Home Assistant e recarregue.
        </Message>
        <div v-else-if="state.loading" class="loading-screen">
          <ProgressSpinner strokeWidth="4" />
          <span>Conversando com o Home Assistant…</span>
        </div>
        <component :is="currentView" v-else />
      </div>
    </main>

    <Drawer v-model:visible="navOpen" position="left" header="Navegação" class="nav-drawer">
      <SidebarContent />
      <div class="fine">Modelo em uso: {{ providerLabel }}</div>
    </Drawer>

    <OnboardingDialog />
    <Toast position="top-right" />
    <ConfirmDialog />
  </div>
</template>
