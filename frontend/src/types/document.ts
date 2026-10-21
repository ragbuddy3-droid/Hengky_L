// Mirror of backend/src/app/schemas/api_schemas.py (Document*)

export type DocumentStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface DocumentItem {
  id: string;
  filename: string;
  subject: string;
  status: DocumentStatus | (string & {});
  created_at?: string | null;
  error_message?: string | null;
  warning_message?: string | null;
}

export interface DocumentUploadResponse {
  id: string;
  status: string;
  message: string;
}

export interface DocumentChunk {
  id: string;
  document_id: string;
  text: string;
  category: string;
  section_heading?: string | null;
  chapter?: string | null;
  word_count: number;
  created_at?: string | null;
}
