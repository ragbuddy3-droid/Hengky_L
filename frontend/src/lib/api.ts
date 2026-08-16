import { Document, DocumentUploadResponse } from '@/types/document';
import { ChatSession, ChatMessage } from '@/types/chat';
import { Question } from '@/types/question';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorText = await response.text();
    let errorMessage = `HTTP Error ${response.status}`;
    try {
      const errorJson = JSON.parse(errorText);
      if (errorJson.detail) errorMessage = errorJson.detail;
    } catch {
      if (errorText) errorMessage = errorText;
    }
    throw new Error(errorMessage);
  }
  return response.json();
}

export const api = {
  // Documents
  async listDocuments(): Promise<Document[]> {
    const res = await fetch(`${API_BASE_URL}/documents`);
    return handleResponse<Document[]>(res);
  },

  async getDocumentStatus(id: string): Promise<Document> {
    const res = await fetch(`${API_BASE_URL}/documents/${id}`);
    return handleResponse<Document>(res);
  },

  async uploadDocument(file: File, subject: string, chunkingStrategy: string = 'fixed'): Promise<DocumentUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('subject', subject);
    formData.append('chunking_strategy', chunkingStrategy);

    const res = await fetch(`${API_BASE_URL}/documents/`, {
      method: 'POST',
      body: formData,
    });
    return handleResponse<DocumentUploadResponse>(res);
  },

  async deleteDocument(id: string): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE_URL}/documents/${id}`, {
      method: 'DELETE',
    });
    return handleResponse<{ status: string }>(res);
  },

  async listDocumentChunks(documentId: string): Promise<import('@/types/document').DocumentChunk[]> {
    const res = await fetch(`${API_BASE_URL}/documents/${documentId}/chunks`);
    return handleResponse<import('@/types/document').DocumentChunk[]>(res);
  },

  // Chat
  async listChatSessions(documentId?: string): Promise<ChatSession[]> {
    const url = documentId
      ? `${API_BASE_URL}/chat/sessions?document_id=${documentId}`
      : `${API_BASE_URL}/chat/sessions`;
    const res = await fetch(url);
    return handleResponse<ChatSession[]>(res);
  },

  async createChatSession(documentId: string): Promise<ChatSession> {
    const res = await fetch(`${API_BASE_URL}/chat/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId }),
    });
    return handleResponse<ChatSession>(res);
  },

  async deleteChatSession(sessionId: string): Promise<{ status: string }> {
    const res = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}`, {
      method: 'DELETE',
    });
    return handleResponse<{ status: string }>(res);
  },

  async getChatMessages(sessionId: string): Promise<ChatMessage[]> {
    const res = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`);
    return handleResponse<ChatMessage[]>(res);
  },

  async sendChatMessage(sessionId: string, content: string): Promise<ChatMessage> {
    const res = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    return handleResponse<ChatMessage>(res);
  },

  // Questions
  async listQuestions(sessionId?: string): Promise<Question[]> {
    const url = sessionId 
      ? `${API_BASE_URL}/questions?session_id=${sessionId}`
      : `${API_BASE_URL}/questions`;
    const res = await fetch(url);
    return handleResponse<Question[]>(res);
  },

  async getQuestionDetail(id: string): Promise<Question> {
    const res = await fetch(`${API_BASE_URL}/questions/${id}`);
    return handleResponse<Question>(res);
  },
};
