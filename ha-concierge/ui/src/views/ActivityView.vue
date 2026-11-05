<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import Timeline from 'primevue/timeline'
import { dismissEvent, markFalsePositive, state } from '../store'
import { eventIcon, eventSeverity, formatDate } from '../utils'

const busyId = ref(null)

async function dismiss(event) {
  busyId.value = event.id
  try {
    await dismissEvent(event)
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    busyId.value = null
  }
}

async function feedback(event) {
  busyId.value = event.id
  try {
    await markFalsePositive(event)
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    busyId.value = null
  }
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">REGISTRO LOCAL</span>
      <h1>Atividade</h1>
      <p class="lead">Mudanças e alertas gerados pelas entidades escolhidas.</p>
    </div>
    <Tag severity="secondary" :value="`${state.events.length} registros`" />
  </div>

  <Card>
    <template #content>
      <Timeline v-if="state.events.length" :value="state.events">
        <template #marker="{ item }">
          <span class="timeline-marker" :class="`sev-${item.severity}`">
            <i :class="eventIcon(item)" />
          </span>
        </template>
        <template #content="{ item }">
          <Card class="timeline-card">
            <template #content>
              <div class="event-title">
                <Tag :severity="eventSeverity(item)" :value="item.severity" />
                <strong>{{ item.title }}</strong>
              </div>
              <p class="fine" style="font-size: 0.8rem">{{ item.detail }}</p>
              <small class="muted"><i class="pi pi-clock" /> {{ formatDate(item.ts) }}</small>
              <div
                v-if="!item.dismissed && item.severity !== 'info'"
                class="actions"
                style="margin-top: 0.6rem"
              >
                <Button
                  label="Dispensar"
                  size="small"
                  text
                  :loading="busyId === item.id"
                  @click="dismiss(item)"
                />
                <Button
                  v-if="item.severity !== 'critical'"
                  label="Falso positivo"
                  size="small"
                  outlined
                  severity="warn"
                  :disabled="busyId === item.id"
                  @click="feedback(item)"
                />
              </div>
            </template>
          </Card>
        </template>
      </Timeline>
      <div v-else class="empty-state">
        <i class="pi pi-inbox" />
        Ainda não há eventos. Selecione entidades em Monitoramento.
      </div>
    </template>
  </Card>
</template>
