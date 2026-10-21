// Small WebGL2 viewer for the tribune (Z up, metres). No libraries, works offline.
"use strict";

const MESH_VS = `#version 300 es
in vec3 a_pos; in vec3 a_nrm; in vec4 a_inst; in float a_free;
uniform mat4 u_vp; uniform bool u_instanced;
out vec3 v_pos; out vec3 v_nrm; out float v_free;
void main(){
  vec3 p = a_pos; vec3 n = a_nrm; v_free = 0.0;
  if (u_instanced){
    float c = cos(a_inst.w), s = sin(a_inst.w);
    p = vec3(c*p.x - s*p.y, s*p.x + c*p.y, p.z) + a_inst.xyz;
    n = vec3(c*n.x - s*n.y, s*n.x + c*n.y, n.z);
    v_free = a_free;
  }
  v_pos = p; v_nrm = n;
  gl_Position = u_vp * vec4(p, 1.0);
}`;

const MESH_FS = `#version 300 es
precision highp float;
in vec3 v_pos; in vec3 v_nrm; in float v_free;
uniform vec3 u_color; uniform float u_rough; uniform float u_metal; uniform vec3 u_eye;
uniform sampler2D u_pat; uniform int u_patMode; uniform float u_patScale; uniform float u_showFree;
out vec4 o;
vec3 toSRGB(vec3 c){ return mix(c*12.92, 1.055*pow(c, vec3(1.0/2.4)) - 0.055, step(0.0031308, c)); }
void main(){
  vec3 N = normalize(v_nrm);
  if (!gl_FrontFacing) N = -N;
  float rough = u_rough;
  float ao = 1.0;
  if (u_patMode > 0){
    vec3 A = abs(N); vec2 uv; vec3 T; vec3 B;
    if (A.z >= A.x && A.z >= A.y){ uv = v_pos.xy; T = vec3(1,0,0); B = vec3(0,1,0); }
    else if (A.x >= A.y){ uv = v_pos.yz; T = vec3(0,1,0); B = vec3(0,0,1); }
    else { uv = v_pos.xz; T = vec3(1,0,0); B = vec3(0,0,1); }
    vec4 tx = texture(u_pat, uv / u_patScale);
    if (u_patMode == 1){
      vec3 tn = tx.xyz * 2.0 - 1.0; tn.y = -tn.y;          // DirectX normal map
      N = normalize(T * tn.x + B * tn.y + N * max(tn.z, 0.2));
      ao = tx.a;
    } else {
      vec3 tn = tx.xyz * 2.0 - 1.0; tn.y = -tn.y;          // seat: scratch grooves + roughness in alpha
      N = normalize(T * tn.x + B * tn.y + N * max(tn.z, 0.2));
      rough = clamp(tx.a, 0.05, 1.0);
    }
  }
  vec3 L = normalize(vec3(-0.35, -0.55, 0.76));
  vec3 V = normalize(u_eye - v_pos);
  vec3 H = normalize(L + V);
  float diff = max(dot(N, L), 0.0);
  float hemi = 0.5 + 0.5 * N.z;
  vec3 base = u_color;
  if (v_free > 0.5 && u_showFree > 0.5) base = mix(base, vec3(0.9, 0.75, 0.2), 0.65);
  vec3 albedo = base * (1.0 - u_metal);
  float shin = mix(90.0, 4.0, rough);
  float spec = pow(max(dot(N, H), 0.0), shin) * (1.0 - rough) * 0.9;
  vec3 specCol = mix(vec3(0.04), base, u_metal);
  vec3 col = albedo * (diff * vec3(1.0, 0.97, 0.92) * 1.15 + hemi * vec3(0.42, 0.47, 0.55) + 0.06)
           + specCol * (spec * 1.6 + hemi * u_metal * 0.5);
  col *= ao;
  o = vec4(toSRGB(col), 1.0);
}`;

const LINE_VS = `#version 300 es
in vec3 a_pos; uniform mat4 u_vp; uniform float u_lift;
void main(){ gl_Position = u_vp * vec4(a_pos + vec3(0,0,u_lift), 1.0); gl_Position.z -= 0.0008 * gl_Position.w; }`;
const LINE_FS = `#version 300 es
precision highp float; uniform vec4 u_color; out vec4 o; void main(){ o = u_color; }`;

