import type { ChatMessage, ChatSession, ChatSessionListItem } from '@/types/chat';
import { API_BASE_URL, request } from './client';

export const chatApi = {
  listSessions: () => request<ChatSessionListItem[]>('/chat/sessions'),

  getSession: (sessionId: string) => request<ChatSessionListItem>(`/chat/sessions/${sessionId}`),

  createSession: (documentId: string) =>
    request<ChatSession>('/chat/sessions', { method: 'POST', json: { document_id: documentId } }),

  removeSession: (sessionId: string) =>
    request<{ status: string }>(`/chat/sessions/${sessionId}`, { method: 'DELETE' }),

  messages: (sessionId: string) => request<ChatMessage[]>(`/chat/sessions/${sessionId}/messages`),

  sendMessage: (sessionId: string, content: string) =>
    request<ChatMessage>(`/chat/sessions/${sessionId}/messages`, { method: 'POST', json: { content } }),

  /** Server-Sent Events progres generasi soal (untuk `EventSource`). */
  generationStreamUrl: (sessionId: string) => `${API_BASE_URL}/chat/sessions/${sessionId}/generation/stream`,
};
