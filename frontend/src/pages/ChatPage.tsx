import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { api } from '../lib/api';
import { useLanguage } from '../lib/i18n';
import RadiantPromptInput from '../components/RadiantPromptInput';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatPage() {
  const { t } = useLanguage();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const send = async (text: string) => {
    setMessages((prev) => [...prev, { role: 'user', content: text }]);
    setLoading(true);
    try {
      const { reply } = await api.chat(text);
      setMessages((prev) => [...prev, { role: 'assistant', content: reply }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: 'assistant', content: t('chat_error_network') }]);
    } finally {
      setLoading(false);
    }
  };

  const handleMic = async () => {
    if (micActive) return;
    setMicActive(true);
    try {
      const { user_text, reply } = await api.voiceTurn();
      if (user_text) {
        setMessages((prev) => [...prev, { role: 'user', content: user_text }, { role: 'assistant', content: reply }]);
      }
    } catch (e) {
      setMessages((prev) => [...prev, { role: 'assistant', content: t('chat_error_mic') }]);
    } finally {
      setMicActive(false);
    }
  };

  return (
    <div className="h-full flex flex-col max-w-2xl mx-auto px-4 pt-6">
      <div className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-3 pb-4">
        {messages.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">{t('chat_empty')}</div>
        )}
        {messages.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              dir="rtl"
              className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                m.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-card text-card-foreground border border-border'
              }`}
            >
              {m.content}
            </div>
          </motion.div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-card border border-border rounded-2xl px-4 py-2.5 flex gap-1">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-muted-foreground"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex-shrink-0 pb-4">
        <RadiantPromptInput
          onSubmit={send}
          onMicClick={handleMic}
          micActive={micActive}
          disabled={loading}
          placeholder={t('chat_placeholder')}
        />
      </div>
    </div>
  );
}
