import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js";
import { telemetryAt } from "./state.js";

const IMG = "https://unpkg.com/three-globe@2.31.1/example/img/";
const CLOUDS = "https://cdn.jsdelivr.net/gh/mrdoob/three.js@r170/examples/textures/planets/earth_clouds_1024.png";

export function mountScene({ container, canvas, label, reduced }) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.75));
  renderer.outputColorSpace = THREE.SRGBColorSpace;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 200);
  camera.position.set(0, 1.1, 9.2);
  camera.lookAt(0, 0, 0);

  const sunDir = new THREE.Vector3(-1, 0.25, 0.35).normalize();
  scene.add(new THREE.AmbientLight(0x8899bb, 0.25));
  const sun = new THREE.DirectionalLight(0xffffff, 2.2);
  sun.position.copy(sunDir).multiplyScalar(20);
  scene.add(sun);

  // ---- stars
  {
    const n = 1800, pos = new Float32Array(n * 3), col = new Float32Array(n * 3);
    let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < n; i++) {
      const r = 40 + rnd() * 40, th = rnd() * Math.PI * 2, ph = Math.acos(2 * rnd() - 1);
      pos.set([r * Math.sin(ph) * Math.cos(th), r * Math.cos(ph), r * Math.sin(ph) * Math.sin(th)], i * 3);
      const c = 0.6 + rnd() * 0.4; col.set([c, c, c + rnd() * 0.15], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("color", new THREE.BufferAttribute(col, 3));
    var stars = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.12, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false }));
    scene.add(stars);
  }

  // ---- earth (day/night shader)
  const R = 2;
  const loader = new THREE.TextureLoader();
  loader.setCrossOrigin("anonymous");
  const tex = (url) => { const t = loader.load(url); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; return t; };
  const earthGroup = new THREE.Group();
  earthGroup.rotation.z = THREE.MathUtils.degToRad(-18);
  scene.add(earthGroup);
  const earthMat = new THREE.ShaderMaterial({
    uniforms: {
      dayMap: { value: tex(IMG + "earth-blue-marble.jpg") },
      nightMap: { value: tex(IMG + "earth-night.jpg") },
      specMap: { value: loader.load(IMG + "earth-water.png") },
      sunDir: { value: sunDir.clone() },
    },
    vertexShader: `
      varying vec2 vUv; varying vec3 vN; varying vec3 vView;
      void main(){ vUv=uv; vec4 wp=modelMatrix*vec4(position,1.);
        vN=normalize(mat3(modelMatrix)*normal); vView=normalize(cameraPosition-wp.xyz);
        gl_Position=projectionMatrix*viewMatrix*wp; }`,
    fragmentShader: `
      uniform sampler2D dayMap; uniform sampler2D nightMap; uniform sampler2D specMap; uniform vec3 sunDir;
      varying vec2 vUv; varying vec3 vN; varying vec3 vView;
      void main(){
        float d=dot(normalize(vN),sunDir);
        float dayMix=smoothstep(-0.18,0.28,d);
        vec3 day=texture2D(dayMap,vUv).rgb; vec3 night=texture2D(nightMap,vUv).rgb*vec3(1.25,1.05,.8);
        vec3 col=mix(night*1.4, day*(0.25+0.95*max(d,0.)), dayMix);
        float water=texture2D(specMap,vUv).r;
        vec3 h=normalize(sunDir+vView); float spec=pow(max(dot(normalize(vN),h),0.),90.)*water*dayMix;
        col+=vec3(0.6,0.75,1.)*spec*0.15;
        float rim=pow(1.-max(dot(vN,vView),0.),3.);
        col+=vec3(0.3,0.6,1.)*rim*0.35*(0.15+dayMix);
        gl_FragColor=vec4(col,1.);
        #include <colorspace_fragment>
      }`,
  });
  const earth = new THREE.Mesh(new THREE.SphereGeometry(R, 96, 96), earthMat);
  earthGroup.add(earth);

  const cloudTex = loader.load(CLOUDS);
  const clouds = new THREE.Mesh(
    new THREE.SphereGeometry(R * 1.012, 72, 72),
    new THREE.MeshLambertMaterial({ map: cloudTex, alphaMap: cloudTex, transparent: true, opacity: 0.55, depthWrite: false }),
  );
  earthGroup.add(clouds);

  // atmosphere glow (back-side fresnel)
  const atmo = new THREE.Mesh(
    new THREE.SphereGeometry(R * 1.1, 64, 64),
    new THREE.ShaderMaterial({
      side: THREE.BackSide, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false,
      uniforms: { sunDir: { value: sunDir } },
      vertexShader: `varying vec3 vN; varying vec3 vW; void main(){ vN=normalize(mat3(modelMatrix)*normal); vW=(modelMatrix*vec4(position,1.)).xyz; gl_Position=projectionMatrix*viewMatrix*vec4(vW,1.);} `,
      fragmentShader: `uniform vec3 sunDir; varying vec3 vN; varying vec3 vW;
        void main(){ vec3 v=normalize(cameraPosition-vW); float i=clamp(pow(0.62-dot(vN,v),4.0),0.,1.);
          float lit=0.35+0.65*smoothstep(-0.4,0.6,dot(-vN,sunDir)*-1.);
          gl_FragColor=vec4(vec3(0.3,0.6,1.)*i*0.85*lit, i*0.8); }`,
    }),
  );
  scene.add(atmo);

  // ---- ground station: Bengaluru 12.97N 77.59E
  const latLon = (lat, lon, r) => {
    const phi = THREE.MathUtils.degToRad(90 - lat), th = THREE.MathUtils.degToRad(lon + 180);
    return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th));
  };
  const gsLocal = latLon(12.97, 77.59, R * 1.003);
  const gs = new THREE.Mesh(new THREE.SphereGeometry(0.035, 16, 16), new THREE.MeshBasicMaterial({ color: 0x5eead4 }));
  gs.position.copy(gsLocal); earth.add(gs);
  const gsRing = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.075, 32), new THREE.MeshBasicMaterial({ color: 0x5eead4, transparent: true, side: THREE.DoubleSide }));
  gsRing.position.copy(gsLocal); gsRing.lookAt(gsLocal.clone().multiplyScalar(2)); earth.add(gsRing);
  // spin earth so Bengaluru faces the camera at the start
  const baseSpin = -Math.atan2(gsLocal.x, gsLocal.z) + 0.55;
  earth.rotation.y = baseSpin; clouds.rotation.y = baseSpin;

  // ---- satellite
  const sat = new THREE.Group();
  const foil = new THREE.MeshStandardMaterial({ color: 0xd4a640, metalness: 0.9, roughness: 0.32, emissive: 0x000000 });
  const white = new THREE.MeshStandardMaterial({ color: 0xdfe6f2, metalness: 0.3, roughness: 0.5 });
  const dark = new THREE.MeshStandardMaterial({ color: 0x222833, metalness: 0.7, roughness: 0.4 });
  const panelTex = (() => {
    const c = document.createElement("canvas"); c.width = 256; c.height = 128; const x = c.getContext("2d");
    const g = x.createLinearGradient(0, 0, 256, 128); g.addColorStop(0, "#14306b"); g.addColorStop(1, "#0a1a40");
    x.fillStyle = g; x.fillRect(0, 0, 256, 128); x.strokeStyle = "#6a8fd8"; x.lineWidth = 1.2;
    for (let i = 0; i <= 256; i += 32) { x.beginPath(); x.moveTo(i, 0); x.lineTo(i, 128); x.stroke(); }
    for (let j = 0; j <= 128; j += 32) { x.beginPath(); x.moveTo(0, j); x.lineTo(256, j); x.stroke(); }
    const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
  })();
  const panelMat = new THREE.MeshStandardMaterial({ map: panelTex, metalness: 0.6, roughness: 0.25, emissive: 0x0a1840, emissiveIntensity: 0.4 });
  const bus = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.2, 0.16), foil); sat.add(bus);
  const top = new THREE.Mesh(new THREE.BoxGeometry(0.17, 0.02, 0.17), white); top.position.y = 0.11; sat.add(top);
  for (const side of [-1, 1]) {
    const boom = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, 0.12), dark);
    boom.rotation.z = Math.PI / 2; boom.position.x = side * 0.14; sat.add(boom);
    const wing = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.005, 0.16), panelMat);
    wing.position.x = side * 0.41; sat.add(wing);
  }
  const dish = new THREE.Mesh(new THREE.SphereGeometry(0.07, 24, 12, 0, Math.PI * 2, 0, Math.PI / 2.6), white);
  dish.material.side = THREE.DoubleSide; dish.rotation.x = Math.PI; dish.position.y = -0.17; sat.add(dish);
  const feed = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.08), dark); feed.position.y = -0.17; sat.add(feed);
  const ant = new THREE.Mesh(new THREE.CylinderGeometry(0.003, 0.003, 0.14), dark); ant.position.set(0.05, 0.18, 0.04); sat.add(ant);
  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 12), new THREE.MeshBasicMaterial({ color: 0x5eead4 }));
  beacon.position.set(0.05, 0.25, 0.04); sat.add(beacon);
  const flame = new THREE.Mesh(new THREE.ConeGeometry(0.03, 0.22, 16, 1, true), new THREE.MeshBasicMaterial({ color: 0x9fd8ff, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  flame.rotation.x = -Math.PI / 2; flame.position.z = -0.2; sat.add(flame);
  sat.scale.setScalar(1.25);
  scene.add(sat);

  // orbit
  const orbitR = R * 1.42;
  const orbitTilt = new THREE.Euler(THREE.MathUtils.degToRad(68), 0, THREE.MathUtils.degToRad(-22));
  const orbitQ = new THREE.Quaternion().setFromEuler(orbitTilt);
  const orbitPts = [];
  for (let i = 0; i <= 256; i++) { const a = (i / 256) * Math.PI * 2; orbitPts.push(new THREE.Vector3(Math.cos(a) * orbitR, 0, Math.sin(a) * orbitR).applyQuaternion(orbitQ)); }
  const orbitLine = new THREE.Line(new THREE.BufferGeometry().setFromPoints(orbitPts), new THREE.LineDashedMaterial({ color: 0x7aa2ff, transparent: true, opacity: 0.22, dashSize: 0.08, gapSize: 0.06 }));
  orbitLine.computeLineDistances(); scene.add(orbitLine);

  // trail
  const TRAIL = 90;
  const trailPos = new Float32Array(TRAIL * 3), trailCol = new Float32Array(TRAIL * 3);
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute("position", new THREE.BufferAttribute(trailPos, 3));
  trailGeo.setAttribute("color", new THREE.BufferAttribute(trailCol, 3));
  const trail = new THREE.Line(trailGeo, new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false }));
  scene.add(trail);

  // beam (ground station -> satellite)
  const beamGeo = new THREE.CylinderGeometry(0.012, 0.09, 1, 24, 1, true); beamGeo.translate(0, 0.5, 0);
  const beam = new THREE.Mesh(beamGeo, new THREE.MeshBasicMaterial({ color: 0x5eead4, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide }));
  scene.add(beam);

  // ---- sizing
  const resize = () => {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h; camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(container); resize();

  let visible = true;
  new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0 }).observe(container);

  let mx = 0, my = 0;
  window.addEventListener("pointermove", (e) => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; }, { passive: true });

  const tmp = new THREE.Vector3(), gsWorld = new THREE.Vector3(), red = new THREE.Color(0xff5d6c), teal = new THREE.Color(0x5eead4);
  const satPosAt = (a, out) => out.set(Math.cos(a) * orbitR, 0, Math.sin(a) * orbitR).applyQuaternion(orbitQ);
  const clock = new THREE.Clock();
  let last = 0;

  const frame = () => {
    const t = clock.getElapsedTime();
    const tel = telemetryAt(t);
    const spin = baseSpin + t * 0.02;
    earth.rotation.y = spin; clouds.rotation.y = spin * 1.04 + t * 0.004;
    stars.rotation.y = t * 0.004;

    const a = t * 0.32 + 1.1;
    satPosAt(a, sat.position);
    satPosAt(a + 0.02, tmp);
    sat.lookAt(tmp);
    const wobble = tel.phase === "anomaly" ? Math.min(1, tel.att / 40) * 0.9 : tel.phase === "burn" ? 0.4 : tel.phase === "recovering" ? Math.max(0, tel.att / 40) * 0.6 : 0;
    sat.rotateZ(Math.sin(t * 2.3) * wobble); sat.rotateX(Math.cos(t * 1.7) * wobble * 0.6);

    const alert = tel.phase === "anomaly";
    const blink = alert ? (Math.sin(t * 10) > 0 ? 1 : 0.15) : 0.6 + Math.sin(t * 3) * 0.4;
    beacon.material.color.copy(alert ? red : teal).multiplyScalar(blink);
    foil.emissive.copy(alert ? red : teal).multiplyScalar(alert ? 0.18 * blink : 0);
    flame.material.opacity = tel.phase === "burn" ? 0.75 + Math.sin(t * 40) * 0.2 : 0;
    flame.scale.y = 0.8 + Math.sin(t * 30) * 0.2;

    // trail
    const trailColor = alert ? red : teal;
    for (let i = 0; i < TRAIL; i++) {
      satPosAt(a - i * 0.012, tmp); trailPos.set([tmp.x, tmp.y, tmp.z], i * 3);
      const f = (1 - i / TRAIL) ** 1.6; trailCol.set([trailColor.r * f, trailColor.g * f, trailColor.b * f], i * 3);
    }
    trailGeo.attributes.position.needsUpdate = true; trailGeo.attributes.color.needsUpdate = true;

    // beam during pass
    gs.getWorldPosition(gsWorld);
    const dist = gsWorld.distanceTo(sat.position);
    const facing = gsWorld.clone().normalize().dot(sat.position.clone().sub(gsWorld).normalize());
    const passOpen = tel.passOpen && facing > 0.1;
    const target = passOpen ? 0.32 + Math.sin(t * 6) * 0.06 : 0;
    beam.material.opacity += (target - beam.material.opacity) * 0.08;
    beam.position.copy(gsWorld); beam.scale.set(1, dist, 1);
    beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), sat.position.clone().sub(gsWorld).normalize());
    gsRing.scale.setScalar(1 + ((t * 0.8) % 1) * 1.6); gsRing.material.opacity = 1 - ((t * 0.8) % 1);

    camera.position.x += (mx * 0.8 - camera.position.x) * 0.03;
    camera.position.y += (1.1 - my * 0.6 - camera.position.y) * 0.03;
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);

    // label
    if (label) {
      tmp.copy(sat.position).project(camera);
      const toCam = camera.position.clone().normalize();
      const along = sat.position.dot(toCam);
      const perp = sat.position.clone().sub(toCam.clone().multiplyScalar(along)).length();
      const behind = along < 0 && perp < R * 1.05;
      const x = (tmp.x * 0.5 + 0.5) * container.clientWidth, y = (-tmp.y * 0.5 + 0.5) * container.clientHeight;
      label.style.transform = `translate(${x + 14}px, ${y - 30}px)`;
      label.style.opacity = behind ? "0" : "1";
      label.classList.toggle("alert", alert);
    }
  };

  if (reduced) {
    // single still frame, no loop
    THREE.DefaultLoadingManager.onLoad = () => frame();
    frame();
    return;
  }
  renderer.setAnimationLoop(() => {
    const now = performance.now();
    if (!visible || document.hidden) return;
    if (now - last < 14) return; last = now;
    frame();
  });
}
