import { useEffect, useState } from 'react';
import { MessageCircle, ShieldCheck, Package, HelpCircle, GraduationCap } from 'lucide-react';
import { api } from './lib/api';
import { useLanguage } from './lib/i18n';
import LoadingScreen from './components/LoadingScreen';
import SplashScreen from './components/SplashScreen';
import MagnificationDock, { type DockItemData } from './components/MagnificationDock';
import LanguageToggle from './components/LanguageToggle';
import ChatPage from './pages/ChatPage';
import GuardrailsPage from './pages/GuardrailsPage';
import StoreDataPage from './pages/StoreDataPage';
import FaqPage from './pages/FaqPage';
import ContinuousLearningPage from './pages/ContinuousLearningPage';

type Page = 'chat' | 'guardrails' | 'store' | 'faq' | 'learning';

export default function App() {
  const [backendReady, setBackendReady] = useState(false);
  const [showSplash, setShowSplash] = useState(true);
  const [page, setPage] = useState<Page>('chat');
  const { lang, t } = useLanguage();

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        try {
          await api.getSettings();
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

  if (!backendReady) {
    return <LoadingScreen label={t('loading_label')} />;
  }

  if (showSplash) {
    return <SplashScreen onDone={() => setShowSplash(false)} />;
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
      <div className="flex-shrink-0 flex justify-end px-4 pt-3">
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
