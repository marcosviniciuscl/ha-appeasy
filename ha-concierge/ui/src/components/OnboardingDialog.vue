<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputText from 'primevue/inputtext'
import { completeOnboarding, state } from '../store'

const firstName = ref('Concierge')
const residentName = ref('')
const saving = ref(false)

const visible = computed({
  get: () => Boolean(state.boot && !state.boot.profile.onboarded),
  set: () => {},
})

watch(
  () => state.boot?.profile,
  (profile) => {
    if (!profile) return
    firstName.value = profile.assistant_name || 'Concierge'
    residentName.value = profile.resident_name || ''
  },
  { immediate: true },
)

async function begin() {
  if (saving.value) return
  saving.value = true
  try {
    await completeOnboarding({
      assistant_name: firstName.value,
      resident_name: residentName.value,
    })
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <Dialog
    v-model:visible="visible"
    modal
    :closable="false"
    :draggable="false"
    :style="{ width: 'min(94vw, 480px)' }"
    class="onboarding-dialog"
  >
    <template #header>
      <div class="onboarding-brand">
        <span class="brand-mark"><i class="pi pi-home" /></span>
        <div>
          <strong>HA Concierge</strong>
          <small>BEM-VINDO À SUA CASA</small>
        </div>
      </div>
    </template>

    <h1 class="welcome-title">Como posso me chamar?</h1>
    <p class="welcome-copy">
      Começamos com uma leitura da casa cadastrada no Home Assistant. Você escolhe o que deseja
      acompanhar depois.
    </p>

    <div class="field">
      <label for="firstName">Nome do assistente</label>
      <InputText id="firstName" v-model="firstName" maxlength="40" autocomplete="off" />
    </div>
    <div class="field" style="margin-top: 0.9rem">
      <label for="residentName">Como devo chamar você? (opcional)</label>
      <InputText
        id="residentName"
        v-model="residentName"
        maxlength="40"
        placeholder="Pode deixar em branco"
      />
    </div>

    <div class="welcome-actions">
      <Button
        label="Conhecer minha casa"
        icon="pi pi-arrow-right"
        iconPos="right"
        :loading="saving"
        @click="begin"
      />
    </div>
  </Dialog>
</template>
