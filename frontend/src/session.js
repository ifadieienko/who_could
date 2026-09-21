const API_URL = import.meta.env.VITE_API_URL || '/api';

const notifyCleared = () => window.dispatchEvent(new Event('who-could:session-cleared'));

export const session = {
  // The cookie is HttpOnly, so JavaScript intentionally cannot inspect it.
  // Returning true keeps the existing boot flow: /me is the authoritative
  // session probe and a 401 clears the local UI state.
  getToken: () => true,
  setToken: () => {},
  clear: async () => {
    try {
      await fetch(`${API_URL}/auth/logout`, { method: 'POST', credentials: 'include' });
    } finally {
      notifyCleared();
    }
  }
};
