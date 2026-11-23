"""
Read a raster floor plan in plan pixels: print the dark-pixel runs along rows and columns. One call gives wall
faces, window jambs and door openings; five or six calls cover a house. Pure Python (no PIL, no numpy).

  ffmpeg -i floorplan.png -pix_fmt gray plan.pgm
  python3 scripts/tools/plan_probe.py plan.pgm row=300:150-1100 col=480 [--threshold 110]

row=Y[:X0-X1]   runs along plan row Y (optionally only from X0 to X1)
col=X[:Y0-Y1]   runs along plan column X
Output: "row 300 [(201, 221), 330, (424, 509)]" = dark from x 201 to 221, a 1 px line at 330, ...
Keep the numbers as plan pixels in the build tables and convert with PX() (docs/02-sources-and-modeling.md).
"""
import sys


def read_pgm(path):
    data = open(path, "rb").read()
    head, pos = [], 0
    while len(head) < 4:                     # P5, width, height, maxval; comments allowed
        while data[pos:pos + 1].isspace():
            pos += 1
        if data[pos:pos + 1] == b"#":
            pos = data.index(b"\n", pos) + 1
            continue
        end = pos
        while not data[end:end + 1].isspace():
            end += 1
        head.append(data[pos:end])
        pos = end
    if head[0] != b"P5":
        sys.exit("expected a binary grey PGM (ffmpeg -i plan.png -pix_fmt gray plan.pgm)")
    w, h = int(head[1]), int(head[2])
    return w, h, data[pos + 1:pos + 1 + w * h]


def runs(values, offset, threshold):
    out, start = [], None
    for i, v in enumerate(values):
        if v < threshold and start is None:
            start = i
        if v >= threshold and start is not None:
            out.append((start + offset, i - 1 + offset))
            start = None
    if start is not None:
        out.append((start + offset, len(values) - 1 + offset))
    return [a if a == b else (a, b) for a, b in out]


def main():
    args = sys.argv[1:]
    threshold = 110
    if "--threshold" in args:
        i = args.index("--threshold")
        threshold = int(args[i + 1])
        del args[i:i + 2]
    w, h, px = read_pgm(args[0])
    for spec in args[1:]:
        kind, rest = spec.split("=")
        at, rng = rest.split(":") if ":" in rest else (rest, None)
        at = int(at)
        if kind == "row":
            lo, hi = map(int, rng.split("-")) if rng else (0, w - 1)
            hi = min(hi, w - 1)
            print("row", at, runs([px[at * w + x] for x in range(lo, hi + 1)], lo, threshold))
        else:
            lo, hi = map(int, rng.split("-")) if rng else (0, h - 1)
            hi = min(hi, h - 1)
            print("col", at, runs([px[y * w + at] for y in range(lo, hi + 1)], lo, threshold))


if __name__ == "__main__":
    main()
