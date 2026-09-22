import { QueryClient } from '@tanstack/react-query';

export const queryKeys = {
  bootstrap: ['bootstrap'] as const,
  me: ['me'] as const,
  qualExams: ['qual-exams'] as const,
};

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      retry: 1,
    },
  },
});
