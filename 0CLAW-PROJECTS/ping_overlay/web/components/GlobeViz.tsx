"use client";
import { useEffect, useRef } from "react";
import * as THREE from "three";

export type GlobePoint = { lat: number; lng: number; weight: number };

const EARTH_DAY  = "https://unpkg.com/three-globe/example/img/earth-day.jpg";
const EARTH_BUMP = "https://unpkg.com/three-globe/example/img/earth-topology.png";
const TOPO_URL   = "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json";
const BORDER_R   = 1.003; // just above globe surface

// ── Lat/Lng → 3D position ─────────────────────────────────────────────────────
function latLngToVec3(lat: number, lng: number, r = 1): THREE.Vector3 {
  const phi   = (90 - lat) * (Math.PI / 180);
  const theta = (lng + 180) * (Math.PI / 180);
  return new THREE.Vector3(
    -Math.sin(phi) * Math.cos(theta) * r,
     Math.cos(phi) * r,
     Math.sin(phi) * Math.sin(theta) * r,
  );
}

// ── Minimal TopoJSON → LineSegments vertex buffer ────────────────────────────
function decodeTopo(topo: any): Float32Array {
  const s = topo.transform?.scale     ?? [1, 1];
  const t = topo.transform?.translate ?? [0, 0];

  const arcs: [number, number][][] = topo.arcs.map((arc: number[][]) => {
    let x = 0, y = 0;
    return arc.map((d: number[]) => {
      x += d[0]; y += d[1];
      return [x * s[0] + t[0], y * s[1] + t[1]] as [number, number];
    });
  });

  const verts: number[] = [];

  function ring(idxs: number[]) {
    const coords: [number, number][] = [];
    for (const idx of idxs) {
      const arc = idx >= 0 ? arcs[idx] : [...arcs[~idx]].reverse();
      coords.push(...(coords.length ? arc.slice(1) : arc));
    }
    for (let i = 0; i < coords.length - 1; i++) {
      const a = latLngToVec3(coords[i][1],     coords[i][0],     BORDER_R);
      const b = latLngToVec3(coords[i + 1][1], coords[i + 1][0], BORDER_R);
      verts.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  }

  function geom(g: any) {
    if (!g) return;
    if      (g.type === "GeometryCollection") g.geometries.forEach(geom);
    else if (g.type === "Polygon")            g.arcs.forEach(ring);
    else if (g.type === "MultiPolygon")       g.arcs.forEach((p: number[][]) => p.forEach(ring));
  }

  geom(topo.objects.countries ?? Object.values(topo.objects)[0]);
  return new Float32Array(verts);
}

// ─────────────────────────────────────────────────────────────────────────────
interface Props {
  points: GlobePoint[];
  width?:  number;
  height?: number;
}

export default function GlobeViz({ points, width = 480, height = 480 }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const W = mount.clientWidth  || width;
    const H = mount.clientHeight || height;

    // ── Renderer ──────────────────────────────────────────────────────────────
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    // ── Scene ─────────────────────────────────────────────────────────────────
    const scene = new THREE.Scene();

    // Stars background
    const starGeo = new THREE.BufferGeometry();
    const starCount = 1500;
    const starPos = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount * 3; i++) starPos[i] = (Math.random() - 0.5) * 200;
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    scene.add(new THREE.Points(
      starGeo,
      new THREE.PointsMaterial({ color: 0xffffff, size: 0.15, sizeAttenuation: true }),
    ));

    // ── Camera — z=3.6 → globe fills ≈2/3 of the canvas ─────────────────────
    // At FOV=45°, half-height visible at z=0 = tan(22.5°)×3.6 = 1.49.
    // Globe radius = 1 → globe/canvas = 1/1.49 ≈ 67% ≈ 2/3.
    const camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 1000);
    camera.position.z = 3.6;

    // ── Globe ─────────────────────────────────────────────────────────────────
    const loader = new THREE.TextureLoader();
    const globeGeo = new THREE.SphereGeometry(1, 64, 64);
    const globeMat = new THREE.MeshPhongMaterial({
      map:       loader.load(EARTH_DAY),
      bumpMap:   loader.load(EARTH_BUMP),
      bumpScale: 0.03,
      specular:  new THREE.Color(0x1a3a5c),
      shininess: 18,
    });
    const globeMesh = new THREE.Mesh(globeGeo, globeMat);
    scene.add(globeMesh);

    // ── Atmosphere — custom fresnel shader (fixes the bright-ring artifact) ──
    // FrontSide + fresnel: fragments facing the camera (center of globe) → nearly
    // transparent; fragments at the rim (edge-on, facing ≈ 0) → max intensity.
    // No lighting is applied, so there are no specular hot-spots or bright bands.
    const atmGeo = new THREE.SphereGeometry(1.08, 64, 64);
    const atmMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite:  false,
      side:        THREE.FrontSide,
      vertexShader: /* glsl */`
        varying float vIntensity;
        void main() {
          vec3 n       = normalize(normalMatrix * normal);
          vec3 vPos    = (modelViewMatrix * vec4(position, 1.0)).xyz;
          vec3 viewDir = normalize(-vPos);          // toward camera (view space)
          float facing = dot(n, viewDir);            // 1 = front, 0 = edge
          vIntensity   = pow(1.0 - max(0.0, facing), 3.5);  // pure rim glow
          gl_Position  = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */`
        varying float vIntensity;
        void main() {
          gl_FragColor = vec4(0.12, 0.42, 1.0, vIntensity * 0.5);
        }
      `,
    });
    scene.add(new THREE.Mesh(atmGeo, atmMat));

    // ── Lights ────────────────────────────────────────────────────────────────
    scene.add(new THREE.AmbientLight(0xffffff, 0.65));
    const sun = new THREE.DirectionalLight(0xffffff, 0.9);
    sun.position.set(5, 3, 5);
    scene.add(sun);

    // ── Country borders ───────────────────────────────────────────────────────
    const fetchCtrl = new AbortController();
    fetch(TOPO_URL, { signal: fetchCtrl.signal })
      .then(r => r.json())
      .then(topo => {
        const vertData  = decodeTopo(topo);
        const borderGeo = new THREE.BufferGeometry();
        borderGeo.setAttribute("position", new THREE.BufferAttribute(vertData, 3));
        globeMesh.add(new THREE.LineSegments(
          borderGeo,
          new THREE.LineBasicMaterial({
            color: 0xffffff, transparent: true, opacity: 0.28, linewidth: 1,
          }),
        ));
      })
      .catch(() => { /* ignore */ });

    // ── Visit dots ────────────────────────────────────────────────────────────
    // FIX 1: declare `attribute vec3 color` explicitly (ShaderMaterial does NOT
    //         inject it automatically — the old code used `color` undeclared,
    //         causing a shader compile error → Three.js fell back to rendering
    //         huge white squares that formed the "glow ring").
    //
    // FIX 2: sizes are in world-space units (0.012–0.06), not pixel counts.
    //         Formula: gl_PointSize = size × projectionMatrix[1][1] × halfH / -mv.z
    //         projectionMatrix[1][1] = 1/tan(22.5°) ≈ 2.414 for FOV=45°.
    //         halfH ≈ 260 (approximation for ~520px canvas).
    //         At camera z=3.6, globe surface mv.z ≈ −2.6 → size=0.019 → ~4.7px. ✓
    if (points.length > 0) {
      const positions = new Float32Array(points.length * 3);
      const colors    = new Float32Array(points.length * 3);
      const sizes     = new Float32Array(points.length);
      const col       = new THREE.Color();

      points.forEach((p, i) => {
        const v = latLngToVec3(p.lat, p.lng, 1.012); // slightly above surface
        positions[i * 3]     = v.x;
        positions[i * 3 + 1] = v.y;
        positions[i * 3 + 2] = v.z;

        // cyan → magenta gradient based on visit weight
        const t = Math.min(p.weight / 20, 1);
        col.setHSL(0.5 - t * 0.18, 1, 0.55 + t * 0.15);
        colors[i * 3]     = col.r;
        colors[i * 3 + 1] = col.g;
        colors[i * 3 + 2] = col.b;

        // World-space size: ~0.019 for 1 visit, ~0.05 for 100+ visits
        sizes[i] = 0.012 + Math.log1p(p.weight) * 0.007;
      });

      const dotGeo = new THREE.BufferGeometry();
      dotGeo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
      dotGeo.setAttribute("color",    new THREE.BufferAttribute(colors,    3));
      dotGeo.setAttribute("size",     new THREE.BufferAttribute(sizes,     1));

      const dotMat = new THREE.ShaderMaterial({
        transparent: true,
        depthWrite:  false,
        vertexShader: /* glsl */`
          attribute float size;
          attribute vec3  color;   /* ← must be declared; ShaderMaterial won't inject it */
          varying   vec3  vColor;
          void main() {
            vColor      = color;
            vec4 mv     = modelViewMatrix * vec4(position, 1.0);
            /* Perspective-correct pixel size:
               projectionMatrix[1][1] = 1/tan(fov/2) ≈ 2.414  (FOV 45°)
               260.0 = approximate half-canvas height in pixels             */
            gl_PointSize = size * projectionMatrix[1][1] * 260.0 / -mv.z;
            gl_Position  = projectionMatrix * mv;
          }
        `,
        fragmentShader: /* glsl */`
          varying vec3 vColor;
          void main() {
            float d = length(gl_PointCoord - vec2(0.5));
            if (d > 0.5) discard;                          /* clip to circle */
            float alpha = 1.0 - smoothstep(0.2, 0.5, d);  /* soft glow edge */
            gl_FragColor = vec4(vColor, alpha * 0.92);
          }
        `,
      });

      globeMesh.add(new THREE.Points(dotGeo, dotMat));
    }

    // ── Drag rotation ─────────────────────────────────────────────────────────
    let rotY = -0.3, rotX = 0;
    let isDragging = false;
    let prevX = 0, prevY = 0;
    let velX = 0, velY = 0;
    let autoRotate = true;
    let autoTimer: ReturnType<typeof setTimeout> | null = null;

    const el = renderer.domElement;

    function onDown(x: number, y: number) {
      isDragging = true; autoRotate = false; prevX = x; prevY = y; velX = 0; velY = 0;
      if (autoTimer) { clearTimeout(autoTimer); autoTimer = null; }
    }
    function onMove(x: number, y: number) {
      if (!isDragging) return;
      const dx = x - prevX, dy = y - prevY;
      velX = dy * 0.005; velY = dx * 0.005;
      rotX += velX; rotY += velY;
      rotX = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2, rotX));
      prevX = x; prevY = y;
    }
    function onUp() {
      isDragging = false;
      autoTimer = setTimeout(() => { autoRotate = true; }, 3000);
    }

    el.addEventListener("mousedown",  e => onDown(e.clientX, e.clientY));
    el.addEventListener("mousemove",  e => onMove(e.clientX, e.clientY));
    el.addEventListener("mouseup",    onUp);
    el.addEventListener("mouseleave", onUp);
    el.addEventListener("touchstart", e => onDown(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
    el.addEventListener("touchmove",  e => onMove(e.touches[0].clientX, e.touches[0].clientY), { passive: true });
    el.addEventListener("touchend",   onUp);

    // ── Resize observer ───────────────────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      const w = mount.clientWidth, h = mount.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    ro.observe(mount);

    // ── Render loop ───────────────────────────────────────────────────────────
    let rafId: number;
    function animate() {
      rafId = requestAnimationFrame(animate);
      if (!isDragging) {
        if (autoRotate) { rotY += 0.0015; velX = 0; velY = 0; }
        else            { rotY += velY *= 0.96; rotX += velX *= 0.96; }
        rotX = Math.max(-Math.PI / 2.2, Math.min(Math.PI / 2.2, rotX));
      }
      globeMesh.rotation.y = rotY;
      globeMesh.rotation.x = rotX;
      renderer.render(scene, camera);
    }
    animate();

    // ── Cleanup ───────────────────────────────────────────────────────────────
    return () => {
      cancelAnimationFrame(rafId);
      if (autoTimer) clearTimeout(autoTimer);
      fetchCtrl.abort();
      ro.disconnect();
      renderer.dispose();
      if (mount.contains(renderer.domElement)) mount.removeChild(renderer.domElement);
    };
  }, [points, width, height]);

  return (
    <div
      ref={mountRef}
      style={{ width: "100%", height: "100%", cursor: "grab", userSelect: "none" }}
    />
  );
}
