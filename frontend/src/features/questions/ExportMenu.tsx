'use client';

import { ActionIcon, Button, Menu, Tooltip } from '@mantine/core';
import { useClipboard } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconClipboardCopy, IconDownload, IconFileText, IconListDetails } from '@tabler/icons-react';
import { downloadTextFile, exportFilename, questionsToMarkdown } from '@/lib/exportMarkdown';
import type { Question } from '@/types/question';

/** Menu ekspor soal ke Markdown (unduh dengan/tanpa kunci jawaban, atau salin). */
export function ExportMenu({ questions, title, compact }: { questions: Question[]; title: string; compact?: boolean }) {
  const clipboard = useClipboard();
  const disabled = questions.length === 0;

  const download = (includeAnswers: boolean) => {
    const name = includeAnswers ? title : `${title} lembar soal`;
    downloadTextFile(exportFilename(name), questionsToMarkdown(questions, { title, includeAnswers }));
  };

  const copy = () => {
    clipboard.copy(questionsToMarkdown(questions, { title, includeAnswers: true }));
    notifications.show({ color: 'green', message: `${questions.length} soal disalin sebagai Markdown.` });
  };

  const target = compact ? (
    <Tooltip label="Ekspor soal">
      <ActionIcon disabled={disabled} aria-label="Ekspor soal">
        <IconDownload size={16} aria-hidden />
      </ActionIcon>
    </Tooltip>
  ) : (
    <Button variant="default" leftSection={<IconDownload size={16} aria-hidden />} disabled={disabled}>
      Ekspor ({questions.length})
    </Button>
  );

  return (
    <Menu position="bottom-end" width={260}>
      <Menu.Target>{target}</Menu.Target>
      <Menu.Dropdown>
        <Menu.Label>Markdown (.md) · {questions.length} soal</Menu.Label>
        <Menu.Item leftSection={<IconFileText size={16} aria-hidden />} onClick={() => download(true)}>
          Unduh lengkap dengan kunci jawaban
        </Menu.Item>
        <Menu.Item leftSection={<IconListDetails size={16} aria-hidden />} onClick={() => download(false)}>
          Unduh lembar soal (kunci di akhir)
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item leftSection={<IconClipboardCopy size={16} aria-hidden />} onClick={copy}>
          Salin ke clipboard
        </Menu.Item>
      </Menu.Dropdown>
    </Menu>
  );
}
