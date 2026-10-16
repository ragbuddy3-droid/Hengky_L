import type { Metadata } from 'next';
import { QuestionDetailView } from '@/features/questions/QuestionDetailView';

export const metadata: Metadata = { title: 'Detail Soal' };

export default async function QuestionDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <QuestionDetailView id={id} />;
}
