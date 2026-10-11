"""Modern (core profile 3.3) OpenGL renderer.

* Bodies are uploaded once per geometry change into VAOs (positions,
  normals, per-vertex face ids) and drawn with a physically-inspired
  Blinn-Phong shader (key + fill + rim light, hemisphere ambient).
* Thick, anti-aliased lines are produced by a geometry shader that expands
  each segment into a screen-space quad -- core profile has no wide lines.
* Picking renders integer ids into an R32UI framebuffer; a small window is
  read around the cursor and the nearest, highest-priority element wins
  (vertex > edge > face), which makes thin edges easy to hit.
* An optional clip plane implements Fusion's Section Analysis.
"""
from __future__ import annotations

import ctypes

import numpy as np
from OpenGL import GL

# ---------------------------------------------------------------------------
# Shader sources
# ---------------------------------------------------------------------------

MESH_VS = """
#version 330 core
layout(location=0) in vec3 a_pos;
layout(location=1) in vec3 a_nrm;
layout(location=2) in uint a_id;
uniform mat4 u_mvp;
uniform mat4 u_view;
uniform vec4 u_clip;
flat out uint v_id;
out vec3 v_nrm;
out vec3 v_vpos;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    gl_ClipDistance[0] = dot(vec4(a_pos, 1.0), u_clip);
    v_nrm = mat3(u_view) * a_nrm;
    v_vpos = (u_view * vec4(a_pos, 1.0)).xyz;
    v_id = a_id;
}
"""

MESH_FS = """
#version 330 core
in vec3 v_nrm;
in vec3 v_vpos;
flat in uint v_id;
uniform vec3 u_color;
uniform float u_alpha;
uniform int u_hl_face;          // hovered face (local index) or -1
uniform vec3 u_hl_color;
uniform int u_flat;              // 1 = flat colour (highlight overlay)
out vec4 o_color;
void main() {
    vec3 base = u_color;
    if (u_flat == 1) { o_color = vec4(base, u_alpha); return; }
    if (u_hl_face >= 0 && int(v_id) == u_hl_face) base = mix(base, u_hl_color, 0.55);
    vec3 n = normalize(v_nrm);
    vec3 v = normalize(-v_vpos);
    if (!gl_FrontFacing) n = -n;
    vec3 l1 = normalize(vec3(0.35, 0.55, 0.75));
    vec3 l2 = normalize(vec3(-0.6, -0.2, 0.45));
    float d1 = max(dot(n, l1), 0.0);
    float d2 = max(dot(n, l2), 0.0);
    vec3 h1 = normalize(l1 + v);
    float s1 = pow(max(dot(n, h1), 0.0), 48.0);
    float hemi = 0.5 + 0.5 * n.y;
    vec3 amb = mix(vec3(0.20, 0.20, 0.22), vec3(0.34, 0.35, 0.38), hemi);
    float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0) * 0.18;
    vec3 c = base * (amb + d1 * 0.62 + d2 * 0.22) + vec3(s1 * 0.28) + vec3(rim);
    o_color = vec4(pow(c, vec3(1.0/1.08)), u_alpha);
}
"""

PICK_MESH_FS = """
#version 330 core
flat in uint v_id;
uniform uint u_base;
out uint o_id;
void main() { o_id = u_base + v_id; }
"""

LINE_VS = """
#version 330 core
layout(location=0) in vec3 a_pos;
layout(location=1) in vec4 a_col;
layout(location=2) in uint a_id;
uniform mat4 u_mvp;
uniform vec4 u_clip;
out vec4 g_col;
flat out uint g_id;
out float g_clip;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    g_clip = dot(vec4(a_pos, 1.0), u_clip);
    g_col = a_col;
    g_id = a_id;
}
"""

