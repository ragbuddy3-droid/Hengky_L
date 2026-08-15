export interface ChatSession {
  id: string;
  document_id: string;
  document_filename?: string;
  message_count?: number;
  last_message_snippet?: string;
  created_at?: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at?: string;
}
