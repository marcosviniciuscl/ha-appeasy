<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import DataTable from 'primevue/datatable'
import Column from 'primevue/column'
import DataView from 'primevue/dataview'
import Message from 'primevue/message'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import EventList from '../components/EventList.vue'
import { answerQuestion, go, refreshSuggestions, state } from '../store'
import { formatDate } from '../utils'

const questionChoice = ref(null)
const answering = ref(false)

const boot = computed(() => state.boot)
const inventory = computed(() => state.inv)
const alerts = computed(() =>
  state.events.filter((event) => !event.dismissed && event.severity !== 'info'),
)
const question = computed(() => boot.value?.question)
const selectedCount = computed(() => boot.value?.selected?.length || 0)

watch(
  question,
  (value) => {
    questionChoice.value = value?.choices?.[0]?.id ?? null
  },
  { immediate: true },
)

const greeting = computed(() => {
  const hour = new Date().getHours()
  const part = hour < 12 ? 'dia' : hour < 18 ? 'tarde' : 'noite'
  const resident = boot.value?.profile?.resident_name
  return `Bom ${part}${resident ? ', ' + resident : ''}.`
})

const activeRatio = computed(() => {
  const total = inventory.value?.entities?.length || 0
  if (!total) return 0
  return Math.round(((inventory.value?.active_count || 0) / total) * 100)
})

const areas = computed(() => (inventory.value?.areas || []).slice(0, 7))

const recent = computed(() =>
  Object.entries(inventory.value?.recent || {})
    .slice(0, 8)
    .map(([entity_id, value]) => ({ entity_id, ...value })),
)

const presenceSeverity = computed(() => {
  const mode = boot.value?.presence?.[0]
  if (mode === 'home') return 'success'
  if (mode === 'away') return 'warn'
  return 'secondary'
})

const suggestions = computed(() => state.suggestions || [])

const suggestionIcons = {
  security: 'pi pi-shield',
  presence: 'pi pi-users',
  energy: 'pi pi-bolt',
  automation: 'pi pi-sun',
  camera: 'pi pi-camera',
  maintenance: 'pi pi-wrench',
  monitor: 'pi pi-list-check',
  system: 'pi pi-info-circle',
}

const suggestionLabels = { high: 'Prioridade alta', medium: 'Sugestão', low: 'Oportunidade' }

function suggestionIcon(item) {
  return suggestionIcons[item.kind] || 'pi pi-lightbulb'
}

function suggestionSeverity(item) {
  if (item.priority === 'high') return 'warn'
  if (item.priority === 'medium') return 'info'
  return 'secondary'
}

function runSuggestion(item) {
  const targets = {
    'settings-presence': ['settings', 'presence'],
    'settings-cameras': ['settings', 'cameras'],
    'settings-notifications': ['settings', 'notifications'],
    'settings-model': ['settings', 'model'],
    automations: ['automations'],
    activity: ['activity'],
    monitor: ['monitor'],
  }
  const [page, tab] = targets[item.action] || ['monitor']
  go(page, tab)
}