LINE_GS = """
#version 330 core
layout(lines) in;
layout(triangle_strip, max_vertices=4) out;
in vec4 g_col[];
flat in uint g_id[];
in float g_clip[];
uniform vec2 u_viewport;
uniform float u_width;
uniform float u_dash;   // dash period in px (0 = solid)
out vec4 f_col;
flat out uint f_id;
noperspective out float f_edge;
noperspective out float f_dist;
void main() {
    vec4 p0 = gl_in[0].gl_Position;
    vec4 p1 = gl_in[1].gl_Position;
    // clip against near plane to avoid w<=0 explosions
    if (p0.w < 1e-5 && p1.w < 1e-5) return;
    if (p0.w < 1e-5) p0 = mix(p0, p1, (1e-5 - p0.w) / (p1.w - p0.w));
    if (p1.w < 1e-5) p1 = mix(p1, p0, (1e-5 - p1.w) / (p0.w - p1.w));
    vec2 s0 = p0.xy / p0.w * u_viewport * 0.5;
    vec2 s1 = p1.xy / p1.w * u_viewport * 0.5;
    vec2 d = s1 - s0;
    float len = length(d);
    vec2 dir = len > 1e-6 ? d / len : vec2(1.0, 0.0);
    vec2 nrm = vec2(-dir.y, dir.x) * (u_width * 0.5 + 1.0);
    vec2 ext = dir * 0.5;
    vec2 o0 = (nrm) / (u_viewport * 0.5);
    vec2 e0 = ext / (u_viewport * 0.5);
    float c0 = g_clip[0], c1 = g_clip[1];
    gl_ClipDistance[0] = c0; f_col = g_col[0]; f_id = g_id[0]; f_edge = -1.0; f_dist = 0.0;
    gl_Position = vec4((s0 / (u_viewport * 0.5) - e0 + o0) * p0.w, p0.z, p0.w); EmitVertex();
    gl_ClipDistance[0] = c0; f_col = g_col[0]; f_id = g_id[0]; f_edge = 1.0; f_dist = 0.0;
    gl_Position = vec4((s0 / (u_viewport * 0.5) - e0 - o0) * p0.w, p0.z, p0.w); EmitVertex();
    gl_ClipDistance[0] = c1; f_col = g_col[1]; f_id = g_id[1]; f_edge = -1.0; f_dist = len;
    gl_Position = vec4((s1 / (u_viewport * 0.5) + e0 + o0) * p1.w, p1.z, p1.w); EmitVertex();
    gl_ClipDistance[0] = c1; f_col = g_col[1]; f_id = g_id[1]; f_edge = 1.0; f_dist = len;
    gl_Position = vec4((s1 / (u_viewport * 0.5) + e0 - o0) * p1.w, p1.z, p1.w); EmitVertex();
    EndPrimitive();
}
"""

LINE_FS = """
#version 330 core
in vec4 f_col;
flat in uint f_id;
noperspective in float f_edge;
noperspective in float f_dist;
uniform float u_width;
uniform float u_dash;
uniform vec4 u_override;  // a > 0 -> override colour
out vec4 o_color;
void main() {
    if (u_dash > 0.0 && mod(f_dist, u_dash) > u_dash * 0.6) discard;
    float half_w = u_width * 0.5 + 1.0;
    float px = abs(f_edge) * half_w;
    float a = clamp(half_w - px, 0.0, 1.0);
    vec4 c = u_override.a > 0.0 ? u_override : f_col;
    o_color = vec4(c.rgb, c.a * a);
}
"""

PICK_LINE_FS = """
#version 330 core
flat in uint f_id;
uniform uint u_base;
out uint o_id;
void main() { if (f_id == 0u) discard; o_id = u_base + f_id; }
"""

POINT_VS = """
#version 330 core
layout(location=0) in vec3 a_pos;
layout(location=1) in vec4 a_col;
layout(location=2) in uint a_id;
uniform mat4 u_mvp;
uniform float u_size;
out vec4 v_col;
flat out uint v_id;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    gl_Position.z -= 0.0005 * gl_Position.w;
    gl_PointSize = u_size;
    v_col = a_col;
    v_id = a_id;
}
"""

POINT_FS = """
#version 330 core
in vec4 v_col;
flat in uint v_id;
uniform int u_round;
out vec4 o_color;
void main() {
    vec2 c = gl_PointCoord * 2.0 - 1.0;
    if (u_round == 1 && dot(c, c) > 1.0) discard;
    float border = max(abs(c.x), abs(c.y));
    vec3 col = (u_round == 0 && border > 0.6) ? v_col.rgb * 0.45 : v_col.rgb;
    o_color = vec4(col, v_col.a);
}
"""

PICK_POINT_FS = """
#version 330 core
flat in uint v_id;
uniform uint u_base;
out uint o_id;
void main() { if (v_id == 0u) discard; o_id = u_base + v_id; }
"""

