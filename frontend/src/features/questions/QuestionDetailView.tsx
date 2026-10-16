'use client';

import Link from 'next/link';
import { Alert, Anchor, Badge, Breadcrumbs, Button, Group, List, Paper, Skeleton, Stack, Tabs, Text, Title } from '@mantine/core';
import {
  IconAlertTriangle,
  IconBook2,
  IconClipboardList,
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
import { QueryError } from '@/components/common/QueryError';
import { useQuestion } from '@/hooks/useQuestions';
import { ApiError } from '@/lib/api/client';
import { AnswerTab } from './tabs/AnswerTab';
import { RubricTab } from './tabs/RubricTab';
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

  const breadcrumbs = (
    <Breadcrumbs mb="md" fz="sm" separator={<Text span c="dimmed" aria-hidden>/</Text>}>
      <Anchor component={Link} href="/soal">
        Bank Soal
      </Anchor>
      <Text size="sm" c="dimmed">
        Detail soal
      </Text>
    </Breadcrumbs>
  );

  if (isLoading) {
    return (
      <PageContainer>
        {breadcrumbs}
        <Skeleton h={22} w={220} mb="sm" />
        <Skeleton h={64} mb="lg" />
        <Skeleton h={320} radius="md" />
      </PageContainer>
    );
  }

  if (error || !question) {
    return (
      <PageContainer>
        {breadcrumbs}
        {error instanceof ApiError && error.status === 404 ? (
          <EmptyState
            icon={<IconQuestionMark size={24} aria-hidden />}
            title="Soal tidak ditemukan"
            description="Soal ini mungkin sudah dihapus bersama sesinya."
            action={
              <Button component={Link} href="/soal" variant="default">
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
  const hasRubric = !!(question.rubric?.length || question.answer_elements?.length);

  return (
    <PageContainer>
      {breadcrumbs}

      <Stack gap="md" mb="lg">
        <Group justify="space-between" gap="sm">
          <Group gap={6}>
            <QuestionTypeBadge type={question.question_type} />
            <BloomBadge level={question.bloom_level} />
            <QuestionStatusBadge status={question.status} />
            {question.refinement_count > 0 && (
              <Badge color="violet" variant="outline">
                {question.refinement_count}× perbaikan
              </Badge>
            )}
          </Group>
          <Button
            component={Link}
            href={`/chat/${question.session_id}`}
            variant="default"
            size="xs"
            leftSection={<IconMessageCircle size={14} aria-hidden />}
          >
            Buka percakapan
          </Button>
        </Group>

        <Paper p="lg">
          <Group align="flex-start" wrap="nowrap" gap="sm">
            <Title order={1} fz={{ base: 18, sm: 22 }} lh={1.45} fw={600} style={{ flex: 1 }}>
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
          <Tabs.Tab value="rubric" leftSection={<IconClipboardList size={16} aria-hidden />}>
            <TabLabel>{hasRubric ? 'Rubrik' : 'Rubrik (–)'}</TabLabel>
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
        <Tabs.Panel value="rubric">
          <RubricTab question={question} />
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
