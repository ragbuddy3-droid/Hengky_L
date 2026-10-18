'use client';

import Link from 'next/link';
import { Alert, Badge, Button, Group, List, Paper, Skeleton, Stack, Tabs, Text, Title } from '@mantine/core';
import {
  IconAlertTriangle,
  IconBook2,
  IconFileSearch,
  IconListCheck,
  IconMessageCircle,
  IconQuestionMark,
  IconShieldCheck,
  IconTerminal2,
} from '@tabler/icons-react';
import { BloomBadge, QuestionStatusBadge, QuestionTypeBadge } from '@/components/common/Badges';
import { CopyTextButton } from '@/components/common/CopyTextButton';
import { EmptyState } from '@/components/common/EmptyState';
import { PageContainer } from '@/components/common/PageContainer';
import { PageBreadcrumbs, PageHeader } from '@/components/common/PageHeader';
import { QueryError } from '@/components/common/QueryError';
import { useQuestion } from '@/hooks/useQuestions';
import { ApiError } from '@/lib/api/client';
import { AnswerTab } from './tabs/AnswerTab';
import { SourcesTab } from './tabs/SourcesTab';
import { TracesTab } from './tabs/TracesTab';
import { ValidationTab } from './tabs/ValidationTab';

function TabLabel({ children, count }: { children: React.ReactNode; count?: number }) {
  return (
    <Group gap={6} wrap="nowrap">
      {children}
      {!!count && (
        <Badge size="xs" color="gray" px={6}>
          {count}
        </Badge>
      )}
    </Group>
  );
}

export function QuestionDetailView({ id }: { id: string }) {
  const { data: question, isLoading, error, refetch } = useQuestion(id);

  const crumbs = [{ label: 'Bank Soal', href: '/questions' }, { label: 'Detail soal' }];

  if (isLoading) {
    return (
      <PageContainer>
        <PageBreadcrumbs items={crumbs} />
        <Skeleton h={22} w={220} mb="sm" />
        <Skeleton h={64} mb="lg" />
        <Skeleton h={320} radius="md" />
      </PageContainer>
    );
  }

  if (error || !question) {
    return (
      <PageContainer>
        <PageBreadcrumbs items={crumbs} />
        {error instanceof ApiError && error.status === 404 ? (
          <EmptyState
            icon={<IconQuestionMark size={24} aria-hidden />}
            title="Soal tidak ditemukan"
            description="Soal ini mungkin sudah dihapus bersama sesinya."
            action={
              <Button component={Link} href="/questions" variant="default">
                Kembali ke Bank Soal
              </Button>
            }
          />
        ) : (
          error && <QueryError error={error} onRetry={() => refetch()} />
        )}
      </PageContainer>
    );
  }

  const warnings = question.quality_warnings ?? [];

  return (
    <PageContainer>
      <PageHeader
        breadcrumbs={crumbs}
        title="Detail Soal"
        meta={
          <>
            <QuestionTypeBadge type={question.question_type} />
            <BloomBadge level={question.bloom_level} />
            <QuestionStatusBadge status={question.status} />
            {question.refinement_count > 0 && (
              <Badge color="violet" variant="outline">
                {question.refinement_count}× perbaikan
              </Badge>
            )}
          </>
        }
        actions={
          <Button
            component={Link}
            href={`/chat/${question.session_id}`}
            variant="default"
            leftSection={<IconMessageCircle size={16} aria-hidden />}
          >
            Buka percakapan
          </Button>
        }
      />

      <Stack gap="md" mb="lg">
        <Paper p="lg">
          <Group align="flex-start" wrap="nowrap" gap="sm">
            <Title order={2} fz={{ base: 18, sm: 20 }} lh={1.45} fw={600} style={{ flex: 1 }}>
              {question.question_text}
            </Title>
            <CopyTextButton value={question.question_text} label="Salin soal" />
          </Group>
          {question.source_reference && (
            <Group gap={6} mt="sm" c="dimmed">
              <IconBook2 size={14} aria-hidden />
              <Text size="xs">{question.source_reference}</Text>
            </Group>
          )}
        </Paper>

        {warnings.length > 0 && (
          <Alert color="orange" icon={<IconAlertTriangle size={18} aria-hidden />} title="Catatan kualitas">
            <List size="sm">
              {warnings.map((w) => (
                <List.Item key={w}>{w}</List.Item>
              ))}
            </List>
          </Alert>
        )}
      </Stack>

      <Tabs defaultValue="answer" keepMounted={false}>
        <Tabs.List mb="lg" style={{ flexWrap: 'nowrap', overflowX: 'auto', overflowY: 'hidden' }}>
          <Tabs.Tab value="answer" leftSection={<IconListCheck size={16} aria-hidden />}>
            <TabLabel>Soal &amp; Jawaban</TabLabel>
          </Tabs.Tab>
          <Tabs.Tab value="sources" leftSection={<IconFileSearch size={16} aria-hidden />}>
            <TabLabel count={question.used_chunks?.length}>Sumber</TabLabel>
          </Tabs.Tab>
          <Tabs.Tab value="validation" leftSection={<IconShieldCheck size={16} aria-hidden />}>
            <TabLabel count={question.validation_logs?.length}>Validasi</TabLabel>
          </Tabs.Tab>
          <Tabs.Tab value="traces" leftSection={<IconTerminal2 size={16} aria-hidden />}>
            <TabLabel count={question.prompt_traces?.length ?? 0}>Jejak Prompt</TabLabel>
          </Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="answer">
          <AnswerTab question={question} />
        </Tabs.Panel>
        <Tabs.Panel value="sources">
          <SourcesTab question={question} />
        </Tabs.Panel>
        <Tabs.Panel value="validation">
          <ValidationTab question={question} />
        </Tabs.Panel>
        <Tabs.Panel value="traces">
          <TracesTab question={question} />
        </Tabs.Panel>
      </Tabs>
    </PageContainer>
  );
}
