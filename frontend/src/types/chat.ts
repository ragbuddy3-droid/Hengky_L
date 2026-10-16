// Mirror of backend/src/app/schemas/api_schemas.py (ChatSession*, ChatMessage*)

/** Status generasi soal di latar belakang untuk sebuah sesi. */
export type GenerationStatus = 'idle' | 'running' | 'done' | 'failed';

/** GET /chat/sessions dan GET /chat/sessions/{id} */
export interface ChatSessionListItem {
  id: string;
  document_id: string;
  document_filename?: string | null;
  message_count: number;
  last_message_snippet?: string | null;
  created_at?: string | null;
  generation_status: GenerationStatus;
  /** Jumlah soal yang diminta pada generasi terakhir. */
  generation_count?: number | null;
  /** Pesan asisten "Sedang membuat..." milik generasi terakhir. */
  generation_message_id?: string | null;
}

export interface ChatSession {
  id: string;
  document_id: string;
  created_at?: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | (string & {});
  content: string;
  /** ISO 8601 ber-zona waktu (UTC). */
  created_at?: string | null;
}
