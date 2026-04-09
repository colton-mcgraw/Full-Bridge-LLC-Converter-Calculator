# Full-Bridge LLC Quick Calculator

Desktop calculator for fast, first-pass full-bridge LLC design exploration.

It is intended for interactive what-if work: adjust one value and review immediate changes in operating point, feasibility, thermal estimate, and output filter recommendations.

## Highlights

- Live recalculation for core LLC inputs (`Vin`, `Vout`, `Pout`, `Np`, `Ns`, `Lr`, `Cr`, `Lm`, `Fs`)
- Topology-aware secondary handling (`center-tap` and `full-bridge`)
- Built-in feasibility checks with explicit invalid/warning reasons
- FHA gain chart and thermal/efficiency chart
- Simplified power-stage schematic and stage-voltage profile visualization
- Output capacitor sizing with topology-aware ripple frequency basis (`fr` for full-bridge secondary, `2fr` for center-tap)
- ESR-based capacitor constraints and optional capacitor CSV-based pass/fail recommendation
- Coilcraft SER-based inductor recommendation support
- CSV snapshot export

## Run Locally

```powershell
python llc_calc.py
```

## Build Portable Executable (Windows)

One-file executable via PyInstaller:

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --windowed --onefile --name FB-LLC-Calc --icon assets/icon.ico --add-data "Power Inductors.csv;." llc_calc.py
```

Output:

- `dist/FB-LLC-Calc.exe`

Packaging notes:

- `Power Inductors.csv` is bundled into the executable.
- App icon is loaded from `assets/icon.ico`.

## CI Artifact Builds (All OS)

Workflow:

- `.github/workflows/build-artifacts.yml`

Behavior:

- Builds one-file artifacts on `windows-latest`, `ubuntu-latest`, and `macos-latest`
- Uploads build outputs as GitHub Actions artifacts

Triggers:

- Push to `main` or `master`
- Pull requests
- Manual `workflow_dispatch`

## Automated Releases (Tag-Driven)

Workflow:

- `.github/workflows/release.yml`

Behavior:

- Runs on tags matching `v*`
- Builds binaries for Windows, Linux, and macOS
- Publishes those files as GitHub Release assets
- Uses `VERSION` and matching `CHANGELOG.md` section for release naming/body

Version gate:

- Tag must match `VERSION` exactly (for example: `VERSION=1.2.3` requires tag `v1.2.3`)

Typical release flow:

1. Update `VERSION`
2. Add release notes under matching version section in `CHANGELOG.md`
3. Commit and push
4. Tag and push (example: `git tag v1.2.3` and `git push origin v1.2.3`)
5. Download binaries from the GitHub Release page

## Project Metadata

- Version file: `VERSION.txt`
- Changelog: `CHANGELOG.md`
- License: `LICENSE` (GNU GPL v3)

`VERSION.txt` format:

- `VERSION=x.y.z` (example: `VERSION=1.2.3`)

## Engineering Notes

- Intended for first-pass trend analysis, not final magnetic/thermal sign-off.
- FHA and thermal results are simplified estimates and should be validated in detailed design tools.
- Catalog recommendations are convenience filters and should be verified against current datasheets.
