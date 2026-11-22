# Browser walkthrough (three.js)

A browser version runs anywhere without an install, so it is the one people actually open. It cannot match a
game engine's real-time global illumination, so the light is baked in Blender (Cycles) and the browser only
looks it up. Two tiers worked; start with the first.

| Tier | What the browser draws | Effort | Looks |
|---|---|---|---|
| v1 baked | albedo × light baked together (or as two atlases) | low | clean, flat reflections |
| v2 light maps | tiling material maps × baked light map + room reflection probes + a game-engine-like post chain | high | close to the engine |

Files: `scripts/web/bake_lightmaps.py` (Blender), `scripts/web/viewer/index.html`, `scripts/web/serve.py`.

```sh
Blender -b model.blend --python-exit-code 1 --python scripts/web/bake_lightmaps.py            # all groups
Blender -b model.blend --python-exit-code 1 --python scripts/web/bake_lightmaps.py -- --albedo # procedural materials
Blender -b model.blend --python-exit-code 1 --python scripts/web/bake_lightmaps.py -- --only floor2 --reuse
python3 scripts/web/serve.py web 8768                                                          # http://localhost:8768
```

Edit the CONFIG block at the top of the bake script: `GROUPS` (collections and texels per metre), the glass
and lamp material prefixes, `INTERIOR_BOXES` for light portals, `DOORS`, `START`, `SPOTS`, `FLOORS`.

## v1: baked colour × light

- Bake per object or per group: the light map (Cycles `DIFFUSE` pass with `DIRECT + INDIRECT`, no colour) and,
  with `--albedo`, the surface colour (`DIFFUSE` with `COLOR`). The viewer multiplies them. This carries
  procedural materials (noise, box mapping, colour ramps) that the glTF exporter cannot export.
- Glass, metal, curtains and leaves stay as real-time materials; they get no light map.
- Use the same view transform as your stills (AgX in Blender, `THREE.AgXToneMapping` in three.js), so the bake and
  the renders agree.
- **Hosting without `.glb`:** some hosts do not serve binary files, and some pages run under a Content Security
  Policy that blocks `fetch()` of `data:` and `blob:` URLs. Then embed the buffer as base64 in a `.gltf.json`,
  decode it yourself in the page, and make GLTFLoader use `<img>` elements for the images.
- A full bake of a three-floor home with its block took about 10–35 minutes. Keep a resume path: skip objects whose
  textures already exist unless `--rebake` is given.

## v2: light maps, tiling materials and probes

The bake stores **only the light**. The colour comes from the same tiling texture maps the engine uses (UV 0, box
projection as in Cycles and Unreal), so surfaces stay sharp up close at any light-map resolution.

**Bake lessons (each cost a rerun):**

- **One joined copy per atlas.** Cycles bakes selected objects one after another over the whole image. 41 objects
  took 217 s; the same objects joined into one copy took 37 s. Remove every UV layer except `Bake` from the copies
  first: `join()` merges layers of other names into `Bake`.
- **Unwrap one concatenated mesh** and copy the UVs back loop by loop. Multi-object edit mode skipped objects.
  Smart project, then `pack_islands` with `margin_method="FRACTION"` (8 px).
- **Collapsed packs bake black.** Margins are absolute, so thousands of single-face islands (a slatted bed frame:
  3,402) shrink every island to nothing. Double the atlas until the texel density reaches 40 % of the goal; a collapsed
  pack cannot be scaled back up, so pack the smart-project UVs again on every try. A black bake means broken UVs,
  not missing light.
- **Light portals** in the window panes (Cycles area lights with `is_portal`) take most of the noise out of rooms lit
  only by daylight. Use 2,048 samples indoors, 256 outdoors, and denoise with OpenImageDenoise guided by a baked
  normal pass (so islands of other surfaces do not blur into each other).
- **Flatten normal maps during the bake**: the viewer applies them again.
- **Dense small decor** (a potted plant: 54k faces) gets no light map; light it from the room probe or a constant.
- **Hidden alternative furniture must be hidden in the bake**, probe-lit pieces too. A hidden sofa set once shadowed the
  visible one.
- **Lamps off means emission off** in the bake and in the viewer, matching the engine's start state.
- **Storage:** `sRGB(light / scale)` in 8-bit, `scale` = 99.8th percentile × 1.1 per atlas (in `scene.json`).
  KTX2 UASTC level 3 **without RDO** for light maps (RDO made blocks in smooth gradients). Colour maps may use RDO.
- **gltfpack** `-cc -kn -km -ke -kv -noq`: `-kv` keeps UVs of materials without textures; `-noq` because box UVs run
  to hundreds of tiles and quantization breaks them.
- **City clip:** limit the surroundings (for example to 350 m). A full-length sidewalk network was 937k faces.
- Timings for reference: full export with all bakes about 80 min; one 2048 px atlas at 2,048 spp 4–7 min.

**Room reflection probes.** Glossy floors and glass need reflections the light map cannot give. At load, capture
one cube map per room (`CubeCamera` at the room centre, then `PMREMGenerator`), and box-project the reflection ray
against the room's box. Scale the reflection by how much light the light map has compared with the probe
(specular occlusion), as Unreal does; otherwise dark corners reflect a bright room.

