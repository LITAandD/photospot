import React from 'react';
/** Native exposure awaits a native viewability adapter; mounting is NOT an impression. */
export function CardExposure({ children }: { children: React.ReactNode; placeId: string; requestId?: string; rank: number; active?: boolean }) {
  return <>{children}</>;
}
