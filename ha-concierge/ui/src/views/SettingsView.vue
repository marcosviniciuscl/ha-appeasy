<script setup>
import { computed, reactive, ref, watch } from 'vue'
import Button from 'primevue/button'
import Dialog from 'primevue/dialog'
import InputNumber from 'primevue/inputnumber'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import MultiSelect from 'primevue/multiselect'
import ProgressBar from 'primevue/progressbar'
import Select from 'primevue/select'
import Tab from 'primevue/tab'
import TabList from 'primevue/tablist'
import TabPanel from 'primevue/tabpanel'
import TabPanels from 'primevue/tabpanels'
import Tabs from 'primevue/tabs'
import Tag from 'primevue/tag'
import ToggleSwitch from 'primevue/toggleswitch'
import { useConfirm } from 'primevue/useconfirm'
import {
  analyzeCamera,
  loadModels,
  saveCameras,
  saveNotifications,
  savePresence,
  saveProfile,
  saveProvider,
  state,
} from '../store'
import { providerNames } from '../utils'

const confirm = useConfirm()
const tab = ref('identity')

const profile = reactive({ assistant_name: '', resident_name: '' })
const identitySaving = ref(false)
const presenceSaving = ref(false)
const modelSaving = ref(false)
const cameraSaving = ref(false)
const notificationsSaving = ref(false)

const manual = ref(state.boot.manual_mode)
const presenceEntities = ref([...(state.boot.presence_entities || [])])

const provider = ref(state.boot.provider)
const model = ref(state.boot.model || '')
const dailyLimit = ref(state.boot.daily_ai_limit ?? 50)

const allowedCameras = ref([...(state.boot.camera_allowed || [])])
const cameraCloud = ref(Boolean(state.boot.camera_cloud))
const cameraAuto = ref(Boolean(state.boot.camera_auto))
const analyzingId = ref(null)
const analysisVisible = ref(false)
const analysisText = ref('')
const analysisEntity = ref('')

const notificationsEnabled = ref(Boolean(state.boot.notifications_enabled))

watch(
  () => state.boot.profile,
  (value) => {
    if (!value) return
    profile.assistant_name = value.assistant_name
    profile.resident_name = value.resident_name
  },
  { immediate: true, deep: true },
)

watch(
  () => state.boot.presence_entities,
  (value) => {
    presenceEntities.value = [...(value || [])]
  },
  { deep: true },
)

watch(
  () => state.boot.manual_mode,
  (value) => {
    manual.value = value
  },
)

watch(
  () => state.boot.camera_allowed,
  (value) => {
    allowedCameras.value = [...(value || [])]
  },
  { deep: true },
)

watch(
  () => state.boot.notifications_enabled,
  (value) => {
    notificationsEnabled.value = Boolean(value)
  },
)

watch(
  provider,
  (value) => {
    model.value = value === state.boot.provider ? state.boot.model || '' : ''
    loadModels(value)
  },
  { immediate: true },
)

const providerOptions = computed(() => [
  { label: 'Local sem LLM', value: 'local' },
  ...Object.keys(state.boot.models || {}).map((key) => ({
    label: providerNames[key] || key,
    value: key,
  })),
])

const manualOptions = [
  { label: 'Automático', value: 'auto' },
  { label: 'Em casa', value: 'home' },
  { label: 'Ausente', value: 'away' },
]

const presenceOptions = computed(() =>
  (state.inv.entities || []).filter(
    (entity) =>
      state.boot.selected.includes(entity.entity_id) &&
      ['person', 'device_tracker', 'binary_sensor'].includes(entity.domain),
  ),
)

const cameraOptions = computed(() =>
  (state.inv.entities || []).filter(
    (entity) => entity.domain === 'camera' && state.boot.selected.includes(entity.entity_id),
  ),
)

const modelMetaSeverity = computed(() => {
  const source = state.modelMeta?.source
  if (source === 'error' || source === 'fallback') return 'warn'
  return 'success'
})

const modelStatus = computed(() => {
  if (state.modelsLoading) return 'Carregando catálogo…'
  const meta = state.modelMeta
  if (!meta) return 'Selecione um provedor para carregar os modelos.'
  if (meta.source === 'error' || meta.source === 'fallback') {
    return meta.message || 'Catálogo indisponível; você ainda pode digitar um ID.'
  }
  const suffix = provider.value === 'ollama' ? ' instalados/disponíveis no servidor' : ''
  return `${state.availableModels.length} modelos disponíveis${suffix}.`
})

const usagePercent = computed(() => {
  const limit = Number(dailyLimit.value) || 0
  const used = state.boot.ai_used_today || 0
  if (!limit) return 100
  return Math.min(100, Math.round((used / limit) * 100))
})

const allowedCameraEntities = computed(() =>
  (state.inv.entities || []).filter((entity) =>
    (state.boot.camera_allowed || []).includes(entity.entity_id),
  ),
)

