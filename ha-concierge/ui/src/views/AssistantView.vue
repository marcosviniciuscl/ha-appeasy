<script setup>
import { computed, nextTick, ref } from 'vue'
import Avatar from 'primevue/avatar'
import Button from 'primevue/button'
import Card from 'primevue/card'
import ProgressSpinner from 'primevue/progressspinner'
import ScrollPanel from 'primevue/scrollpanel'
import Tag from 'primevue/tag'
import Textarea from 'primevue/textarea'
import { sendChat, state } from '../store'
import { providerNames } from '../utils'

const message = ref('')
const end = ref(null)

const provider = computed(() => {
  const value = state.boot?.provider || 'local'
  return value === 'local' ? 'Modo local, sem LLM externa' : providerNames[value] || value
})

async function submit() {
  const text = message.value.trim()
  if (!text || state.chatBusy) return
  message.value = ''
  await sendChat(text)
  await nextTick()
  end.value?.scrollIntoView({ block: 'end', behavior: 'smooth' })
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">CONVERSA CONTEXTUAL</span>
      <h1>Assistente</h1>
      <p class="lead">
        Pergunte sobre áreas, presença e alertas. Respostas externas só são usadas se você
        configurar um provedor.
      </p>
    </div>
    <Tag severity="secondary" :value="provider" />
  </div>

  <Card>
    <template #content>
      <ScrollPanel class="chat-scroll" :style="{ height: '420px' }">
        <div class="chat-log">
          <div v-if="!state.chat.length" class="empty-state">
            <i class="pi pi-comments" />
            Como posso ajudar com sua casa?
          </div>
          <div
            v-for="(entry, index) in state.chat"
            :key="index"
            class="chat-line"
            :class="{ mine: entry.mine }"
          >
            <Avatar
              :icon="entry.mine ? 'pi pi-user' : 'pi pi-sparkles'"
              shape="circle"
              size="normal"
            />
            <div class="bubble" :class="{ error: entry.error }">{{ entry.text }}</div>
          </div>
          <div v-if="state.chatBusy" class="chat-line">
            <Avatar icon="pi pi-sparkles" shape="circle" size="normal" />
            <div class="bubble"><ProgressSpinner style="width: 22px; height: 22px" /></div>
          </div>
          <div ref="end" />
        </div>
      </ScrollPanel>

      <form class="chat-form" @submit.prevent="submit">
        <Textarea
          v-model="message"
          autoResize
          rows="1"
          :maxlength="1000"
          placeholder="Pergunte sobre a casa"
          aria-label="Mensagem para o assistente"
          @keydown.enter.exact.prevent="submit"
        />
        <Button
          type="submit"
          label="Enviar"
          icon="pi pi-send"
          :loading="state.chatBusy"
          :disabled="!message.trim()"
        />
      </form>
      <small class="chat-provider">
        Provedor atual: {{ provider }}. O modelo recebe apenas os estados selecionados e alertas
        recentes.
      </small>
    </template>
  </Card>
</template>