const GROUND_VS = `#version 300 es
in vec2 a_pos; uniform mat4 u_vp; uniform vec2 u_center; uniform float u_size; out vec2 v_xy;
void main(){ v_xy = u_center + a_pos * u_size; gl_Position = u_vp * vec4(v_xy, -0.002, 1.0); }`;
const GROUND_FS = `#version 300 es
precision highp float; in vec2 v_xy; uniform vec2 u_center; uniform float u_size; out vec4 o;
float grid(vec2 p, float w){ vec2 g = abs(fract(p - 0.5) - 0.5) / fwidth(p); return 1.0 - min(min(g.x, g.y) / w, 1.0); }
void main(){
  float d = length(v_xy - u_center) / u_size;
  vec3 c = vec3(0.555, 0.60, 0.53);
  c = mix(c, vec3(0.47, 0.52, 0.46), grid(v_xy, 1.0) * 0.55);
  c = mix(c, vec3(0.40, 0.45, 0.40), grid(v_xy / 5.0, 1.2) * 0.6);
  float a = smoothstep(1.0, 0.55, d);
  o = vec4(c, a);
}`;

const SKY_VS = `#version 300 es
in vec2 a_pos; out float v_y; void main(){ v_y = a_pos.y; gl_Position = vec4(a_pos, 0.999, 1.0); }`;
const SKY_FS = `#version 300 es
precision highp float; in float v_y; out vec4 o;
void main(){ float t = v_y * 0.5 + 0.5; o = vec4(mix(vec3(0.80, 0.84, 0.86), vec3(0.47, 0.61, 0.74), t), 1.0); }`;

function compile(gl, vs, fs) {
  const p = gl.createProgram();
  for (const [type, src] of [[gl.VERTEX_SHADER, vs], [gl.FRAGMENT_SHADER, fs]]) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
    gl.attachShader(p, s);
  }
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) { const name = gl.getActiveUniform(p, i).name; u[name] = gl.getUniformLocation(p, name); }
  return { p, u, a: (name) => gl.getAttribLocation(p, name) };
}

function b64f32(s) {
  if (!s) return new Float32Array(0);
  const bin = atob(s); const buf = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Float32Array(buf.buffer);
}

// --- tiny matrix helpers (column major)
function perspective(fov, aspect, near, far) {
  const f = 1 / Math.tan(fov / 2), nf = 1 / (near - far);
  return [f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1, 0, 0, 2 * far * near * nf, 0];
}
function lookAt(e, t, up) {
  let zx = e[0] - t[0], zy = e[1] - t[1], zz = e[2] - t[2];
  let l = Math.hypot(zx, zy, zz); zx /= l; zy /= l; zz /= l;
  let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
  l = Math.hypot(xx, xy, xz); xx /= l; xy /= l; xz /= l;
  const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
  return [xx, yx, zx, 0, xy, yy, zy, 0, xz, yz, zz, 0,
    -(xx * e[0] + xy * e[1] + xz * e[2]), -(yx * e[0] + yy * e[1] + yz * e[2]), -(zx * e[0] + zy * e[1] + zz * e[2]), 1];
}
function mul(a, b) {
  const o = new Array(16);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) {
    let s = 0; for (let k = 0; k < 4; k++) s += a[k * 4 + r] * b[c * 4 + k]; o[c * 4 + r] = s;
  }
  return o;
}

export class Viewer {
  constructor(canvas) {
    this.canvas = canvas;
    const gl = canvas.getContext("webgl2", { antialias: true, alpha: false, preserveDrawingBuffer: true });
    if (!gl) throw new Error("WebGL2 fehlt");
    this.gl = gl;
    this.mesh = compile(gl, MESH_VS, MESH_FS);
    this.line = compile(gl, LINE_VS, LINE_FS);
    this.ground = compile(gl, GROUND_VS, GROUND_FS);
    this.sky = compile(gl, SKY_VS, SKY_FS);
    this.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    this.objs = []; this.lines = []; this.seatParts = []; this.inst = null; this.instCount = 0;
    this.materials = {}; this.patterns = {}; this.patTex = {};
    this.show = { nav: false, outline: true, free: false };
    this.cam = { yaw: -0.6, pitch: 0.55, dist: 40, target: [0, 0, 1] };
    this.bounds = null;
    this._bindInput();
    this._dirty = true;
    const loop = () => { if (this._dirty) { this._dirty = false; this.draw(); } requestAnimationFrame(loop); };
    requestAnimationFrame(loop);
    new ResizeObserver(() => this.redraw()).observe(canvas);
  }
  redraw() { this._dirty = true; }

