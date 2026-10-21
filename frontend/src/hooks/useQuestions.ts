'use client';

import { useQuery } from '@tanstack/react-query';
import { questionsApi } from '@/lib/api/questions';
import { queryKeys } from '@/lib/query-keys';

/** Daftar soal, opsional per sesi. */
export function useQuestions(sessionId?: string) {
  return useQuery({
    queryKey: queryKeys.questions(sessionId),
    queryFn: () => questionsApi.list(sessionId),
  });
}

export function useQuestion(id: string) {
  return useQuery({ queryKey: queryKeys.question(id), queryFn: () => questionsApi.get(id) });
}
