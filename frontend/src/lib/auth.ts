const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL as string;
const SUPABASE_PUBLISHABLE_KEY = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY as string;

// Local development mode - see frontend/.env and the backend's src/auth.py. The Supabase
// project that issued these tokens is gone, so in this mode there's nothing to authenticate
// against: login() stores a placeholder token purely so the existing "is there a token?"
// gate in App.tsx still works, and the backend ignores it entirely, resolving the business
// from its own LOCAL_AUTH_EMAIL instead. Real auth returns the moment Supabase is configured
// again - nothing below this line changes for that, it just stops taking the local branch.
const LOCAL_AUTH = import.meta.env.VITE_LOCAL_AUTH === 'true';
const LOCAL_TOKEN = 'local-dev-no-auth';

const TOKEN_KEY = 'sara_access_token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function logout() {
  localStorage.removeItem(TOKEN_KEY);
}

export function isLocalAuth(): boolean {
  return LOCAL_AUTH;
}

export async function login(email: string, password: string): Promise<void> {
  if (LOCAL_AUTH) {
    localStorage.setItem(TOKEN_KEY, LOCAL_TOKEN);
    return;
  }

  const res = await fetch(`${SUPABASE_URL}/auth/v1/token?grant_type=password`, {
    method: 'POST',
    headers: { apikey: SUPABASE_PUBLISHABLE_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });
  const data = await res.json();
  if (!res.ok || !data.access_token) {
    throw new Error(data.error_description || data.msg || 'Invalid email or password');
  }
  localStorage.setItem(TOKEN_KEY, data.access_token);
}
