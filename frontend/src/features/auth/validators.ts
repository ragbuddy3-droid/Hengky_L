/** Validator nama pengguna untuk @mantine/form (daftar & ubah profil). */
export const validateName = (value: string) => (value.trim().length < 2 ? 'Nama minimal 2 karakter.' : null);
