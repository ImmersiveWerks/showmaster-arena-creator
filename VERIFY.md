# How to verify a download

The program is built by GitHub, not on anyone's PC. You can check that a file you downloaded
is exactly what this public source code produces.

## 1. Where the files come from

Every file on the Releases page is made by the workflow [`.github/workflows/release.yml`](.github/workflows/release.yml)
on a fresh GitHub Windows machine, from the tagged source. Open the **Actions** tab to see the full,
public log of each build: which packages were installed (exact versions in
[`packaging/requirements-build.txt`](packaging/requirements-build.txt)), which cobra-tools commit was
used, and every build step.

## 2. Check the signature of the build (recommended)

Each release file has a signed build provenance (GitHub artifact attestation). With the
[GitHub CLI](https://cli.github.com/):

```
gh attestation verify ShowMaster_Arena_Creator_Setup_<version>.exe --repo ImmersiveWerks/showmaster-arena-creator
```

It confirms that the file was built by this repository's workflow, from which commit, and that
it was not changed afterwards.

## 3. Check the checksum

Each release has a `SHA256SUMS.txt`. In PowerShell:

```
Get-FileHash .\ShowMaster_Arena_Creator_Setup_<version>.exe -Algorithm SHA256
```

The value must match the line in `SHA256SUMS.txt`.

## 4. Build it yourself

See *Run from source* in the [README](README.md). The program contains no code that is not in this
repository, apart from the open-source packages listed in [THIRD_PARTY.md](THIRD_PARTY.md).

## cobra-tools

cobra-tools is included in the program unmodified: the build downloads commit `2dd9d14` from
`github.com/OpenNaja/cobra-tools` (see `COBRA_COMMIT` in `packaging/build_exe.py`) and copies it as it is.
The program itself makes no internet connections.

## Why antivirus programs sometimes warn

The program is not code-signed (a certificate costs money every year), and programs packed with
PyInstaller are sometimes flagged by heuristics. If a scanner warns, please check the attestation
above, and report the false positive to the scanner's vendor.
