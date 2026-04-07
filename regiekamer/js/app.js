import { initSidebar } from './sidebar.js'
import { initChat } from './chat.js'
import { initModels } from './models.js'

window.addEventListener('DOMContentLoaded', () => {
  initSidebar()
  initModels()
  initChat()
})
