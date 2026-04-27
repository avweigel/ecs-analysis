# Paper Banana Prompts for Metric Diagrams

Use these as inputs at https://paper-banana.org/ to generate explanatory diagrams for each analysis metric.

---

## Metric 1: ECS Volume Fraction

**Description:**
A schematic diagram explaining how ECS volume fraction is computed from a 3D volume EM segmentation. Show a small 2D cross-section of tissue with cells (colored regions with distinct IDs) and extracellular space (ECS, white/light region between cells). Highlight that ECS voxels are counted vs total crop voxels. Include the formula: ECS% = (ECS voxels / total crop voxels) × 100. Use arrows or labels to indicate "Cell" and "ECS" regions. Keep the style clean and publication-ready with a simple color scheme.

**Relevant paper section:**
For each crop, the total number of voxels labeled as ECS and as cell (any nonzero instance ID) were counted directly from the segmentation arrays. ECS volume fraction was computed as: ECS% = (ECS voxels / total crop voxels) × 100. No spatial analysis was needed; this is a simple label count. Two label types were used: (1) a semantic binary ECS mask (0 = not ECS, 1 = ECS) and (2) an instance cell segmentation mask (0 = no cell, nonzero integer = cell ID).

**Caption:**
Schematic illustrating ECS volume fraction computation. Each voxel in the segmented volume is classified as either cell (colored) or extracellular space (ECS, white). The fraction of ECS voxels relative to total voxels gives the ECS volume percentage.

---

## Metric 2: ECS Channel Half-Width

**Description:**
A diagram explaining the Euclidean distance transform applied to the ECS mask. Show a 2D cross-section with two neighboring cells separated by a narrow ECS channel. Draw the distance transform as a gradient/heatmap within the ECS, with values increasing from the cell boundaries toward the center of the channel. Label the "half-width" as the distance from an ECS voxel to the nearest cell boundary. Show the 200 nm filtering threshold that removes large open spaces like vessel lumens. Include a small inset or side panel showing the distance transform concept: each ECS voxel gets a value equal to its distance to the nearest cell surface.

**Relevant paper section:**
A Euclidean distance transform was applied to the binary ECS mask for each crop, using cell voxels (any nonzero instance label) as the reference surface. Each ECS voxel received a value equal to its distance in nm to the nearest cell boundary. This gives the "half-width" of the ECS channel at that point — the distance from that ECS location to the nearest cell membrane. To remove contamination from vessel lumens, large intercellular pools, and other non-channel open spaces, values were filtered to <200 nm half-width.

**Caption:**
ECS channel half-width measurement via Euclidean distance transform. Each ECS voxel (colored by distance) receives a value equal to its distance to the nearest cell boundary. The half-width represents the local radius of the ECS channel. Values above 200 nm (open spaces, lumens) are filtered out to focus on intercellular channels.

---

## Metric 3: Per-Cell Surface-Area-to-Volume Ratio

**Description:**
A diagram showing how SA:V ratio is computed for individual cells using face-counting on a cubic voxel grid. Show a single cell as a cluster of voxels in 3D (or a simplified 2D projection). Highlight the boundary faces: color ECS-facing faces in one color (e.g., blue), cell-cell contact faces in another color (e.g., orange), and crop boundary faces in a third color (e.g., gray). Show that only ECS-facing surface area is used in the SA:V calculation. Include the concept that volume = voxel count × voxel volume. Include a small inset showing the "staircase effect" — how voxelized surfaces overestimate true surface area compared to a smooth surface.

**Relevant paper section:**
For each segmented cell (each unique nonzero ID in the instance segmentation), volume was computed as voxel count × voxel volume. Surface area was computed by face-counting on the cubic voxel grid: for each cell voxel, each of its 6 faces was checked. If the neighboring voxel was labeled as ECS, that face was counted as ECS-facing surface area. Faces abutting the crop boundary or other cells were counted separately. The SA:V ratio uses only ECS-facing surface area, in units of 1/nm.

**Caption:**
Per-cell surface-area-to-volume ratio computation via voxel face-counting. For each cell voxel, its six faces are classified as ECS-facing (blue), cell-cell contact (orange), or crop boundary (gray). Only ECS-facing surface area enters the SA:V calculation. Inset: the voxel staircase effect overestimates true surface area relative to the smooth biological membrane.

---

## Metric 4: Per-Cell Sphericity

**Description:**
A diagram illustrating the sphericity metric. Show three example shapes side by side: a perfect sphere (ψ = 1.0), a moderately elongated cell shape (ψ ≈ 0.5), and a highly irregular/branched cell (ψ ≈ 0.2). Label each with its sphericity value. Include the formula: ψ = π^(1/3) × (6V)^(2/3) / A, where V is volume and A is total surface area. Emphasize that sphericity uses total surface area (all faces), unlike SA:V which uses only ECS-facing faces.

**Relevant paper section:**
Sphericity was computed for each cell as: ψ = π^(1/3) (6V)^(2/3) / A, where V is cell volume and A is total surface area (all 6-connected faces, including cell-cell contacts and crop boundary faces). This ranges from 0 (highly non-spherical) to 1 (perfect sphere). Unlike SA:V, sphericity uses total surface area rather than ECS-facing surface area only.

