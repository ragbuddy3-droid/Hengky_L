export interface QuestionOption {
  label: string;
  text: string;
}

export interface ValidationLog {
  id: string;
  attempt_number: number;
  layer: 'grounding' | 'judge';
  score_or_verdict: string;
  feedback?: string;
  created_at?: string;
}

export interface UsedChunk {
  id: string;
  document_id: string;
  text: string;
  category: string;
  section_heading?: string;
  chapter?: string;
}

export interface Question {
  id: string;
  session_id?: string;
  question_type?: 'esai' | 'isian_singkat' | string;
  question_text: string;
  options?: Record<string, string> | QuestionOption[] | null;
  answer_key: string;
  explanation?: string;
  source_reference?: string;
  bloom_level: string;
  status: 'final' | 'needs_review';
  refinement_count: number;
  validation_logs?: ValidationLog[];
  used_chunks?: UsedChunk[];
}
