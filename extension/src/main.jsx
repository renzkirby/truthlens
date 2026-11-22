import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource-variable/mona-sans/wght.css'
import './index.css'
import App from './App.jsx'
import { logStartupTiming } from './modules/startupDiagnostics.js'

const popupBootstrap = window.__truthlensPopupBootstrap || null
const popupResources = typeof performance !== 'undefined'
  ? performance.getEntriesByType('resource')
      .map((entry) => ({
        name: (() => {
          try {
            return new URL(entry.name).pathname.split('/').pop() || entry.name
          } catch {
            return entry.name
          }
        })(),
        initiatorType: entry.initiatorType,
        startTimeMs: Number(entry.startTime.toFixed(2)),
        durationMs: Number(entry.duration.toFixed(2)),
        transferSize: entry.transferSize ?? null,
      }))
      .sort((left, right) => right.durationMs - left.durationMs)
      .slice(0, 8)
  : []

logStartupTiming('popup_main_module_evaluated', {
  context: 'popup',
  delaySinceHtmlBootstrapMs: popupBootstrap
    ? Number((performance.now() - popupBootstrap.contextAgeMs).toFixed(2))
    : null,
  slowestResources: popupResources,
})

const root = createRoot(document.getElementById('root'))
logStartupTiming('popup_react_root_created', { context: 'popup' })

root.render(
  <StrictMode>
    <App />
  </StrictMode>,
)

logStartupTiming('popup_render_requested', { context: 'popup' })
