import { useEffect, useState } from 'react';
import { MessageCircle, ShieldCheck, Package, HelpCircle, GraduationCap, LogOut } from 'lucide-react';
import { api, type WhoAmI } from './lib/api';
import { getToken, logout } from './lib/auth';
import { useLanguage } from './lib/i18n';
import LoadingScreen from './components/LoadingScreen';
import MagnificationDock, { type DockItemData } from './components/MagnificationDock';
import LanguageToggle from './components/LanguageToggle';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import GuardrailsPage from './pages/GuardrailsPage';
import StoreDataPage from './pages/StoreDataPage';
import FaqPage from './pages/FaqPage';
import ContinuousLearningPage from './pages/ContinuousLearningPage';

type Page = 'chat' | 'guardrails' | 'store' | 'faq' | 'learning';

export default function App() {
  const [backendReady, setBackendReady] = useState(false);
  const [page, setPage] = useState<Page>('chat');
  const [business, setBusiness] = useState<WhoAmI | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const { lang, t } = useLanguage();

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        try {
          await api.health();
          if (!cancelled) setBackendReady(true);
          return;
        } catch {
          await new Promise((r) => setTimeout(r, 400));
        }
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!backendReady) return;
    if (!getToken()) {
      setCheckingAuth(false);
      return;
    }
    api
      .whoami()
      .then(setBusiness)
      .catch(() => setBusiness(null))
      .finally(() => setCheckingAuth(false));
  }, [backendReady]);

  useEffect(() => {
    // Fired by api.ts's request() on any 401/403, from whatever page happened to be
    // mounted when the token expired - drops straight back to the login screen instead of
    // leaving that page silently failing every subsequent request.
    const onAuthExpired = () => setBusiness(null);
    window.addEventListener('sara:auth-expired', onAuthExpired);
    return () => window.removeEventListener('sara:auth-expired', onAuthExpired);
  }, []);

  if (!backendReady || checkingAuth) {
    return <LoadingScreen label={t('loading_label')} />;
  }

  if (!business) {
    return (
      <LoginPage
        onLoggedIn={() => {
          api.whoami().then(setBusiness);
        }}
      />
    );
  }

  const dockItems: DockItemData[] = [
    { icon: <MessageCircle size={20} />, label: t('nav_chat'), onClick: () => setPage('chat'), isActive: page === 'chat' },
    { icon: <ShieldCheck size={20} />, label: t('nav_guardrails'), onClick: () => setPage('guardrails'), isActive: page === 'guardrails' },
    { icon: <Package size={20} />, label: t('nav_data'), onClick: () => setPage('store'), isActive: page === 'store' },
    { icon: <HelpCircle size={20} />, label: t('nav_faq'), onClick: () => setPage('faq'), isActive: page === 'faq' },
    { icon: <GraduationCap size={20} />, label: t('nav_learning'), onClick: () => setPage('learning'), isActive: page === 'learning' },
  ];

  return (
    <div dir={lang === 'en' ? 'ltr' : 'rtl'} className="h-full w-full flex flex-col bg-background text-foreground">
      <div className="flex-shrink-0 flex items-center justify-between px-4 pt-3">
        <button
          onClick={() => {
            logout();
            setBusiness(null);
          }}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
          title={business.slug}
        >
          <LogOut size={14} /> {t('logout_button')}
        </button>
        <LanguageToggle />
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto">
        {page === 'chat' && <ChatPage />}
        {page === 'guardrails' && <GuardrailsPage />}
        {page === 'store' && <StoreDataPage />}
        {page === 'faq' && <FaqPage />}
        {page === 'learning' && <ContinuousLearningPage />}
      </div>
      <div className="flex-shrink-0 pb-2">
        <MagnificationDock items={dockItems} />
      </div>
    </div>
  );
}
