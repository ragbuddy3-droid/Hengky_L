import type { Metadata } from 'next';
import { DocumentsView } from '@/features/documents/DocumentsView';

export const metadata: Metadata = { title: 'Dokumen' };

export default function DocumentsPage() {
  return <DocumentsView />;
}
