import type { Metadata } from 'next';
import { ChatSessionView } from '@/features/chat/ChatSessionView';

export const metadata: Metadata = { title: 'Percakapan' };

export default async function ChatSessionPage({ params }: { params: Promise<{ sessionId: string }> }) {
  const { sessionId } = await params;
  return <ChatSessionView key={sessionId} sessionId={sessionId} />;
}