async function answer(action) {
  answering.value = true
  try {
    await answerQuestion(action, questionChoice.value)
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    answering.value = false
  }
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">PAINEL DA CASA</span>
      <h1>{{ greeting }}</h1>
      <p class="lead">
        Um retrato do que o Home Assistant informa agora. Você decide o que será monitorado.
      </p>
    </div>
    <Tag severity="secondary" :value="`Atualizado ${formatDate(inventory.retrieved_at)}`" />
  </div>

  <Message v-if="boot.connection_error" severity="error" :closable="false">
    Conexão com o Home Assistant: {{ boot.connection_error }}
  </Message>

  <Message v-if="question" severity="info" :closable="false">
    <div class="stack" style="gap: 0.6rem">
      <strong>{{ question.title }}</strong>
      <span>{{ question.detail }}</span>
      <div class="toolbar">
        <Select
          v-model="questionChoice"
          :options="question.choices"
          optionLabel="name"
          optionValue="id"
          class="grow"
          placeholder="Escolha uma entidade"
        />
        <Button
          label="Salvar resposta"
          icon="pi pi-check"
          :loading="answering"
          @click="answer('answer')"
        />
        <Button label="Agora não" severity="secondary" outlined @click="answer('later')" />
        <Button label="Não perguntar novamente" text severity="secondary" @click="answer('never')" />
      </div>
    </div>
  </Message>

  <div class="grid metric-grid">
    <Card class="metric-card">
      <template #content>
        <span class="metric-label">ÁREAS CADASTRADAS</span>
        <strong class="metric-value">{{ inventory.area_count }}</strong>
        <span class="metric-hint">Podem não representar todos os cômodos físicos</span>
      </template>
    </Card>
    <Card class="metric-card">
      <template #content>
        <span class="metric-label">ENTIDADES ATIVAS</span>
        <strong class="metric-value">{{ inventory.active_count }}</strong>
        <span class="metric-hint">
          de {{ inventory.entities.length }} encontradas · janela de 2 horas
        </span>
        <ProgressBar :value="activeRatio" :showValue="false" class="metric-bar" />
      </template>
    </Card>
    <Card class="metric-card">
      <template #content>
        <span class="metric-label">ALERTAS PENDENTES</span>
        <strong class="metric-value">{{ alerts.length }}</strong>
        <span class="metric-hint">{{ selectedCount }} entidades monitoradas</span>
      </template>
    </Card>
  </div>

  <Card class="suggestions-card">
    <template #title>
      <div class="card-title-row">
        <span><i class="pi pi-lightbulb" /> Sugestões para a sua casa</span>
        <Button
          icon="pi pi-refresh"
          text
          rounded
          size="small"
          :loading="state.suggestionsLoading"
          aria-label="Atualizar sugestões"
          v-tooltip.bottom="'Atualizar sugestões'"
          @click="refreshSuggestions"
        />
      </div>
    </template>
    <template #content>
      <div v-if="state.suggestionsLoading && !suggestions.length" class="empty-state">
        <i class="pi pi-spin pi-spinner" /> Analisando as entidades…
      </div>
      <div v-else-if="suggestions.length" class="suggestion-list">
        <div v-for="item in suggestions" :key="item.id" class="suggestion-row">
          <span class="suggestion-icon"><i :class="suggestionIcon(item)" /></span>
          <div class="suggestion-main">
            <div class="suggestion-title">
              <strong>{{ item.title }}</strong>
              <Tag :severity="suggestionSeverity(item)" :value="suggestionLabels[item.priority]" />
            </div>
            <p>{{ item.detail }}</p>
            <small>{{ item.reason }}</small>
          </div>
          <Button :label="item.action_label" size="small" outlined @click="runSuggestion(item)" />
        </div>
      </div>
      <div v-else class="empty-state">
        <i class="pi pi-check-circle" />
        Nada pendente. As propostas de rotina aparecem após alguns dias de observação.
      </div>
    </template>
  </Card>

  <div class="grid two-col">
    <Card>
      <template #title>
        <div class="card-title-row">
          <span><i class="pi pi-bell" /> O que merece atenção</span>
          <Tag v-if="alerts.length" severity="warn" :value="`${alerts.length} pendentes`" />
        </div>
      </template>
      <template #content>
        <EventList :events="alerts.slice(0, 5)" />
      </template>
    </Card>

    <Card>
      <template #title>
        <div class="card-title-row">
          <span><i class="pi pi-th-large" /> Áreas da casa</span>
        </div>
      </template>
      <template #content>
        <DataView v-if="areas.length" :value="areas" layout="list">
          <template #list="{ items }">
            <div v-for="area in items" :key="area.name" class="area-row">
              <div>
                <strong>{{ area.name }}</strong>
                <small>{{ area.entity_count }} entidades</small>
              </div>
              <Tag severity="success" value="Área" />
            </div>
          </template>
        </DataView>
        <div v-else class="empty-state">
          <i class="pi pi-map" />
          Nenhuma área cadastrada no Home Assistant.
        </div>
      </template>
    </Card>
  </div>

  <div class="grid two-col">
    <Card>
      <template #title>
        <div class="card-title-row">
          <span><i class="pi pi-history" /> Dados recentes</span>
        </div>
      </template>
      <template #content>
        <DataTable
          v-if="recent.length"
          :value="recent"
          dataKey="entity_id"
          size="small"
          scrollable
          scrollHeight="260px"
        >
          <Column field="entity_id" header="Entidade" />
          <Column field="state" header="Estado" />
          <Column header="Atualizado">
            <template #body="{ data }">
              <span class="muted">{{ formatDate(data.at) }}</span>
            </template>
          </Column>
        </DataTable>
        <div v-else class="empty-state">
          <i class="pi pi-database" />
          Histórico recente não disponível para os sensores consultados.
        </div>
      </template>
    </Card>

    <Card class="house-status">
      <template #title>
        <div class="card-title-row">
          <span><i class="pi pi-heart" /> Como está a casa</span>
          <Tag :severity="presenceSeverity" :value="boot.presence[0]" />
        </div>
      </template>
      <template #content>
        <p>{{ boot.presence[1] }}.</p>
        <p class="fine">
          {{ inventory.unavailable_count }} entidades indisponíveis.
          <template v-if="inventory.registry_failures.length">
            Não foi possível consultar: {{ inventory.registry_failures.join(', ') }}.
          </template>
        </p>
        <Button
          label="Escolher entidades"
          icon="pi pi-arrow-right"
          iconPos="right"
          severity="secondary"
          outlined
          @click="go('monitor')"
        />
      </template>
    </Card>
  </div>
</template>
