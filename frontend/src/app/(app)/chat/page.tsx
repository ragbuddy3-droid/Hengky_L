import type { Metadata } from 'next';
import { NewChatView } from '@/features/chat/NewChatView';

export const metadata: Metadata = { title: 'Chat Baru' };

export default function ChatPage() {
  return <NewChatView />;
}
