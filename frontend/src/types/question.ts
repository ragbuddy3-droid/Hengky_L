// Mirror of backend/src/app/schemas/api_schemas.py (Question*)

export interface UsedChunk {
  id: string;
  document_id: string;
  text: string;
  category: string;
  section_heading?: string | null;
  chapter?: string | null;
  page_number?: number | null;
  chunk_index?: number | null;
  section_type?: string | null;
}

export interface PromptTraceItem {
  stage_name: string;
  step_number: number;
  attempt_number: number;
  prompt_sent: string;
  raw_response: string;
  parsed_output?: Record<string, unknown> | null;
  latency_ms: number;
  status: string;
  error_message?: string | null;
}

export interface ValidationLog {
  id: string;
  attempt_number: number;
  layer: 'pre_check' | 'grounding' | 'judge' | (string & {});
  score_or_verdict: string;
  feedback?: string | null;
  aspect_evaluations?: Record<string, unknown> | string | null;
  created_at?: string | null;
}

export type QuestionType = 'esai' | 'esai_pendek' | 'isian_singkat' | (string & {});
export type QuestionStatus = 'final' | 'needs_review' | (string & {});

/** GET /questions */
export interface Question {
  id: string;
  session_id?: string | null;
  document_id?: string | null;
  document_filename?: string | null;
  question_type: QuestionType;
  question_text: string;
  answer_key: string;
  explanation?: string | null;
  source_reference?: string | null;
  bloom_level: string;
  status: QuestionStatus;
  refinement_count: number;
  /** Berapa kali soal direvisi / dibuat ulang lewat chat. */
  revision_count: number;
  knowledge_point?: string | null;
  grounding_evidence?: string | null;
  source_chunks: string[];
  used_chunks: UsedChunk[];
  quality_warnings?: string[] | null;
}

/** GET /questions/{id} */
export interface QuestionDetail extends Omit<Question, 'source_chunks' | 'document_id' | 'document_filename'> {
  session_id: string;
  prompt_traces?: PromptTraceItem[] | null;
  validation_logs: ValidationLog[];
}
