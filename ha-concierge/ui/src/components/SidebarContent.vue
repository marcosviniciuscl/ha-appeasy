<script setup>
import { computed } from 'vue'
import Badge from 'primevue/badge'
import Menu from 'primevue/menu'
import { go, navItems, state } from '../store'

const emit = defineEmits(['navigate'])
const name = computed(() => state.boot?.profile?.assistant_name || 'Concierge')
const selectedCount = computed(() => state.boot?.selected?.length || 0)
const items = computed(() =>
  navItems.map((item) => ({
    ...item,
    command: () => {
      go(item.key)
      emit('navigate')
    },
  })),
)
</script>

<template>
  <div class="brand">
    <span class="brand-mark"><i class="pi pi-home" /></span>
    <div>
      <strong>{{ name }}</strong>
      <small>CASA EM PERSPECTIVA</small>
    </div>
  </div>

  <Menu :model="items" class="nav-menu">
    <template #item="{ item, props }">
      <a
        v-ripple
        class="nav-link"
        :class="{ active: state.page === item.key }"
        v-bind="props.action"
      >
        <i :class="item.icon" />
        <span>{{ item.label }}</span>
      </a>
    </template>
  </Menu>

  <div class="side-foot">
    <span class="status-dot" :class="{ bad: state.boot?.connection_error }" />
    <span>{{ state.boot?.connection_error ? 'Conexão com falha' : 'Home Assistant conectado' }}</span>
    <Badge :value="selectedCount" severity="success" class="side-badge" />
  </div>
</template>
