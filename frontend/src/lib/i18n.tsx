import React, { createContext, useContext, useState } from 'react';

export type Lang = 'en' | 'ur';

const dict = {
  nav_chat: { en: 'Chat', ur: 'چیٹ' },
  nav_guardrails: { en: 'Guardrails', ur: 'گارڈریلز' },
  nav_data: { en: 'Data', ur: 'ڈیٹا' },
  nav_faq: { en: 'FAQ', ur: 'FAQ' },
  nav_learning: { en: 'Learning', ur: 'سیکھنا' },

  splash_tagline: { en: 'Your Urdu customer support assistant', ur: 'آپ کا اردو کسٹمر سپورٹ اسسٹنٹ' },
  splash_start: { en: 'Get Started', ur: 'شروع کریں' },
  loading_label: { en: 'Getting Sara ready...', ur: 'سارہ کو تیار ہونے دیں...' },

  chat_empty: { en: 'Type a message or use the mic to talk to Sara', ur: 'سارہ سے بات کرنے کے لیے کچھ لکھیں یا مائیک استعمال کریں' },
  chat_placeholder: { en: 'Type something...', ur: 'کچھ لکھیں...' },
  chat_error_network: { en: 'Sorry, there was a connection problem.', ur: 'معذرت، رابطے میں مسئلہ ہوا۔' },
  chat_error_mic: { en: 'Sorry, there was a problem with the mic.', ur: 'معذرت، مائیک میں مسئلہ ہوا۔' },

  guardrails_title: { en: 'Guardrails & Persona', ur: 'گارڈریلز اور شخصیت' },
  guardrails_subtitle: {
    en: "Edit the agent's role, tone, and boundaries here.",
    ur: 'ایجنٹ کا کردار، بولنے کا انداز، اور حدود یہاں سے تبدیل کریں۔',
  },
  guardrails_role: { en: "Agent's Role", ur: 'ایجنٹ کا کردار' },
  guardrails_tone_rules: { en: 'Tone Rules', ur: 'بولنے کے انداز کے اصول' },
  guardrails_guardrails: { en: 'Boundaries & Guardrails', ur: 'حدود اور احتیاطیں (گارڈریلز)' },
  guardrails_tuning: { en: 'Tuning', ur: 'ٹیوننگ' },
  guardrails_temperature: {
    en: 'Response creativity (higher = more varied, lower = more predictable)',
    ur: 'جواب کی تخلیقی صلاحیت (زیادہ = زیادہ متنوع، کم = زیادہ متوقع)',
  },
  guardrails_tts_rate: { en: 'Speech rate', ur: 'بولنے کی رفتار' },
  guardrails_vad: { en: 'Mic silence cutoff (milliseconds)', ur: 'مائیک کتنی دیر خاموشی کے بعد بند ہو (ملی سیکنڈ)' },
  save: { en: 'Save', ur: 'محفوظ کریں' },
  save_all: { en: 'Save All', ur: 'سب محفوظ کریں' },
  saved: { en: 'Saved', ur: 'محفوظ ہو گیا' },
  add_new: { en: 'Add new', ur: 'نیا شامل کریں' },
  loading: { en: 'Loading...', ur: 'لوڈ ہو رہا ہے...' },

  data_title: { en: 'Data Management', ur: 'ڈیٹا مینجمنٹ' },
  data_subtitle: {
    en: 'Data the agent uses to answer stock, appointment, and menu questions.',
    ur: 'وہ ڈیٹا جو ایجنٹ اسٹاک، اپائنٹمنٹ، اور مینو کے سوالات کے جواب دینے کے لیے استعمال کرتا ہے۔',
  },
  data_tab_stock: { en: 'Stock', ur: 'اسٹاک' },
  data_tab_services: { en: 'Appointments', ur: 'اپائنٹمنٹس' },
  data_tab_menu: { en: 'Menu', ur: 'مینو' },
  data_stock_desc: {
    en: "Each product's name, price (in rupees), and current stock quantity. The agent checks here when asked about availability.",
    ur: 'ہر پروڈکٹ کا نام، قیمت (روپے میں)، اور اسٹاک میں موجودہ تعداد۔ صارف اسٹاک پوچھے تو ایجنٹ یہیں سے چیک کرتا ہے۔',
  },
  data_services_desc: {
    en: 'Each service name, duration (minutes), and available slots (comma-separated, format: YYYY-MM-DD HH:MM).',
    ur: 'ہر سروس کا نام، دورانیہ (منٹ میں)، اور دستیاب اوقات (کاما سے الگ، فارمیٹ: YYYY-MM-DD HH:MM)۔',
  },
  data_menu_desc: {
    en: "Menu items, today's special, and available table booking slots.",
    ur: 'مینو آئٹمز، آج کی اسپیشل ڈش، اور میز بکنگ کے لیے دستیاب اوقات۔',
  },
  field_name: { en: 'Name', ur: 'نام' },
  field_price: { en: 'Price (Rs)', ur: 'قیمت (روپے)' },
  field_quantity: { en: 'Stock qty', ur: 'اسٹاک تعداد' },
  field_service_name: { en: 'Service name', ur: 'سروس کا نام' },
  field_duration: { en: 'Duration (min)', ur: 'دورانیہ (منٹ)' },
  field_slots: { en: 'Available slots (comma-separated)', ur: 'دستیاب اوقات (کاما سے الگ)' },
  field_special: { en: "Today's special", ur: 'آج کی اسپیشل ڈش' },
  field_dish_name: { en: 'Dish name', ur: 'ڈش کا نام' },
  field_description: { en: 'Description', ur: 'تفصیل' },
  field_table_slots: { en: 'Table booking slots (comma-separated)', ur: 'میز بکنگ کے دستیاب اوقات (کاما سے الگ)' },
  add_product: { en: 'Add product', ur: 'نیا پروڈکٹ' },
  add_service: { en: 'Add service', ur: 'نئی سروس' },
  add_dish: { en: 'Add dish', ur: 'نئی ڈش' },

  faq_title: { en: 'Frequently Asked Questions', ur: 'اکثر پوچھے جانے والے سوالات' },
  faq_subtitle: {
    en: "These Q&A pairs ground the agent's replies when a user's question matches.",
    ur: 'یہ سوال/جواب کے جوڑے ایجنٹ کے جواب کی بنیاد بنتے ہیں جب صارف کا سوال ان سے ملتا جلتا ہو۔',
  },
  faq_question: { en: 'Question', ur: 'سوال' },
  faq_answer: { en: 'Answer', ur: 'جواب' },
  faq_add: { en: 'Add a question', ur: 'نیا سوال شامل کریں' },

  learning_title: { en: 'Continuous Learning', ur: 'مسلسل سیکھنا' },
  learning_subtitle: {
    en: 'Review past conversations and promote good replies as future examples, or check sensitive cases sent to a human agent.',
    ur: 'پرانی گفتگوئیں دیکھیں اور اچھے جوابات کو مستقبل کی مثالوں میں شامل کریں، یا حساس کیسز چیک کریں جو انسانی نمائندے کے پاس بھیجے گئے۔',
  },
  learning_sessions: { en: 'Sessions', ur: 'سیشنز' },
  learning_escalations: { en: 'Sensitive Cases', ur: 'حساس کیسز' },
  learning_no_sessions: { en: 'No sessions recorded yet.', ur: 'ابھی تک کوئی سیشن ریکارڈ نہیں ہوا۔' },
  learning_no_escalations: { en: 'No sensitive cases reported yet.', ur: 'ابھی تک کوئی حساس کیس رپورٹ نہیں ہوا۔' },
  learning_add_example: { en: 'Add as example', ur: 'مثال کے طور پر شامل کریں' },
  learning_added: { en: 'Added as example', ur: 'مثال کے طور پر شامل ہو گیا' },
  you: { en: 'You', ur: 'آپ' },
} as const;

export type DictKey = keyof typeof dict;

interface LanguageContextValue {
  lang: Lang;
  setLang: (l: Lang) => void;
  t: (key: DictKey) => string;
}

const LanguageContext = createContext<LanguageContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => (localStorage.getItem('sara_lang') as Lang) || 'ur');

  const setLang = (l: Lang) => {
    localStorage.setItem('sara_lang', l);
    setLangState(l);
  };

  const t = (key: DictKey) => dict[key][lang];

  return <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider');
  return ctx;
}
