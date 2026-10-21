export interface User {
  id: string;
  name: string;
  email: string;
  created_at: string;
}

export interface LoginPayload {
  email: string;
  password: string;
  remember: boolean;
}

export interface RegisterPayload extends LoginPayload {
  name: string;
}

/** Kuota sekali pakai mode tamu; selalu `true` untuk akun. */
export interface GuestQuota {
  can_upload: boolean;
  can_create_session: boolean;
  can_generate: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}
