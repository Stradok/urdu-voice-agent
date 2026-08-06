import { useLanguage } from '../lib/i18n';

export function LanguageToggle() {
  const { lang, setLang } = useLanguage();

  return (
    <div className="flex items-center gap-0.5 bg-card border border-border rounded-full p-0.5 text-xs">
      <button
        onClick={() => setLang('ur')}
        className={`px-3 py-1 rounded-full transition-colors ${lang === 'ur' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
      >
        اردو
      </button>
      <button
        onClick={() => setLang('en')}
        className={`px-3 py-1 rounded-full transition-colors ${lang === 'en' ? 'bg-primary text-primary-foreground' : 'text-muted-foreground'}`}
      >
        EN
      </button>
    </div>
  );
}

export default LanguageToggle;
