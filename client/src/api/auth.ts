import { StaffUser } from '../types';
import { ApiError, apiRequest, jsonBody } from './http';
import { ApiUser, mapUser } from './serializers';

interface UserResponse {
  user: ApiUser;
}

export const authApi = {
  getCurrentUser: async (): Promise<StaffUser | null> => {
    try {
      const response = await apiRequest<UserResponse>('/auth/me/');
      return mapUser(response.user);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },

  login: async (email: string, password: string): Promise<StaffUser> => {
    const response = await apiRequest<UserResponse>('/auth/login/', {
      method: 'POST',
      body: jsonBody({ email, password }),
    });
    return mapUser(response.user);
  },

  logout: async (): Promise<void> => {
    await apiRequest<void>('/auth/logout/', { method: 'POST', body: jsonBody({}) });
  },
};
