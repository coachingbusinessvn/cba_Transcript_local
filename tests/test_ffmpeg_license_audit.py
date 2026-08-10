"""Unit tests for shared FFmpeg license audit (R2-1 + residual source/LGPL fixes)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "desktop" / "scripts" / "ffmpeg_license_audit.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("ffmpeg_license_audit", AUDIT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


def test_nonfree_before_gpl(audit):
    """--enable-nonfree must win even when --enable-gpl is also present."""
    cfg = "--prefix=/usr --enable-gpl --enable-nonfree --enable-libx264"
    assert audit.classify_configuration(cfg) == "NONFREE"


def test_nonfree_alone(audit):
    assert audit.classify_configuration("--enable-nonfree") == "NONFREE"


def test_gpl_without_version3_is_gplv2(audit):
    assert audit.classify_configuration("--enable-gpl --enable-libx264") == "GPLv2"


def test_gpl_with_version3_is_gplv3(audit):
    assert (
        audit.classify_configuration("--enable-gpl --enable-version3 --enable-libx264")
        == "GPLv3"
    )


def test_lgpl_default_is_lgplv21(audit):
    assert audit.classify_configuration("--disable-ffplay --enable-shared") == "LGPLv2.1"


def test_lgpl_with_version3_is_lgplv3(audit):
    assert audit.classify_configuration("--enable-version3 --enable-shared") == "LGPLv3"


def test_disable_gpl_is_lgplv21(audit):
    assert audit.classify_configuration("--disable-gpl --enable-shared") == "LGPLv2.1"


def test_disable_gpl_with_version3_is_lgplv3(audit):
    assert (
        audit.classify_configuration("--disable-gpl --enable-version3 --enable-shared")
        == "LGPLv3"
    )


def test_bundled_license_texts_exist():
    d = ROOT / "desktop" / "third_party" / "ffmpeg"
    for name in (
        "COPYING.GPLv2",
        "COPYING.GPLv3",
        "COPYING.LGPLv2.1",
        "COPYING.LGPLv3",
    ):
        p = d / name
        assert p.is_file(), name
        assert p.stat().st_size > 1000, name


def test_parse_ffmpeg_version_number(audit):
    assert audit.parse_ffmpeg_version_number("ffmpeg version n6.1 Copyright") == "6.1"
    assert audit.parse_ffmpeg_version_number("ffmpeg version 7.0.2-static") == "7.0.2"
    assert audit.parse_ffmpeg_version_number("ffmpeg version 6.1.1") == "6.1.1"
    assert audit.parse_ffmpeg_version_number("not a version") is None


def test_corresponding_source_url_for_version(audit):
    url = audit.corresponding_source_url_for_version("ffmpeg version n6.1 Copyright (c)")
    assert url == "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz"
    assert audit.corresponding_source_url_for_version("garbage") is None


def test_is_platform_binary_zip_url(audit):
    assert audit.is_platform_binary_zip_url(
        "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    )
    assert audit.is_platform_binary_zip_url("https://example.com/v8.0/win32.zip")
    assert not audit.is_platform_binary_zip_url(
        "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz"
    )
    assert not audit.is_platform_binary_zip_url(None)


def test_validate_corresponding_source_ok(audit):
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    source = "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz"
    assert audit.validate_corresponding_source(binary, source) is None


def test_validate_corresponding_source_fail_missing(audit):
    assert audit.validate_corresponding_source("https://x/a.zip", None) is not None
    assert audit.validate_corresponding_source("https://x/a.zip", "") is not None


def test_validate_corresponding_source_fail_same_as_binary(audit):
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    err = audit.validate_corresponding_source(binary, binary)
    assert err is not None
    assert "differ" in err


def test_validate_corresponding_source_fail_binary_zip(audit):
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    other_zip = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/macos.zip"
    err = audit.validate_corresponding_source(binary, other_zip)
    assert err is not None
    assert "binary ZIP" in err or "ZIP" in err


@pytest.mark.parametrize(
    "kind,filenames",
    [
        ("GPLv2", ["COPYING.GPLv2"]),
        ("GPLv3", ["COPYING.GPLv3"]),
        ("LGPLv2.1", ["COPYING.LGPLv2.1"]),
        # LGPLv3 incorporates GPLv3 → both texts required
        ("LGPLv3", ["COPYING.LGPLv3", "COPYING.GPLv3"]),
        ("GPL", ["COPYING.GPLv3"]),  # alias
        ("LGPL", ["COPYING.LGPLv2.1"]),  # alias
    ],
)
def test_stage_license_artifacts_picks_correct_copying_set(audit, tmp_path, kind, filenames):
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    source = "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz"
    meta = {
        "ffmpeg_version_line": "ffmpeg version n6.1 test",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "ffmpeg_configuration": "--enable-gpl",
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": "linux",
        "binary_download_url": binary,
        "download_url": binary,
        "corresponding_source_url": source,
        "build_recipe_url": "https://github.com/zackees/ffmpeg_bins",
        "download_revision": "v8.0",
    }
    info = audit.stage_license_artifacts(tmp_path, kind, meta)
    notices = tmp_path / "ffmpeg-notices"
    for name in filenames:
        assert (notices / name).is_file(), name
    assert info["license_files"] == filenames
    assert info["license_file"] == filenames[0]
    # No extra unexpected COPYING.* beyond the required set (and none missing)
    staged_copying = sorted(p.name for p in notices.glob("COPYING.*"))
    assert staged_copying == sorted(filenames)

    offer = (notices / "SOURCE_OFFER.txt").read_text(encoding="utf-8")
    assert f"ffmpeg_license: {kind}" in offer
    assert meta["ffmpeg_sha256"] in offer
    assert meta["ffprobe_sha256"] in offer
    assert binary in offer
    assert source in offer
    assert "binary_download_url" in offer
    assert "corresponding_source_url" in offer
    assert "NOT corresponding source" in offer
    assert "Compliance sign-off" in offer or "compliance sign-off" in offer
    assert info["license_sha256"]
    assert info["source_offer_sha256"]
    assert info["corresponding_source_url"] == source
    assert info["binary_download_url"] == binary


def test_stage_license_artifacts_fails_when_source_is_binary_zip(audit, tmp_path):
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    meta = {
        "ffmpeg_version_line": "ffmpeg version n6.1 test",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "ffmpeg_configuration": "--enable-shared",
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": "linux",
        "binary_download_url": binary,
        "corresponding_source_url": binary,  # wrong: same as binary ZIP
        "download_revision": "v8.0",
    }
    with pytest.raises(SystemExit) as ei:
        audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert ei.value.code == 1


def test_stage_license_artifacts_derives_source_from_version_line(audit, tmp_path):
    """If corresponding_source_url omitted, derive official tarball from version line."""
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    meta = {
        "ffmpeg_version_line": "ffmpeg version n6.1 Copyright (c)",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "ffmpeg_configuration": "--enable-shared",
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": "linux",
        "binary_download_url": binary,
        "download_revision": "v8.0",
    }
    info = audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert info["corresponding_source_url"] == "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz"
    offer = (tmp_path / "ffmpeg-notices" / "SOURCE_OFFER.txt").read_text(encoding="utf-8")
    assert "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz" in offer
    assert binary in offer
    assert binary != info["corresponding_source_url"]


def test_lgplv3_stages_both_lgplv3_and_gplv3(audit, tmp_path):
    """RESIDUAL-2: LGPLv3 must ship COPYING.LGPLv3 AND COPYING.GPLv3."""
    binary = "https://example.com/v8.0/linux.zip"
    source = "https://ffmpeg.org/releases/ffmpeg-7.0.tar.xz"
    meta = {
        "ffmpeg_version_line": "ffmpeg version 7.0",
        "ffmpeg_sha256": "c" * 64,
        "ffprobe_sha256": "d" * 64,
        "ffmpeg_configuration": "--enable-version3",
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": "linux",
        "binary_download_url": binary,
        "corresponding_source_url": source,
        "download_revision": "v8.0",
    }
    info = audit.stage_license_artifacts(tmp_path, "LGPLv3", meta)
    notices = tmp_path / "ffmpeg-notices"
    assert (notices / "COPYING.LGPLv3").is_file()
    assert (notices / "COPYING.GPLv3").is_file()
    assert info["license_files"] == ["COPYING.LGPLv3", "COPYING.GPLv3"]
    assert set(info["license_sha256_map"]) == {"COPYING.LGPLv3", "COPYING.GPLv3"}


def test_write_manifest_requires_resolve_json(audit, tmp_path, monkeypatch):
    """write-manifest must fail closed when resolve artifacts are missing."""
    monkeypatch.setattr(audit, "RESOLVE_JSON", tmp_path / "missing.json")
    monkeypatch.setattr(audit, "PYI_DIR", tmp_path)
    args = type("A", (), {"mode": "both", "dist": str(tmp_path / "dist")})()
    with pytest.raises(SystemExit) as ei:
        audit.cmd_write_manifest(args)
    assert ei.value.code == 1


def test_write_manifest_rejects_source_equal_binary_zip(audit, tmp_path, monkeypatch):
    """Gate: corresponding_source_url must not be the platform binary ZIP."""
    binary = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
    resolve = {
        "ffmpeg_license": "LGPLv2.1",
        "ffmpeg_version_line": "ffmpeg version n6.1 test",
        "ffmpeg_configuration": "--enable-shared",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "resolver_package_version": "2.7",
        "binary_download_url": binary,
        "download_url": binary,
        "corresponding_source_url": binary,  # invalid
    }
    resolve_path = tmp_path / "_ffmpeg_resolve.json"
    resolve_path.write_text(__import__("json").dumps(resolve), encoding="utf-8")
    monkeypatch.setattr(audit, "RESOLVE_JSON", resolve_path)
    monkeypatch.setattr(audit, "PYI_DIR", tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "vitranscript-sidecar").write_bytes(b"x")
    args = type("A", (), {"mode": "onefile", "dist": str(dist)})()
    with pytest.raises(SystemExit) as ei:
        audit.cmd_write_manifest(args)
    assert ei.value.code == 1