TRI_VS = """
#version 330 core
layout(location=0) in vec3 a_pos;
layout(location=1) in vec4 a_col;
layout(location=2) in uint a_id;
uniform mat4 u_mvp;
uniform vec4 u_clip;
out vec4 v_col;
flat out uint v_id;
void main() {
    gl_Position = u_mvp * vec4(a_pos, 1.0);
    gl_ClipDistance[0] = dot(vec4(a_pos, 1.0), u_clip);
    v_col = a_col;
    v_id = a_id;
}
"""

TRI_FS = """
#version 330 core
in vec4 v_col;
flat in uint v_id;
uniform int u_hl;
out vec4 o_color;
void main() {
    vec4 c = v_col;
    if (u_hl >= 0 && int(v_id) == u_hl) c = vec4(mix(c.rgb, vec3(0.35, 0.65, 1.0), 0.6), min(1.0, c.a + 0.25));
    o_color = c;
}
"""

BG_VS = """
#version 330 core
out vec2 v_uv;
void main() {
    vec2 p = vec2((gl_VertexID << 1) & 2, gl_VertexID & 2);
    v_uv = p;
    gl_Position = vec4(p * 2.0 - 1.0, 0.9999, 1.0);
}
"""

BG_FS = """
#version 330 core
in vec2 v_uv;
uniform vec3 u_top;
uniform vec3 u_bottom;
out vec4 o_color;
void main() { o_color = vec4(mix(u_bottom, u_top, v_uv.y), 1.0); }
"""


SHADOW_FS = """
#version 330 core
void main() {}
"""

GROUND_VS = """
#version 330 core
layout(location=0) in vec3 a_pos;
uniform mat4 u_mvp;
uniform mat4 u_light;
out vec4 v_lpos;
out vec3 v_wpos;
void main() {
    v_wpos = a_pos;
    v_lpos = u_light * vec4(a_pos, 1.0);
    gl_Position = u_mvp * vec4(a_pos, 1.0);
}
"""

GROUND_FS = """
#version 330 core
in vec4 v_lpos;
in vec3 v_wpos;
uniform sampler2D u_shadow;
uniform float u_texel;
uniform float u_strength;
uniform vec3 u_center;
uniform float u_radius;
out vec4 o_color;
void main() {
    vec3 p = v_lpos.xyz / v_lpos.w * 0.5 + 0.5;
    float lit = 0.0;
    for (int x = -3; x <= 3; x++)
        for (int y = -3; y <= 3; y++) {
            float d = texture(u_shadow, p.xy + vec2(x, y) * u_texel * 1.5).r;
            lit += (p.z - 0.0015 > d) ? 0.0 : 1.0;
        }
    lit /= 49.0;
    float fade = 1.0 - smoothstep(u_radius * 1.2, u_radius * 3.5, length(v_wpos.xy - u_center.xy));
    o_color = vec4(0.04, 0.05, 0.08, (1.0 - lit) * u_strength * fade);
}
"""


def _compile(src, kind):
    sh = GL.glCreateShader(kind)
    GL.glShaderSource(sh, src)
    GL.glCompileShader(sh)
    if not GL.glGetShaderiv(sh, GL.GL_COMPILE_STATUS):
        raise RuntimeError(GL.glGetShaderInfoLog(sh).decode())
    return sh


class Program:
    def __init__(self, vs, fs, gs=None):
        self.id = GL.glCreateProgram()
        shaders = [_compile(vs, GL.GL_VERTEX_SHADER), _compile(fs, GL.GL_FRAGMENT_SHADER)]
        if gs:
            shaders.append(_compile(gs, GL.GL_GEOMETRY_SHADER))
        for s in shaders:
            GL.glAttachShader(self.id, s)
        GL.glLinkProgram(self.id)
        if not GL.glGetProgramiv(self.id, GL.GL_LINK_STATUS):
            raise RuntimeError(GL.glGetProgramInfoLog(self.id).decode())
        for s in shaders:
            GL.glDeleteShader(s)
        self._loc = {}

    def use(self):
        GL.glUseProgram(self.id)
        return self

    def loc(self, name):
        if name not in self._loc:
            self._loc[name] = GL.glGetUniformLocation(self.id, name)
        return self._loc[name]

    def m4(self, name, m):
        GL.glUniformMatrix4fv(self.loc(name), 1, GL.GL_TRUE, np.asarray(m, np.float32))

    def v4(self, name, v):
        GL.glUniform4f(self.loc(name), *[float(x) for x in v])

    def v3(self, name, v):
        GL.glUniform3f(self.loc(name), *[float(x) for x in v])

    def v2(self, name, v):
        GL.glUniform2f(self.loc(name), *[float(x) for x in v])

    def f(self, name, v):
        GL.glUniform1f(self.loc(name), float(v))

    def i(self, name, v):
        GL.glUniform1i(self.loc(name), int(v))

    def u(self, name, v):
        GL.glUniform1ui(self.loc(name), int(v))


