import { describe, expect, it } from 'vitest';
import { pollInterval, reconnectDelay } from '../useRealtime';

describe('reconnectDelay', () => {
  it('suit le palier exponentiel 1 s → 30 s, entre sa moitié et sa totalité', () => {
    expect(reconnectDelay(1, () => 0)).toBe(500);
    expect(reconnectDelay(1, () => 1)).toBe(1000);
    expect(reconnectDelay(4, () => 0.999)).toBeLessThanOrEqual(8000);
    expect(reconnectDelay(4, () => 0)).toBe(4000);
    expect(reconnectDelay(20, () => 1)).toBe(30000);
  });

  it('étale les clients coupés au même instant (campagne de chaos s17)', () => {
    const delays = Array.from({ length: 300 }, () => reconnectDelay(1));
    const distinctMs = new Set(delays).size;
    expect(distinctMs).toBeGreaterThan(100);
    expect(Math.min(...delays)).toBeGreaterThanOrEqual(500);
    expect(Math.max(...delays)).toBeLessThanOrEqual(1000);
  });
});

describe('pollInterval', () => {
  it('reste entre 60 et 70 s', () => {
    expect(pollInterval(() => 0)).toBe(60000);
    expect(pollInterval(() => 1)).toBe(70000);
  });
});