async function saveIdentity() {
  identitySaving.value = true
  try {
    await saveProfile({
      assistant_name: profile.assistant_name,
      resident_name: profile.resident_name,
    })
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    identitySaving.value = false
  }
}

async function savePresenceSettings() {
  presenceSaving.value = true
  try {
    await savePresence({ manual: manual.value, entities: presenceEntities.value })
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    presenceSaving.value = false
  }
}

async function saveModelSettings() {
  modelSaving.value = true
  try {
    await saveProvider({
      provider: provider.value,
      model: model.value,
      daily_ai_limit: dailyLimit.value,
    })
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    modelSaving.value = false
  }
}

async function saveCameraSettings() {
  cameraSaving.value = true
  try {
    await saveCameras({
      allowed: allowedCameras.value,
      cloud: cameraCloud.value,
      auto: cameraAuto.value && cameraCloud.value,
    })
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    cameraSaving.value = false
  }
}

async function saveNotificationSettings() {
  notificationsSaving.value = true
  try {
    await saveNotifications(notificationsEnabled.value)
  } catch {
    // O aviso de erro já é exibido pelo store.
  } finally {
    notificationsSaving.value = false
  }
}

function analyze(entity) {
  confirm.require({
    message: `Capturar e enviar uma imagem de ${entity.name} ao provedor configurado?`,
    header: 'Analisar câmera',
    icon: 'pi pi-camera',
    acceptLabel: 'Analisar',
    rejectLabel: 'Cancelar',
    accept: async () => {
      analyzingId.value = entity.entity_id
      try {
        analysisText.value = await analyzeCamera(entity.entity_id)
        analysisEntity.value = entity.name
        analysisVisible.value = true
      } catch {
        // O aviso de erro já é exibido pelo store.
      } finally {
        analyzingId.value = null
      }
    },
  })
}
</script>

