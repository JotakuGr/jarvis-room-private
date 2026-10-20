import type { VoiceState } from '../contracts';
export type Quality = 'auto' | 'low' | 'balanced' | 'high';
export const stateTargets: Record<VoiceState, { speed: number; brightness: number; focus: number; pulse: number; error: number }> = {
  IDLE: { speed: .65, brightness: .85, focus: 0, pulse: .02, error: 0 },
  LISTENING: { speed: .8, brightness: 1.12, focus: .15, pulse: .07, error: 0 },
  TRANSCRIBING: { speed: 1.12, brightness: 1.2, focus: .4, pulse: .035, error: 0 },
  THINKING: { speed: 1.65, brightness: 1.3, focus: .8, pulse: .025, error: 0 },
  RESPONDING: { speed: 1.05, brightness: 1.15, focus: .2, pulse: .16, error: 0 },
  ERROR: { speed: .4, brightness: .85, focus: 0, pulse: .02, error: 1 },
};
export function damp(current: number, target: number, speed: number, delta: number) {
  return current + (target - current) * (1 - Math.exp(-speed * Math.min(.1, Math.max(0, delta))));
}
export function qualityProfile(quality: Quality, width: number, height: number, ratio = 1, cores = 8) {
  const level = quality === 'auto' ? (cores <= 4 ? 'low' : 'balanced') : quality;
  const config = { low: { particles: 550, layers: 5, rings: 12, pixels: 900_000, fps: 30 },
    balanced: { particles: 1300, layers: 8, rings: 19, pixels: 1_900_000, fps: 40 },
    high: { particles: 2100, layers: 10, rings: 24, pixels: 2_800_000, fps: 45 } }[level];
  return { ...config, level, pixelRatio: Math.max(.25, Math.min(1.5, ratio, Math.sqrt(config.pixels / Math.max(1, width * height)))) };
}
export function seeded(seed: number) { let value = seed >>> 0; return () => { value = (1664525 * value + 1013904223) >>> 0; return value / 4294967296; }; }
