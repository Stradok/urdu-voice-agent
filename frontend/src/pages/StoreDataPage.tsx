import { useEffect, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { api, type StockItem, type ServiceItem, type MenuData } from '../lib/api';
import { useLanguage, type DictKey } from '../lib/i18n';
import LightBeamButton from '../components/LightBeamButton';

type Tab = 'stock' | 'services' | 'menu';

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] text-muted-foreground uppercase tracking-wide">{label}</span>
      {children}
    </div>
  );
}

const inputCls = 'bg-card border border-border rounded-md px-2 py-1.5 text-sm text-foreground focus:outline-none focus:border-primary/50';

function StockTab() {
  const { t } = useLanguage();
  const [items, setItems] = useState<StockItem[]>([]);
  useEffect(() => {
    api.getStock().then(setItems);
  }, []);

  const update = (i: number, patch: Partial<StockItem>) => {
    const next = [...items];
    next[i] = { ...next[i], ...patch };
    setItems(next);
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('data_stock_desc')}</p>
      {items.map((item, i) => (
        <div key={item.id} className="grid grid-cols-[1fr_120px_100px_36px] gap-3 items-end bg-card/50 border border-border rounded-lg p-3">
          <Field label={t('field_name')}>
            <input dir="rtl" className={inputCls} value={item.name} onChange={(e) => update(i, { name: e.target.value })} />
          </Field>
          <Field label={t('field_price')}>
            <input type="number" className={inputCls} value={item.price} onChange={(e) => update(i, { price: Number(e.target.value) })} />
          </Field>
          <Field label={t('field_quantity')}>
            <input type="number" className={inputCls} value={item.quantity} onChange={(e) => update(i, { quantity: Number(e.target.value) })} />
          </Field>
          <button onClick={() => setItems(items.filter((_, idx) => idx !== i))} className="text-muted-foreground hover:text-destructive p-2">
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <button
        onClick={() => setItems([...items, { id: `p${Date.now()}`, name: '', price: 0, quantity: 0 }])}
        className="flex items-center gap-1.5 text-sm text-primary hover:opacity-80"
      >
        <Plus size={14} /> {t('add_product')}
      </button>
      <LightBeamButton onClick={() => api.saveStock(items)}>{t('save')}</LightBeamButton>
    </div>
  );
}

function ServicesTab() {
  const { t } = useLanguage();
  const [items, setItems] = useState<ServiceItem[]>([]);
  useEffect(() => {
    api.getServices().then(setItems);
  }, []);

  const update = (i: number, patch: Partial<ServiceItem>) => {
    const next = [...items];
    next[i] = { ...next[i], ...patch };
    setItems(next);
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('data_services_desc')}</p>
      {items.map((item, i) => (
        <div key={item.id} className="space-y-2 bg-card/50 border border-border rounded-lg p-3">
          <div className="grid grid-cols-[1fr_120px_36px] gap-3 items-end">
            <Field label={t('field_service_name')}>
              <input dir="rtl" className={inputCls} value={item.name} onChange={(e) => update(i, { name: e.target.value })} />
            </Field>
            <Field label={t('field_duration')}>
              <input type="number" className={inputCls} value={item.duration_minutes} onChange={(e) => update(i, { duration_minutes: Number(e.target.value) })} />
            </Field>
            <button onClick={() => setItems(items.filter((_, idx) => idx !== i))} className="text-muted-foreground hover:text-destructive p-2">
              <Trash2 size={16} />
            </button>
          </div>
          <Field label={t('field_slots')}>
            <input
              className={inputCls + ' w-full'}
              value={item.available_slots.join(', ')}
              onChange={(e) => update(i, { available_slots: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
            />
          </Field>
        </div>
      ))}
      <button
        onClick={() => setItems([...items, { id: `s${Date.now()}`, name: '', duration_minutes: 30, available_slots: [] }])}
        className="flex items-center gap-1.5 text-sm text-primary hover:opacity-80"
      >
        <Plus size={14} /> {t('add_service')}
      </button>
      <LightBeamButton onClick={() => api.saveServices(items)}>{t('save')}</LightBeamButton>
    </div>
  );
}

function MenuTab() {
  const { t } = useLanguage();
  const [menu, setMenu] = useState<MenuData | null>(null);
  useEffect(() => {
    api.getMenu().then(setMenu);
  }, []);

  if (!menu) return null;

  const updateItem = (i: number, patch: Partial<MenuData['items'][0]>) => {
    const items = [...menu.items];
    items[i] = { ...items[i], ...patch };
    setMenu({ ...menu, items });
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('data_menu_desc')}</p>

      <Field label={t('field_special')}>
        <input dir="rtl" className={inputCls + ' w-full'} value={menu.today_special} onChange={(e) => setMenu({ ...menu, today_special: e.target.value })} />
      </Field>

      {menu.items.map((item, i) => (
        <div key={i} className="grid grid-cols-[1fr_100px_2fr_36px] gap-3 items-end bg-card/50 border border-border rounded-lg p-3">
          <Field label={t('field_dish_name')}>
            <input dir="rtl" className={inputCls} value={item.name} onChange={(e) => updateItem(i, { name: e.target.value })} />
          </Field>
          <Field label={t('field_price')}>
            <input type="number" className={inputCls} value={item.price} onChange={(e) => updateItem(i, { price: Number(e.target.value) })} />
          </Field>
          <Field label={t('field_description')}>
            <input dir="rtl" className={inputCls} value={item.description} onChange={(e) => updateItem(i, { description: e.target.value })} />
          </Field>
          <button
            onClick={() => setMenu({ ...menu, items: menu.items.filter((_, idx) => idx !== i) })}
            className="text-muted-foreground hover:text-destructive p-2"
          >
            <Trash2 size={16} />
          </button>
        </div>
      ))}
      <button
        onClick={() => setMenu({ ...menu, items: [...menu.items, { name: '', price: 0, description: '' }] })}
        className="flex items-center gap-1.5 text-sm text-primary hover:opacity-80"
      >
        <Plus size={14} /> {t('add_dish')}
      </button>

      <Field label={t('field_table_slots')}>
        <input
          className={inputCls + ' w-full'}
          value={menu.table_slots.join(', ')}
          onChange={(e) => setMenu({ ...menu, table_slots: e.target.value.split(',').map((s) => s.trim()).filter(Boolean) })}
        />
      </Field>

      <LightBeamButton onClick={() => api.saveMenu(menu)}>{t('save')}</LightBeamButton>
    </div>
  );
}

export default function StoreDataPage() {
  const { t } = useLanguage();
  const [tab, setTab] = useState<Tab>('stock');

  const tabs: { id: Tab; key: DictKey }[] = [
    { id: 'stock', key: 'data_tab_stock' },
    { id: 'services', key: 'data_tab_services' },
    { id: 'menu', key: 'data_tab_menu' },
  ];

  return (
    <div className="max-w-2xl mx-auto px-4 py-6 space-y-6">
      <div>
        <h2 className="text-lg font-semibold mb-1">{t('data_title')}</h2>
        <p className="text-xs text-muted-foreground">{t('data_subtitle')}</p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {tabs.map((tabDef) => (
          <button
            key={tabDef.id}
            onClick={() => setTab(tabDef.id)}
            className={`px-4 py-2 text-sm transition-colors border-b-2 -mb-px ${
              tab === tabDef.id ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
            }`}
          >
            {t(tabDef.key)}
          </button>
        ))}
      </div>

      <div className="pb-6">
        {tab === 'stock' && <StockTab />}
        {tab === 'services' && <ServicesTab />}
        {tab === 'menu' && <MenuTab />}
      </div>
    </div>
  );
}
