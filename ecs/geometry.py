"""
Geometry primitives for the ECS analysis.

Provides:
  - ECS distance transform and Voronoi-based cell assignment
  - 6-connected boundary-face counting (ECS-facing surface area)
  - Marching-cubes mesh extraction with physical-scale Gaussian smoothing
  - Mean curvature via cotangent Laplacian (signed, convention-validated)
  - Per-vertex barycentric area
  - Local-plane deviation (for multi-scale roughness and feature detection)
  - Local extremum detection on a mesh

Sign convention for mean curvature H:
    POSITIVE H = CONVEX  (surface bulges away from cell interior, into ECS)
    NEGATIVE H = CONCAVE (invagination / membrane wraps around neighbor)

This convention is validated by `sphere_sign_check()` — run it before
trusting any H-sign results downstream.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes
import trimesh


# ---------- Distance transforms ----------

def ecs_distance_nm(ecs_binary: np.ndarray,
                    voxel_size_nm: tuple[float, float, float]) -> np.ndarray:
    """Euclidean distance in nm from each ECS voxel to the nearest non-ECS
    (cell or background) voxel. Non-ECS voxels have distance 0."""
    return distance_transform_edt(ecs_binary, sampling=voxel_size_nm)


def voronoi_cell_assignment(
    cell_instance: np.ndarray,
    voxel_size_nm: tuple[float, float, float],
) -> np.ndarray:
    """For each voxel, the ID of its nearest cell (Euclidean in physical units).

    Voxels already inside a cell return that cell's ID. Voxels in ECS or in
    unlabelled background return the ID of the nearest cell.
    """
    not_cell = (cell_instance == 0)
    _, idx = distance_transform_edt(
        not_cell, sampling=voxel_size_nm, return_indices=True
    )
    return cell_instance[idx[0], idx[1], idx[2]]


# ---------- Boundary-face counting (SA:V) ----------

@dataclass
class BoundaryFaceCounts:
    ecs_faces: int            # cell faces whose neighbor is ECS
    cell_cell_faces: int      # cell faces whose neighbor is a DIFFERENT cell
    outer_faces: int          # cell faces at the crop edge (partial cells)

    @property
    def total_faces(self) -> int:
        return self.ecs_faces + self.cell_cell_faces + self.outer_faces


def count_cell_boundary_faces(
    cell_instance: np.ndarray,
    ecs_binary: np.ndarray,
    cell_id: int,
) -> BoundaryFaceCounts:
    """Count 6-connected boundary faces for one cell.

    Faces are classified by what the neighboring voxel is:
      - ECS voxel      -> ecs_faces
      - another cell   -> cell_cell_faces
      - at volume edge -> outer_faces (neighbor doesn't exist)
    Same-cell-ID faces are interior and not counted.
    """
    cell_mask = (cell_instance == cell_id)
    if not cell_mask.any():
        return BoundaryFaceCounts(0, 0, 0)

    # Tight bounding box PLUS 1-voxel padding so we can look at neighbors.
    # Track whether the bbox (without padding) touches a volume edge — those
    # faces become outer_faces (cell voxels with no neighbor to compare).
    coords = np.argwhere(cell_mask)
    raw_lo = coords.min(axis=0)
    raw_hi = coords.max(axis=0) + 1
    shape = np.asarray(cell_instance.shape)
    lo = np.maximum(raw_lo - 1, 0)
    hi = np.minimum(raw_hi + 1, shape)
    # Is the cell at the volume boundary along this axis (low/high)?
    touches_lo = (raw_lo == 0)
    touches_hi = (raw_hi == shape)

    sl = tuple(slice(l, h) for l, h in zip(lo, hi))
    cm = cell_mask[sl]
    ci = cell_instance[sl]
    em = ecs_binary[sl]

    ecs_f = 0
    cc_f = 0
    outer_f = 0

    for axis in range(3):
        fwd = [slice(None)] * 3
        bwd = [slice(None)] * 3
        fwd[axis] = slice(1, None)
        bwd[axis] = slice(0, -1)
        fwd = tuple(fwd); bwd = tuple(bwd)

        # +axis faces: cell at bwd, neighbor at fwd
        face_from_bwd = cm[bwd] & ~cm[fwd]
        if face_from_bwd.any():
            ecs_f += int((face_from_bwd & em[fwd]).sum())
            cc_f += int((face_from_bwd & (ci[fwd] != 0) & ~em[fwd]).sum())

        # -axis faces: cell at fwd, neighbor at bwd
        face_from_fwd = cm[fwd] & ~cm[bwd]
        if face_from_fwd.any():
            ecs_f += int((face_from_fwd & em[bwd]).sum())
            cc_f += int((face_from_fwd & (ci[bwd] != 0) & ~em[bwd]).sum())

        # Volume-edge faces: cell voxels at the true volume boundary have no
        # neighbor; count those as outer. Check the original (unpadded) bbox.
        if touches_lo[axis]:
            edge = [slice(None)] * 3
            edge[axis] = 0  # first slice of full volume, within sub
            # In `cm`, the first slice of the full volume is at padded index
            # lo[axis]==0 -> cm index 0; else padding added one slot.
            cm_idx = 0 if lo[axis] == 0 else 1
            edge[axis] = cm_idx
            outer_f += int(cm[tuple(edge)].sum())
        if touches_hi[axis]:
            edge = [slice(None)] * 3
            cm_idx = cm.shape[axis] - 1 if hi[axis] == shape[axis] else cm.shape[axis] - 2
            edge[axis] = cm_idx
            outer_f += int(cm[tuple(edge)].sum())

    return BoundaryFaceCounts(ecs_f, cc_f, outer_f)


# ---------- Mesh extraction ----------

@dataclass
class CellMesh:
    verts_nm: np.ndarray     # (V, 3) float, physical nm
    faces: np.ndarray        # (F, 3) int, triangle indices
    trimesh: trimesh.Trimesh = None

    @classmethod
    def from_mask(cls, cell_mask: np.ndarray,
                  voxel_size_nm: tuple[float, float, float],
                  sigma_nm: float,
                  padding_voxels: int = 4,
                  sub_origin_nm: tuple[float, float, float] = (0.0, 0.0, 0.0),
                  ) -> "CellMesh | None":
        """Smooth a binary mask with a physical-scale Gaussian and extract
        an isosurface at level 0.5. Vertices returned in physical (nm)
        coordinates, offset by sub_origin_nm.

        Returns None if the mesh is degenerate (fewer than 4 verts or faces).
        """
        if not cell_mask.any():
            return None

        # Pad so the smoothing kernel has room.
        pad_vox = max(padding_voxels, int(np.ceil(3 * sigma_nm / min(voxel_size_nm))))
        padded = np.pad(cell_mask.astype(np.float32),
                        pad_vox, mode="constant", constant_values=0.0)
        sigma_vox = tuple(sigma_nm / v for v in voxel_size_nm)
        phi = gaussian_filter(padded, sigma=sigma_vox)

        try:
            verts, faces, _, _ = marching_cubes(
                phi, level=0.5, spacing=tuple(voxel_size_nm)
            )
        except (ValueError, RuntimeError):
            return None
        if len(verts) < 4 or len(faces) < 4:
            return None

        # Undo the padding offset (in nm) and add any sub-volume origin.
        pad_offset_nm = np.array([pad_vox * v for v in voxel_size_nm])
        sub_origin_arr = np.asarray(sub_origin_nm, dtype=float)
        verts_nm = verts - pad_offset_nm + sub_origin_arr

        mesh = trimesh.Trimesh(vertices=verts_nm, faces=faces, process=False)
        return cls(verts_nm=verts_nm, faces=faces, trimesh=mesh)


# ---------- Curvature ----------

def cotangent_mean_curvature(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mean curvature magnitude + vector + per-vertex barycentric area via
    cotangent Laplacian.

    Returns:
        H_mag        : (V,) non-negative |H| in 1/nm
        Hn           : (V, 3) mean curvature normal vector (Laplacian / 2A)
        vert_area    : (V,)   sum of 1/3 of each adjacent triangle's area, nm^2
    """
    V = mesh.vertices
    F = mesh.faces

    v0 = V[F[:, 0]]; v1 = V[F[:, 1]]; v2 = V[F[:, 2]]

    e01 = v1 - v0
    e02 = v2 - v0
    e12 = v2 - v1

    cross = np.cross(e01, e02)
    tri_area = 0.5 * np.linalg.norm(cross, axis=1)
    twoA = 2.0 * tri_area  # denominator for cotangents
    eps = 1e-30
    valid = twoA > eps

    cot0 = np.zeros(len(F))
    cot1 = np.zeros(len(F))
    cot2 = np.zeros(len(F))
    # cot(angle at v0) = dot(e01, e02) / (2 * tri_area)
    cot0[valid] = np.sum(e01[valid] * e02[valid], axis=1) / twoA[valid]
    cot1[valid] = np.sum((-e01[valid]) * e12[valid], axis=1) / twoA[valid]
    cot2[valid] = np.sum((-e02[valid]) * (-e12[valid]), axis=1) / twoA[valid]

    n_verts = len(V)
    vert_area = np.zeros(n_verts)
    third = tri_area / 3.0
    np.add.at(vert_area, F[:, 0], third)
    np.add.at(vert_area, F[:, 1], third)
    np.add.at(vert_area, F[:, 2], third)

    laplacian = np.zeros((n_verts, 3))
    # Contribution to vertex i from edge (i, j) is w_ij * (v_j - v_i),
    # where w_ij comes from the cotangent of the angle opposite that edge in
    # each adjacent triangle. Accumulating here as a sum of
    # per-triangle contributions.
    diff_12 = v2 - v1
    for d in range(3):
        np.add.at(laplacian[:, d], F[:, 1],  cot0 * diff_12[:, d])
        np.add.at(laplacian[:, d], F[:, 2], -cot0 * diff_12[:, d])
    diff_02 = v2 - v0
    for d in range(3):
        np.add.at(laplacian[:, d], F[:, 0],  cot1 * diff_02[:, d])
        np.add.at(laplacian[:, d], F[:, 2], -cot1 * diff_02[:, d])
    diff_01 = v1 - v0
    for d in range(3):
        np.add.at(laplacian[:, d], F[:, 0],  cot2 * diff_01[:, d])
        np.add.at(laplacian[:, d], F[:, 1], -cot2 * diff_01[:, d])

    # Meyer-Desbrun-Schroeder: Delta(x) = -2 H n.
    # Our `laplacian` accumulates sum_j (cot a + cot b) (x_j - x_i), so
    # laplacian / (2 A) = Delta(x) = -2 H n  =>  |H| = |laplacian| / (4 A).
    safe_area = np.maximum(vert_area, 1e-20)
    Hn = laplacian / (4.0 * safe_area[:, np.newaxis])
    H_mag = np.linalg.norm(Hn, axis=1)
    return H_mag, Hn, vert_area


def signed_mean_curvature(mesh: trimesh.Trimesh) -> tuple[np.ndarray, np.ndarray]:
    """Signed mean curvature + per-vertex barycentric area.

    Sign convention (calibrated on a synthetic convex sphere):
        H > 0  <=>  CONVEX   (surface bulges into ECS)
        H < 0  <=>  CONCAVE  (invagination)

    Calibration note: for meshes produced by `CellMesh.from_mask`
    (skimage.marching_cubes on a smoothed cell=1 / ECS=0 mask), trimesh's
    vertex_normals point INWARD (toward the cell interior). For a convex
    surface, the mean-curvature-normal vector Hn also points inward (toward
    the center of curvature), so dot(Hn, trimesh.normal) > 0. The sign
    below is chosen to make convex surfaces come out positive under this
    setup. `sphere_sign_check()` should always report convex_positive=True.
    """
    H_mag, Hn, vert_area = cotangent_mean_curvature(mesh)
    normals = np.asarray(mesh.vertex_normals)
    dot = np.sum(Hn * normals, axis=1)
    sign = np.sign(dot)
    sign[H_mag < 1e-12] = 0.0
    return sign * H_mag, vert_area


# ---------- Reference surface and roughness ----------

def _build_umbrella_laplacian(edges: np.ndarray, n_verts: int):
    """Build the sparse combinatorial Laplacian L = D - A where A is the
    adjacency matrix and D is the diagonal of vertex valences.

    L x = valence(i)*x_i - sum_{j in N(i)} x_j  (unnormalised form).
    Equivalent to D*(I - D^-1 A), so D^-1 L = I - D^-1 A = I - averaging.

    Returns L as scipy.sparse.csr_matrix (D is implicit in L's diagonal).
    """
    from scipy.sparse import coo_matrix, diags
    i = np.concatenate([edges[:, 0], edges[:, 1]])
    j = np.concatenate([edges[:, 1], edges[:, 0]])
    ones = np.ones_like(i, dtype=float)
    A = coo_matrix((ones, (i, j)), shape=(n_verts, n_verts)).tocsr()
    valence = np.asarray(A.sum(axis=1)).ravel()
    D = diags(valence)
    L = (D - A).tocsr()
    return L, valence


def smoothed_surface_deviation(
    mesh: trimesh.Trimesh,
    scale_nm: float,
    lamb: float = 0.5,
    max_iterations: int = 2000,
) -> tuple[np.ndarray, np.ndarray]:
    """Laplacian-smooth the mesh to a target spatial scale and return the
    per-vertex displacement from the original position.

    Sign convention for returned `signed_dev`:
        > 0  =>  protrusion (bulge into ECS)
        < 0  =>  indentation (pit)
        |.|  =>  unsigned roughness amplitude

    Implementation: explicit (random-walk) Laplacian iteration on vertex
    coordinates. Number of iterations needed to approximate Gaussian
    smoothing at scale sigma on a mesh with mean edge length h:

        N ~ sigma^2 / (2 * h^2 * lamb)

    Iterations are capped at `max_iterations`. When a cap kicks in, the
    effective smoothing scale is sqrt(max_iterations * 2 * h^2 * lamb) —
    downstream metrics should treat this case with care.

    Returns (signed_dev, smoothed_verts).
    """
    verts = np.asarray(mesh.vertices, dtype=float)
    edges = np.asarray(mesh.edges_unique)
    n = len(verts)
    if n == 0 or len(edges) == 0:
        return np.zeros(n), verts.copy()

    edge_vecs = verts[edges[:, 1]] - verts[edges[:, 0]]
    h = float(np.linalg.norm(edge_vecs, axis=1).mean())
    if h < 1e-9:
        return np.zeros(n), verts.copy()
    n_iter_requested = int(round(scale_nm ** 2 / (2.0 * h ** 2 * lamb)))
    n_iter = max(1, min(max_iterations, n_iter_requested))

    L, valence = _build_umbrella_laplacian(edges, n)
    # Random-walk operator: v_new = (1-lamb)*v + lamb * (D^-1 A) v
    # Equivalent to v - lamb * D^-1 L v.
    inv_val = 1.0 / np.maximum(valence, 1)
    smoothed = verts.copy()
    for _ in range(n_iter):
        Lv = L @ smoothed                       # shape (N, 3)
        smoothed = smoothed - lamb * inv_val[:, None] * Lv

    disp = verts - smoothed
    inward = np.asarray(mesh.vertex_normals)
    signed = -np.sum(disp * inward, axis=1)
    return signed.astype(float), smoothed


def local_plane_deviation(
    verts: np.ndarray,
    radius_nm: float,
    min_neighbors: int = 6,
) -> np.ndarray:
    """Legacy (slow) PCA-based deviation. Retained for comparison /
    validation. For production, prefer `smoothed_surface_deviation`,
    which is ~100x faster on typical meshes."""
    tree = cKDTree(verts)
    idxs = tree.query_ball_point(verts, r=radius_nm)
    dev = np.zeros(len(verts))
    for i, neigh in enumerate(idxs):
        if len(neigh) < min_neighbors:
            continue
        pts = verts[neigh]
        c = pts.mean(axis=0)
        Q = pts - c
        _, _, vt = np.linalg.svd(Q, full_matrices=False)
        n = vt[-1]
        dev[i] = float(np.dot(verts[i] - c, n))
    return dev


def rms_roughness(dev: np.ndarray, vert_area: np.ndarray | None = None) -> float:
    """Area-weighted RMS of a deviation field. If vert_area is None,
    returns the unweighted RMS."""
    if len(dev) == 0:
        return float("nan")
    if vert_area is None:
        return float(np.sqrt(np.mean(dev ** 2)))
    w = vert_area / vert_area.sum()
    return float(np.sqrt(np.sum(w * dev ** 2)))


# ---------- Feature detection ----------

def local_extrema_on_mesh(
    signal: np.ndarray,
    verts: np.ndarray,
    radius_nm: float,
    amplitude_threshold: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Find local maxima and minima of a vertex-valued signal within a
    physical radius.

    A vertex i is a local maximum if signal[i] >= signal[j] for all j
    within radius_nm and signal[i] > amplitude_threshold. Ties are broken
    by vertex index (lower index wins), so flat plateaus contribute at
    most one extremum.

    Returns (maxima_indices, minima_indices).
    """
    tree = cKDTree(verts)
    idxs = tree.query_ball_point(verts, r=radius_nm)
    maxima = []
    minima = []
    for i, neigh in enumerate(idxs):
        s_i = signal[i]
        if abs(s_i) < amplitude_threshold:
            continue
        neigh_signal = signal[neigh]
        if s_i > amplitude_threshold:
            # Strict max except ties broken by index
            if s_i > neigh_signal.max() - 1e-12:
                if all(i <= j for j in neigh if signal[j] == s_i):
                    maxima.append(i)
        elif s_i < -amplitude_threshold:
            if s_i < neigh_signal.min() + 1e-12:
                if all(i <= j for j in neigh if signal[j] == s_i):
                    minima.append(i)
    return np.array(maxima, dtype=int), np.array(minima, dtype=int)


# ---------- ECS-facing vertex classification ----------

def classify_ecs_facing_vertices(
    verts_nm: np.ndarray,
    voxel_size_nm: tuple[float, float, float],
    ecs_binary: np.ndarray,
    origin_nm: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> np.ndarray:
    """Boolean mask of vertices within 1 voxel of an ECS voxel."""
    vx = np.asarray(voxel_size_nm)
    origin = np.asarray(origin_nm)
    vi = np.round((verts_nm - origin) / vx).astype(int)
    shape = np.asarray(ecs_binary.shape)
    for d in range(3):
        vi[:, d] = np.clip(vi[:, d], 0, shape[d] - 1)
    hit = ecs_binary[vi[:, 0], vi[:, 1], vi[:, 2]].copy()
    for axis in range(3):
        for delta in (-1, +1):
            sh = vi.copy()
            sh[:, axis] = np.clip(sh[:, axis] + delta, 0, shape[axis] - 1)
            hit |= ecs_binary[sh[:, 0], sh[:, 1], sh[:, 2]]
    return hit


# ---------- Sign-convention calibration ----------

def sphere_sign_check(radius_nm: float = 400.0,
                      voxel_size_nm: float = 8.0,
                      sigma_nm: float = 16.0) -> dict:
    """Run the curvature pipeline on a synthetic solid sphere and report
    what sign the convex surface returns. The correct answer: convex ->
    positive H.

    If the returned median H is NEGATIVE, `signed_mean_curvature` needs to
    be called with `outward_sign=-1` everywhere downstream.

    Returns a diagnostic dict with median_H, fraction_positive, expected
    radius of curvature (== radius_nm), and measured radius (1 / |median H|).
    """
    margin_nm = 6 * sigma_nm + 2 * voxel_size_nm
    box_nm = 2 * (radius_nm + margin_nm)
    N = int(round(box_nm / voxel_size_nm))
    if N % 2 == 0:
        N += 1  # ensure center voxel exists
    ii = np.arange(N)
    zz, yy, xx = np.meshgrid(ii, ii, ii, indexing="ij")
    center = (N - 1) / 2.0
    r = np.sqrt((zz - center) ** 2 + (yy - center) ** 2 + (xx - center) ** 2) * voxel_size_nm
    mask = r < radius_nm

    vs = (voxel_size_nm, voxel_size_nm, voxel_size_nm)
    mesh = CellMesh.from_mask(mask, vs, sigma_nm=sigma_nm)
    if mesh is None:
        return {"ok": False, "error": "mesh extraction failed"}
    H, area = signed_mean_curvature(mesh.trimesh)
    med = float(np.median(H))
    frac_pos = float(np.mean(H > 0))
    measured_R = 1.0 / abs(med) if med != 0 else float("inf")
    return {
        "ok": True,
        "median_H_per_nm": med,
        "fraction_positive": frac_pos,
        "expected_radius_nm": radius_nm,
        "measured_radius_nm": measured_R,
        "convex_positive": med > 0,
    }
