# PulseCoder modifications (CARTESIAN MOD / DEDUPE MOD)

This fork adapts the AxiDraw Inkscape extension to drive a **standard Cartesian
pen plotter** (converted Genmitsu LC-60A frame, EiBotBoard v2.7, MOTOR1 = X axis
only, MOTOR2 = Y axis only) instead of AxiDraw's stock mixed-axis (CoreXY-like)
motion system, and adds automatic duplicate-line removal for CAD/SketchUp
exports. Every modified site is marked with a `CARTESIAN MOD` or `DEDUPE MOD`
comment — grep for those tags to find or re-apply the changes after an
upstream merge.

## Cartesian motor math (`CARTESIAN MOD`)

Stock AxiDraw converts each (x, y) move to motor steps as `motor1 = x + y`,
`motor2 = x − y`. On a Cartesian machine that renders every plot rotated 45°
and scaled by √2. These changes make `motor1 = x`, `motor2 = y`, controlled by
a **"Cartesian plotter (Motor 1 = X, Motor 2 = Y)" checkbox** in AxiDraw
Control (default on). Unchecked restores stock mixed-axis behavior exactly.

- `inkscape driver/motion.py` — forward transform + both step-rounding
  inverses in `compute_segment()`, gated on the `cartesian` option
  (module-level `CARTESIAN_MODE` is the fallback when no option is present).
- `inkscape driver/axidraw.py` — `walk_home`'s hardware step-readback inverse
  (note the Cartesian divisor is `2 × native_res_factor`, not the stock `4 ×`,
  which embeds the mixed-axis factor).
- `inkscape driver/axidraw_options/common_options.py` — `--cartesian` option.
- `inkscape driver/axidraw_control.py` — `'cartesian'` in the
  `selected_options` pass-through whitelist. **Any new option must be added to
  this whitelist** or the inner AxiDraw instance silently uses the conf
  default instead of the UI value.
- `inkscape driver/axidraw_conf.py` — `cartesian = True` default.
- `inkscape driver/axidraw.inx` — the checkbox.
- `cli/axicli/utils.py` — `'cartesian'` in `OPTION_NAMES` (CLI/config-file
  support; no CLI flag is defined because axicli's presence-only boolean
  flags cannot express false — set it in a config file instead).

## Duplicate-line removal (`DEDUPE MOD`)

CAD exports (SketchUp especially) write an edge shared by two faces once per
face, so the pen retraces identical lines. A new optimization pass removes any
segment that coincides with an already-plotted segment (either direction,
0.001″ tolerance), splitting paths so the pen lifts over the duplicate.
Exposed as **"Remove duplicate lines (CAD exports)"** (default on) in both
AxiDraw Control and the plob-export dialog.

- `inkscape driver/plot_optimizations.py` — new `dedupe(digest, tolerance)`.
- `inkscape driver/axidraw.py` — called in the digest-optimize block **after**
  `connect_nearby_ends` (before it, path joining bridges back over removed
  duplicates shorter than `min_gap`).
- `common_options.py` / `axidraw_control.py` whitelist / `axidraw_conf.py`
  (`dedupe`, `dedupe_tolerance`) / `axidraw.inx` / `axidraw_saveplob.inx` /
  `cli/axicli/utils.py` — option plumbing as above.

Caveats: intentional double-stroking (drawing a line twice for darker ink) is
removed too — untick the checkbox for such plots. Duplicates are only removed
within a layer, never across layers. Don't toggle the option between pausing
and resuming a plot.

## Install-tree steps not representable in this repo

The deployed Inkscape extension folder (Windows) needed two changes that live
outside this source tree:

1. The release bundle's top-level `axidraw_control.py` / `axidraw_naming.py`
   are PyInstaller launchers running frozen `build_deps/*.exe` binaries with
   pre-mod code embedded — they silently ignore all of the above. They must be
   replaced with source wrappers (pattern: `axidraw_svg_reorder.py`) that
   import `axidraw_deps/axidrawinternal` directly. The control wrapper must
   also pre-cache pyclipper (`from_dependency_import('pyclipper')`, guarded by
   try/except) because `clipping.py` imports it lazily at plot time, after
   `axidraw_deps` is off `sys.path`.
2. `axidraw_deps/` must vendor the packages the frozen exe used to embed:
   `serial` (pyserial), `tqdm`, `mpmath`, and `pyclipper` (win_amd64 pyds for
   cp310–cp313 coexist in one package dir; Python selects by ABI tag).

The deployed, physically-tested copy lives in the PulseCoder workspace at
`extensions/` (based on the 3.9.5/3.9.6 release bundle; this fork is 3.9.7 —
the mods were ported with anchors verified and the full preview/motor-step
test battery re-run against this tree).
