import { describe, expect, it, vi } from 'vitest';
import { damp, qualityProfile, seeded, stateTargets } from './motion';
import { buildHologram } from './hologram';
import { VOICE_STATES } from '../contracts';
describe('lightweight animation safeguards', () => {
  it('defines targets for all six states without hiding the core', () => { expect(Object.keys(stateTargets)).toEqual([...VOICE_STATES]); for (const state of VOICE_STATES) expect(stateTargets[state].brightness).toBeGreaterThan(0); });
  it('concentrates energy when thinking and responds to speaking amplitude', () => { expect(stateTargets.THINKING.focus).toBeGreaterThan(stateTargets.IDLE.focus); expect(stateTargets.RESPONDING.pulse).toBeGreaterThan(stateTargets.IDLE.pulse); expect(stateTargets.ERROR.error).toBe(1); });
  it('interpolates without overshooting and accounts for delta time', () => { const one = damp(0, 1, 3, .1); const two = damp(damp(0, 1, 3, .05), 1, 3, .05); expect(one).toBeCloseTo(two, 10); expect(damp(0, 1, 3, -1)).toBe(0); expect(damp(0, 1, 3, 50)).toBeLessThan(1); });
  it('caps rendering resolution at 1080p, 1440p and 4K', () => { for (const [width, height] of [[1920,1080],[2560,1440],[3840,2160]]) { const q = qualityProfile('balanced', width, height, 2); expect(width * height * q.pixelRatio ** 2).toBeLessThanOrEqual(q.pixels + 1); expect(q.pixelRatio).toBeLessThanOrEqual(1.5); } });
  it('uses conservative quality on limited devices', () => { expect(qualityProfile('auto', 1920,1080,1,4).level).toBe('low'); expect(qualityProfile('auto', 1920,1080,1,8).level).toBe('balanced'); expect(qualityProfile('high', 1920,1080).particles).toBeLessThan(2500); });
  it('builds deterministic geometry rather than a video texture', () => { const a = seeded(42), b = seeded(42); expect([a(),a(),a()]).toEqual([b(),b(),b()]); const model = buildHologram(2,3,20); expect(model.rotors.length).toBeGreaterThan(3); expect(model.geometries.size).toBeGreaterThan(3); expect(model.object.children.length).toBeGreaterThan(3); model.dispose(); });
  it('disposes each geometry and material exactly once', () => { const model = buildHologram(2,3,20); const resources = [...model.geometries, ...model.materials]; const spies = resources.map(resource => vi.spyOn(resource, 'dispose')); model.dispose(); model.dispose(); spies.forEach(spy => expect(spy).toHaveBeenCalledOnce()); });
});
