import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import * as Sentry from '@sentry/react'
import './index.css'
import '@/lib/i18n'
import App from './App.tsx'
import { SentryFallback } from '@/components/SentryFallback'
import { initSentry } from '@/lib/sentry'

// Init avant createRoot — on veut attraper les erreurs du premier render.
initSentry()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Sentry.ErrorBoundary fallback={SentryFallback}>
      <App />
    </Sentry.ErrorBoundary>
  </StrictMode>,
)
