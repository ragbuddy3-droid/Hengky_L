import { Container } from '@mantine/core';

/** Wadah standar halaman non-chat (scroll normal, lebar terbatas). */
export function PageContainer({ children }: { children: React.ReactNode }) {
  return (
    <Container size="lg" py={{ base: 'md', sm: 'xl' }} px={{ base: 'md', sm: 'xl' }}>
      {children}
    </Container>
  );
}
