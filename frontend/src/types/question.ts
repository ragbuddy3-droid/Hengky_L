export interface QuestionOption {
  label: string;
  text: string;
}

export interface RubricCriterion {
  score: number;
  criteria: string;
}

export interface AnswerElement {
  element: string;
  weight: number;
}

export interface PromptTraceItem {
  stage_name: string;
  step_number: number;
  attempt_number: number;
  prompt_sent: string;
  raw_response: string;
  parsed_output?: Record<string, any> | null;
  latency_ms: number;
  status: string;
  error_message?: string | null;
}

export interface ValidationLog {
  id: string;
  attempt_number: number;
  layer: 'grounding' | 'judge' | 'pre_check' | string;
  score_or_verdict: string;
  feedback?: string;
  aspect_evaluations?: Record<string, any> | string | null;
  created_at?: string;
}

export interface UsedChunk {
  id: string;
  document_id: string;
  text: string;
  category: string;
  section_heading?: string;
  chapter?: string;
  page_number?: number;
  chunk_index?: number;
  section_type?: string;
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
  knowledge_point?: string;
  grounding_evidence?: string;
  rubric?: RubricCriterion[];
  answer_elements?: AnswerElement[];
  prompt_traces?: PromptTraceItem[];
  validation_logs?: ValidationLog[];
  used_chunks?: UsedChunk[];
}