<template>
  <div class="page-head">
    <div>
      <span class="eyebrow">SUAS ESCOLHAS</span>
      <h1>Configurações</h1>
      <p class="lead">Controle nome, presença, modelos e acesso às câmeras.</p>
    </div>
  </div>

  <Tabs v-model:value="tab" class="settings-tabs">
    <TabList>
      <Tab value="identity">Identidade</Tab>
      <Tab value="presence">Presença</Tab>
      <Tab value="model">Modelo</Tab>
      <Tab value="cameras">Câmeras</Tab>
      <Tab value="notifications">Avisos</Tab>
    </TabList>

    <TabPanels>
      <TabPanel value="identity">
        <div class="settings-tab-body">
          <form class="form-grid" @submit.prevent="saveIdentity">
            <div class="field">
              <label for="assistantName">Nome do assistente</label>
              <InputText
                id="assistantName"
                v-model="profile.assistant_name"
                maxlength="40"
                required
              />
            </div>
            <div class="field">
              <label for="residentNameSettings">Como chamar você</label>
              <InputText id="residentNameSettings" v-model="profile.resident_name" maxlength="40" />
            </div>
            <div class="actions span-2">
              <Button
                type="submit"
                label="Salvar"
                icon="pi pi-save"
                :loading="identitySaving"
              />
            </div>
          </form>
        </div>
      </TabPanel>

      <TabPanel value="presence">
        <div class="settings-tab-body">
          <form class="form-grid" @submit.prevent="savePresenceSettings">
            <div class="field">
              <label for="presenceMode">Modo</label>
              <Select
                id="presenceMode"
                v-model="manual"
                :options="manualOptions"
                optionLabel="label"
                optionValue="value"
              />
            </div>
            <div class="field">
              <label for="presenceEntities">Entidades de presença</label>
              <MultiSelect
                id="presenceEntities"
                v-model="presenceEntities"
                :options="presenceOptions"
                optionLabel="name"
                optionValue="entity_id"
                filter
                display="chip"
                placeholder="Escolha pessoas ou sensores"
                :disabled="!presenceOptions.length"
              />
            </div>
            <Message v-if="!presenceOptions.length" severity="info" :closable="false" class="span-2">
              Selecione pessoas ou sensores primeiro em Monitoramento.
            </Message>
            <div class="actions span-2">
              <Button
                type="submit"
                label="Salvar presença"
                icon="pi pi-save"
                :loading="presenceSaving"
              />
            </div>
          </form>
        </div>
      </TabPanel>

      <TabPanel value="model">
        <div class="settings-tab-body">
          <form class="form-grid" @submit.prevent="saveModelSettings">
            <div class="field">
              <label for="provider">Provedor</label>
              <Select
                id="provider"
                v-model="provider"
                :options="providerOptions"
                optionLabel="label"
                optionValue="value"
              />
            </div>
            <div class="field">
              <label for="dailyLimit">Máximo de chamadas por dia</label>
              <InputNumber
                id="dailyLimit"
                v-model="dailyLimit"
                :min="0"
                :max="1000"
                showButtons
              />
            </div>

            <div class="field span-2">
              <label for="modelSelect">Modelo</label>
              <Select
                id="modelSelect"
                v-model="model"
                :options="state.availableModels"
                optionLabel="name"
                optionValue="id"
                filter
                :filterFields="['name', 'id']"
                filterPlaceholder="Buscar por nome ou ID"
                placeholder="Escolha um modelo ou use o padrão"
                overlayClass="model-select-overlay"
                showClear
                emptyMessage="Nenhum modelo encontrado"
                class="model-select"
              >
                <template #option="{ option }">
                  <div class="model-option">
                    <strong>{{ option.name }}</strong>
                    <small>{{ option.id }}</small>
                  </div>
                </template>
              </Select>
              <small class="fine">
                O catálogo é carregado do provedor selecionado. Deixe vazio para usar o padrão.
              </small>
            </div>

            <div class="field span-2">
              <label for="modelManual">ID do modelo (manual)</label>
              <InputText
                id="modelManual"
                v-model="model"
                maxlength="100"
                placeholder="Deixe vazio para usar o padrão do provedor"
              />
            </div>

            <Message
              v-if="state.modelMeta?.source === 'error' || state.modelMeta?.source === 'fallback'"
              severity="warn"
              :closable="false"
              class="span-2"
            >
              {{ modelStatus }}
            </Message>
            <div v-else class="span-2 model-status">
              <Tag :severity="modelMetaSeverity" :value="modelStatus" />
            </div>

            <div class="span-2">
              <span class="fine">
                {{ state.boot.ai_used_today }} chamadas hoje. Chaves de API são configuradas nas
                opções do App no Home Assistant.
              </span>
              <ProgressBar :value="usagePercent" :showValue="false" style="margin-top: 0.5rem" />
            </div>

            <div class="actions span-2">
              <Button
                type="submit"
                label="Salvar provedor"
                icon="pi pi-save"
                :loading="modelSaving"
              />
            </div>
          </form>
        </div>
      </TabPanel>

      <TabPanel value="cameras">
        <div class="settings-tab-body">
          <p class="section-note">
            Análise manual ou, se autorizada abaixo, após alerta de segurança na mesma área.
            Intervalo mínimo de cinco minutos; imagens não são salvas.
          </p>
          <form @submit.prevent="saveCameraSettings">
            <div class="field">
              <label for="cameraEntities">Câmeras autorizadas</label>
              <MultiSelect
                id="cameraEntities"
                v-model="allowedCameras"
                :options="cameraOptions"
                optionLabel="name"
                optionValue="entity_id"
                filter
                display="chip"
                placeholder="Escolha câmeras selecionadas"
                :disabled="!cameraOptions.length"
              />
            </div>
            <Message v-if="!cameraOptions.length" severity="info" :closable="false">
              Selecione uma câmera em Monitoramento.
            </Message>

            <div class="toggle-row">
              <div>
                <strong>Permitir enviar imagem ao provedor configurado</strong>
                <small>Necessário para qualquer análise visual externa.</small>
              </div>
              <ToggleSwitch v-model="cameraCloud" />
            </div>
            <div class="toggle-row">
              <div>
                <strong>Analisar automaticamente após alerta de segurança</strong>
                <small>Somente na mesma área da câmera e com o envio autorizado.</small>
              </div>
              <ToggleSwitch v-model="cameraAuto" :disabled="!cameraCloud" />
            </div>

            <div class="actions">
              <Button
                type="submit"
                label="Salvar permissões"
                icon="pi pi-save"
                :loading="cameraSaving"
              />
            </div>
          </form>

          <div v-if="allowedCameraEntities.length" class="actions">
            <Button
              v-for="camera in allowedCameraEntities"
              :key="camera.entity_id"
              :label="`Analisar ${camera.name}`"
              icon="pi pi-camera"
              severity="secondary"
              outlined
              size="small"
              :loading="analyzingId === camera.entity_id"
              @click="analyze(camera)"
            />
          </div>
        </div>
      </TabPanel>

      <TabPanel value="notifications">
        <div class="settings-tab-body">
          <form @submit.prevent="saveNotificationSettings">
            <div class="toggle-row">
              <div>
                <strong>Criar notificações persistentes no Home Assistant</strong>
                <small>Somente para alertas das entidades monitoradas.</small>
              </div>
              <ToggleSwitch v-model="notificationsEnabled" />
            </div>
            <div class="actions">
              <Button
                type="submit"
                label="Salvar avisos"
                icon="pi pi-save"
                :loading="notificationsSaving"
              />
            </div>
          </form>
        </div>
      </TabPanel>
    </TabPanels>
  </Tabs>

  <Dialog
    v-model:visible="analysisVisible"
    modal
    :header="`Análise: ${analysisEntity}`"
    :style="{ width: 'min(94vw, 560px)' }"
  >
    <p class="analysis-text">{{ analysisText }}</p>
  </Dialog>
</template>
