import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'

/* Base CSS must load first — defines :root defaults and reset */
import './assets/base.css'
/* Theme overrides load after base — :root[data-theme] beats :root in cascade order */
import './themes/cyberpunk.css'
import './themes/dark.css'
import './themes/light.css'
import './themes/midnight.css'
import './themes/hacker.css'
import './themes/neon.css'
import './themes/paper.css'
import './themes/arctic.css'
import './themes/solarized.css'

import App from './App.vue'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
