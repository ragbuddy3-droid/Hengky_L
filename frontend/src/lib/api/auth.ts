import type { ChangePasswordPayload, LoginPayload, RegisterPayload, User } from '@/types/auth';
import { ApiError, request } from './client';

type Status = { status: string };

export const authApi = {
  register: (payload: RegisterPayload) => request<User>('/auth/register', { method: 'POST', json: payload }),

  login: (payload: LoginPayload) => request<User>('/auth/login', { method: 'POST', json: payload }),

  logout: () => request<Status>('/auth/logout', { method: 'POST' }),

  /** Pengguna yang sedang login, atau `null` bila masih tamu (backend membalas 401). */
  me: async () => {
    try {
      return await request<User>('/auth/me');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return null;
      throw err;
    }
  },

  updateProfile: (name: string) => request<User>('/auth/me', { method: 'PATCH', json: { name } }),

  changePassword: (payload: ChangePasswordPayload) =>
    request<Status>('/auth/me/password', { method: 'POST', json: payload }),

  deleteAccount: (password: string) => request<Status>('/auth/me', { method: 'DELETE', json: { password } }),
};