**Caption:**
Sphericity quantifies how closely a cell's shape approximates a sphere. A perfect sphere has ψ = 1; increasingly irregular or elongated shapes approach ψ = 0. The metric uses total surface area (all voxel faces), providing a shape compactness measure independent of ECS exposure.

---

## Metric 5: Inter-Cell Gap Width (Voronoi Tessellation)

**Description:**
A diagram showing the Voronoi tessellation approach to measuring inter-cell gap widths. Show a 2D cross-section with several cells (colored regions). In the ECS between them, draw Voronoi boundaries (dashed lines) where each ECS voxel is assigned to its nearest cell. At the Voronoi boundary between two cells, show how the gap width is computed as the sum of distances from the boundary to each cell surface (d1 + d2). Use arrows to indicate the distance contributions from each cell. Show an example of a narrow gap and a wide gap for contrast.

**Relevant paper section:**
A Voronoi tessellation of the ECS was constructed by assigning each ECS voxel to its nearest cell (using the distance transform on the cell instance mask). At Voronoi boundaries — where two cells' territories meet — the gap width was computed as the sum of both cells' distance contributions (i.e., twice the distance transform value at the boundary, since each side contributes half the gap). For each crop, the median gap width was computed across all Voronoi boundary voxels. Contact fractions were also computed: at each threshold (10, 20, 40, 80, 160, 320 nm), the fraction of Voronoi boundary voxels with gap width below that threshold.

**Caption:**
Inter-cell gap width via Voronoi tessellation. Each ECS voxel is assigned to its nearest cell, creating Voronoi territories (colored regions). At territory boundaries (dashed lines), the gap width equals the sum of distances to each neighboring cell surface (d₁ + d₂), giving the full intercellular separation.

---

## Metric 7: Surface Curvature — Voxel-Based (Superseded)

**Description:**
A diagram explaining voxel-based mean curvature computation. Show a 2D cross-section of a cell boundary with the binary mask. Show the Gaussian smoothing step (σ = 16 nm) converting the sharp binary edge to a smooth gradient. Then show how mean curvature H is computed from the smoothed field using partial derivatives (level-set formula). Illustrate the sign convention: positive H (convex, surface bulging outward into ECS) and negative H (concave, invagination). Label surface voxels that are ECS-facing. Include a note that this method was superseded by the mesh-based approach.

**Relevant paper section:**
For each cell, a bounding box was extracted from the binary cell mask. The mask was converted to a float array and smoothed with a 3D Gaussian kernel with σ = 16 nm. Mean curvature H was computed at each surface voxel using the level-set formula. Surface voxels were identified as cell voxels with at least one non-cell neighbor. Only ECS-facing surface voxels were retained. Sign convention: positive H = convex (cell surface bulging outward into ECS); negative H = concave (invagination or wrapping around a neighbor).

**Caption:**
Voxel-based mean curvature computation. The binary cell mask is Gaussian-smoothed (σ = 16 nm), and mean curvature H is computed via the level-set formula on the smoothed field. Positive H indicates convex surfaces (bulging into ECS); negative H indicates concavities. Only ECS-facing surface voxels are analyzed. This method was superseded by the mesh-based approach (Metric 8).

---

## Metric 8: Surface Curvature — Mesh-Based

**Description:**
A diagram showing the mesh-based curvature pipeline. Show a three-step process: (1) Binary cell mask → (2) Marching cubes extracts a triangulated isosurface (show the mesh with triangular faces overlaid on the voxelized cell boundary) → (3) Mean curvature H computed at each vertex using the discrete Laplace-Beltrami operator. Color the mesh surface by curvature values (e.g., red for concave/negative H, blue for convex/positive H). Show the ECS-facing vertex selection step: only vertices whose nearest non-self label is ECS are retained. Include a comparison inset showing the smoother mesh surface vs the staircase voxel surface.

**Relevant paper section:**
For each cell, a triangulated isosurface was extracted from the binary cell mask using the marching cubes algorithm (scikit-image), with 1-voxel Gaussian pre-smoothing applied to the binary mask to regularize the surface. The resulting mesh was a set of vertices and triangular faces in physical coordinates (nm). Mean curvature H was computed at each mesh vertex using the discrete Laplace-Beltrami operator (trimesh library). To restrict analysis to ECS-facing surfaces, each mesh vertex was tested against the full segmentation volume: the nearest non-self voxel label was looked up, and only vertices where this label was ECS were retained.

**Caption:**
Mesh-based curvature analysis pipeline. (1) The binary cell mask is smoothed and converted to a triangulated isosurface via marching cubes. (2) Mean curvature is computed at each mesh vertex using the discrete Laplace-Beltrami operator. (3) Vertices are classified by their nearest non-self label; only ECS-facing vertices (not cell-cell contacts) are retained. Surface coloring indicates curvature: convex (positive H, blue) vs concave (negative H, red).
