import rawDevices from '../../../config/room_devices.json';
import rawScenes from '../../../config/room_scenes.json';
import type { RoomDevice, RoomScene } from '../contracts';

// Direct imports from the versioned canonical files; no second inventory.
export const devices: readonly RoomDevice[] = Object.freeze(rawDevices.devices.map(d => Object.freeze({
  id: d.id, name: d.name, group: d.group as RoomDevice['group'], category: d.category as RoomDevice['category'],
  manufacturer: d.manufacturer, model: d.model, integration: d.integration_status as RoomDevice['integration'], recordKind: d.record_kind,
})));
export const scenes = Object.freeze(rawScenes.scenes) as unknown as readonly RoomScene[];
export const deviceById = new Map(devices.map(d => [d.id, d]));

export interface ScenePreviewItem { readonly id: string; readonly name: string; readonly action: string; readonly pending: boolean; readonly after: readonly string[] }
export function previewScene(scene: RoomScene): readonly ScenePreviewItem[] {
  const byStep = new Map(scene.steps.map(step => [step.id, step]));
  const pending = [...scene.steps]; const ordered: typeof pending = [];
  while (pending.length) {
    const ready = pending.filter(step => step.depends_on.every(ref => byStep.has(ref) && ordered.some(done => done.id === ref)));
    if (!ready.length) throw new Error('invalid_scene_dependencies');
    for (const step of ready) { ordered.push(step); pending.splice(pending.indexOf(step), 1); }
  }
  const result = new Map<string, ScenePreviewItem>();
  for (const step of ordered) {
    const targets = devices.filter(d => step.target_kind === 'group' ? d.group === step.target_id : d.id === step.target_id);
    if (!targets.length) throw new Error('unknown_scene_target');
    for (const d of targets) {
      const previous = result.get(d.id);
      if (previous && previous.action !== step.action) throw new Error('conflicting_scene_actions');
      if (!previous) result.set(d.id, { id: d.id, name: d.name, action: step.action, pending: d.integration !== 'lab_existing', after: step.depends_on });
    }
  }
  return Object.freeze([...result.values()]);
}
