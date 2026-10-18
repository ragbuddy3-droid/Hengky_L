import type { Metadata } from 'next';
import { DocumentDetailView } from '@/features/documents/DocumentDetailView';

export const metadata: Metadata = { title: 'Detail Dokumen' };

export default async function DocumentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <DocumentDetailView id={id} />;
}
