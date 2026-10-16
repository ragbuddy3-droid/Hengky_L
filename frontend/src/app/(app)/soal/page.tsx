import type { Metadata } from 'next';
import { QuestionBankView } from '@/features/questions/QuestionBankView';

export const metadata: Metadata = { title: 'Bank Soal' };

export default function QuestionsPage() {
  return <QuestionBankView />;
}
