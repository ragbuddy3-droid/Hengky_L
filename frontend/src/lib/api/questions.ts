import type { Question, QuestionDetail } from '@/types/question';
import { request } from './client';

export const questionsApi = {
  list: (sessionId?: string) => request<Question[]>('/questions/', { query: { session_id: sessionId } }),

  get: (id: string) => request<QuestionDetail>(`/questions/${id}`),
};
