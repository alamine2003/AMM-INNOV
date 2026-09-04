import { create } from 'zustand';

export type RealtimeStatus = 'connected' | 'reconnecting' | 'polling' | 'idle';

interface RealtimeState {
  status: RealtimeStatus;
  lastEventAt: number | null;
  setStatus: (status: RealtimeStatus) => void;
  touch: () => void;
}

export const useRealtimeStore = create<RealtimeState>((set) => ({
  status: 'idle',
  lastEventAt: null,
  setStatus: (status) => set({ status }),
  touch: () => set({ lastEventAt: Date.now() }),
}));
