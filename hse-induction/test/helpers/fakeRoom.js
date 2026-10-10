import * as pc from 'playcanvas';

export const PROPS = ['x', 'y', 'z', 'opacity', 'scale_0', 'scale_1', 'scale_2', 'rot_0', 'rot_1', 'rot_2', 'rot_3'];

// A Y-up 10 x 10 x 3 m room of flat splats (floor, ceiling, 4 walls) plus a solid table on the floor,
// then turned by `rotation` (degrees) and moved by `offset` to look like a raw scan.
// `doorway` leaves a 1 m gap (x in [-0.5, 0.5]) in the north wall (z = -5) below 2.1 m.
export function makeRoom({ rotation = [0, 0, 0], offset = [0, 0, 0], doorway = false, step = 0.2 } = {}) {
  const rows = [];
  const flat = (x, y, z, thin) => {
    const s = [Math.log(0.1), Math.log(0.1), Math.log(0.1)];
    s[thin] = Math.log(0.005);
    rows.push({ kind: null, p: [x, y, z], s });
  };
  const add = (kind, fn) => { const n = rows.length; fn(); for (let i = n; i < rows.length; i++) rows[i].kind = kind; };
  const span = (a, b) => { const out = []; for (let v = a; v <= b + 1e-9; v += step) out.push(+v.toFixed(4)); return out; };

  add('floor', () => span(-5, 5).forEach((x) => span(-5, 5).forEach((z) => flat(x, 0, z, 1))));
  add('ceiling', () => span(-5, 5).forEach((x) => span(-5, 5).forEach((z) => flat(x, 3, z, 1))));
  add('wall', () => span(-5, 5).forEach((t) => span(0, 3).forEach((y) => {
    flat(-5, y, t, 0); flat(5, y, t, 0); flat(t, y, 5, 2);
    if (!(doorway && Math.abs(t) <= 0.5 && y < 2.1)) flat(t, y, -5, 2);
  })));
  add('table', () => span(1, 2).forEach((x) => span(0.1, 0.8).forEach((y) => span(1, 2).forEach((z) => {
    rows.push({ p: [x, y, z], s: [Math.log(0.08), Math.log(0.08), Math.log(0.08)] });
  }))));

  const q = new pc.Quat().setFromEulerAngles(...rotation);
  const data = new Float32Array(rows.length * PROPS.length);
  const v = new pc.Vec3();
  rows.forEach((r, n) => {
    q.transformVector(v.set(...r.p), v);
    const o = n * PROPS.length;
    data.set([v.x + offset[0], v.y + offset[1], v.z + offset[2], 3, ...r.s, q.w, q.x, q.y, q.z], o);
  });
  return { splat: { props: PROPS, count: rows.length, data }, kinds: rows.map((r) => r.kind) };
}

export function stripProps(splat, keep) {
  const idx = keep.map((p) => splat.props.indexOf(p));
  const data = new Float32Array(splat.count * keep.length);
  for (let n = 0; n < splat.count; n++) idx.forEach((k, j) => { data[n * keep.length + j] = splat.data[n * splat.props.length + k]; });
  return { props: keep, count: splat.count, data };
}
