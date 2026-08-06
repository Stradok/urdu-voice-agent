import { useEffect, useState } from 'react';
import { Plus, Trash2, Gauge, Volume2, Ear, Mic, Speaker } from 'lucide-react';
import { api, type PersonaConfig, type AppSettings, type AudioDevices } from '../lib/api';
import { useLanguage } from '../lib/i18n';
import LightBeamButton from '../components/LightBeamButton';
import ElasticSlider from '../components/ElasticSlider';

const selectCls = 'w-full bg-card border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary/50';

function EditableList({
  title,
  addLabel,
  items,
  onChange,
}: {
  title: string;
  addLabel: string;
  items: string[];
  onChange: (items: string[]) => void;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">{title}</h3>
      {items.map((item, i) => (
        <div key={i} className="flex gap-2">
          <textarea
            dir="rtl"
            value={item}
            onChange={(e) => {
              const next = [...items];
              next[i] = e.target.value;
              onChange(next);
            }}
            rows={2}
            className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground text-right resize-none focus:outline-none focus:border-primary/50"
          />
          <button
            onClick={() => onChange(items.filter((_, idx) => idx !== i))}
            className="text-muted-foreground hover:text-destructive transition-colors self-start p-2"
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <button
        onClick={() => onChange([...items, ''])}
        className="flex items-center gap-1.5 text-sm text-primary hover:opacity-80 transition-opacity"
      >
        <Plus size={14} /> {addLabel}
      </button>
    </div>
  );
}

export default function GuardrailsPage() {
  const { t } = useLanguage();
  const [persona, setPersona] = useState<PersonaConfig | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [devices, setDevices] = useState<AudioDevices | null>(null);
  const [savedMsg, setSavedMsg] = useState('');

  useEffect(() => {
    api.getPersona().then(setPersona);
    api.getSettings().then(setSettings);
    api.getAudioDevices().then(setDevices);
  }, []);

  const saveAll = async () => {
    if (persona) await api.savePersona(persona);
    if (settings) await api.saveSettings(settings);
    setSavedMsg(t('saved'));
    setTimeout(() => setSavedMsg(''), 2000);
  };

  if (!persona || !settings) {
    return <div className="p-8 text-muted-foreground text-sm">{t('loading')}</div>;
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-8">
      <div>
        <h2 className="text-lg font-semibold mb-1">{t('guardrails_title')}</h2>
        <p className="text-xs text-muted-foreground">{t('guardrails_subtitle')}</p>
      </div>

      <div className="space-y-2">
        <h3 className="text-sm font-medium text-muted-foreground">{t('guardrails_role')}</h3>
        <textarea
          dir="rtl"
          value={persona.role_description}
          onChange={(e) => setPersona({ ...persona, role_description: e.target.value })}
          rows={3}
          className="w-full bg-card border border-border rounded-lg px-3 py-2 text-sm text-foreground text-right resize-none focus:outline-none focus:border-primary/50"
        />
      </div>

      <EditableList
        title={t('guardrails_tone_rules')}
        addLabel={t('add_new')}
        items={persona.tone_rules}
        onChange={(v) => setPersona({ ...persona, tone_rules: v })}
      />

      <EditableList
        title={t('guardrails_guardrails')}
        addLabel={t('add_new')}
        items={persona.guardrails}
        onChange={(v) => setPersona({ ...persona, guardrails: v })}
      />

      <div className="space-y-6 border-t border-border pt-6">
        <h3 className="text-sm font-medium text-muted-foreground">{t('guardrails_tuning')}</h3>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground justify-center">
            <Gauge size={14} /> {t('guardrails_temperature')}
          </div>
          <ElasticSlider
            startingValue={0}
            maxValue={100}
            defaultValue={settings.llm_temperature * 100}
            formatValue={(v) => (v / 100).toFixed(2)}
            onChangeCommitted={(v) => setSettings({ ...settings, llm_temperature: Math.round(v) / 100 })}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground justify-center">
            <Volume2 size={14} /> {t('guardrails_tts_rate')}
          </div>
          <ElasticSlider
            startingValue={-20}
            maxValue={50}
            defaultValue={settings.tts_rate_percent}
            isStepped
            stepSize={5}
            formatValue={(v) => `${v > 0 ? '+' : ''}${Math.round(v)}%`}
            onChangeCommitted={(v) => setSettings({ ...settings, tts_rate_percent: Math.round(v) })}
          />
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2 text-xs text-muted-foreground justify-center">
            <Ear size={14} /> {t('guardrails_vad')}
          </div>
          <ElasticSlider
            startingValue={300}
            maxValue={2000}
            defaultValue={settings.vad_silence_ms}
            isStepped
            stepSize={100}
            formatValue={(v) => `${Math.round(v)}ms`}
            onChangeCommitted={(v) => setSettings({ ...settings, vad_silence_ms: Math.round(v) })}
          />
        </div>
      </div>

      <div className="space-y-4 border-t border-border pt-6">
        <h3 className="text-sm font-medium text-muted-foreground">{t('guardrails_audio_devices')}</h3>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Mic size={14} /> {t('guardrails_mic_device')}
          </div>
          <select
            className={selectCls}
            value={settings.mic_device}
            onChange={(e) => setSettings({ ...settings, mic_device: e.target.value })}
          >
            <option value="auto">{t('audio_device_auto')}</option>
            {devices?.mic_devices.map((d) => (
              <option key={d.id} value={d.id}>{d.label}</option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Speaker size={14} /> {t('guardrails_speaker_device')}
          </div>
          <select
            className={selectCls}
            value={settings.speaker_device}
            onChange={(e) => setSettings({ ...settings, speaker_device: e.target.value })}
          >
            <option value="auto">{t('audio_device_auto')}</option>
            {devices?.speaker_devices.map((d) => (
              <option key={d.id} value={d.id}>{d.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-center gap-4 pt-2 pb-6">
        <LightBeamButton onClick={saveAll}>{t('save')}</LightBeamButton>
        {savedMsg && <span className="text-sm text-emerald-400">{savedMsg}</span>}
      </div>
    </div>
  );
}