# ---------------------------------------------------------------------------
# GPU buffers
# ---------------------------------------------------------------------------

class VertexArray:
    """A VAO with interleaved float attributes + one uint id attribute."""

    def __init__(self, floats: np.ndarray, float_sizes: list[int], ids: np.ndarray, indices: np.ndarray | None = None):
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        floats = np.ascontiguousarray(floats, np.float32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, floats.nbytes, floats, GL.GL_STATIC_DRAW)
        stride = floats.shape[1] * 4 if floats.ndim == 2 else 12
        off = 0
        for loc, n in enumerate(float_sizes):
            GL.glEnableVertexAttribArray(loc)
            GL.glVertexAttribPointer(loc, n, GL.GL_FLOAT, False, stride, ctypes.c_void_p(off))
            off += n * 4
        self.ibo = GL.glGenBuffers(1)
        ids = np.ascontiguousarray(ids, np.uint32)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.ibo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, max(ids.nbytes, 4), ids if ids.size else np.zeros(1, np.uint32),
                        GL.GL_STATIC_DRAW)
        loc = len(float_sizes)
        GL.glEnableVertexAttribArray(loc)
        GL.glVertexAttribIPointer(loc, 1, GL.GL_UNSIGNED_INT, 4, ctypes.c_void_p(0))
        self.ebo = None
        self.count = len(floats)
        if indices is not None:
            self.ebo = GL.glGenBuffers(1)
            idx = np.ascontiguousarray(indices, np.uint32).ravel()
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
            GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, max(idx.nbytes, 4), idx if idx.size else np.zeros(1, np.uint32),
                            GL.GL_STATIC_DRAW)
            self.count = idx.size
        GL.glBindVertexArray(0)

    def draw(self, mode, first=0, count=None):
        n = self.count if count is None else count
        if n <= 0:
            return
        GL.glBindVertexArray(self.vao)
        if self.ebo is not None:
            GL.glDrawElements(mode, n, GL.GL_UNSIGNED_INT, ctypes.c_void_p(first * 4))
        else:
            GL.glDrawArrays(mode, first, n)
        GL.glBindVertexArray(0)

    def delete(self):
        bufs = [b for b in (self.vbo, self.ibo, self.ebo) if b is not None]
        GL.glDeleteBuffers(len(bufs), bufs)
        GL.glDeleteVertexArrays(1, [self.vao])


class BodyGPU:
    """GPU resources for one body mesh."""

    def __init__(self, mesh):
        self.mesh = mesh
        # Per-vertex face id (vertices are not shared across faces)
        vid = np.zeros(len(mesh.positions), np.uint32)
        if len(mesh.indices):
            vid[mesh.indices[:, 0]] = mesh.face_of_tri
            vid[mesh.indices[:, 1]] = mesh.face_of_tri
            vid[mesh.indices[:, 2]] = mesh.face_of_tri
        inter = np.hstack([mesh.positions, mesh.normals]).astype(np.float32)
        self.tris = VertexArray(inter, [3, 3], vid, mesh.indices)
        # Face ranges in the index buffer (triangles are grouped per face)
        self.face_ranges = {}
        if len(mesh.face_of_tri):
            fot = mesh.face_of_tri
            change = np.flatnonzero(np.diff(fot)) + 1
            starts = np.concatenate([[0], change])
            ends = np.concatenate([change, [len(fot)]])
            for s, e in zip(starts, ends):
                self.face_ranges[int(fot[s])] = (int(s) * 3, int(e - s) * 3)
        # Edges as GL_LINES segments; ids are edge index + 1 (0 = none)
        segs, ids, self.edge_ranges = [], [], {}
        k = 0
        for ei, pl in enumerate(mesh.edge_lines):
            if len(pl) < 2:
                continue
            a = np.repeat(pl, 2, axis=0)[1:-1]
            segs.append(a)
            ids.append(np.full(len(a), ei + 1, np.uint32))
            self.edge_ranges[ei] = (k, len(a))
            k += len(a)
        if segs:
            pos = np.vstack(segs).astype(np.float32)
            col = np.zeros((len(pos), 4), np.float32)
            self.edges = VertexArray(np.hstack([pos, col]), [3, 4], np.concatenate(ids))
        else:
            self.edges = None
        if len(mesh.vertex_points):
            vp = mesh.vertex_points.astype(np.float32)
            col = np.tile(np.array([[0.1, 0.1, 0.1, 1]], np.float32), (len(vp), 1))
            self.verts = VertexArray(np.hstack([vp, col]), [3, 4], np.arange(1, len(vp) + 1, dtype=np.uint32))
        else:
            self.verts = None

    def delete(self):
        self.tris.delete()
        if self.edges:
            self.edges.delete()
        if self.verts:
            self.verts.delete()


