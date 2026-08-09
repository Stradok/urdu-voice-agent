import { useEffect, useState } from 'react';
import { AlertTriangle, BookmarkPlus, Check } from 'lucide-react';
import { api, type Session, type Escalation } from '../lib/api';
import { useLanguage } from '../lib/i18n';

type Tab = 'sessions' | 'escalations';

export default function ContinuousLearningPage() {
  const { t, lang } = useLanguage();
  const [tab, setTab] = useState<Tab>('sessions');
  const [sessions, setSessions] = useState<Session[]>([]);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [addedKeys, setAddedKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    api.getSessions().then((s) => setSessions([...s].reverse()));
    api.getEscalations().then((e) => setEscalations([...e].reverse()));
  }, []);

  const addAsExample = async (key: string, userText: string, assistantText: string) => {
    await api.addExample({ user: userText, assistant: assistantText });
    setAddedKeys((prev) => new Set(prev).add(key));
  };

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">{t('learning_title')}</h2>
        <p className="text-xs text-muted-foreground">{t('learning_subtitle')}</p>
      </div>

      <div className="flex gap-1 border-b border-border">
        <button
          onClick={() => setTab('sessions')}
          className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${
            tab === 'sessions' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground'
          }`}
        >
          {t('learning_sessions')} ({sessions.length})
        </button>
        <button
          onClick={() => setTab('escalations')}
          className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors flex items-center gap-1.5 ${
            tab === 'escalations' ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground'
          }`}
        >
          <AlertTriangle size={14} /> {t('learning_escalations')} ({escalations.length})
        </button>
      </div>

      {tab === 'sessions' && (
        <div className="space-y-6 pb-6">
          {sessions.length === 0 && <p className="text-sm text-muted-foreground">{t('learning_no_sessions')}</p>}
          {sessions.map((session) => (
            <div key={session.session_id} className="space-y-3">
              <p className="text-xs text-muted-foreground">{new Date(session.started_at).toLocaleString(lang === 'en' ? 'en-US' : 'ur-PK')}</p>
              {session.exchanges.map((ex, i) => {
                const key = `${session.session_id}-${i}`;
                const added = addedKeys.has(key);
                return (
                  <div key={key} className="bg-card/50 border border-border rounded-lg p-3 space-y-2">
                    <p dir="rtl" className="text-sm">
                      <span className="text-muted-foreground">{t('you')}: </span>
                      {ex.user}
                    </p>
                    <p dir="rtl" className="text-sm">
                      <span className="text-muted-foreground">{lang === 'en' ? 'Sara' : 'سارہ'}: </span>
                      {ex.assistant}
                    </p>
                    <button
                      disabled={added}
                      onClick={() => addAsExample(key, ex.user, ex.assistant)}
                      className={`flex items-center gap-1.5 text-xs ${
                        added ? 'text-emerald-400' : 'text-primary hover:opacity-80'
                      }`}
                    >
                      {added ? <Check size={13} /> : <BookmarkPlus size={13} />}
                      {added ? t('learning_added') : t('learning_add_example')}
                    </button>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}

      {tab === 'escalations' && (
        <div className="space-y-3 pb-6">
          {escalations.length === 0 && <p className="text-sm text-muted-foreground">{t('learning_no_escalations')}</p>}
          {escalations.map((esc, i) => (
            <div key={i} className="bg-card/50 border border-destructive/30 rounded-lg p-3 space-y-1">
              <div className="flex items-center justify-between gap-2">
                <p className="text-xs text-muted-foreground">{new Date(esc.timestamp).toLocaleString(lang === 'en' ? 'en-US' : 'ur-PK')}</p>
                <span className="font-mono text-xs text-muted-foreground">{esc.reference_code}</span>
              </div>
              <p dir="rtl" className="text-sm">
                {esc.reason}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
