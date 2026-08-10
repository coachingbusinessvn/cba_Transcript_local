"""Unit tests for shared FFmpeg license audit (R2-1)."""
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


@pytest.mark.parametrize(
    "kind,filename",
    [
        ("GPLv2", "COPYING.GPLv2"),
        ("GPLv3", "COPYING.GPLv3"),
        ("LGPLv2.1", "COPYING.LGPLv2.1"),
        ("LGPLv3", "COPYING.LGPLv3"),
        ("GPL", "COPYING.GPLv3"),  # alias
        ("LGPL", "COPYING.LGPLv2.1"),  # alias
    ],
)
def test_stage_license_artifacts_picks_correct_copying(audit, tmp_path, kind, filename):
    meta = {
        "ffmpeg_version_line": "ffmpeg version n6.1 test",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "ffmpeg_configuration": "--enable-gpl",
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": "linux",
        "download_url": "https://example.com/v8.0/linux.zip",
        "download_revision": "v8.0",
    }
    info = audit.stage_license_artifacts(tmp_path, kind, meta)
    notices = tmp_path / "ffmpeg-notices"
    assert (notices / filename).is_file()
    assert info["license_file"] == filename
    offer = (notices / "SOURCE_OFFER.txt").read_text(encoding="utf-8")
    assert f"ffmpeg_license: {kind}" in offer
    assert meta["ffmpeg_sha256"] in offer
    assert meta["ffprobe_sha256"] in offer
    assert meta["download_url"] in offer
    assert info["license_sha256"]
    assert info["source_offer_sha256"]


def test_write_manifest_requires_resolve_json(audit, tmp_path, monkeypatch):
    """write-manifest must fail closed when resolve artifacts are missing."""
    monkeypatch.setattr(audit, "RESOLVE_JSON", tmp_path / "missing.json")
    monkeypatch.setattr(audit, "PYI_DIR", tmp_path)
    args = type("A", (), {"mode": "both", "dist": str(tmp_path / "dist")})()
    with pytest.raises(SystemExit) as ei:
        audit.cmd_write_manifest(args)
    assert ei.value.code == 1
