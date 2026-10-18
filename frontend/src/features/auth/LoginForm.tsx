'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { PAGE_TITLE_FZ } from '@/components/common/PageHeader';
import { Alert, Anchor, Button, Checkbox, Divider, PasswordInput, Stack, Text, TextInput, Title } from '@mantine/core';
import { isEmail, isNotEmpty, useForm } from '@mantine/form';
import { notifications } from '@mantine/notifications';
import { IconAlertCircle, IconArrowRight } from '@tabler/icons-react';
import { useLogin } from '@/hooks/useAuth';
import { safeNext, useRedirectIfLoggedIn } from './useAuthRedirect';

export function LoginForm({ next }: { next?: string }) {
  const router = useRouter();
  const target = safeNext(next);
  const login = useLogin();
  const [serverError, setServerError] = useState<string | null>(null);
  useRedirectIfLoggedIn(target);

  const form = useForm({
    mode: 'uncontrolled',
    initialValues: { email: '', password: '', remember: false },
    validate: {
      email: isEmail('Masukkan alamat email yang valid.'),
      password: isNotEmpty('Password wajib diisi.'),
    },
  });

  const handleSubmit = form.onSubmit((values) => {
    setServerError(null);
    return login
      .mutateAsync({ ...values, email: values.email.trim() })
      .then((user) => {
        notifications.show({ color: 'green', message: `Selamat datang kembali, ${user.name}!` });
        router.replace(target);
      })
      .catch((err: Error) => setServerError(err.message));
  });

  const registerHref = next ? `/register?next=${encodeURIComponent(target)}` : '/register';

  return (
    <Stack gap="lg">
      <div>
        <Title order={1} fz={PAGE_TITLE_FZ}>
          Masuk ke Soalnya
        </Title>
        <Text c="dimmed" mt={6}>
          Lanjutkan menyusun soal dan buka kembali Bank Soal Anda.
        </Text>
      </div>

      {serverError && (
        <Alert color="red" variant="light" icon={<IconAlertCircle size={18} aria-hidden />} role="alert">
          {serverError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate>
        <Stack gap="md">
          <TextInput
            label="Email"
            placeholder="nama@email.com"
            type="email"
            autoComplete="email"
            inputMode="email"
            size="md"
            required
            key={form.key('email')}
            {...form.getInputProps('email')}
          />
          <PasswordInput
            label="Password"
            placeholder="Password Anda"
            autoComplete="current-password"
            size="md"
            required
            visibilityToggleFocusable
            visibilityToggleButtonProps={{ 'aria-label': 'Tampilkan atau sembunyikan password' }}
            key={form.key('password')}
            {...form.getInputProps('password')}
          />
          <Checkbox
            label="Ingat saya selama 30 hari"
            key={form.key('remember')}
            {...form.getInputProps('remember', { type: 'checkbox' })}
          />
          <Button type="submit" size="md" fullWidth loading={form.submitting}>
            Masuk
          </Button>
        </Stack>
      </form>

      <Text size="sm" ta="center">
        Belum punya akun?{' '}
        <Anchor component={Link} href={registerHref} fw={600}>
          Daftar gratis
        </Anchor>
      </Text>

      <Divider label="atau" labelPosition="center" />

      <Stack gap={6}>
        <Button
          component={Link}
          href="/chat"
          variant="default"
          size="md"
          fullWidth
          rightSection={<IconArrowRight size={16} aria-hidden />}
        >
          Lanjut tanpa login
        </Button>
        <Text size="xs" c="dimmed" ta="center">
          Mode tamu: riwayat hanya tersimpan di browser ini selama 24 jam.
        </Text>
      </Stack>
    </Stack>
  );
}
