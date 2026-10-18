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

// Mirror of backend/src/app/services/generation/progress.py (SSE GET /chat/sessions/{id}/generation/stream)

export type CandidateStatus = 'blueprint' | 'writing' | 'validating' | 'refining' | 'final' | 'needs_review' | 'dropped';

/** Isi sementara soal kandidat, dikirim sejak Stage 4 selesai. */
export interface CandidateDraft {
  question?: string | null;
  answer?: string | null;
  bloom_level?: string | null;
  question_type?: string | null;
  source_reference?: string | null;
}

export type GenerationEvent =
  | { type: 'start'; target: number }
  | { type: 'phase'; phase: string; label: string }
  | { type: 'candidate'; id: string; status: CandidateStatus; attempt?: number; question?: CandidateDraft }
  | { type: 'done'; status: GenerationStatus; message?: string | null };
