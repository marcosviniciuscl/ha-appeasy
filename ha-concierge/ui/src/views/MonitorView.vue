<script setup>
import { computed, ref, watch } from 'vue'
import Button from 'primevue/button'
import Card from 'primevue/card'
import Checkbox from 'primevue/checkbox'
import DataView from 'primevue/dataview'
import IconField from 'primevue/iconfield'
import InputIcon from 'primevue/inputicon'
import InputText from 'primevue/inputtext'
import Select from 'primevue/select'
import Tag from 'primevue/tag'
import Toolbar from 'primevue/toolbar'
import { saveSelection, state } from '../store'
import { formatDate, stateLabel, stateSeverity } from '../utils'

const search = ref('')
const domain = ref('all')
const saving = ref(false)
const selected = ref([...(state.boot?.selected || [])])

watch(
  () => state.boot?.selected,
  (value) => {
    selected.value = [...(value || [])]
  },
  { deep: true },
)

const domains = computed(() =>
  [...new Set((state.inv?.entities || []).map((entity) => entity.domain))].sort(),
)

const domainOptions = computed(() => [
  { label: 'Todos os tipos', value: 'all' },
  ...domains.value.map((value) => ({ label: value, value })),
])

const filtered = computed(() => {
  const term = search.value.trim().toLowerCase()
  return (state.inv?.entities || []).filter((entity) => {
    const matchesDomain = domain.value === 'all' || entity.domain === domain.value
    const haystack = `${entity.name} ${entity.entity_id} ${entity.area || ''}`.toLowerCase()
    return matchesDomain && (!term || haystack.includes(term))
  })
})

const dirty = computed(() => {
  const current = [...selected.value].sort()
  const saved = [...(state.boot?.selected || [])].sort()
  return JSON.stringify(current) !== JSON.stringify(saved)
})

async function save() {
  if (!dirty.value || saving.value) return
  saving.value = true
  try {
    await saveSelection(selected.value)
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">ESCOLHAS DA CASA</span>
      <h1>Monitoramento</h1>
      <p class="lead">
        Encontramos {{ state.inv.entities.length }} entidades. Selecione as que devem gerar
        observações e alertas.
      </p>
    </div>
    <Tag severity="success" :value="`${selected.length} selecionadas`" />
  </div>

  <Card>
    <template #content>
      <Toolbar>
        <template #start>
          <IconField class="grow">
            <InputIcon class="pi pi-search" />
            <InputText v-model="search" placeholder="Buscar entidade ou cômodo" />
          </IconField>
          <Select
            v-model="domain"
            :options="domainOptions"
            optionLabel="label"
            optionValue="value"
            aria-label="Filtrar por tipo"
          />
        </template>
        <template #end>
          <Button
            label="Salvar seleção"
            icon="pi pi-save"
            :loading="saving"
            :disabled="!dirty"
            @click="save"
          />
        </template>
      </Toolbar>

      <DataView
        :value="filtered"
        layout="list"
        :paginator="filtered.length > 12"
        :rows="12"
        dataKey="entity_id"
        class="entity-view"
      >
        <template #list="{ items }">
          <div v-for="entity in items" :key="entity.entity_id" class="entity-row">
            <Checkbox
              v-model="selected"
              :inputId="`entity-${entity.entity_id}`"
              :value="entity.entity_id"
            />
            <label class="entity-main" :for="`entity-${entity.entity_id}`">
              <strong>{{ entity.name }}</strong>
              <small>
                {{ entity.entity_id }} · {{ entity.area || 'Sem área' }} ·
                {{ formatDate(entity.last_updated) }}
              </small>
            </label>
            <div class="entity-side">
              <Tag severity="secondary" :value="entity.state" />
              <Tag :severity="stateSeverity(entity)" :value="stateLabel(entity)" />
            </div>
          </div>
        </template>
        <template #empty>
          <div class="empty-state">
            <i class="pi pi-filter-slash" />
            Nenhuma entidade corresponde à busca.
          </div>
        </template>
      </DataView>

      <p class="fine">
        Ativa = estado válido atualizado nas últimas 2 horas. A seleção não altera dispositivos.
      </p>
    </template>
  </Card>
</template>