  _buf(data) { const gl = this.gl, b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW); return b; }
  _free() {
    const gl = this.gl;
    for (const o of [...this.objs, ...this.seatParts]) { gl.deleteBuffer(o.p); gl.deleteBuffer(o.n); }
    for (const l of this.lines) gl.deleteBuffer(l.p);
    if (this.inst) gl.deleteBuffer(this.inst);
    this.objs = []; this.seatParts = []; this.lines = []; this.inst = null;
  }

  setMaterials(m) { this.materials = m; this.redraw(); }
  setPattern(group, kind, scale) {
    this.patterns[group] = { kind, scale };
    if (kind !== "NONE" && !this.patTex[group + kind]) {
      const img = new Image();
      img.onload = () => {
        const gl = this.gl, t = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.REPEAT);
        const ext = gl.getExtension("EXT_texture_filter_anisotropic");
        if (ext) gl.texParameterf(gl.TEXTURE_2D, ext.TEXTURE_MAX_ANISOTROPY_EXT, 8);
        this.patTex[group + kind] = t; this.redraw();
      };
      img.src = `/api/pattern?group=${group}&kind=${kind}`;
    }
    this.redraw();
  }

  setData(d, frame) {
    this._free();
    const gl = this.gl;
    let lo = [1e9, 1e9, 1e9], hi = [-1e9, -1e9, -1e9];
    const grow = (P) => { for (let i = 0; i < P.length; i += 3) for (let k = 0; k < 3; k++) { if (P[i + k] < lo[k]) lo[k] = P[i + k]; if (P[i + k] > hi[k]) hi[k] = P[i + k]; } };
    for (const [name, m] of Object.entries(d.meshes)) {
      const P = b64f32(m.p); grow(P);
      this.objs.push({ name, p: this._buf(P), n: this._buf(b64f32(m.n)), count: m.count });
    }
    for (const [name, m] of Object.entries(d.seat)) this.seatParts.push({ name, p: this._buf(b64f32(m.p)), n: this._buf(b64f32(m.n)), count: m.count });
    const inst = b64f32(d.inst);
    this.inst = this._buf(inst); this.instCount = d.inst_count;
    for (let i = 0; i < inst.length; i += 5) { grow([inst[i], inst[i + 1], inst[i + 2] + 1.0]); }
    // navmesh wireframe
    const nv = b64f32(d.nav), L = [];
    for (let i = 0; i < nv.length; i += 9) {
      const a = [nv[i], nv[i + 1], nv[i + 2]], b = [nv[i + 3], nv[i + 4], nv[i + 5]], c = [nv[i + 6], nv[i + 7], nv[i + 8]];
      L.push(...a, ...b, ...b, ...c, ...c, ...a);
    }
    this.lines.push({ key: "nav", p: this._buf(new Float32Array(L)), count: L.length / 3, color: [0.1, 0.55, 1.0, 0.75], lift: 0.02 });
    // outline: entrances green, the rest dark
    const poly = d.outline.poly, kinds = d.outline.kinds, E = [], W = [];
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i], b = poly[(i + 1) % poly.length];
      (kinds[i] === "EXF" ? E : W).push(a[0], a[1], 0.03, b[0], b[1], 0.03);
    }
    this.lines.push({ key: "outline", p: this._buf(new Float32Array(W)), count: W.length / 3, color: [1, 1, 1, 0.85], lift: 0 });
    this.lines.push({ key: "outline", p: this._buf(new Float32Array(E)), count: E.length / 3, color: [0.2, 0.95, 0.35, 1], lift: 0 });
    // booth (box edges) and seats that cannot be reached
    const bx = d.booth[0], by = d.booth[1], s = 0.75, B = [];
    const c8 = [[-s, -s, 0], [s, -s, 0], [s, s, 0], [-s, s, 0], [-s, -s, 1.5], [s, -s, 1.5], [s, s, 1.5], [-s, s, 1.5]];
    for (const [i, j] of [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]])
      B.push(bx + c8[i][0], by + c8[i][1], c8[i][2], bx + c8[j][0], by + c8[j][1], c8[j][2]);
    this.lines.push({ key: "booth", p: this._buf(new Float32Array(B)), count: B.length / 3, color: [1.0, 0.78, 0.15, 1], lift: 0 });
    const R = [];
    for (const t of d.bad_targets || []) R.push(t[0], t[1], t[2], t[3], t[4], t[5]);
    if (R.length) this.lines.push({ key: "bad", p: this._buf(new Float32Array(R)), count: R.length / 3, color: [1, 0.15, 0.1, 1], lift: 0 });
    for (const p of poly) { grow([p[0], p[1], 0]); }
    this.bounds = { lo, hi };
    if (frame) this.frame();
    this.redraw();
  }

  frame() {
    if (!this.bounds) return;
    const { lo, hi } = this.bounds;
    this.cam.target = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, Math.max(0.5, (hi[2] - lo[2]) * 0.3)];
    const r = Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2;
    this.cam.dist = Math.max(6, r * 2.1);
    this.cam.yaw = -Math.PI / 2 - 0.6; this.cam.pitch = 0.5;
    this.redraw();
  }
  view(name) {
    const c = this.cam;
    if (name !== "fit") { const y = c.yaw, p = c.pitch; this.frame(); c.yaw = y; c.pitch = p; }
    if (name === "front") { c.yaw = -Math.PI / 2; c.pitch = 0.32; }
    else if (name === "top") { c.yaw = -Math.PI / 2; c.pitch = 1.53; c.target[2] = 0; }
    else if (name === "side") { c.yaw = 0; c.pitch = 0.25; }
    else { this.frame(); return; }
    this.redraw();
  }

  _eye() {
    const c = this.cam;
    return [c.target[0] + c.dist * Math.cos(c.pitch) * Math.cos(c.yaw), c.target[1] + c.dist * Math.cos(c.pitch) * Math.sin(c.yaw), c.target[2] + c.dist * Math.sin(c.pitch)];
  }

  _bindInput() {
    const cv = this.canvas; let drag = null;
    cv.addEventListener("contextmenu", (e) => e.preventDefault());
    cv.addEventListener("pointerdown", (e) => { cv.setPointerCapture(e.pointerId); drag = { x: e.clientX, y: e.clientY, pan: e.button !== 0 || e.shiftKey }; });
    cv.addEventListener("pointerup", () => { drag = null; });
    cv.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag.x = e.clientX; drag.y = e.clientY;
      const c = this.cam;
      if (drag.pan) {
        const k = c.dist * 0.0016;
        const rx = -Math.sin(c.yaw), ry = Math.cos(c.yaw);
        c.target[0] -= (rx * dx) * k; c.target[1] -= (ry * dx) * k;
        c.target[0] += Math.cos(c.yaw) * dy * k * Math.sin(c.pitch); c.target[1] += Math.sin(c.yaw) * dy * k * Math.sin(c.pitch);
        c.target[2] += dy * k * Math.cos(c.pitch);
      } else {
        c.yaw -= dx * 0.006; c.pitch = Math.min(1.53, Math.max(-0.05, c.pitch + dy * 0.006));
      }
      this.redraw();
    });
    cv.addEventListener("wheel", (e) => { e.preventDefault(); this.cam.dist = Math.min(800, Math.max(2, this.cam.dist * Math.exp(e.deltaY * 0.0012))); this.redraw(); }, { passive: false });
  }

  draw() {
    const gl = this.gl, cv = this.canvas;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.max(1, Math.round(cv.clientWidth * dpr)), h = Math.max(1, Math.round(cv.clientHeight * dpr));
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0.7, 0.76, 0.8, 1); gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    const eye = this._eye();
    const vp = mul(perspective(0.75, w / h, Math.max(0.05, this.cam.dist / 500), this.cam.dist * 30 + 500), lookAt(eye, this.cam.target, [0, 0, 1]));
    // sky
    gl.disable(gl.DEPTH_TEST);
    gl.useProgram(this.sky.p);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    let a = this.sky.a("a_pos"); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.disableVertexAttribArray(a);
    gl.enable(gl.DEPTH_TEST);
    // ground
    gl.enable(gl.BLEND); gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.useProgram(this.ground.p);
    const b = this.bounds || { lo: [-10, -10, 0], hi: [10, 10, 0] };
    gl.uniformMatrix4fv(this.ground.u.u_vp, false, vp);
    gl.uniform2f(this.ground.u.u_center, (b.lo[0] + b.hi[0]) / 2, (b.lo[1] + b.hi[1]) / 2);
    gl.uniform1f(this.ground.u.u_size, Math.max(30, Math.hypot(b.hi[0] - b.lo[0], b.hi[1] - b.lo[1]) * 1.6));
    a = this.ground.a("a_pos"); gl.enableVertexAttribArray(a); gl.vertexAttribPointer(a, 2, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    gl.disableVertexAttribArray(a);
    gl.disable(gl.BLEND);
    // meshes
    const M = this.mesh; gl.useProgram(M.p);
    gl.uniformMatrix4fv(M.u.u_vp, false, vp);
    gl.uniform3fv(M.u.u_eye, eye);
    gl.uniform1f(M.u.u_showFree, this.show.free ? 1 : 0);
    const ap = M.a("a_pos"), an = M.a("a_nrm"), ai = M.a("a_inst"), af = M.a("a_free");
    const setMat = (name) => {
      const m = this.materials[name] || { color: [0.5, 0.5, 0.5], rough: 0.6, metal: 0 };
      gl.uniform3fv(M.u.u_color, m.color); gl.uniform1f(M.u.u_rough, m.rough); gl.uniform1f(M.u.u_metal, m.metal);
      const grp = name === "TB Seat" ? "seat" : (name === "TB Concrete" || name === "TB Steps") ? "floor" : null;
      const pt = grp && this.patterns[grp];
      const tex = pt && pt.kind !== "NONE" && this.patTex[grp + pt.kind];
      if (tex) {
        gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex); gl.uniform1i(M.u.u_pat, 0);
        gl.uniform1i(M.u.u_patMode, grp === "floor" ? 1 : 2); gl.uniform1f(M.u.u_patScale, pt.scale || 0.5);
      } else gl.uniform1i(M.u.u_patMode, 0);
    };
    const bindPN = (o) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, o.p); gl.enableVertexAttribArray(ap); gl.vertexAttribPointer(ap, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, o.n); gl.enableVertexAttribArray(an); gl.vertexAttribPointer(an, 3, gl.FLOAT, false, 0, 0);
    };
    gl.uniform1i(M.u.u_instanced, 0);
    if (ai >= 0) { gl.disableVertexAttribArray(ai); gl.vertexAttrib4f(ai, 0, 0, 0, 0); }
    if (af >= 0) { gl.disableVertexAttribArray(af); gl.vertexAttrib1f(af, 0); }
    for (const o of this.objs) { setMat(o.name); bindPN(o); gl.drawArrays(gl.TRIANGLES, 0, o.count); }
    if (this.inst && this.instCount) {
      gl.uniform1i(M.u.u_instanced, 1);
      for (const o of this.seatParts) {
        setMat(o.name); bindPN(o);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.inst);
        gl.enableVertexAttribArray(ai); gl.vertexAttribPointer(ai, 4, gl.FLOAT, false, 20, 0); gl.vertexAttribDivisor(ai, 1);
        gl.enableVertexAttribArray(af); gl.vertexAttribPointer(af, 1, gl.FLOAT, false, 20, 16); gl.vertexAttribDivisor(af, 1);
        gl.drawArraysInstanced(gl.TRIANGLES, 0, o.count, this.instCount);
        gl.vertexAttribDivisor(ai, 0); gl.vertexAttribDivisor(af, 0);
        gl.disableVertexAttribArray(ai); gl.disableVertexAttribArray(af);
      }
    }
    gl.disableVertexAttribArray(ap); gl.disableVertexAttribArray(an);
    // lines
    const Lp = this.line; gl.useProgram(Lp.p);
    gl.uniformMatrix4fv(Lp.u.u_vp, false, vp);
    gl.enable(gl.BLEND);
    const la = Lp.a("a_pos");
    for (const l of this.lines) {
      if ((l.key === "nav" && !this.show.nav) || ((l.key === "outline" || l.key === "booth") && !this.show.outline)) continue;
      if (!l.count) continue;
      gl.uniform4fv(Lp.u.u_color, l.color); gl.uniform1f(Lp.u.u_lift, l.lift);
      gl.bindBuffer(gl.ARRAY_BUFFER, l.p); gl.enableVertexAttribArray(la); gl.vertexAttribPointer(la, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, l.count);
    }
    gl.disableVertexAttribArray(la);
    gl.disable(gl.BLEND);
  }
}