class Batch:
    """Dynamic batch of coloured lines / points / triangles with ids."""

    def __init__(self):
        self.pos: list = []
        self.col: list = []
        self.ids: list = []
        self.gpu: VertexArray | None = None
        self.dirty = True

    def clear(self):
        self.pos, self.col, self.ids = [], [], []
        self.dirty = True

    def add_polyline(self, pts, color, pid=0, closed=False):
        pts = np.asarray(pts, np.float32)
        if len(pts) < 2:
            return
        if closed:
            pts = np.vstack([pts, pts[:1]])
        seg = np.repeat(pts, 2, axis=0)[1:-1]
        self.pos.append(seg)
        self.col.append(np.tile(np.asarray(color, np.float32), (len(seg), 1)))
        self.ids.append(np.full(len(seg), pid, np.uint32))
        self.dirty = True

    def add_points(self, pts, color, pid=0):
        pts = np.atleast_2d(np.asarray(pts, np.float32))
        self.pos.append(pts)
        self.col.append(np.tile(np.asarray(color, np.float32), (len(pts), 1)))
        ids = np.full(len(pts), pid, np.uint32) if np.isscalar(pid) else np.asarray(pid, np.uint32)
        self.ids.append(ids)
        self.dirty = True

    def add_triangles(self, tris, color, pid=0):
        tris = np.asarray(tris, np.float32).reshape(-1, 3)
        self.pos.append(tris)
        self.col.append(np.tile(np.asarray(color, np.float32), (len(tris), 1)))
        self.ids.append(np.full(len(tris), pid, np.uint32))
        self.dirty = True

    def upload(self):
        if not self.dirty:
            return
        if self.gpu:
            self.gpu.delete()
            self.gpu = None
        if self.pos:
            pos = np.vstack(self.pos)
            col = np.vstack(self.col)
            self.gpu = VertexArray(np.hstack([pos, col]), [3, 4], np.concatenate(self.ids))
        self.dirty = False

    def draw(self, mode):
        self.upload()
        if self.gpu:
            self.gpu.draw(mode)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class Renderer:
    def __init__(self):
        self.mesh = Program(MESH_VS, MESH_FS)
        self.mesh_pick = Program(MESH_VS, PICK_MESH_FS)
        self.line = Program(LINE_VS, LINE_FS, LINE_GS)
        self.line_pick = Program(LINE_VS, PICK_LINE_FS, LINE_GS)
        self.point = Program(POINT_VS, POINT_FS)
        self.point_pick = Program(POINT_VS, PICK_POINT_FS)
        self.tri = Program(TRI_VS, TRI_FS)
        self.tri_pick = Program(TRI_VS, PICK_POINT_FS.replace("v_id", "v_id"))
        self.bg = Program(BG_VS, BG_FS)
        self.shadow_prog = Program(MESH_VS, SHADOW_FS)
        self.ground_prog = Program(GROUND_VS, GROUND_FS)
        self._shadow = None
        self._ground_vao = None
        self.empty_vao = GL.glGenVertexArrays(1)
        self.pick_fbo = None
        self.pick_size = (0, 0)
        self.clip = np.array([0, 0, 0, 1.0])  # disabled by default (always >= 0)

    # ------------------------------------------------------------------ state
    def begin(self, w, h, top, bottom):
        GL.glViewport(0, 0, w, h)
        GL.glClearColor(*bottom, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        GL.glDisable(GL.GL_DEPTH_TEST)
        self.bg.use()
        self.bg.v3("u_top", top)
        self.bg.v3("u_bottom", bottom)
        GL.glBindVertexArray(self.empty_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glBindVertexArray(0)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glEnable(GL.GL_BLEND)
        # keep destination alpha at 1 so the widget composites opaquely
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glEnable(GL.GL_PROGRAM_POINT_SIZE)
        GL.glEnable(GL.GL_CLIP_DISTANCE0)

    def draw_body(self, gpu: BodyGPU, mvp, view, color, alpha=1.0, hl_face=-1, hl_color=(0.3, 0.6, 1.0)):
        p = self.mesh.use()
        p.m4("u_mvp", mvp)
        p.m4("u_view", view)
        p.v4("u_clip", self.clip)
        p.v3("u_color", color)
        p.f("u_alpha", alpha)
        p.i("u_hl_face", hl_face)
        p.v3("u_hl_color", hl_color)
        p.i("u_flat", 0)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(1.0, 1.0)
        if alpha < 1.0:
            GL.glDepthMask(GL.GL_FALSE)
        gpu.tris.draw(GL.GL_TRIANGLES)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

    SHADOW_SIZE = 4096

    def _ensure_shadow(self):
        if self._shadow is not None:
            return
        n = self.SHADOW_SIZE
        prev = GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING)
        tex = GL.glGenTextures(1)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_DEPTH_COMPONENT24, n, n, 0, GL.GL_DEPTH_COMPONENT, GL.GL_FLOAT, None)
        for k, v in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_NEAREST), (GL.GL_TEXTURE_MAG_FILTER, GL.GL_NEAREST),
                     (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_BORDER), (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_BORDER)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, k, v)
        GL.glTexParameterfv(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_BORDER_COLOR, [1.0, 1.0, 1.0, 1.0])
        fbo = GL.glGenFramebuffers(1)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_TEXTURE_2D, tex, 0)
        GL.glDrawBuffer(GL.GL_NONE)
        GL.glReadBuffer(GL.GL_NONE)
        self._shadow = (fbo, tex)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, prev)
        quad = np.array([[-1, -1, 0], [1, -1, 0], [1, 1, 0], [-1, -1, 0], [1, 1, 0], [-1, 1, 0]], np.float32)
        self._ground_vao = GL.glGenVertexArrays(1)
        vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self._ground_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, quad.nbytes, quad, GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12, None)
        GL.glBindVertexArray(0)

    def draw_ground_shadow(self, gpus, mvp, center, radius, z_floor, light_dir, strength=0.55):
        """Shadow-mapped soft shadow on a transparent ground plane at ``z_floor`` (render export only)."""
        self._ensure_shadow()
        fbo, tex = self._shadow
        n = self.SHADOW_SIZE
        l = np.asarray(light_dir, float)
        l /= np.linalg.norm(l)
        eye = np.asarray(center, float) + l * radius * 4
        f = -l
        up = np.array([0, 1.0, 0]) if abs(f[1]) < 0.9 else np.array([1.0, 0, 0])
        s = np.cross(f, up)
        s /= np.linalg.norm(s)
        u = np.cross(s, f)
        view = np.eye(4)
        view[0, :3], view[1, :3], view[2, :3] = s, u, -f
        view[:3, 3] = -view[:3, :3] @ eye
        h = radius * 1.6
        proj = np.diag([1 / h, 1 / h, -2 / (radius * 8), 1.0])
        proj[2, 3] = -1.0
        light = proj @ view
        prev_fbo = GL.glGetIntegerv(GL.GL_FRAMEBUFFER_BINDING)
        prev_vp = GL.glGetIntegerv(GL.GL_VIEWPORT)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, fbo)
        GL.glViewport(0, 0, n, n)
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)
        p = self.shadow_prog.use()
        p.m4("u_mvp", light)
        p.m4("u_view", np.eye(4))
        p.v4("u_clip", np.array([0, 0, 0, 1.0]))
        GL.glDisable(GL.GL_BLEND)
        for g in gpus:
            g.tris.draw(GL.GL_TRIANGLES)
        GL.glEnable(GL.GL_BLEND)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, prev_fbo)
        GL.glViewport(*[int(v) for v in prev_vp])
        g = self.ground_prog.use()
        g.m4("u_mvp", mvp @ np.array([[radius * 6, 0, 0, center[0]], [0, radius * 6, 0, center[1]],
                                      [0, 0, 1, z_floor - 0.01 * radius], [0, 0, 0, 1.0]]))
        g.m4("u_light", light @ np.array([[radius * 6, 0, 0, center[0]], [0, radius * 6, 0, center[1]],
                                          [0, 0, 1, z_floor - 0.01 * radius], [0, 0, 0, 1.0]]))
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
        g.i("u_shadow", 0)
        g.f("u_texel", 1.0 / n)
        g.f("u_strength", strength)
        g.v3("u_center", center)
        g.f("u_radius", radius)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glBindVertexArray(self._ground_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6)
        GL.glBindVertexArray(0)
        GL.glDepthMask(GL.GL_TRUE)

    def draw_faces_flat(self, gpu: BodyGPU, mvp, view, faces, color, alpha=0.6):
        p = self.mesh.use()
        p.m4("u_mvp", mvp)
        p.m4("u_view", view)
        p.v4("u_clip", self.clip)
        p.v3("u_color", color)
        p.f("u_alpha", alpha)
        p.i("u_hl_face", -1)
        p.i("u_flat", 1)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(0.0, -2.0)
        for fi in faces:
            r = gpu.face_ranges.get(fi)
            if r:
                gpu.tris.draw(GL.GL_TRIANGLES, r[0], r[1])
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)

    def draw_edges(self, gpu: BodyGPU, mvp, vp, color, width=1.4, only=None):
        if not gpu.edges:
            return
        p = self._line_setup(self.line, mvp, vp, width)
        p.v4("u_override", color)
        if only is None:
            gpu.edges.draw(GL.GL_LINES)
        else:
            for ei in only:
                r = gpu.edge_ranges.get(ei)
                if r:
                    gpu.edges.draw(GL.GL_LINES, r[0], r[1])

    def draw_vertices(self, gpu: BodyGPU, mvp, color, size=7.0, only=None):
        if not gpu.verts:
            return
        p = self.point.use()
        p.m4("u_mvp", mvp)
        p.f("u_size", size)
        p.i("u_round", 1)
        if only is None:
            gpu.verts.draw(GL.GL_POINTS)
        else:
            for vi in only:
                gpu.verts.draw(GL.GL_POINTS, vi, 1)

    def _line_setup(self, prog, mvp, vp, width, dash=0.0):
        p = prog.use()
        p.m4("u_mvp", mvp)
        p.v4("u_clip", self.clip)
        p.v2("u_viewport", vp)
        p.f("u_width", width)
        p.f("u_dash", dash)
        return p

    def draw_lines(self, batch: Batch, mvp, vp, width=1.5, dash=0.0, depth=True, override=(0, 0, 0, 0)):
        if not depth:
            GL.glDisable(GL.GL_DEPTH_TEST)
        p = self._line_setup(self.line, mvp, vp, width, dash)
        p.v4("u_override", override)
        batch.draw(GL.GL_LINES)
        if not depth:
            GL.glEnable(GL.GL_DEPTH_TEST)

    def draw_points(self, batch: Batch, mvp, size=6.0, round_=False, depth=True):
        if not depth:
            GL.glDisable(GL.GL_DEPTH_TEST)
        p = self.point.use()
        p.m4("u_mvp", mvp)
        p.f("u_size", size)
        p.i("u_round", 1 if round_ else 0)
        batch.draw(GL.GL_POINTS)
        if not depth:
            GL.glEnable(GL.GL_DEPTH_TEST)

    def draw_tris(self, batch: Batch, mvp, hl=-1, depth_write=False):
        p = self.tri.use()
        p.m4("u_mvp", mvp)
        p.v4("u_clip", self.clip)
        p.i("u_hl", hl)
        GL.glDepthMask(GL.GL_TRUE if depth_write else GL.GL_FALSE)
        GL.glDisable(GL.GL_CULL_FACE)
        batch.draw(GL.GL_TRIANGLES)
        GL.glDepthMask(GL.GL_TRUE)

    # ------------------------------------------------------------------ picking
    def ensure_pick_fbo(self, w, h):
        if self.pick_fbo is not None and self.pick_size == (w, h):
            return
        if self.pick_fbo is not None:
            GL.glDeleteFramebuffers(1, [self.pick_fbo])
            GL.glDeleteRenderbuffers(2, [self.pick_rb, self.pick_depth])
        self.pick_fbo = GL.glGenFramebuffers(1)
        self.pick_rb, self.pick_depth = GL.glGenRenderbuffers(2)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self.pick_rb)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_R32UI, w, h)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, self.pick_depth)
        GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, GL.GL_DEPTH_COMPONENT24, w, h)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.pick_fbo)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_COLOR_ATTACHMENT0, GL.GL_RENDERBUFFER, self.pick_rb)
        GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT, GL.GL_RENDERBUFFER, self.pick_depth)
        self.pick_size = (w, h)

    def begin_pick(self, w, h):
        self.ensure_pick_fbo(w, h)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.pick_fbo)
        GL.glViewport(0, 0, w, h)
        GL.glDisable(GL.GL_BLEND)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glClearBufferuiv(GL.GL_COLOR, 0, np.zeros(4, np.uint32))
        GL.glClear(GL.GL_DEPTH_BUFFER_BIT)

    def pick_body(self, gpu: BodyGPU, mvp, view, base_face, base_edge, base_vert, vp, edges=True, verts=False):
        p = self.mesh_pick.use()
        p.m4("u_mvp", mvp)
        p.m4("u_view", view)
        p.v4("u_clip", self.clip)
        p.u("u_base", base_face)
        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(1.0, 1.0)
        gpu.tris.draw(GL.GL_TRIANGLES)
        GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
        if edges and gpu.edges:
            p = self._line_setup(self.line_pick, mvp, vp, 3.0)
            p.u("u_base", base_edge)
            gpu.edges.draw(GL.GL_LINES)
        if verts and gpu.verts:
            p = self.point_pick.use()
            p.m4("u_mvp", mvp)
            p.f("u_size", 11.0)
            p.u("u_base", base_vert)
            gpu.verts.draw(GL.GL_POINTS)

    def pick_lines(self, batch: Batch, mvp, vp, base, width=6.0, depth=True):
        if not depth:
            GL.glDisable(GL.GL_DEPTH_TEST)
        p = self._line_setup(self.line_pick, mvp, vp, width)
        p.u("u_base", base)
        batch.draw(GL.GL_LINES)
        GL.glEnable(GL.GL_DEPTH_TEST)

    def pick_points(self, batch: Batch, mvp, base, size=12.0, depth=True):
        if not depth:
            GL.glDisable(GL.GL_DEPTH_TEST)
        p = self.point_pick.use()
        p.m4("u_mvp", mvp)
        p.f("u_size", size)
        p.u("u_base", base)
        batch.draw(GL.GL_POINTS)
        GL.glEnable(GL.GL_DEPTH_TEST)

    def pick_tris(self, batch: Batch, mvp, base):
        p = self.tri_pick.use()
        p.m4("u_mvp", mvp)
        p.v4("u_clip", self.clip)
        p.u("u_base", base)
        batch.draw(GL.GL_TRIANGLES)

    def read_pick(self, x, y, h, radius=6):
        """Read ids and depths in a (2r+1)^2 window around pixel (x, y)."""
        w_, h_ = self.pick_size
        x0, y0 = max(0, x - radius), max(0, h - 1 - y - radius)
        x1, y1 = min(w_, x + radius + 1), min(h_, h - y + radius)
        if x1 <= x0 or y1 <= y0:
            return None, None, (x0, y0)
        GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, self.pick_fbo)
        GL.glReadBuffer(GL.GL_COLOR_ATTACHMENT0)
        ids = GL.glReadPixels(x0, y0, x1 - x0, y1 - y0, GL.GL_RED_INTEGER, GL.GL_UNSIGNED_INT)
        ids = np.frombuffer(ids, np.uint32).reshape(y1 - y0, x1 - x0)
        dep = GL.glReadPixels(x0, y0, x1 - x0, y1 - y0, GL.GL_DEPTH_COMPONENT, GL.GL_FLOAT)
        dep = np.frombuffer(dep, np.float32).reshape(y1 - y0, x1 - x0)
        return ids, dep, (x0, y0)
