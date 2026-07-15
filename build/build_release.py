#!/usr/bin/env python3
"""
Build a ready-to-install Inkscape extension zip from this fork.

Adapted from `inkscape driver/public_build_materials/` (the official build),
with these differences:
  - Builds from THIS checkout (the official scripts re-clone upstream repos).
  - Pure-python source build only; no PyInstaller, so it runs anywhere and the
    output works on any OS whose Inkscape bundles Python 3.8+ (lxml comes from
    Inkscape itself and is deliberately NOT vendored -- a vendored
    platform-specific lxml would shadow Inkscape's working copy).
  - Vendors tqdm and pyclipper, which plot_status.py / clipping.py import but
    the official source build omits. pyclipper ships Windows pyds for
    cp310-cp313 side by side; Python selects the right one by ABI tag.
  - Patches the control wrapper to pre-cache pyclipper (clipping.py imports it
    lazily at plot time, after axidraw_deps is removed from sys.path).
  - Excludes axidraw_hatch.inx and hershey_axidraw.inx, whose backing scripts
    live in the separate EggBot / hershey-text repos.

Usage: python build/build_release.py --version v3.9.7-cartesian.1
Output: dist/axidraw-cartesian-<version>.zip  (contents go directly into
        Inkscape's user extensions directory)
"""
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DRIVER = REPO / 'inkscape driver'
WRAPPERS = DRIVER / 'public_build_materials' / 'wrappers'

# Pure-python dependencies, pinned to match the official requirements.txt /
# cli requirements where they specify versions.
PURE_DEPS = [
    'plotink==1.9.0',
    'ink-extensions==2.0.0',
    'pyserial==3.5',
    'tqdm==4.64.1',
    'mpmath==1.3.0',
    'requests==2.31.0',
    'urllib3==1.26.18',
    'idna==2.8',
    'charset-normalizer==3.2.0',
    'certifi==2023.7.22',
    'packaging==21.3',
]
PYCLIPPER = 'pyclipper==1.4.0'
PYCLIPPER_ABIS = ['310', '311', '312', '313']  # Inkscape 1.2 - 1.4+ bundled Pythons

EXCLUDED_INX = {'axidraw_hatch.inx', 'hershey_axidraw.inx'}

PYCLIPPER_PRECACHE = """
# CARTESIAN/DEDUPE MOD: pre-cache pyclipper into sys.modules.
# axidrawinternal/clipping.py imports it lazily at plot time (hidden-line
# removal option), after from_dependency_import has removed axidraw_deps from
# sys.path; without this, enabling that option crashes. The vendored binaries
# are Windows-only, so tolerate failure elsewhere.
try:
    from_dependency_import('pyclipper')
except ImportError:
    pass
"""

INSTALL_TXT = """AxiDraw for Inkscape -- PulseCoder Cartesian fork
====================================================

This build includes the CARTESIAN MOD (Motor 1 = X, Motor 2 = Y for standard
Cartesian plotters; toggleable in AxiDraw Control) and the DEDUPE MOD
(duplicate-line removal for CAD/SketchUp exports). See CARTESIAN-MODS.md.

Install:
1. Open Inkscape. Edit > Preferences > System, find "User extensions"
   (e.g. %APPDATA%\\inkscape\\extensions on Windows).
2. Extract the CONTENTS of this zip directly into that directory (the .inx
   files must sit at the top level of the extensions directory).
3. Restart Inkscape. The extensions appear under Extensions > AxiDraw.

Notes:
- Requires Inkscape 1.2 or newer (bundled Python 3.10-3.13; lxml is provided
  by Inkscape and intentionally not included here).
- "Hidden-line removal" uses bundled Windows pyclipper binaries; on other
  platforms install pyclipper into Inkscape's Python to use that one option.
- The Hatch fill and Hershey Text extensions are not included in this build.
"""


def run(*cmd):
    subprocess.run(list(cmd), check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    version = args.version

    dist = REPO / 'dist'
    build = dist / 'axidraw_for_inkscape_build'
    wheels = dist / 'wheels'
    shutil.rmtree(dist, ignore_errors=True)
    build.mkdir(parents=True)
    wheels.mkdir()
    deps = build / 'axidraw_deps'

    print('== Installing pure-python dependencies into axidraw_deps')
    run(sys.executable, '-m', 'pip', 'install', '-q', '--no-deps',
        '--target', str(deps), *PURE_DEPS)
    for junk in ['bin', '__pycache__']:
        shutil.rmtree(deps / junk, ignore_errors=True)
    (deps / '__init__.py').touch()

    print('== Vendoring pyclipper (win_amd64, multi-ABI)')
    for abi in PYCLIPPER_ABIS:
        run(sys.executable, '-m', 'pip', 'download', '-q', '--no-deps',
            '--platform', 'win_amd64', '--python-version', abi,
            '--only-binary=:all:', '-d', str(wheels), PYCLIPPER)
    whl_files = sorted(wheels.glob('pyclipper-*.whl'))
    assert len(whl_files) == len(PYCLIPPER_ABIS), whl_files
    for i, whl in enumerate(whl_files):
        with zipfile.ZipFile(whl) as zf:
            for name in zf.namelist():
                if not name.startswith('pyclipper/'):
                    continue
                # full package from the first wheel; only the ABI-tagged
                # binary from the rest
                if i == 0 or '_pyclipper' in name:
                    zf.extract(name, deps)
    assert (deps / 'pyclipper' / '__init__.py').exists()

    print('== Copying axidrawinternal from local checkout')
    shutil.copytree(
        DRIVER, deps / 'axidrawinternal',
        ignore=shutil.ignore_patterns(
            '*.inx', 'public_build_materials', '__pycache__', 'tests'))

    print('== Copying .inx files, conf, and wrappers to the root')
    for inx in sorted(DRIVER.glob('*.inx')):
        if inx.name not in EXCLUDED_INX:
            shutil.copy(inx, build)
    shutil.copy(DRIVER / 'axidraw_conf.py', build)
    for wrapper in sorted(WRAPPERS.glob('*.py')):
        shutil.copy(wrapper, build)
    shutil.copy(deps / 'plotink' / 'plot_utils_import.py', build)

    print('== Patching control wrapper: pyclipper pre-cache')
    control = build / 'axidraw_control.py'
    text = control.read_text()
    anchor = "message = from_dependency_import('ink_extensions_utils.message')"
    assert text.count(anchor) == 1, 'wrapper anchor not found'
    control.write_text(text.replace(anchor, anchor + '\n' + PYCLIPPER_PRECACHE))

    print('== Adding docs')
    (build / 'INSTALL.txt').write_text(INSTALL_TXT)
    shutil.copy(REPO / 'CARTESIAN-MODS.md', build)

    # Sanity checks: files the extension cannot run without.
    for required in ['axidraw.inx', 'axidraw_control.py', 'axidraw_conf.py',
                     'plot_utils_import.py', 'axidraw_deps/axidrawinternal/motion.py',
                     'axidraw_deps/serial/__init__.py', 'axidraw_deps/tqdm/__init__.py',
                     'axidraw_deps/mpmath/__init__.py',
                     'axidraw_deps/ink_extensions_utils/exit_status.py']:
        assert (build / required).exists(), f'missing from build: {required}'
    assert 'CARTESIAN MOD' in (deps / 'axidrawinternal' / 'motion.py').read_text()

    print('== Zipping')
    out = dist / f'axidraw-cartesian-{version}.zip'
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(build.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts:
                zf.write(path, path.relative_to(build))
    print(f'DONE: {out} ({out.stat().st_size // 1024} KiB)')


if __name__ == '__main__':
    main()
