import { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { CheckCheck } from 'lucide-react';
import { api } from '../lib/api';
import { useLanguage } from '../lib/i18n';
import WhatsAppInput from '../components/WhatsAppInput';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

// WhatsApp-style skin for the same text/voice chat flow src/api.py already serves (POST
// /chat, POST /voice_turn/start+/stop) - a placeholder ahead of the real WhatsApp Business
// Cloud API integration (see plan.md's Open Decisions), so businesses/prospects can already
// see and demo what the actual channel will feel like. The underlying send/mic logic below is
// unchanged from before this pass - only the visuals (bubbles, header, input bar) are new.
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
    setMessages((prev) => [...prev, { role: 'user', content: text, timestamp: Date.now() }]);
    setLoading(true);
    try {
      const { reply } = await api.chat(text);
      setMessages((prev) => [...prev, { role: 'assistant', content: reply, timestamp: Date.now() }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: 'assistant', content: t('chat_error_network'), timestamp: Date.now() }]);
    } finally {
      setLoading(false);
    }
  };

  const handleMicHoldStart = async () => {
    if (micActive) return;
    setMicActive(true);
    try {
      await api.voiceTurnStart();
    } catch (e) {
      setMicActive(false);
      setMessages((prev) => [...prev, { role: 'assistant', content: t('chat_error_mic'), timestamp: Date.now() }]);
    }
  };

  const handleMicHoldEnd = async () => {
    if (!micActive) return;
    setMicActive(false);
    setLoading(true);
    try {
      const { user_text, reply } = await api.voiceTurnStop();
      if (user_text) {
        setMessages((prev) => [
          ...prev,
          { role: 'user', content: user_text, timestamp: Date.now() },
          { role: 'assistant', content: reply, timestamp: Date.now() },
        ]);
      }
    } catch (e) {
      setMessages((prev) => [...prev, { role: 'assistant', content: t('chat_error_mic'), timestamp: Date.now() }]);
    } finally {
      setLoading(false);
    }
  };

  const formatTime = (ts: number) =>
    new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="h-full flex flex-col bg-[#0b141a]">
      {/* WhatsApp-style contact header - "Sara" is who the customer is chatting with */}
      <div className="flex-shrink-0 flex items-center gap-3 px-4 py-2.5 bg-[#202c33] border-b border-black/20">
        <div className="w-10 h-10 rounded-full bg-[#00a884] flex items-center justify-center text-[#111b21] font-semibold text-lg">
          S
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[#e9edef] text-[15px] font-medium leading-tight">Sara</div>
          <div className="text-[#8696a0] text-xs leading-tight">{loading ? t('chat_typing') : t('chat_online')}</div>
        </div>
      </div>

      {/* WhatsApp's chat background is a subtle repeating doodle pattern on a dark base -
          approximated here with a plain low-contrast dot pattern rather than shipping a real
          asset, since the color alone already reads unmistakably as WhatsApp. */}
      <div
        className="flex-1 min-h-0 overflow-y-auto flex flex-col gap-1.5 px-4 py-3"
        style={{
          backgroundColor: '#0b141a',
          backgroundImage: 'radial-gradient(rgba(255,255,255,0.03) 1px, transparent 1px)',
          backgroundSize: '18px 18px',
        }}
      >
        {messages.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-center text-[#8696a0] text-sm px-8">
            {t('chat_empty')}
          </div>
        )}
        {messages.map((m, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              dir="rtl"
              className={`relative max-w-[75%] rounded-lg px-3 pt-1.5 pb-1 text-[14.5px] leading-relaxed shadow-sm ${
                m.role === 'user' ? 'bg-[#005c4b] text-[#e9edef]' : 'bg-[#202c33] text-[#e9edef]'
              }`}
            >
              <div className="pr-1">{m.content}</div>
              <div
                className={`flex items-center gap-1 justify-end text-[11px] mt-0.5 ${
                  m.role === 'user' ? 'text-[#8fd6c4]' : 'text-[#8696a0]'
                }`}
              >
                {formatTime(m.timestamp)}
                {m.role === 'user' && <CheckCheck size={14} className="text-[#53bdeb]" />}
              </div>
            </div>
          </motion.div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-[#202c33] rounded-lg px-4 py-3 flex gap-1">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full bg-[#8696a0]"
                  animate={{ opacity: [0.3, 1, 0.3] }}
                  transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }}
                />
              ))}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="flex-shrink-0">
        <WhatsAppInput
          onSubmit={send}
          onMicHoldStart={handleMicHoldStart}
          onMicHoldEnd={handleMicHoldEnd}
          micActive={micActive}
          disabled={loading}
          placeholder={t('chat_placeholder')}
        />
      </div>
    </div>
  );
}
