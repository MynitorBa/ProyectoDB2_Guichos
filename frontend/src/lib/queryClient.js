import { QueryClient } from '@tanstack/react-query'

// Instancia global de React Query: 1 reintento y datos frescos por 30 segundos antes de considerar stale
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 30_000 },
  },
})