```js
// WebGPU + TSL (three r18x). Surfaces with a light map: albedo x baked light + probe reflection.
function litMaterial(name, d, lm, probe) {
  const m = new THREE.MeshBasicNodeMaterial({ name });
  const base = baseColor(d), rough = roughNode(d).toVar(), metal = float(d.metal ?? 0);
  const N = normalWorld, V = normalize(cameraPosition.sub(positionWorld));
  const NdotV = max(dot(N, V), 0.001), R = reflect(V.negate(), N);
  const irr = texture(lm.tex, uv(1)).rgb.mul(lm.scale);                 // baked light, UV 1
  const spec = pmremTexture(probe.tex, boxDir(probe, R), rough).rgb;     // box-projected room probe
  const pIrr = pmremTexture(probe.tex, N, float(1)).rgb;
  const occ = clamp(luminance(irr).div(max(luminance(pIrr), 1e-4)), 0, 1); // specular occlusion
  const F0 = mix(vec3(0.04), base, metal);
  m.colorNode = base.mul(metal.oneMinus()).mul(irr).add(spec.mul(envBRDF(F0, rough, NdotV)).mul(occ));
  return m;
}
// Karis' fit of the split-sum environment BRDF
const envBRDF = (F0, rough, NdotV) => {
  const r = rough.mul(vec4(-1, -0.0275, -0.572, 0.022)).add(vec4(1, 0.0425, 1.04, -0.04));
  const a004 = min(r.x.mul(r.x), exp2(NdotV.mul(-9.28))).mul(r.x).add(r.y);
  return F0.mul(a004.mul(-1.04).add(r.z)).add(a004.mul(1.04).add(r.w));
};
```

## Matching the engine look

The browser version should look like the Unreal walkthrough people saw first. What closed the gap:

- **Exposure:** −1 EV default on a game-engine-like EV scale; eye adaptation from a small read-back (48 × 27) every
  few frames, metering the 10–75 % luminance range (the windows burn out like a real camera).
- **Local exposure for window views:** pull regions brighter than the metered mean toward it, mostly per pixel with a
  third of a blurred log luminance. A wide blur alone made halos at window frames.
- **Grade:** saturation 1.1, a slightly warm white `(1.04, 1, 0.88)` measured against the engine's white walls,
  vignette 0.25, light bloom.
- **Outdoor surfaces ×2 while the walker is inside** (v1) imitates the engine's local exposure cheaply.
- **Sharpness:** render at a pixel ratio up to 2 (start at 1.5, lower it when the frame rate drops below 40) and
  sharpen lightly after temporal anti-aliasing. At 1× on a high-DPI screen the image looked smudgy.

```js
// Local exposure + grade (TSL post chain: scene pass -> GTAO -> TRAA -> sharpen -> this)
const grade = Fn(() => {
  const ownLog = log2(max(luminance(sharp.rgb), 1e-5));
  const dLog = mix(ownLog, blurLog.r, 0.35).sub(uMeterLog);              // above the metered mean?
  const local = exp2(max(dLog, 0).mul(uHiContrast.sub(1)));             // compress highlights only
  const c = sharp.rgb.mul(local).add(bloomPass.rgb).toVar();
  const s = max(mix(vec3(luminance(c)), c, uSat), vec3(0)).mul(uWhite);
  const d = screenUV.sub(0.5).mul(vec2(uAspect, 1));
  return vec4(s.mul(float(1).sub(uVig.mul(smoothstep(0.3, 1.0, length(d).mul(1.2))))), 1.0);
});
```

## The viewer in this kit

`scripts/web/viewer/index.html` is a compact WebGL version of the above (three.js r170 from a CDN, pinned):

- Groups from `scene.json`, light map on UV 1 (`texture.channel = 1`, `lightMapIntensity = scale × π`, because
  three.js divides light maps by π).
- Walking: pointer lock and WASD, a capsule from knee to head height pushed out of a `MeshBVH` (three-mesh-bvh)
  of the static model, a ground ray (step height 0.3 m), gravity. Doors have their own BVH in hinge space.
- Keys: 1–9 spots, E doors (node extras `door: {hinge, open, closed, baked}`), F field of view 75°/90°, V dollhouse
  (orbit, clipping plane above the current floor, `[` `]` change floor), M room labels from `labels.json`, R measure,
  L look panel (exposure, auto, bloom, reflections).
- Checks: `?at=x,y,z&view=yaw,pitch&fov=90` (model metres and degrees) and `window.__ready`.

## Testing headless

- Serve with `serve.py`: it sends `Cache-Control: no-cache` (browsers kept old model files) and the right media
  types for `.glb`, `.ktx2` and `.wasm`.
- Chrome's `--screenshot` flag gave black or "Loading" images. Drive Chrome over the DevTools protocol instead:
  start it with `--headless=new --remote-debugging-port=<port> --use-angle=metal` (add `--enable-unsafe-webgpu` for
  WebGPU), open the page, poll `window.__ready`, then `Page.captureScreenshot`. Node 22 has a built-in WebSocket, so
  no Playwright is needed; puppeteer-core works too.
- Expose a pick helper (for example `window.__pick(ndcX, ndcY)` listing the surfaces under a point) to debug a
  wrong material without screenshots.
- Use a free port: another tool may already hold the usual debugging port.
