<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Tag from 'primevue/tag'
import { dismissEvent, markFalsePositive } from '../store'
import { eventSeverity, formatDate } from '../utils'

defineProps({
  events: { type: Array, default: () => [] },
})

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
  <div v-if="!events.length" class="empty-state">
    <i class="pi pi-inbox" />
    Nenhum alerta pendente.
  </div>
  <div v-else>
    <div v-for="event in events" :key="event.id" class="event-row">
      <div class="event-main">
        <div class="event-title">
          <Tag :severity="eventSeverity(event)" :value="event.severity" />
          <strong>{{ event.title }}</strong>
        </div>
        <p>{{ event.detail }}</p>
        <small><i class="pi pi-clock" />{{ formatDate(event.ts) }}</small>
      </div>
      <div v-if="!event.dismissed && event.severity !== 'info'" class="event-actions">
        <Button
          label="Dispensar"
          size="small"
          text
          :loading="busyId === event.id"
          @click="dismiss(event)"
        />
        <Button
          v-if="event.severity !== 'critical'"
          label="Falso positivo"
          size="small"
          outlined
          severity="warn"
          :disabled="busyId === event.id"
          @click="feedback(event)"
        />
      </div>
    </div>
  </div>
</template>
