import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { api, type FaqEntry } from '../lib/api';
import { useLanguage } from '../lib/i18n';
import LightBeamButton from '../components/LightBeamButton';

const inputCls = 'w-full bg-card border border-border rounded-md px-3 py-2 text-sm text-foreground text-right focus:outline-none focus:border-primary/50';

export default function FaqPage() {
  const { t } = useLanguage();
  const [entries, setEntries] = useState<FaqEntry[]>([]);

  useEffect(() => {
    api.getFaq().then(setEntries);
  }, []);

  const update = (i: number, patch: Partial<FaqEntry>) => {
    const next = [...entries];
    next[i] = { ...next[i], ...patch };
    setEntries(next);
  };

  const remove = async (i: number) => {
    const entry = entries[i];
    setEntries(entries.filter((_, idx) => idx !== i));
    if (entry.id) await api.deleteFaq(entry.id).catch(() => {});
  };

  const saveAll = () => api.saveFaq(entries);

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h2 className="text-lg font-semibold mb-1">{t('faq_title')}</h2>
        <p className="text-xs text-muted-foreground">{t('faq_subtitle')}</p>
      </div>

      {entries.map((entry, i) => (
        <div key={entry.id + i} className="space-y-2 bg-card/50 border border-border rounded-lg p-3">
          <textarea
            dir="rtl"
            placeholder={t('faq_question')}
            value={entry.question}
            onChange={(e) => update(i, { question: e.target.value })}
            rows={2}
            className={inputCls + ' resize-none'}
          />
          <textarea
            dir="rtl"
            placeholder={t('faq_answer')}
            value={entry.answer}
            onChange={(e) => update(i, { answer: e.target.value })}
            rows={3}
            className={inputCls + ' resize-none'}
          />
          <div className="flex justify-end">
            <button onClick={() => remove(i)} className="text-muted-foreground hover:text-destructive p-1.5">
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      ))}

      <button
        onClick={() => setEntries([...entries, { id: `faq_${Date.now()}`, question: '', answer: '' }])}
        className="flex items-center gap-1.5 text-sm text-primary hover:opacity-80"
      >
        <Plus size={14} /> {t('faq_add')}
      </button>

      <div className="pb-6">
        <LightBeamButton onClick={saveAll}>{t('save_all')}</LightBeamButton>
      </div>
    </div>
  );
}
