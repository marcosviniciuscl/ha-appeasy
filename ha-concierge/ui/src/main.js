import { createApp } from 'vue'
import PrimeVue from 'primevue/config'
import ToastService from 'primevue/toastservice'
import ConfirmationService from 'primevue/confirmationservice'
import Ripple from 'primevue/ripple'
import Tooltip from 'primevue/tooltip'
import { definePreset } from '@primeuix/themes'
import Aura from '@primeuix/themes/aura'
import 'primeicons/primeicons.css'
import './styles.css'
import App from './App.vue'

const ConciergePreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: '#eff7f1',
      100: '#d9ecde',
      200: '#b5d9c0',
      300: '#86bf98',
      400: '#549f70',
      500: '#2f7f51',
      600: '#256a43',
      700: '#1f5436',
      800: '#1b442d',
      900: '#173826',
      950: '#0c2015',
    },
  },
})

const app = createApp(App)

app.use(PrimeVue, {
  ripple: false,
  theme: {
    preset: ConciergePreset,
    options: {
      darkModeSelector: '.app-dark',
      cssLayer: false,
    },
  },
})
app.use(ToastService)
app.use(ConfirmationService)
app.directive('ripple', Ripple)
app.directive('tooltip', Tooltip)
app.mount('#app')
