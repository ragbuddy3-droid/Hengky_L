export interface Document {
  id: string;
  filename: string;
  subject: string;
  status: 'pending' | 'processing' | 'ready' | 'failed';
  chunking_strategy?: string;
  created_at?: string;
  error_message?: string;
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
  section_heading?: string;
  chapter?: string;
  page_number?: number;
  chunk_index?: number;
  section_type?: string;
  word_count: number;
  created_at?: string;
}
