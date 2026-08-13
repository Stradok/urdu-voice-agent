import React, { useState } from 'react';
import { Mic, Send } from 'lucide-react';
import { cn } from '../lib/utils';

export interface WhatsAppInputProps {
  placeholder?: string;
  onSubmit?: (value: string) => void;
  onMicHoldStart?: () => void;
  onMicHoldEnd?: () => void;
  micActive?: boolean;
  disabled?: boolean;
}

// WhatsApp shows either a mic OR a send arrow, never both at once - swaps the moment there's
// text to send, unlike the dashboard's other pages (RadiantPromptInput), which show both side
// by side. Kept as its own component rather than a RadiantPromptInput variant so this page's
// WhatsApp look doesn't leak into the rest of the dashboard's existing style.
export default function WhatsAppInput({
  placeholder = 'Type a message',
  onSubmit,
  onMicHoldStart,
  onMicHoldEnd,
  micActive,
  disabled,
}: WhatsAppInputProps) {
  const [value, setValue] = useState('');

  const handleSubmit = () => {
    if (value.trim() && !disabled) {
      onSubmit?.(value);
      setValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const hasText = value.trim().length > 0;

  return (
    <div className="flex items-end gap-2 px-3 py-2 bg-[#202c33]">
      <div className="flex-1 flex items-center bg-[#2a3942] rounded-3xl px-4 py-2.5 min-h-[44px]">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || micActive}
          className="flex-1 bg-transparent border-none outline-none text-[#e9edef] placeholder:text-[#8696a0] text-[15px] min-w-0"
        />
      </div>

      {hasText ? (
        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled}
          aria-label="Send"
          className="flex-shrink-0 flex items-center justify-center w-11 h-11 rounded-full bg-[#00a884] text-[#111b21] hover:bg-[#06cf9c] transition-colors disabled:opacity-50"
        >
          <Send size={19} strokeWidth={2} />
        </button>
      ) : (
        <button
          type="button"
          onMouseDown={onMicHoldStart}
          onMouseUp={onMicHoldEnd}
          onMouseLeave={() => micActive && onMicHoldEnd?.()}
          onTouchStart={(e) => {
            e.preventDefault();
            onMicHoldStart?.();
          }}
          onTouchEnd={(e) => {
            e.preventDefault();
            onMicHoldEnd?.();
          }}
          disabled={disabled}
          aria-label="Hold to talk"
          className={cn(
            'flex-shrink-0 flex items-center justify-center w-11 h-11 rounded-full transition-colors select-none disabled:opacity-50',
            micActive ? 'bg-[#ef4444] text-white animate-pulse' : 'bg-[#00a884] text-[#111b21] hover:bg-[#06cf9c]',
          )}
        >
          <Mic size={19} strokeWidth={2} />
        </button>
      )}
    </div>
  );
}
