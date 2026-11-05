<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Textarea from 'primevue/textarea'
import { useConfirm } from 'primevue/useconfirm'
import {
  addMemory,
  clearMemories,
  exportMemories,
  forgetMemory,
  state,
} from '../store'
import { formatDate } from '../utils'

const confirm = useConfirm()
const content = ref('')
const saving = ref(false)
const busyId = ref(null)

async function submit() {
  const text = content.value.trim()
  if (!text || saving.value) return
  saving.value = true
  try {
    await addMemory(text)
    content.value = ''
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    saving.value = false
  }
}

function forget(memory) {
  confirm.require({
    message: 'Esquecer esta preferência permanentemente?',
    header: 'Esquecer preferência',
    icon: 'pi pi-trash',
    acceptLabel: 'Esquecer',
    rejectLabel: 'Cancelar',
    accept: async () => {
      busyId.value = memory.id
      try {
        await forgetMemory(memory)
      } catch {
        // O aviso de erro já é exibido pelo store.
      } finally {
        busyId.value = null
      }
    },
  })
}

function clear() {
  confirm.require({
    message: 'Apagar permanentemente todas as memórias e respostas salvas?',
    header: 'Apagar memória',
    icon: 'pi pi-exclamation-triangle',
    acceptLabel: 'Apagar tudo',
    rejectLabel: 'Cancelar',
    accept: () => clearMemories().catch(() => {}),
  })
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">O QUE APRENDEMOS</span>
      <h1>Memória</h1>
      <p class="lead">
        Preferências são salvas neste App e podem ser esquecidas a qualquer momento.
      </p>
    </div>
  </div>

  <div class="grid two-col even">
    <Card>
      <template #title>
        <div class="card-title-row"><span><i class="pi pi-plus-circle" /> Adicionar preferência</span></div>
      </template>
      <template #content>
        <form @submit.prevent="submit">
          <div class="field">
            <label for="memoryInput">Algo que devo lembrar</label>
            <Textarea
              id="memoryInput"
              v-model="content"
              rows="4"
              autoResize
              :maxlength="500"
              placeholder="Ex.: não alertar sobre a varanda antes das 22h"
            />
          </div>
          <div class="actions">
            <Button
              type="submit"
              label="Salvar"
              icon="pi pi-save"
              :loading="saving"
              :disabled="!content.trim()"
            />
          </div>
        </form>
      </template>
    </Card>

    <Card>
      <template #title>
        <div class="card-title-row">
          <span><i class="pi pi-book" /> Preferências salvas</span>
          <span class="toolbar">
            <Button
              label="Exportar"
              icon="pi pi-download"
              size="small"
              severity="secondary"
              outlined
              @click="exportMemories"
            />
            <Button
              label="Apagar toda a memória"
              icon="pi pi-trash"
              size="small"
              severity="danger"
              text
              @click="clear"
            />
          </span>
        </div>
      </template>
      <template #content>
        <div v-if="state.memories.length">
          <div v-for="memory in state.memories" :key="memory.id" class="memory-row">
            <div>
              <strong>{{ memory.content }}</strong>
              <small>{{ formatDate(memory.ts) }} · {{ memory.source }}</small>
            </div>
            <Button
              label="Esquecer"
              icon="pi pi-times"
              size="small"
              severity="danger"
              text
              :loading="busyId === memory.id"
              @click="forget(memory)"
            />
          </div>
        </div>
        <div v-else class="empty-state">
          <i class="pi pi-book" />
          Ainda não há preferências salvas.
        </div>
      </template>
    </Card>
  </div>
</template>
