# 2. Sources and modelling rules

A walkthrough is only useful if people can trust it. These rules keep it trustworthy.

## Sourced facts and assumptions

Write two lists at the top of every build script, and keep them current:

- **SOURCES:** what came from which document, for example "Wall positions: plan 1:50, page 2" or "Ceiling height:
  photo 4, measured against the 2.1 m door".
- **ASSUMPTIONS:** everything else, for example the floor-to-floor height, the window sills where no photo shows them,
  or the neighbouring buildings.

When someone gives new data, change the matching assumption and move it to SOURCES. Never change a sourced number to
make something fit. Find out why it doesn't fit.

## Getting numbers out of the sources

| Source | How to read it | Watch out for |
|---|---|---|
| Vector PDF plan | Read the wall rectangles from the vector paths (`pymupdf` or `pypdf` in a scratch venv). They beat hand-placed dimension comments. | Comment dimensions can be labelled "mm" when the values are metres. Hand-placed endpoints miss walls by 2–6 cm. |
| Raster plan (image) | Keep **plan pixels** in the tables and convert with `PX()`. Get the scale from the scale bar or a dimension line, and check it against two room areas. | Plans "not to scale". In that case take the user's room sizes over the map outline. |
| Room sizes from the owner | Use them as inner sizes and build the walls outward from them. | Confirm which room each size belongs to. |
| Listing or owner photos | Solve each camera from wall, window and door corners, then project floor points back. Phone main cameras are about 24–26 mm equivalent; portrait photos are 3:4. | One photo alone can put things 0.4 m off. Compare every position in two photos. |
| Product pages and spec sheets | Sizes of doors, pulls, beds and lamps. Write the page in SOURCES. | When a page gives no size, read it from the photo against a known size, and mark it as an assumption. |
| Developer renders | Exterior colours, window heights (measure against storey heights), the finish option shown | Renders show one interior option; pick it explicitly. |
| Material sheet | Floor, wall and kitchen finishes | Colours: convert sRGB to linear before you type them into Blender. |
| OpenStreetMap (Overpass) | Neighbour footprints, streets, trees, storey counts where they are mapped | Footprints can be smaller than real interiors. Rivers can be mapped as sea. Only a few buildings carry a roof shape. |
| National open data (elevation model, orthophoto, building register, laser scanning) | Terrain, roof heights, facade material, year of building | Check the licence (often CC BY 4.0) and the coverage first. |
| Street-level photos | Facade colours, by hand or projected per wall | Check the terms of use: some services forbid it. Mapillary has reconstruction-corrected positions; plain GPS positions can be 80 m off. |

## Coordinates

- Use one origin and one orientation for everything, for example the inner corner of the ground floor with
  +x along the main facade.
- Store the angle to true north (for example `NORTH_DEG = 15.0`) for the sun.
- Convert map data with a local flat projection around the origin's latitude and longitude, then rotate it into the
  model frame. Anchor it to a street corner or a facade line that you can see in the plan, not to the GPS centre.

## Modelling rules that pay off later

- **Data tables, not geometry code.** ROOMS, WALLS, WINDOWS and DOORS are tables, and the geometry code reads them.
  A change is a one-line edit (see `scripts/blender/build_template.py`).
- **One object per logical part.** For example "F1 walls", "Kitchen", "Door bathroom". The exporters tag, bevel and
  hide parts by name.
- **Prefix names by unit and floor**, for example "B F2 ...". A second unit can then reuse the same builders.
- **Door leaves are their own objects**, modelled closed, with a `door` property that gives the hinge and the angles.
- **No coplanar faces.** They render black in Cycles and flicker in real time.
- **Real thicknesses.** Walls 0.1–0.3 m, glass 6 mm, frames 50–60 mm, door leaves 40 mm. The light leaks at thin
  joints in Lumen.
- **Finishes as thin skins** on wall faces. Then one wall can carry tiles on one side and paint on the other.
- **Several furniture sets** can live in one file. For example, the owner's furniture next to the developer's set,
  hidden in Blender. The exporters tag them, and a key in Unreal swaps them.
- **Reusing shared helpers:** if several projects exec the same helper file, search the projects before you change a
  function signature.

## Assets

- **Textures:** ambientCG and Poly Haven (CC0). Use 1K–2K JPGs. Tiles must be powers of two, or Unreal makes no mips.
  A repeating knot or stain on a 60 cm grid shows at once. Build a larger tile from random strips of the scan (for
  example a 2.4 m board tile from 0.6 m scans, with knots kept on only 30 % of the boards).
- **Models:** Poly Haven (CC0) for plants, chairs and grass clumps. Blender's Human Base Meshes bundle (CC0) for a scale
  figure.
- **Product colours:** sample the colour from the product photo in sRGB, convert it to linear, and write the hex code
  and the source in a comment.
- **Third-party add-ons** may be blocked in automated sessions. Write your own small generators instead, such as a tree
  generator from L-system branches and leaf cards.

## The camera-matching check

Before you trust the model, render views that match the photos. Use the same lens and the same position, solved from
corners. Then put the photos and the renders side by side in one sheet (`compare_photos.jpg`). This finds wrong window
heights, a wrong ceiling and wrong furniture positions faster than any measuring.
