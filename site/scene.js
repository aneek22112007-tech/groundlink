import * as THREE from "https://cdn.jsdelivr.net/npm/three@0.170.0/build/three.module.js";

const DAY = "https://unpkg.com/three-globe@2.31.1/example/img/earth-blue-marble.jpg";
const NIGHT = "https://unpkg.com/three-globe@2.31.1/example/img/earth-night.jpg";

const canvas = document.querySelector("#space");
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
renderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(42, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(6.2, 2.1, 7.4);
camera.lookAt(0, 0, 0);

scene.add(new THREE.AmbientLight(0x88aacc, 0.35));
const sun = new THREE.DirectionalLight(0xfff2d8, 1.6);
sun.position.set(-8, 3, 4);
scene.add(sun);

const stars = starfield();
scene.add(stars);

const earth = new THREE.Mesh(
  new THREE.SphereGeometry(2, 64, 64),
  new THREE.MeshPhongMaterial({ color: 0xffffff }),
);
scene.add(earth);
const clouds = new THREE.Mesh(
  new THREE.SphereGeometry(2.03, 48, 48),
  new THREE.MeshPhongMaterial({
    map: cloudTexture(),
    transparent: true,
    opacity: 0.45,
    depthWrite: false,
  }),
);
scene.add(clouds);
scene.add(atmosphere());

const loader = new THREE.TextureLoader();
loader.load(DAY, (texture) => {
  earth.material.map = texture;
  earth.material.needsUpdate = true;
});
loader.load(NIGHT, (texture) => {
  earth.material.emissiveMap = texture;
  earth.material.emissive = new THREE.Color(0x6688aa);
  earth.material.needsUpdate = true;
});

const satellite = buildSatellite();
scene.add(satellite);
const trail = new THREE.Line(
  new THREE.BufferGeometry(),
  new THREE.LineBasicMaterial({ color: 0x9af6ff, transparent: true, opacity: 0.7 }),
);
scene.add(trail);
const trailPoints = [];

const beam = new THREE.Mesh(
  new THREE.CylinderGeometry(0.01, 0.08, 1.2, 8, 1, true),
  new THREE.MeshBasicMaterial({ color: 0x9af6ff, transparent: true, opacity: 0.0, side: THREE.DoubleSide }),
);
beam.position.copy(latLon(13.03, 77.51, 2.15));
beam.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), beam.position.clone().normalize());
scene.add(beam);

const burn = new THREE.PointLight(0xff8844, 0, 4);
satellite.add(burn);

let progress = 0;
const gsap = window.gsap;
const ScrollTrigger = window.ScrollTrigger;
if (gsap && ScrollTrigger) {
  gsap.registerPlugin(ScrollTrigger);
  ScrollTrigger.create({
    trigger: "#story",
    start: "top top",
    end: "bottom bottom",
    scrub: true,
    onUpdate: (self) => {
      progress = self.progress;
    },
  });
}

const clock = new THREE.Clock();
function frame() {
  const t = clock.getElapsedTime();
  earth.rotation.y = t * 0.04;
  clouds.rotation.y = t * 0.05;
  stars.rotation.y = t * 0.008 + progress * 0.2;
  const theta = t * 0.35;
  const radius = 3.15;
  const position = orbitPoint(theta, radius);
  satellite.position.copy(position);
  trailPoints.push(position.clone());
  if (trailPoints.length > 48) trailPoints.shift();
  trail.geometry.setFromPoints(trailPoints);
  const anomaly = smooth(progress, 0.08, 0.22);
  satellite.traverse((child) => {
    if (child.isMesh && child.material && child.material.color) {
      child.material.color.set(anomaly > 0.4 ? "#ff5d5d" : "#d7efe4");
    }
  });
  burn.intensity = smooth(progress, 0.32, 0.48) * 4;
  beam.material.opacity = smooth(progress, 0.18, 0.34) * 0.85;
  document.querySelector("#kill")?.classList.toggle("is-on", progress > 0.62 && progress < 0.78);
  camera.position.z = 7.4 - progress * 1.2;
  camera.lookAt(0, 0, 0);
  renderer.render(scene, camera);
  requestAnimationFrame(frame);
}
frame();

