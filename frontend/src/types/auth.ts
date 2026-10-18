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

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}
