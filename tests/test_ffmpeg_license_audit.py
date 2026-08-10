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


def test_gpl(audit):
    assert audit.classify_configuration("--enable-gpl --enable-libx264") == "GPL"


def test_lgpl_default(audit):
    assert audit.classify_configuration("--disable-ffplay --enable-shared") == "LGPL"


def test_disable_gpl_is_lgpl(audit):
    assert audit.classify_configuration("--disable-gpl --enable-shared") == "LGPL"


def test_bundled_license_texts_exist():
    d = ROOT / "desktop" / "third_party" / "ffmpeg"
    assert (d / "COPYING.GPLv3").is_file()
    assert (d / "COPYING.LGPLv2.1").is_file()
    assert (d / "COPYING.GPLv3").stat().st_size > 1000


def test_stage_license_artifacts_embeds_hashes(audit, tmp_path):
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
    info = audit.stage_license_artifacts(tmp_path, "GPL", meta)
    notices = tmp_path / "ffmpeg-notices"
    assert (notices / "COPYING.GPLv3").is_file()
    offer = (notices / "SOURCE_OFFER.txt").read_text(encoding="utf-8")
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