addEventListener("resize", () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

function orbitPoint(theta, radius) {
  return new THREE.Vector3(Math.cos(theta) * radius, Math.sin(theta * 2) * 0.35, Math.sin(theta) * radius);
}

function buildSatellite() {
  const group = new THREE.Group();
  const bus = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.22, 0.22), new THREE.MeshStandardMaterial({ color: 0xd7efe4, metalness: 0.4, roughness: 0.35 }));
  const panelGeo = new THREE.BoxGeometry(0.42, 0.16, 0.02);
  const panelMat = new THREE.MeshStandardMaterial({ color: 0x16324a, metalness: 0.2, roughness: 0.4 });
  const left = new THREE.Mesh(panelGeo, panelMat);
  const right = new THREE.Mesh(panelGeo, panelMat);
  left.position.x = -0.38;
  right.position.x = 0.38;
  const antenna = new THREE.Mesh(new THREE.CylinderGeometry(0.015, 0.015, 0.22), new THREE.MeshStandardMaterial({ color: 0xffb45a }));
  antenna.position.y = 0.2;
  group.add(bus, left, right, antenna);
  group.scale.setScalar(0.7);
  return group;
}

function atmosphere() {
  const material = new THREE.ShaderMaterial({
    transparent: true,
    depthWrite: false,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    uniforms: {},
    vertexShader: `
      varying vec3 vNormal;
      varying vec3 vWorld;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        vec4 world = modelMatrix * vec4(position, 1.0);
        vWorld = world.xyz;
        gl_Position = projectionMatrix * viewMatrix * world;
      }
    `,
    fragmentShader: `
      varying vec3 vNormal;
      varying vec3 vWorld;
      void main() {
        vec3 viewDir = normalize(cameraPosition - vWorld);
        float fresnel = pow(1.0 - abs(dot(viewDir, normalize(vNormal))), 2.6);
        gl_FragColor = vec4(0.45, 0.78, 1.0, fresnel * 0.9);
      }
    `,
  });
  return new THREE.Mesh(new THREE.SphereGeometry(2.18, 48, 48), material);
}

function starfield() {
  const count = 1200;
  const positions = new Float32Array(count * 3);
  let seed = 7;
  const rnd = () => {
    seed = (seed * 16807) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < count; i += 1) {
    const r = 18 + rnd() * 30;
    const theta = rnd() * Math.PI * 2;
    const phi = Math.acos(2 * rnd() - 1);
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = r * Math.cos(phi);
    positions[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return new THREE.Points(geometry, new THREE.PointsMaterial({ color: 0xd7e6ff, size: 0.045 }));
}

function cloudTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 256;
  const ctx = canvas.getContext("2d");
  let seed = 11;
  const rnd = () => {
    seed = (seed * 48271) % 2147483647;
    return (seed - 1) / 2147483646;
  };
  for (let i = 0; i < 70; i += 1) {
    ctx.fillStyle = `rgba(255,255,255,${0.08 + rnd() * 0.2})`;
    ctx.beginPath();
    ctx.ellipse(rnd() * 512, rnd() * 256, 20 + rnd() * 70, 8 + rnd() * 18, rnd(), 0, Math.PI * 2);
    ctx.fill();
  }
  return new THREE.CanvasTexture(canvas);
}

function latLon(lat, lon, radius) {
  const phi = ((90 - lat) * Math.PI) / 180;
  const theta = ((lon + 180) * Math.PI) / 180;
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function smooth(value, start, end) {
  if (value <= start) return 0;
  if (value >= end) return 1;
  return (value - start) / (end - start);
}
