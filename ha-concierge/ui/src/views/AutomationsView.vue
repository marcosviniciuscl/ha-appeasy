<script setup>
import { ref } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Tag from 'primevue/tag'
import { useConfirm } from 'primevue/useconfirm'
import { decideProposal, state } from '../store'
import { formatDate, proposalLabel, proposalSeverity } from '../utils'

const confirm = useConfirm()
const busyId = ref(null)

function payload(proposal) {
  try {
    return JSON.parse(proposal.payload)
  } catch {
    return null
  }
}

function preview(proposal) {
  const data = payload(proposal)
  if (!data) return 'Prévia indisponível.'
  const hour = String(data.hour ?? 0).padStart(2, '0')
  const minute = String(data.minute ?? 0).padStart(2, '0')
  return `Todos os dias às ${hour}:${minute}, executar ${data.domain}.${data.service} em ${data.entity_id}.`
}

async function decide(proposal, status) {
  busyId.value = proposal.id
  try {
    await decideProposal(proposal, status)
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    busyId.value = null
  }
}

function approve(proposal) {
  confirm.require({
    message: 'Aprovar esta rotina para execução diária pelo App?',
    header: 'Aprovar rotina',
    icon: 'pi pi-check-circle',
    acceptLabel: 'Aprovar',
    rejectLabel: 'Cancelar',
    accept: () => decide(proposal, 'approved'),
  })
}

function disable(proposal) {
  confirm.require({
    message: 'Desativar esta rotina? Ela deixará de ser executada pelo App.',
    header: 'Desativar rotina',
    icon: 'pi pi-stop-circle',
    acceptLabel: 'Desativar',
    rejectLabel: 'Cancelar',
    accept: () => decide(proposal, 'disabled'),
  })
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">ROTINAS OBSERVADAS</span>
      <h1>Automações</h1>
      <p class="lead">
        Uma rotina repetida em três dias pode virar proposta. Só será executada após sua
        aprovação.
      </p>
    </div>
  </div>

  <div v-if="state.proposals.length" class="stack">
    <Card v-for="proposal in state.proposals" :key="proposal.id" class="proposal">
      <template #content>
        <div class="proposal-head">
          <h2 style="margin: 0; font-size: 1.05rem">{{ proposal.title }}</h2>
          <Tag
            :severity="proposalSeverity(proposal.status)"
            :value="proposalLabel(proposal.status)"
          />
        </div>
        <p>{{ proposal.detail }}</p>
        <p class="fine">
          Prévia: {{ preview(proposal) }} Gerenciada por este App; desativável aqui.
        </p>
        <p class="fine">{{ formatDate(proposal.ts) }} · {{ proposal.entity_id }}</p>
        <div class="actions">
          <template v-if="proposal.status === 'pending'">
            <Button
              label="Aprovar"
              icon="pi pi-check"
              :loading="busyId === proposal.id"
              @click="approve(proposal)"
            />
            <Button
              label="Rejeitar"
              icon="pi pi-times"
              severity="secondary"
              outlined
              :disabled="busyId === proposal.id"
              @click="decide(proposal, 'rejected')"
            />
          </template>
          <Button
            v-if="proposal.status === 'approved'"
            label="Desativar"
            icon="pi pi-stop"
            severity="danger"
            outlined
            :loading="busyId === proposal.id"
            @click="disable(proposal)"
          />
        </div>
      </template>
    </Card>
  </div>
  <div v-else class="empty-state">
    <i class="pi pi-bolt" />
    Nenhuma rotina recorrente detectada ainda.
  </div>
</template>
