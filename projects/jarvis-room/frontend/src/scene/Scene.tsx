import { Component, memo, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';
import type { VoiceState } from '../contracts';
import { buildHologram } from './hologram';
import { damp, qualityProfile, seeded, stateTargets, type Quality } from './motion';

function Hologram({ state, amplitude, reduced, quality }: { state: VoiceState; amplitude: number; reduced: boolean; quality: ReturnType<typeof qualityProfile> }) {
  const model = useMemo(() => buildHologram(quality.layers, quality.rings, quality.particles), [quality.layers, quality.rings, quality.particles]);
  const animation = useRef({ speed: .65, brightness: .85, focus: 0, pulse: .02, error: 0, amplitude: 0, time: 0 });
  const { viewport } = useThree();
  useEffect(() => () => model.dispose(), [model]);
  useFrame((_, rawDelta) => {
    const delta = Math.min(rawDelta, .05); const a = animation.current; const target = stateTargets[state];
    for (const key of ['speed', 'brightness', 'focus', 'pulse', 'error'] as const) a[key] = reduced ? target[key] : damp(a[key], target[key], 3, delta);
    a.amplitude = reduced ? 0 : damp(a.amplitude, state === 'RESPONDING' || state === 'LISTENING' ? amplitude : 0, 8, delta);
    if (!reduced) {
      a.time += delta;
      for (const rotor of model.rotors) {
        rotor.object.rotation.x += rotor.x * delta * a.speed;
        rotor.object.rotation.y += rotor.y * delta * a.speed;
        rotor.object.rotation.z += rotor.z * delta * a.speed;
      }
    }
    const organic = reduced ? 0 : Math.sin(a.time * 1.15) * .006;
    const pulse = a.amplitude * a.pulse;
    const fit = Math.min(1, viewport.width / 6.2);
    model.object.scale.set(fit * (1 + organic + pulse), fit * (1 + organic + pulse * .74), fit * (1 + pulse * .42));
    model.uniforms.uTime.value = a.time;
    model.uniforms.uEnergy.value = a.amplitude;
    model.uniforms.uFocus.value = a.focus;
    model.uniforms.uError.value = a.error;
    model.core.scale.setScalar(a.brightness * (1 + a.amplitude * .3));
    model.ringMaterial.opacity = Math.min(.94, .52 * a.brightness + a.amplitude * .15);
    model.ringMaterial.color.setRGB(2.2, .76 - a.error * .4, .09);
  });
  return <primitive object={model.object} dispose={null} />;
}

function Bloom({ fps, reduced }: { fps: number; reduced: boolean }) {
  const { gl, scene, camera, size } = useThree();
  const composer = useMemo(() => {
    const c = new EffectComposer(gl);
    c.addPass(new RenderPass(scene, camera));
    c.addPass(new UnrealBloomPass(new THREE.Vector2(1, 1), .78, .65, .55));
    c.addPass(new OutputPass()); return c;
  }, [gl, scene, camera]);
  const elapsed = useRef(1);
  useEffect(() => { composer.setPixelRatio(gl.getPixelRatio()); composer.setSize(size.width, size.height); }, [composer, gl, size.width, size.height]);
  useEffect(() => () => { composer.passes.forEach(pass => pass.dispose()); composer.dispose(); }, [composer]);
  useFrame((_, delta) => {
    elapsed.current += Math.min(delta, .1);
    if (reduced || elapsed.current >= 1 / fps) { composer.render(delta); elapsed.current = 0; }
  }, 1);
  return null;
}

function webGLAvailable() {
  try {
    const canvas = document.createElement('canvas');
    const gl = canvas.getContext('webgl2', { failIfMajorPerformanceCaveat: false });
    if (!gl) return false;
    gl.getExtension('WEBGL_lose_context')?.loseContext(); return true;
  } catch { return false; }
}

export function CompatibilityHologram({ reduced, state }: { reduced: boolean; state: VoiceState }) {
  const paths = useMemo(() => {
    const random = seeded(44); return Array.from({ length: 9 }, (_, layer) => {
      let path = ''; const r = 170 + layer * 13;
      for (let i = 0; i < 150; i++) {
        if (random() < .3) continue;
        const a = i / 150 * Math.PI * 2; const b = (i + .7) / 150 * Math.PI * 2;
        const rad = r + (random() > .78 ? 6 : 0);
        path += `M${Math.cos(a) * rad},${Math.sin(a) * rad}L${Math.cos(b) * rad},${Math.sin(b) * rad}`;
        if (i % 5 === 0) path += `l${Math.cos(b) * 11},${Math.sin(b) * 11}`;
      }
      return path;
    });
  }, []);
  return <div className={`compatibility-hologram ${reduced ? 'reduced' : ''}`} data-renderer="fallback" aria-label="Holograma em modo de compatibilidade">
    <svg viewBox="-350 -350 700 700" role="img" aria-label={`Holograma dourado, estado ${state}`}>
      <defs><radialGradient id="core"><stop stopColor="#fff6c9" /><stop offset=".16" stopColor="#ffd578" /><stop offset=".4" stopColor="#f69b25" stopOpacity=".28" /><stop offset="1" stopColor="#ec8a15" stopOpacity="0" /></radialGradient></defs>
      {paths.map((d, i) => <g key={i} className="fallback-layer" style={{ animationDuration: `${65 + i * 11}s`, animationDirection: i % 2 ? 'reverse' : 'normal' }}><path d={d} fill="none" stroke={i % 3 ? '#ffb539' : '#ffd583'} strokeWidth={i % 2 ? '.65' : '1.1'} opacity=".8" transform={`rotate(${i * 37}) scale(1 ${.4 + i * .065})`} /></g>)}
      {Array.from({ length: 8 }, (_, i) => <ellipse key={i} rx={80 + i * 26} ry={28 + i * 16} transform={`rotate(${i * 31})`} fill="none" stroke="#ffb430" opacity=".55" strokeWidth=".9" strokeDasharray={`${40 + i * 7} ${8 + i * 5}`} />)}
      <circle r="100" fill="url(#core)" /><circle r="26" fill="none" stroke="#ffe4a5" strokeWidth="2" /><circle r="15" fill="#fff1c1" opacity=".9" />
    </svg>
    <span className="compatibility-note">Modo compatibilidade · WebGL indisponível</span>
  </div>;
}
class Boundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

export const SceneSurface = memo(function SceneSurface({ state, amplitude, quality, reduced, visible }: { state: VoiceState; amplitude: number; quality: Quality; reduced: boolean; visible: boolean }) {
  const [available, setAvailable] = useState(webGLAvailable);
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight });
  useEffect(() => { const resize = () => setSize({ width: window.innerWidth, height: window.innerHeight }); window.addEventListener('resize', resize); return () => window.removeEventListener('resize', resize); }, []);
  const profile = useMemo(() => qualityProfile(quality, size.width, size.height, window.devicePixelRatio, navigator.hardwareConcurrency), [quality, size]);
  const fallback = <CompatibilityHologram state={state} reduced={reduced} />;
  if (!available) return fallback;
  return <Boundary fallback={fallback}><div className="scene-canvas" data-renderer="webgl" data-quality={profile.level} data-frameloop={!visible ? 'never' : reduced ? 'demand' : 'always'}>
    <Canvas camera={{ position: [0, 0, 8.5], fov: 43, near: .1, far: 30 }} dpr={profile.pixelRatio}
      frameloop={!visible ? 'never' : reduced ? 'demand' : 'always'}
      gl={{ alpha: true, antialias: false, powerPreference: 'low-power' }}
      onCreated={({ gl }) => { gl.setClearColor(0x000000, 0); gl.domElement.addEventListener('webglcontextlost', () => setAvailable(false), { once: true }); }}>
      <Hologram state={state} amplitude={amplitude} reduced={reduced} quality={profile} />
      <Bloom fps={profile.fps} reduced={reduced} />
    </Canvas>
  </div></Boundary>;
});
