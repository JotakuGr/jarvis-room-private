import * as THREE from 'three';
import { seeded } from './motion';

const TAU = Math.PI * 2;
type Rotor = { object: THREE.Object3D; x: number; y: number; z: number };
export function buildHologram(layers: number, ringCount: number, particleCount: number) {
  const random = seeded(831); const root = new THREE.Group(); const rotors: Rotor[] = [];
  const geometries = new Set<THREE.BufferGeometry>(); const materials = new Set<THREE.Material>();
  const uniforms = { uTime: { value: 0 }, uEnergy: { value: 0 }, uFocus: { value: 0 }, uError: { value: 0 } };
  const lineMaterial = new THREE.ShaderMaterial({
    uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `attribute float aSeed; varying float vSeed; uniform float uTime; uniform float uEnergy;
      void main(){vSeed=aSeed;vec3 p=position; p+=normalize(position)*sin(position.y*8.+position.x*5.+uTime*1.3)*uEnergy*.027;
      gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`,
    fragmentShader: `varying float vSeed;uniform float uTime;uniform float uEnergy;uniform float uError;
      void main(){float activity=.75+.25*sin(vSeed*52.+uTime*.7); vec3 gold=mix(vec3(1.,.21,.008),vec3(1.,.69,.15),vSeed);
      gold=mix(gold,vec3(1.,.095,.025),uError*.55);gl_FragColor=vec4(gold*(1.25+uEnergy*.75),(.28+vSeed*.62)*activity);}`,
  }); materials.add(lineMaterial);
  const fragmentMaterial = new THREE.MeshBasicMaterial({ color: new THREE.Color(1.5, .57, .04), transparent: true, opacity: .06, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }); materials.add(fragmentMaterial);
  const ringMaterial = new THREE.MeshBasicMaterial({ color: new THREE.Color(2.2, .76, .09), transparent: true, opacity: .63, depthWrite: false, blending: THREE.AdditiveBlending, toneMapped: false }); materials.add(ringMaterial);
  function geometry(vertices: number[], isLine = true) {
    const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    if (isLine) geo.setAttribute('aSeed', new THREE.Float32BufferAttribute(Array.from({ length: vertices.length / 3 }, () => random()), 1));
    geometries.add(geo); return geo;
  }
  function polar(radius: number, angle: number, latitude: number): [number, number, number] {
    return [radius * Math.cos(latitude) * Math.cos(angle), radius * Math.sin(latitude), radius * Math.cos(latitude) * Math.sin(angle)];
  }
  function segment(vertices: number[], a: number[], b: number[]) { vertices.push(...a, ...b); }
  for (let layer = 0; layer < layers; layer++) {
    const group = new THREE.Group(); const lines: number[] = []; const panels: number[] = [];
    const radius = 1.15 + layer * .175;
    // Broken spherical bands, radial jumpers and tiny circuit teeth.
    for (let belt = 0; belt < 11; belt++) {
      const latitude = -.95 + belt * .19 + (random() - .5) * .12;
      const count = 58 + layer * 4; const phase = random() * TAU;
      for (let i = 0; i < count; i++) {
        if (random() < .34) continue;
        const angle = phase + i * TAU / count; const length = (.4 + random() * .45) * TAU / count;
        const r = radius + (random() > .8 ? .045 : 0);
        const a = polar(r, angle, latitude); const b = polar(r, angle + length, latitude);
        segment(lines, a, b);
        if (random() > .66) segment(lines, b, polar(r + .06 + random() * .07, angle + length, latitude));
        if (random() > .75) {
          const c = polar(r, angle, latitude + .065); const d = polar(r, angle + length, latitude + .065);
          panels.push(...a, ...b, ...c, ...b, ...d, ...c);
        }
      }
    }
    // Fragmented meridians; no opaque spherical skin.
    for (let stripe = 0; stripe < 15; stripe++) {
      const azimuth = random() * TAU;
      for (let j = 0; j < 20; j++) {
        if (random() < .46) continue;
        const latitude = -1.35 + j * .135;
        segment(lines, polar(radius + .035, azimuth, latitude), polar(radius + .035, azimuth, latitude + .085));
      }
    }
    group.add(new THREE.LineSegments(geometry(lines), lineMaterial), new THREE.Mesh(geometry(panels, false), fragmentMaterial));
    group.rotation.set(layer * .51, layer * .78, layer * .32);
    rotors.push({ object: group, x: .007 * (layer % 2 ? -1 : 1), y: .018 * (layer % 2 ? 1 : -1), z: .008 + layer * .001 });
    root.add(group);
  }
  for (let i = 0; i < ringCount; i++) {
    const radius = .5 + (i / ringCount) * 2.12;
    const geo = new THREE.TorusGeometry(radius, i < 4 ? .009 : .0035, 3, 140, TAU * (.4 + random() * .5)); geometries.add(geo);
    const ring = new THREE.Mesh(geo, ringMaterial); const orbit = new THREE.Group(); orbit.add(ring);
    orbit.rotation.set(random() * Math.PI, random() * Math.PI, random() * TAU);
    rotors.push({ object: orbit, x: .014 * (i % 2 ? 1 : -1), y: .023 * (i % 3 ? -1 : 1), z: .012 * (i % 2 ? -1 : 1) });
    root.add(orbit);
  }
  // Sweeping, eccentric filaments around the nucleus and outer shell.
  for (let i = 0; i < 10; i++) {
    const vertices: number[] = []; const r = .55 + random() * 2.05;
    for (let j = 0; j < 130; j++) {
      const a = j / 130 * TAU; const b = (j + .8) / 130 * TAU;
      segment(vertices, [Math.cos(a) * r, Math.sin(a) * r * .22, Math.sin(a * 3 + i) * .1],
        [Math.cos(b) * r, Math.sin(b) * r * .22, Math.sin(b * 3 + i) * .1]);
    }
    const line = new THREE.LineSegments(geometry(vertices), lineMaterial); line.rotation.set(i * .57, i * .38, i * .71);
    rotors.push({ object: line, x: .008, y: -.01, z: i % 2 ? .025 : -.018 }); root.add(line);
  }
  const pointVertices: number[] = []; const seeds: number[] = [];
  for (let i = 0; i < particleCount; i++) {
    const r = 1.5 + random() * 1.13; const lat = Math.asin(random() * 2 - 1);
    pointVertices.push(...polar(r, random() * TAU, lat)); seeds.push(random());
  }
  const pointGeometry = geometry(pointVertices, false); pointGeometry.setAttribute('aSeed', new THREE.Float32BufferAttribute(seeds, 1));
  const pointMaterial = new THREE.ShaderMaterial({ uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `attribute float aSeed; varying float vSeed;uniform float uTime;uniform float uFocus;uniform float uEnergy;
      void main(){vSeed=aSeed;vec3 p=position;float a=uTime*(.025+aSeed*.03);p.xz=mat2(cos(a),-sin(a),sin(a),cos(a))*p.xz;
      p*=1.-uFocus*.11*(.5+.5*sin(aSeed*37.+uTime));p+=normalize(p)*uEnergy*.04*sin(uTime*3.+aSeed*40.);
      vec4 mv=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*mv;gl_PointSize=min(9.,(1.3+aSeed*1.5)*(9./-mv.z));}`,
    fragmentShader: `varying float vSeed;uniform float uTime;uniform float uError;
      void main(){float d=length(gl_PointCoord-.5);if(d>.5)discard;float spark=pow(max(0.,sin(vSeed*193.+uTime*1.1)),28.);
      vec3 gold=mix(vec3(1.,.36,.015),vec3(1.,.83,.36),spark);gold=mix(gold,vec3(1.,.15,.06),uError*.5);
      gl_FragColor=vec4(gold*(1.3+spark),pow(1.-d*2.,1.7)*(.55+spark*.45));}`,
  }); materials.add(pointMaterial);
  const points = new THREE.Points(pointGeometry, pointMaterial); root.add(points);
  const coreGeometry = new THREE.PlaneGeometry(2.4, 2.4); geometries.add(coreGeometry);
  const coreMaterial = new THREE.ShaderMaterial({ uniforms, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`,
    fragmentShader: `varying vec2 vUv;uniform float uTime;uniform float uEnergy;uniform float uError;
      void main(){vec2 p=(vUv-.5)*2.;float r=length(p);float a=atan(p.y,p.x);float core=.022/(r*r+.006);
      float halo=.04/(r+.08);float rings=pow(max(0.,sin(r*62.-uTime*.5+sin(a*5.)*.4)),16.)*exp(-r*5.);
      float rays=pow(abs(sin(a*7.+sin(r*9.+uTime*.3))),25.)*exp(-r*4.)*.45;
      vec3 gold=mix(vec3(1.,.51,.08),vec3(1.,.18,.025),uError*.5);vec3 color=gold*(core+halo+rings+rays)*(1.+uEnergy*.8);
      gl_FragColor=vec4(color,clamp((core+halo+rings+rays)*.7,0.,1.)*(1.-smoothstep(.6,1.,r)));}`,
  }); materials.add(coreMaterial);
  const core = new THREE.Mesh(coreGeometry, coreMaterial); core.position.z = .15; root.add(core);
  root.position.y = .25;
  let disposed = false;
  return { object: root, rotors, uniforms, core, ringMaterial, fragmentMaterial, geometries, materials,
    dispose() { if (disposed) return; disposed = true; geometries.forEach(g => g.dispose()); materials.forEach(m => m.dispose()); },
  };
}
