const BASE_URL = 'http://127.0.0.1:8420';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${options?.method ?? 'GET'} ${path} failed (${res.status}): ${body}`);
  }
  return res.json();
}

export interface PersonaConfig {
  name: string;
  role_description: string;
  tone_rules: string[];
  faq_grounding_instruction: string;
  code_switching_note: string;
  tools_instruction: string;
  guardrails: string[];
}

export interface ExampleEntry {
  user: string;
  assistant: string;
}

export interface AppSettings {
  llm_temperature: number;
  tts_rate_percent: number;
  vad_silence_ms: number;
  mic_device: string;
  speaker_device: string;
}

export interface AudioDevice {
  id: string;
  label: string;
}

export interface AudioDevices {
  mic_devices: AudioDevice[];
  speaker_devices: AudioDevice[];
}

export interface FaqEntry {
  id: string;
  question: string;
  answer: string;
}

export interface StockItem {
  id: string;
  name: string;
  price: number;
  quantity: number;
}

export interface ServiceItem {
  id: string;
  name: string;
  duration_minutes: number;
  available_slots: string[];
}

export interface MenuData {
  today_special: string;
  items: { name: string; price: number; description: string }[];
  table_slots: string[];
}

export interface SessionExchange {
  timestamp: string;
  user: string;
  assistant: string;
}

export interface Session {
  session_id: string;
  started_at: string;
  exchanges: SessionExchange[];
}

export interface Escalation {
  timestamp: string;
  session_id: string | null;
  reason: string;
}

export const api = {
  chat: (message: string) => request<{ reply: string }>('/chat', { method: 'POST', body: JSON.stringify({ message }) }),
  voiceTurn: () => request<{ user_text: string; reply: string }>('/voice_turn', { method: 'POST' }),

  getPersona: () => request<PersonaConfig>('/config/persona'),
  savePersona: (config: PersonaConfig) => request<PersonaConfig>('/config/persona', { method: 'PUT', body: JSON.stringify(config) }),

  getExampleBank: () => request<ExampleEntry[]>('/config/example_bank'),
  saveExampleBank: (examples: ExampleEntry[]) => request<ExampleEntry[]>('/config/example_bank', { method: 'PUT', body: JSON.stringify(examples) }),
  addExample: (entry: ExampleEntry) => request<ExampleEntry[]>('/config/example_bank', { method: 'POST', body: JSON.stringify(entry) }),

  getSettings: () => request<AppSettings>('/config/settings'),
  saveSettings: (settings: AppSettings) => request<AppSettings>('/config/settings', { method: 'PUT', body: JSON.stringify(settings) }),

  getAudioDevices: () => request<AudioDevices>('/audio/devices'),

  getFaq: () => request<FaqEntry[]>('/faq'),
  saveFaq: (entries: FaqEntry[]) => request<FaqEntry[]>('/faq', { method: 'PUT', body: JSON.stringify(entries) }),
  addFaq: (entry: FaqEntry) => request<FaqEntry[]>('/faq', { method: 'POST', body: JSON.stringify(entry) }),
  deleteFaq: (id: string) => request<FaqEntry[]>(`/faq/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  getStock: () => request<StockItem[]>('/store/stock'),
  saveStock: (items: StockItem[]) => request<StockItem[]>('/store/stock', { method: 'PUT', body: JSON.stringify(items) }),

  getServices: () => request<ServiceItem[]>('/store/services'),
  saveServices: (items: ServiceItem[]) => request<ServiceItem[]>('/store/services', { method: 'PUT', body: JSON.stringify(items) }),

  getMenu: () => request<MenuData>('/store/menu'),
  saveMenu: (menu: MenuData) => request<MenuData>('/store/menu', { method: 'PUT', body: JSON.stringify(menu) }),

  getSessions: () => request<Session[]>('/sessions'),
  getEscalations: () => request<Escalation[]>('/escalations'),
};
