import { useState } from 'react';
import { login } from '../lib/auth';
import { useLanguage } from '../lib/i18n';
import LightBeamButton from '../components/LightBeamButton';

const inputCls = 'w-full bg-card border border-border rounded-md px-3 py-2 text-sm text-foreground focus:outline-none focus:border-primary/50';

export default function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const { lang, t } = useLanguage();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
      onLoggedIn();
    } catch {
      setError(t('login_error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div dir={lang === 'en' ? 'ltr' : 'rtl'} className="h-full w-full flex items-center justify-center bg-background px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 bg-card/50 border border-border rounded-lg p-6">
        <div className="text-center space-y-1">
          <h1 className="text-lg font-semibold text-foreground">{t('login_title')}</h1>
          <p className="text-xs text-muted-foreground">{t('login_subtitle')}</p>
        </div>

        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">{t('login_email')}</label>
          <input
            type="email"
            required
            autoFocus
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputCls}
            dir="ltr"
          />
        </div>

        <div className="space-y-2">
          <label className="text-xs text-muted-foreground">{t('login_password')}</label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputCls}
            dir="ltr"
          />
        </div>

        {error && <p className="text-xs text-destructive text-center">{error}</p>}

        <LightBeamButton type="submit" disabled={loading} className="w-full justify-center">
          {loading ? t('login_loading') : t('login_button')}
        </LightBeamButton>
      </form>
    </div>
  );
}
