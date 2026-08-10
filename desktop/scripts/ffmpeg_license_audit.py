#!/usr/bin/env python3
"""Shared FFmpeg license audit for desktop/scripts/build-sidecar.{sh,ps1}.

Single source of truth for classification order (NONFREE first → fail),
provenance (resolver package version, platform zip URL/revision), hashes,
and release gate (license text + corresponding source/source-offer).

Usage (from repo root):
  uv run python desktop/scripts/ffmpeg_license_audit.py resolve
  uv run python desktop/scripts/ffmpeg_license_audit.py write-manifest \\
      --mode both --dist desktop/pyinstaller/dist
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as im
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Repo-root relative paths
ROOT = Path(__file__).resolve().parents[2]
PYI_DIR = ROOT / "desktop" / "pyinstaller"
NOTICES_SRC = ROOT / "desktop" / "third_party" / "ffmpeg"
RESOLVE_JSON = PYI_DIR / "_ffmpeg_resolve.json"
FFMPEG_PATH_FILE = PYI_DIR / "_ffmpeg.path"
FFPROBE_PATH_FILE = PYI_DIR / "_ffprobe.path"

# Build recipe for static-ffmpeg prebuilt binaries (not corresponding source by itself).
BUILD_RECIPE_URL = "https://github.com/zackees/ffmpeg_bins"
# Official FFmpeg release tarball template — corresponding source for the version line.
FFMPEG_SOURCE_TARBALL_TMPL = "https://ffmpeg.org/releases/ffmpeg-{version}.tar.xz"


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify_configuration(configuration: str) -> str:
    """Classify ffmpeg configure flags into a concrete license kind.

    Order is intentional and must not drift between shells:
    1. --enable-nonfree → NONFREE (unconditional reject by callers)
    2. --enable-gpl (and not --disable-gpl):
       - + --enable-version3 → GPLv3
       - else → GPLv2
    3. else (LGPL family):
       - + --enable-version3 → LGPLv3
       - else → LGPLv2.1
    """
    cfg_l = (configuration or "").lower()
    if re.search(r"--enable-nonfree\b", cfg_l):
        return "NONFREE"
    version3 = bool(re.search(r"--enable-version3\b", cfg_l))
    gpl = bool(
        re.search(r"--enable-gpl\b", cfg_l) and not re.search(r"--disable-gpl\b", cfg_l)
    )
    if gpl:
        return "GPLv3" if version3 else "GPLv2"
    return "LGPLv3" if version3 else "LGPLv2.1"


def parse_ffmpeg_version(path: str) -> tuple[str, str]:
    try:
        proc = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError as e:
        print(f"ERROR: cannot execute ffmpeg for audit: {e}", file=sys.stderr)
        sys.exit(1)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if "ffmpeg version" not in text.lower() and "version" not in text.lower():
        print(f"ERROR: ffmpeg -version failed (code={proc.returncode})", file=sys.stderr)
        print(text[:2000], file=sys.stderr)
        sys.exit(1)
    version_line = ""
    configuration = ""
    for line in text.splitlines():
        ls = line.strip()
        if not version_line and ls.lower().startswith("ffmpeg version"):
            version_line = ls
        if ls.lower().startswith("configuration:"):
            configuration = ls.split(":", 1)[1].strip() if ":" in ls else ls
    if not version_line:
        print("ERROR: could not parse ffmpeg version line", file=sys.stderr)
        print(text[:2000], file=sys.stderr)
        sys.exit(1)
    if not configuration:
        print(
            "ERROR: could not parse ffmpeg configuration — cannot audit license",
            file=sys.stderr,
        )
        print(text[:2000], file=sys.stderr)
        sys.exit(1)
    return version_line, configuration


def parse_ffmpeg_version_number(version_line: str) -> str | None:
    """Extract numeric version from `ffmpeg -version` first line (e.g. n6.1 → 6.1)."""
    m = re.search(
        r"ffmpeg version\s+n?(\d+\.\d+(?:\.\d+)?)",
        version_line or "",
        re.IGNORECASE,
    )
    return m.group(1) if m else None


def corresponding_source_url_for_version(version_line: str) -> str | None:
    """Official FFmpeg source tarball URL matching the binary version line."""
    ver = parse_ffmpeg_version_number(version_line)
    if not ver:
        return None
    return FFMPEG_SOURCE_TARBALL_TMPL.format(version=ver)


def is_platform_binary_zip_url(url: str | None) -> bool:
    """True if URL looks like a static-ffmpeg / ffmpeg_bins prebuilt binary ZIP."""
    if not url:
        return False
    u = url.strip()
    # Platform zips: .../v8.0/linux.zip, .../win32.zip, etc.
    if re.search(r"/v[\d.]+/[^/]+\.zip(?:\?|$)", u, re.IGNORECASE):
        return True
    if re.search(
        r"/(?:linux|macos|darwin|win(?:dows|32|64)?|osx)[^/]*\.zip(?:\?|$)",
        u,
        re.IGNORECASE,
    ):
        return True
    if "ffmpeg_bins" in u.lower() and u.lower().endswith(".zip"):
        return True
    return False


def validate_corresponding_source(
    binary_download_url: str | None,
    corresponding_source_url: str | None,
) -> str | None:
    """Return error message if corresponding source is missing/invalid, else None."""
    if not corresponding_source_url:
        return "corresponding_source_url missing"
    if binary_download_url and corresponding_source_url == binary_download_url:
        return "corresponding_source_url must differ from binary_download_url"
    if is_platform_binary_zip_url(corresponding_source_url):
        return "corresponding_source_url must not be a platform binary ZIP"
    # Source must look like an archive or known source host — not a binary zip.
    cs = corresponding_source_url.lower()
    if cs.endswith(".zip") and "ffmpeg.org" not in cs:
        return "corresponding_source_url looks like a binary ZIP, not source"
    return None


def _static_ffmpeg_provenance() -> dict:
    """Resolver package version + platform zip URL/revision from static_ffmpeg."""
    try:
        pkg_version = im.version("static-ffmpeg")
    except im.PackageNotFoundError:
        pkg_version = None
    binary_download_url = None
    platform_key = None
    revision = None
    try:
        import static_ffmpeg.run as sfr

        platform_key = sfr.get_platform_key()
        binary_download_url = sfr.get_platform_http_zip()
        # URLs look like .../raw/main/v8.0/linux.zip → revision "v8.0"
        if binary_download_url:
            m = re.search(r"/(v[\d.]+)/[^/]+\.zip", binary_download_url)
            if m:
                revision = m.group(1)
            else:
                # fallback: last two path parts
                parts = binary_download_url.rstrip("/").split("/")
                if len(parts) >= 2:
                    revision = parts[-2]
    except Exception as e:  # noqa: BLE001 — provenance best-effort then gate
        print(f"ERROR: cannot resolve static_ffmpeg provenance: {e}", file=sys.stderr)
        sys.exit(1)
    return {
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": pkg_version,
        "platform_key": platform_key,
        # Binary ZIP only — NOT corresponding source.
        "binary_download_url": binary_download_url,
        # Backward-compat alias (same as binary ZIP; never treat as source).
        "download_url": binary_download_url,
        "download_revision": revision,
        "build_recipe_url": BUILD_RECIPE_URL,
    }


# Map classify_configuration() output → list of bundled COPYING.* filenames.
# LGPLv3 incorporates GPLv3 (additional permissions on GPLv3) → stage both.
_LICENSE_FILE_MAP: dict[str, list[str]] = {
    "GPLv2": ["COPYING.GPLv2"],
    "GPLv3": ["COPYING.GPLv3"],
    "LGPLv2.1": ["COPYING.LGPLv2.1"],  # independent license; no GPL text required
    "LGPLv3": ["COPYING.LGPLv3", "COPYING.GPLv3"],
    # Backward-compat aliases if older resolve meta still says GPL/LGPL.
    "GPL": ["COPYING.GPLv3"],
    "LGPL": ["COPYING.LGPLv2.1"],
}


def license_files_for_kind(license_kind: str) -> list[str] | None:
    """Return the COPYING.* file list for a license kind, or None if unknown."""
    files = _LICENSE_FILE_MAP.get(license_kind)
    return list(files) if files else None


def stage_license_artifacts(
    out_dir: Path,
    license_kind: str,
    meta: dict,
) -> dict:
    """Copy license text(s) + write SOURCE_OFFER matched to binary hashes. Fail if missing."""
    notices = out_dir / "ffmpeg-notices"
    notices.mkdir(parents=True, exist_ok=True)

    license_names = license_files_for_kind(license_kind)
    if not license_names:
        print(
            f"ERROR: unknown ffmpeg license kind for staging: {license_kind!r}",
            file=sys.stderr,
        )
        sys.exit(1)

    license_sha_map: dict[str, str] = {}
    for license_name in license_names:
        src_license = NOTICES_SRC / license_name
        if not src_license.is_file():
            print(f"ERROR: missing bundled license text: {src_license}", file=sys.stderr)
            sys.exit(1)
        dest_license = notices / license_name
        dest_license.write_bytes(src_license.read_bytes())
        license_sha_map[license_name] = sha256_file(dest_license)

    binary_url = meta.get("binary_download_url") or meta.get("download_url")
    source_url = meta.get("corresponding_source_url")
    if not source_url:
        source_url = corresponding_source_url_for_version(
            str(meta.get("ffmpeg_version_line") or "")
        )
    build_recipe = meta.get("build_recipe_url") or BUILD_RECIPE_URL

    err = validate_corresponding_source(binary_url, source_url)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)

    license_list = ", ".join(license_names)
    offer_body = (
        "Corresponding Source Offer — FFmpeg binaries bundled with ViTranscript\n"
        "======================================================================\n\n"
        f"ffmpeg_license: {license_kind}\n"
        f"license_files: {license_list}\n"
        f"ffmpeg_version_line: {meta.get('ffmpeg_version_line')}\n"
        f"ffmpeg_sha256: {meta.get('ffmpeg_sha256')}\n"
        f"ffprobe_sha256: {meta.get('ffprobe_sha256')}\n"
        f"ffmpeg_configuration: {meta.get('ffmpeg_configuration')}\n\n"
        f"Resolver package: {meta.get('resolver_package')}"
        f"=={meta.get('resolver_package_version')}\n"
        f"Platform key: {meta.get('platform_key')}\n"
        f"binary_download_url (prebuilt ZIP — NOT corresponding source):\n"
        f"  {binary_url}\n"
        f"Download revision: {meta.get('download_revision')}\n\n"
        f"corresponding_source_url (FFmpeg source tarball for this version):\n"
        f"  {source_url}\n"
        f"build_recipe_url (static build scripts/config for the prebuilt binaries):\n"
        f"  {build_recipe}\n\n"
        "Written offer: the prebuilt ffmpeg/ffprobe binaries (hashed above) were\n"
        "obtained from binary_download_url. Corresponding source is the official\n"
        "FFmpeg release tarball at corresponding_source_url (version pinned to the\n"
        "ffmpeg_version_line) together with the build recipe/config in the\n"
        "ffmpeg_bins repository (build_recipe_url). The binary ZIP is NOT\n"
        "corresponding source under GPL/LGPL.\n\n"
        "Releasers must keep this offer next to the published sidecar artifact.\n"
        "Final compliance sign-off is required before public release.\n"
    )
    offer_path = notices / "SOURCE_OFFER.txt"
    offer_path.write_text(offer_body, encoding="utf-8")
    offer_sha = sha256_file(offer_path)

    # Also stage a short README for humans
    readme = notices / "README.txt"
    readme.write_text(
        f"FFmpeg/FFprobe license={license_kind}. "
        f"See {license_list} and SOURCE_OFFER.txt.\n"
        "Compliance sign-off required before public release.\n",
        encoding="utf-8",
    )

    try:
        notices_dir = str(notices.relative_to(ROOT))
    except ValueError:
        notices_dir = str(notices)
    return {
        "notices_dir": notices_dir,
        # Primary file (first) kept for backward-compat consumers.
        "license_file": license_names[0],
        "license_files": license_names,
        "license_sha256": license_sha_map[license_names[0]],
        "license_sha256_map": license_sha_map,
        "source_offer_file": "SOURCE_OFFER.txt",
        "source_offer_sha256": offer_sha,
        "binary_download_url": binary_url,
        "corresponding_source_url": source_url,
        "build_recipe_url": build_recipe,
    }


def cmd_resolve(_args: argparse.Namespace) -> int:
    import static_ffmpeg.run as sfr

    PYI_DIR.mkdir(parents=True, exist_ok=True)
    ff, fp = sfr.get_or_fetch_platform_executables_else_raise()
    version_line, configuration = parse_ffmpeg_version(ff)
    license_kind = classify_configuration(configuration)
    if license_kind == "NONFREE":
        print(
            "ERROR: ffmpeg build is NONFREE (--enable-nonfree) — cannot distribute",
            file=sys.stderr,
        )
        sys.exit(1)

    prov = _static_ffmpeg_provenance()
    source_url = corresponding_source_url_for_version(version_line)
    err = validate_corresponding_source(prov.get("binary_download_url"), source_url)
    if err:
        print(f"ERROR: cannot form corresponding source offer: {err}", file=sys.stderr)
        sys.exit(1)

    meta = {
        "ffmpeg_basename": Path(ff).name,
        "ffprobe_basename": Path(fp).name,
        "ffmpeg_path": ff,
        "ffprobe_path": fp,
        "ffmpeg_sha256": sha256_file(ff),
        "ffprobe_sha256": sha256_file(fp),
        "ffmpeg_version_line": version_line,
        "ffmpeg_configuration": configuration,
        "ffmpeg_license": license_kind,
        "source_package": (
            f"{prov['resolver_package']}=={prov['resolver_package_version']}"
            if prov.get("resolver_package_version")
            else prov["resolver_package"]
        ),
        **prov,
        "corresponding_source_url": source_url,
        "os": platform.system(),
        "arch": platform.machine(),
        "python": sys.version.split()[0],
    }
    # Stage notices next to resolve artifacts (also re-staged into dist later)
    stage_info = stage_license_artifacts(PYI_DIR, license_kind, meta)
    meta["license_artifacts"] = stage_info

    RESOLVE_JSON.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    FFMPEG_PATH_FILE.write_text(ff, encoding="utf-8")
    FFPROBE_PATH_FILE.write_text(fp, encoding="utf-8")

    print("OK resolved ffmpeg", ff, file=sys.stderr)
    print("OK resolved ffprobe", fp, file=sys.stderr)
    print("OK ffmpeg license=", license_kind, file=sys.stderr)
    print("OK", version_line, file=sys.stderr)
    print("OK binary_download_url=", prov.get("binary_download_url"), file=sys.stderr)
    print("OK corresponding_source_url=", source_url, file=sys.stderr)
    # stdout: paths for shells that want them
    print(ff)
    print(fp)
    return 0


def _sha_entry(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def cmd_write_manifest(args: argparse.Namespace) -> int:
    dist = Path(args.dist)
    dist.mkdir(parents=True, exist_ok=True)
    if not RESOLVE_JSON.is_file():
        print("ERROR: missing _ffmpeg_resolve.json — run resolve first", file=sys.stderr)
        sys.exit(1)
    ff_meta = json.loads(RESOLVE_JSON.read_text(encoding="utf-8"))
    for key in (
        "ffmpeg_license",
        "ffmpeg_version_line",
        "ffmpeg_configuration",
        "ffmpeg_sha256",
        "ffprobe_sha256",
        "resolver_package_version",
    ):
        if not ff_meta.get(key):
            print(f"ERROR: incomplete ffmpeg audit field: {key}", file=sys.stderr)
            sys.exit(1)

    binary_url = ff_meta.get("binary_download_url") or ff_meta.get("download_url")
    if not binary_url:
        print("ERROR: incomplete ffmpeg audit field: binary_download_url", file=sys.stderr)
        sys.exit(1)
    ff_meta["binary_download_url"] = binary_url
    # Ensure corresponding_source_url is set (recompute from version if missing).
    source_url = ff_meta.get("corresponding_source_url") or corresponding_source_url_for_version(
        str(ff_meta.get("ffmpeg_version_line") or "")
    )
    err = validate_corresponding_source(binary_url, source_url)
    if err:
        print(f"ERROR: {err}", file=sys.stderr)
        sys.exit(1)
    ff_meta["corresponding_source_url"] = source_url
    if not ff_meta.get("build_recipe_url"):
        ff_meta["build_recipe_url"] = BUILD_RECIPE_URL

    if ff_meta.get("ffmpeg_license") == "NONFREE":
        print("ERROR: NONFREE ffmpeg in resolve meta", file=sys.stderr)
        sys.exit(1)

    # Re-stage notices into dist for the published artifact
    stage_info = stage_license_artifacts(dist, ff_meta["ffmpeg_license"], ff_meta)
    # Verify gate: license text(s) + source offer exist and match recorded hashes
    notices = dist / "ffmpeg-notices"
    license_names = stage_info.get("license_files") or [stage_info["license_file"]]
    for name in license_names:
        lic = notices / name
        if not lic.is_file():
            print(f"ERROR: license text missing after staging: {name}", file=sys.stderr)
            sys.exit(1)
        expected = (stage_info.get("license_sha256_map") or {}).get(name)
        if expected and sha256_file(lic) != expected:
            print(f"ERROR: license text hash mismatch: {name}", file=sys.stderr)
            sys.exit(1)
    offer = notices / stage_info["source_offer_file"]
    if not offer.is_file():
        print("ERROR: source-offer missing after staging", file=sys.stderr)
        sys.exit(1)
    if sha256_file(offer) != stage_info["source_offer_sha256"]:
        print("ERROR: source-offer hash mismatch", file=sys.stderr)
        sys.exit(1)
    # SOURCE_OFFER must reference the binary hashes and distinguish binary vs source
    offer_text = offer.read_text(encoding="utf-8")
    if ff_meta["ffmpeg_sha256"] not in offer_text or ff_meta["ffprobe_sha256"] not in offer_text:
        print("ERROR: SOURCE_OFFER does not reference binary hashes", file=sys.stderr)
        sys.exit(1)
    if source_url not in offer_text:
        print("ERROR: SOURCE_OFFER does not reference corresponding_source_url", file=sys.stderr)
        sys.exit(1)
    if binary_url not in offer_text:
        print("ERROR: SOURCE_OFFER does not reference binary_download_url", file=sys.stderr)
        sys.exit(1)
    # Gate again after staging: source must not equal binary ZIP
    staged_err = validate_corresponding_source(
        stage_info.get("binary_download_url") or binary_url,
        stage_info.get("corresponding_source_url") or source_url,
    )
    if staged_err:
        print(f"ERROR: staged SOURCE_OFFER invalid: {staged_err}", file=sys.stderr)
        sys.exit(1)

    onefile_names = ["vitranscript-sidecar", "vitranscript-sidecar.exe"]
    onedir_names = [
        Path("vitranscript-sidecar") / "vitranscript-sidecar",
        Path("vitranscript-sidecar") / "vitranscript-sidecar.exe",
    ]
    onefile = next(
        (dist / n for n in onefile_names if (dist / n).is_file()),
        dist / onefile_names[0],
    )
    onedir = next(
        (dist / n for n in onedir_names if (dist / n).is_file()),
        dist / onedir_names[0],
    )

    mode = (args.mode or "both").lower()
    onefile_entry = _sha_entry(onefile)
    onedir_entry = _sha_entry(onedir)
    if mode in ("onefile", "both") and onefile_entry is None:
        print(f"ERROR: onefile binary missing for mode={mode}: {onefile}", file=sys.stderr)
        sys.exit(1)
    if mode in ("onedir", "both") and onedir_entry is None:
        print(f"ERROR: onedir binary missing for mode={mode}: {onedir}", file=sys.stderr)
        sys.exit(1)

    ff_public = {
        "ffmpeg_basename": ff_meta.get("ffmpeg_basename"),
        "ffprobe_basename": ff_meta.get("ffprobe_basename"),
        "ffmpeg_sha256": ff_meta.get("ffmpeg_sha256"),
        "ffprobe_sha256": ff_meta.get("ffprobe_sha256"),
        "ffmpeg_version_line": ff_meta.get("ffmpeg_version_line"),
        "ffmpeg_configuration": ff_meta.get("ffmpeg_configuration"),
        "ffmpeg_license": ff_meta.get("ffmpeg_license"),
        "source_package": ff_meta.get("source_package"),
        "resolver_package": ff_meta.get("resolver_package"),
        "resolver_package_version": ff_meta.get("resolver_package_version"),
        "platform_key": ff_meta.get("platform_key"),
        "binary_download_url": binary_url,
        "download_url": binary_url,  # alias: binary ZIP only
        "download_revision": ff_meta.get("download_revision"),
        "corresponding_source_url": source_url,
        "build_recipe_url": ff_meta.get("build_recipe_url") or BUILD_RECIPE_URL,
        "license_artifacts": stage_info,
    }

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "os": platform.system(),
        "arch": platform.machine(),
        "python": sys.version.split()[0],
        "ffmpeg": ff_public,
        "onefile": onefile_entry,
        "onedir": onedir_entry,
    }
    out = dist / "sidecar-manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Wrote", out)
    print(json.dumps(manifest, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_res = sub.add_parser("resolve", help="Resolve ffmpeg/ffprobe + audit license")
    p_res.set_defaults(func=cmd_resolve)

    p_man = sub.add_parser("write-manifest", help="Write sidecar-manifest.json + stage notices")
    p_man.add_argument("--mode", default="both", choices=("onefile", "onedir", "both"))
    p_man.add_argument("--dist", default=str(PYI_DIR / "dist"))
    p_man.set_defaults(func=cmd_write_manifest)

    args = ap.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
