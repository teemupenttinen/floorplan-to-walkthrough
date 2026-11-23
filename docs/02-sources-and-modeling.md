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
| Raster plan (image) | Keep **plan pixels** in the tables and convert with `PX()`. Get the scale from the scale bar or a dimension line, and check it against two room areas. Read positions with `scripts/tools/plan_probe.py` (dark runs along a row or column: wall faces, jambs, door gaps in one call); check the result with `scripts/blender/plan_overlay.py`. | Plans "not to scale". In that case take the user's room sizes over the map outline. |
| Room sizes from the owner | Use them as inner sizes and build the walls outward from them. | Confirm which room each size belongs to. |
| Listing or owner photos | Solve each camera from wall, window and door corners, then project floor points back. Phone main cameras are about 24–26 mm equivalent; portrait photos are 3:4. | One photo alone can put things 0.4 m off. Compare every position in two photos. |
| Product pages and spec sheets | Sizes of doors, pulls, beds and lamps. Write the page in SOURCES. | When a page gives no size, read it from the photo against a known size, and mark it as an assumption. |
| Developer renders | Exterior colours, window heights (measure against storey heights), the finish option shown | Renders show one interior option; pick it explicitly. |
| Material sheet | Floor, wall and kitchen finishes | Colours: convert sRGB to linear before you type them into Blender. |
| OpenStreetMap (Overpass) | Neighbour footprints, streets, trees, storey counts where they are mapped | Footprints can be smaller than real interiors. Rivers can be mapped as sea. Only a few buildings carry a roof shape. |
| National open data (elevation model, orthophoto, building register, laser scanning) | Terrain, roof heights, facade material, year of building | Check the licence (often CC BY 4.0) and the coverage first. |
| Street-level photos | Facade colours, by hand or projected per wall | Check the terms of use: some services forbid it. Mapillary has reconstruction-corrected positions; plain GPS positions can be 80 m off. |

### Finnish plans and listings

Codes on Finnish floor plans (dimensions in decimetre modules):

| Code | Meaning |
|---|---|
| `19x30` at a window | window 1.9 m wide × 3.0 m high (here floor to ceiling) |
| `UO10x23` | exterior door (ulko-ovi) 1.0 × 2.3 m |
| `YI16x7` | transom window above a door (yläikkuna) 1.6 × 0.7 m |
| `O9`, `LIO9`, `LO8` | interior door 0.9 m, sliding door 0.9 m, glass (sauna) door 0.8 m |
| `ST/RK` dash-dot line | roof outline; the north arrow letter is `P` (pohjoinen) |
| MH, ET, AET, KT / RT / OH | bedroom, hall, everyday (back) entrance, kitchen / dining / living |
| KPH, LH, KHH, VH, VAR, TEKN, WC | bathroom, sauna, utility, walk-in closet, storage, technical room, toilet |

Room areas are written in each room. Check the traced rectangles against them (±0.2 m² validates the scale).

On a common Finnish listing site, the gallery JSON in the page source tags the plan image (`"tags":["ai_floorplan"]`). Every image is
served as **WebP**, even when the URL says `format(jpeg)` and the file is saved as `.jpg`: convert with ffmpeg before
any tool that trusts the extension. The listing text gives ceiling height, window type, floor and kitchen materials
and the terrace orientation.

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
- **Door leaves are their own objects**, with a `door` property that gives the hinge and the angles (radians; see
  docs/00-interfaces.md). Model them closed, or open with `"baked"` set when the light-map bake should see through.
- **No coplanar faces.** They render black in Cycles and flicker in real time.
- **Real thicknesses.** Walls 0.1–0.3 m, glass 6 mm, frames 50–60 mm, door leaves 40 mm. The light leaks at thin
  joints in Lumen.
- **Finishes as thin skins** on wall faces. Then one wall can carry tiles on one side and paint on the other.
  A post-pass without extra geometry also works: bisect the wall mesh at the finished rooms' edges, then give each
  vertical face the finish of the room in front of it (a partition face often spans two rooms).
- **Don't assume one wall colour.** Listing rooms are often painted: greige bedrooms, a darker accent wall, white
  kitchens. Measure each wall against the white ceiling in the same photo (wall / ceiling mean colour: exposure and
  white balance cancel); a clearly warmer or darker ratio is a real paint colour.
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
- **Textures graded to the photos:** `scripts/textures/make_textures.py` recolours scans to the mean colour of a photo
  patch (corrected by a known white in the same photo), turns boards vertical, draws tile joints and builds a plank
  floor from a wood scan, from a JSON recipe table (`recipes.example.json`). Grade for the renderer you show: the same
  image reads about 10 % more yellow and saturated under Unreal's filmic tone map than under three.js Neutral.
- **ambientCG downloads** are named `<Set>_1K-JPG_Color.jpg`; `mat_tex()` finds both that and `<Set>_Color.jpg`. The
  zips also hold `.blend`, `.usdc` and `.mtlx` files: delete them unread (`find -delete`, not a shell glob).
- **Third-party add-ons** may be blocked in automated sessions. Write your own small generators instead, such as a tree
  generator from L-system branches and leaf cards.

## The plan overlay check

Before any photo matching: `scripts/blender/plan_overlay.py` cuts the model at 1 m like a plan section, renders it from
above at plan-pixel scale and blends it over the plan (under a second). Every misplaced wall, window and door shows at
once.

## The camera-matching check

Before you trust the model, render views that match the photos. Use the same lens and the same position, solved from
corners. Then put the photos and the renders side by side in one sheet (`compare_photos.jpg`). This finds wrong window
heights, a wrong ceiling and wrong furniture positions faster than any measuring. In Unreal the same check is one
script round (docs/04-unreal.md, "The photo-matching loop").
