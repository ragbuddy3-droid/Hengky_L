import type { DocumentChunk, DocumentItem, DocumentUploadResponse } from '@/types/document';
import { request } from './client';

export interface UploadDocumentInput {
  file: File;
  subject: string;
}

export const documentsApi = {
  list: () => request<DocumentItem[]>('/documents/'),

  get: (id: string) => request<DocumentItem>(`/documents/${id}`),

  chunks: (id: string) => request<DocumentChunk[]>(`/documents/${id}/chunks`),

  upload: ({ file, subject }: UploadDocumentInput) => {
    const body = new FormData();
    body.append('file', file);
    body.append('subject', subject);
    return request<DocumentUploadResponse>('/documents/', { method: 'POST', body });
  },

  remove: (id: string) => request<{ status: string }>(`/documents/${id}`, { method: 'DELETE' }),
};
