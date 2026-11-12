import React, { useEffect, useRef } from 'react';
import { View } from 'react-native';
import { track } from '@/analytics';

/** >=50% of the card visible for >=1s, foreground tab, once per request/place. */
export function CardExposure({ children, placeId, requestId, rank, active = true }: { children: React.ReactNode; placeId: string; requestId?: string; rank: number; active?: boolean }) {
  const ref = useRef<View>(null);
  const sent = useRef<string | null>(null);
  useEffect(() => {
    const node = ref.current as unknown as Element;
    if (!active || !node || !requestId || typeof IntersectionObserver === 'undefined') return;
    let timer: ReturnType<typeof setTimeout> | undefined, visible = false;
    const cancel = () => { if (timer) clearTimeout(timer); timer = undefined; };
    const check = () => {
      cancel();
      if (!visible || document.visibilityState !== 'visible' || sent.current === requestId) return;
      timer = setTimeout(() => {
        sent.current = requestId;
        void track('card_impression', { request_id: requestId, place_id: placeId, rank });
      }, 1000);
    };
    const observer = new IntersectionObserver(entries => { visible = entries[0].intersectionRatio >= 0.5; check(); }, { threshold: [0, 0.5] });
    observer.observe(node);
    document.addEventListener('visibilitychange', check);
    return () => { cancel(); observer.disconnect(); document.removeEventListener('visibilitychange', check); };
  }, [placeId, requestId, rank, active]);
  return <View ref={ref}>{children}</View>;
}
