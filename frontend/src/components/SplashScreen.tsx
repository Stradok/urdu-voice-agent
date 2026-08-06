import React, { useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import { useLanguage } from '../lib/i18n';
import LightBeamButton from './LightBeamButton';

interface Trail {
  x: number;
  y: number;
  id: number;
}

const CALM_COLORS = ['#312e81', '#4c1d95', '#0e7490'];
const REVEALED_COLORS = ['#a21caf', '#c026d3', '#f97316'];

function WaveMotif({ colors, seed }: { colors: string[]; seed: number }) {
  const bars = Array.from({ length: 40 }, (_, i) => {
    const h = 20 + Math.abs(Math.sin(i * 0.5 + seed)) * 60;
    return h;
  });
  return (
    <svg viewBox="0 0 800 400" className="w-full h-full" preserveAspectRatio="xMidYMid slice">
      <defs>
        <linearGradient id={`grad-${seed}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor={colors[0]} />
          <stop offset="50%" stopColor={colors[1]} />
          <stop offset="100%" stopColor={colors[2]} />
        </linearGradient>
      </defs>
      <rect width="800" height="400" fill="#0a0a0f" />
      {bars.map((h, i) => (
        <rect
          key={i}
          x={i * 20}
          y={200 - h / 2}
          width="10"
          height={h}
          rx="5"
          fill={`url(#grad-${seed})`}
          opacity={0.85}
        />
      ))}
    </svg>
  );
}

export function SplashScreen({ onDone }: { onDone: () => void }) {
  const { t } = useLanguage();
  const containerRef = useRef<HTMLDivElement>(null);
  const [mouse, setMouse] = useState({ x: -500, y: -500 });
  const [trails, setTrails] = useState<Trail[]>([]);
  const lastMove = useRef({ x: -500, y: -500, t: 0 });
  const trailId = useRef(0);

  useEffect(() => {
    const handleMove = (e: MouseEvent) => {
      const rect = containerRef.current?.getBoundingClientRect();
      if (!rect) return;
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      setMouse({ x, y });

      const now = performance.now();
      const dt = now - lastMove.current.t;
      const dist = Math.hypot(x - lastMove.current.x, y - lastMove.current.y);
      const speed = dt > 0 ? dist / dt : 0;

      if (speed > 0.3) {
        trailId.current += 1;
        const id = trailId.current;
        setTrails((prev) => [...prev.slice(-6), { x, y, id }]);
        setTimeout(() => {
          setTrails((prev) => prev.filter((t) => t.id !== id));
        }, 500);
      }

      lastMove.current = { x, y, t: now };
    };

    window.addEventListener('mousemove', handleMove);
    return () => window.removeEventListener('mousemove', handleMove);
  }, []);

  const maskImage = [
    `radial-gradient(circle 90px at ${mouse.x}px ${mouse.y}px, black 60%, transparent 100%)`,
    ...trails.map((t) => `radial-gradient(circle 50px at ${t.x}px ${t.y}px, black 40%, transparent 100%)`),
  ].join(', ');

  const parallaxX = (mouse.x - 640) * -0.01;
  const parallaxY = (mouse.y - 400) * -0.01;

  return (
    <div ref={containerRef} className="relative h-full w-full overflow-hidden bg-background cursor-none">
      {/* base layer - always visible */}
      <div className="absolute inset-0">
        <WaveMotif colors={CALM_COLORS} seed={1} />
      </div>

      {/* revealed layer - shown only inside the blob mask */}
      <div
        className="absolute inset-0"
        style={{
          maskImage,
          WebkitMaskImage: maskImage,
        }}
      >
        <WaveMotif colors={REVEALED_COLORS} seed={2} />
      </div>

      {/* subtle wave lines, parallax-reactive */}
      <svg
        className="absolute inset-0 w-full h-full pointer-events-none opacity-20"
        style={{ transform: `translate(${parallaxX}px, ${parallaxY}px)` }}
        viewBox="0 0 800 400"
      >
        <path d="M0,200 Q200,150 400,200 T800,200" stroke="#8b5cf6" strokeWidth="1.5" fill="none" />
        <path d="M0,240 Q200,290 400,240 T800,240" stroke="#06b6d4" strokeWidth="1.5" fill="none" />
        <path d="M0,160 Q200,110 400,160 T800,160" stroke="#8b5cf6" strokeWidth="1" fill="none" opacity="0.6" />
      </svg>

      {/* content */}
      <div className="relative z-10 h-full w-full flex flex-col items-center justify-center gap-6 pointer-events-none">
        <motion.h1
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-5xl font-semibold text-white transition-colors duration-300"
        >
          سارہ
        </motion.h1>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-neutral-400 text-sm tracking-wide"
        >
          {t('splash_tagline')}
        </motion.p>

        <div className="pointer-events-auto mt-4">
          <LightBeamButton onClick={onDone}>{t('splash_start')}</LightBeamButton>
        </div>
      </div>
    </div>
  );
}

export default SplashScreen;
