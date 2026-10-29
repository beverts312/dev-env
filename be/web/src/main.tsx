import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'

import App from '@/App'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import '@/index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    // the server keeps what it fetched, so rereading is cheap; a PR table only goes to GitHub on refresh
    queries: { staleTime: 30_000, refetchOnWindowFocus: false, retry: false },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="dark" enableSystem storageKey="be.theme" disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider>
          <App />
          <Toaster richColors closeButton position="bottom-right" toastOptions={{ className: 'whitespace-pre-line' }} />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
