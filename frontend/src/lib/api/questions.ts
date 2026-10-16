import type { Question, QuestionDetail } from '@/types/question';
import { request } from './client';

export const questionsApi = {
  list: (filters: { sessionId?: string; documentId?: string } = {}) =>
    request<Question[]>('/questions/', { query: { session_id: filters.sessionId, document_id: filters.documentId } }),

  get: (id: string) => request<QuestionDetail>(`/questions/${id}`),
};
