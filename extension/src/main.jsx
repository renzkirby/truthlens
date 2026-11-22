import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/mona-sans/wght.css'
import './index.css'
import App from './App.jsx'
import { logStartupTiming } from './modules/startupDiagnostics.js'

logStartupTiming('popup_main_module_evaluated', { context: 'popup' })

const root = createRoot(document.getElementById('root'))
logStartupTiming('popup_react_root_created', { context: 'popup' })

root.render(
  <StrictMode>
    <App />
  </StrictMode>,
)

logStartupTiming('popup_render_requested', { context: 'popup' })
