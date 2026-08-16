"""Unit tests for shared FFmpeg license audit (R2-1 + residual source/LGPL fixes)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = ROOT / "desktop" / "scripts" / "ffmpeg_license_audit.py"

# Realistic git-describe version line matching shipped third-party binaries.
GIT_DESCRIBE_VERSION = "ffmpeg version n8.0.1-48-g0592be14ff-20260116 Copyright (c)"
GIT_REV = "0592be14ff"
COMMIT_SOURCE = f"https://github.com/FFmpeg/FFmpeg/archive/{GIT_REV}.tar.xz"
RELEASE_SOURCE_601 = "https://ffmpeg.org/releases/ffmpeg-6.1.tar.xz"
BINARY_ZIP = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/linux.zip"
RECIPE_URL = "https://github.com/zackees/static_ffmpeg"


def _load_audit():
    spec = importlib.util.spec_from_file_location("ffmpeg_license_audit", AUDIT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def audit():
    return _load_audit()


def _base_meta(
    *,
    version_line: str = GIT_DESCRIBE_VERSION,
    source: str = COMMIT_SOURCE,
    source_revision: str | None = GIT_REV,
    binary: str = BINARY_ZIP,
    recipe: str = RECIPE_URL,
    platform_key: str = "linux",
) -> dict:
    return {
        "ffmpeg_version_line": version_line,
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "ffmpeg_configuration": "--enable-shared",
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": platform_key,
        "binary_download_url": binary,
        "download_url": binary,
        "corresponding_source_url": source,
        "source_revision": source_revision,
        "build_recipe_url": recipe,
        "recipe_revision": "2.7",
        "binary_provider": "BtbN (github.com/BtbN/FFmpeg-Builds)",
        "download_revision": "v8.0",
    }


def test_canonical_license_kinds_are_single_source_of_truth(audit):
    """Classifier free labels must equal CANONICAL/ALLOWED; NONFREE is reject-only.

    Guards enum drift: if classify_configuration gains/drops a free-software label
    without updating CANONICAL_LICENSE_KINDS / ALLOWED_LICENSE_KINDS, this fails.
    CI workflow loads ALLOWED_LICENSE_KINDS from the same module.
    """
    expected_canonical = frozenset({"GPLv2", "GPLv3", "LGPLv2.1", "LGPLv3"})
    assert audit.CANONICAL_LICENSE_KINDS == expected_canonical
    assert audit.ALLOWED_LICENSE_KINDS == expected_canonical
    assert audit.ALLOWED_LICENSE_KINDS == audit.CANONICAL_LICENSE_KINDS
    assert "NONFREE" not in audit.ALLOWED_LICENSE_KINDS
    assert audit.CLASSIFIER_LICENSE_KINDS == expected_canonical | {"NONFREE"}

    # Exhaustive flag matrix → every free label the classifier can emit.
    flag_cases = (
        "--enable-nonfree",
        "--enable-gpl --enable-nonfree",
        "--enable-gpl",
        "--enable-gpl --enable-libx264",
        "--enable-gpl --enable-version3",
        "--enable-gpl --enable-version3 --enable-libx264",
        "",
        "--enable-shared",
        "--disable-ffplay --enable-shared",
        "--disable-gpl --enable-shared",
        "--enable-version3",
        "--enable-version3 --enable-shared",
        "--disable-gpl --enable-version3 --enable-shared",
    )
    produced = {audit.classify_configuration(cfg) for cfg in flag_cases}
    free_produced = produced - {"NONFREE"}
    assert free_produced == audit.CANONICAL_LICENSE_KINDS
    assert free_produced == audit.ALLOWED_LICENSE_KINDS
    assert "NONFREE" in produced
    # Staging map must cover every allowed kind (aliases GPL/LGPL may also exist).
    for kind in audit.ALLOWED_LICENSE_KINDS:
        files = audit.license_files_for_kind(kind)
        assert files, f"missing license file map for {kind}"


def test_desktop_build_workflow_uses_allowed_license_kinds_not_legacy_enum():
    """CI must not reintroduce legacy ('GPL','LGPL') assert; load ALLOWED_LICENSE_KINDS."""
    yml = (ROOT / ".github" / "workflows" / "desktop-build.yml").read_text(
        encoding="utf-8"
    )
    assert "ALLOWED_LICENSE_KINDS" in yml
    assert 'in ("GPL", "LGPL")' not in yml
    assert "in ('GPL', 'LGPL')" not in yml
    # Workflow imports the audit module rather than hard-coding a second enum.
    assert "ffmpeg_license_audit" in yml


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
    assert audit.parse_ffmpeg_version_number(GIT_DESCRIBE_VERSION) == "8.0.1"
    assert audit.parse_ffmpeg_version_number("not a version") is None


def test_parse_ffmpeg_source_revision(audit):
    assert audit.parse_ffmpeg_source_revision(GIT_DESCRIBE_VERSION) == GIT_REV
    assert (
        audit.parse_ffmpeg_source_revision("ffmpeg version n8.0.1-48-g0592be14ff")
        == GIT_REV
    )
    # Pure release tag — no git revision
    assert audit.parse_ffmpeg_source_revision("ffmpeg version n6.1 Copyright") is None
    assert audit.parse_ffmpeg_source_revision("ffmpeg version 7.0.2-static") is None
    assert audit.parse_ffmpeg_source_revision("garbage") is None


def test_corresponding_source_url_for_version(audit):
    # Pure release tag → official tarball
    url = audit.corresponding_source_url_for_version("ffmpeg version n6.1 Copyright (c)")
    assert url == RELEASE_SOURCE_601
    # Git-describe → exact commit archive (NOT release tarball 8.0.1)
    git_url = audit.corresponding_source_url_for_version(GIT_DESCRIBE_VERSION)
    assert git_url == COMMIT_SOURCE
    assert "8.0.1.tar.xz" not in git_url
    assert GIT_REV in git_url
    assert audit.corresponding_source_url_for_version("garbage") is None


def test_build_recipe_url_is_static_ffmpeg_not_bins(audit):
    assert "static_ffmpeg" in audit.BUILD_RECIPE_URL
    assert "ffmpeg_bins" not in audit.BUILD_RECIPE_URL
    assert audit.is_binary_bins_repo_url("https://github.com/zackees/ffmpeg_bins")
    assert not audit.is_binary_bins_repo_url(RECIPE_URL)


def test_platform_binary_provider(audit):
    assert "BtbN" in audit.platform_binary_provider("linux")
    assert "gyan" in audit.platform_binary_provider("win32").lower()
    assert "evermeet" in audit.platform_binary_provider("macos").lower()


def test_is_platform_binary_zip_url(audit):
    assert audit.is_platform_binary_zip_url(BINARY_ZIP)
    assert audit.is_platform_binary_zip_url("https://example.com/v8.0/win32.zip")
    assert not audit.is_platform_binary_zip_url(RELEASE_SOURCE_601)
    assert not audit.is_platform_binary_zip_url(COMMIT_SOURCE)
    assert not audit.is_platform_binary_zip_url(None)


def test_validate_corresponding_source_ok(audit):
    assert (
        audit.validate_corresponding_source(
            BINARY_ZIP,
            COMMIT_SOURCE,
            version_line=GIT_DESCRIBE_VERSION,
            source_revision=GIT_REV,
            build_recipe_url=RECIPE_URL,
        )
        is None
    )
    # Pure release tag + release tarball is OK
    assert (
        audit.validate_corresponding_source(
            BINARY_ZIP,
            RELEASE_SOURCE_601,
            version_line="ffmpeg version n6.1 Copyright",
            build_recipe_url=RECIPE_URL,
        )
        is None
    )


def test_validate_corresponding_source_fail_missing(audit):
    assert audit.validate_corresponding_source("https://x/a.zip", None) is not None
    assert audit.validate_corresponding_source("https://x/a.zip", "") is not None


def test_validate_corresponding_source_fail_same_as_binary(audit):
    err = audit.validate_corresponding_source(BINARY_ZIP, BINARY_ZIP)
    assert err is not None
    assert "differ" in err


def test_validate_corresponding_source_fail_binary_zip(audit):
    other_zip = "https://github.com/zackees/ffmpeg_bins/raw/main/v8.0/macos.zip"
    err = audit.validate_corresponding_source(BINARY_ZIP, other_zip)
    assert err is not None
    assert "binary ZIP" in err or "ZIP" in err


def test_validate_corresponding_source_fail_release_tarball_when_git_rev(audit):
    """HIGH-2: binary with -gHASH must not be paired with release-only X.Y.Z tarball."""
    release_only = "https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz"
    err = audit.validate_corresponding_source(
        BINARY_ZIP,
        release_only,
        version_line=GIT_DESCRIBE_VERSION,
        source_revision=GIT_REV,
        build_recipe_url=RECIPE_URL,
    )
    assert err is not None
    assert "git revision" in err or "release tarball" in err or GIT_REV in err


def test_validate_corresponding_source_fail_recipe_is_bins_repo(audit):
    """HIGH-2: build_recipe_url must not be the ffmpeg_bins binary mirror."""
    err = audit.validate_corresponding_source(
        BINARY_ZIP,
        COMMIT_SOURCE,
        version_line=GIT_DESCRIBE_VERSION,
        source_revision=GIT_REV,
        build_recipe_url="https://github.com/zackees/ffmpeg_bins",
    )
    assert err is not None
    assert "ffmpeg_bins" in err or "binary" in err.lower()


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
    meta = _base_meta()
    meta["ffmpeg_configuration"] = "--enable-gpl"
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
    assert BINARY_ZIP in offer
    assert COMMIT_SOURCE in offer
    assert GIT_REV in offer
    assert "binary_download_url" in offer
    assert "corresponding_source_url" in offer
    assert "source_revision" in offer
    assert "NOT corresponding source" in offer
    assert "Compliance sign-off" in offer or "compliance sign-off" in offer
    assert "BtbN" in offer or "binary_provider" in offer
    assert "static_ffmpeg" in offer
    assert info["license_sha256"]
    assert info["source_offer_sha256"]
    assert info["corresponding_source_url"] == COMMIT_SOURCE
    assert info["binary_download_url"] == BINARY_ZIP
    assert info["source_revision"] == GIT_REV
    assert info["build_recipe_url"] == RECIPE_URL


def test_stage_license_artifacts_fails_when_source_is_binary_zip(audit, tmp_path):
    meta = _base_meta(source=BINARY_ZIP)  # wrong: same as binary ZIP
    with pytest.raises(SystemExit) as ei:
        audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert ei.value.code == 1


def test_stage_license_artifacts_fails_when_source_url_missing(audit, tmp_path):
    """HIGH-1: stage must fail-closed if corresponding_source_url is absent."""
    meta = _base_meta()
    del meta["corresponding_source_url"]
    with pytest.raises(SystemExit) as ei:
        audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert ei.value.code == 1


def test_stage_license_artifacts_fails_when_source_is_release_only_for_git_binary(
    audit, tmp_path
):
    """HIGH-2: stage rejects release tarball when binary version has -gHASH."""
    meta = _base_meta(source="https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz")
    with pytest.raises(SystemExit) as ei:
        audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert ei.value.code == 1


def test_stage_license_artifacts_fails_when_recipe_is_bins_repo(audit, tmp_path):
    """HIGH-2: stage rejects build_recipe_url pointing at ffmpeg_bins."""
    meta = _base_meta(recipe="https://github.com/zackees/ffmpeg_bins")
    with pytest.raises(SystemExit) as ei:
        audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert ei.value.code == 1


def test_stage_license_artifacts_pure_release_tag(audit, tmp_path):
    """Pure release version (no -g) may use official release tarball."""
    meta = _base_meta(
        version_line="ffmpeg version n6.1 Copyright (c)",
        source=RELEASE_SOURCE_601,
        source_revision=None,
    )
    info = audit.stage_license_artifacts(tmp_path, "LGPLv2.1", meta)
    assert info["corresponding_source_url"] == RELEASE_SOURCE_601
    offer = (tmp_path / "ffmpeg-notices" / "SOURCE_OFFER.txt").read_text(encoding="utf-8")
    assert RELEASE_SOURCE_601 in offer
    assert BINARY_ZIP in offer


def test_lgplv3_stages_both_lgplv3_and_gplv3(audit, tmp_path):
    """RESIDUAL-2: LGPLv3 must ship COPYING.LGPLv3 AND COPYING.GPLv3."""
    meta = _base_meta(
        version_line="ffmpeg version 7.0",
        source="https://ffmpeg.org/releases/ffmpeg-7.0.tar.xz",
        source_revision=None,
        binary="https://example.com/v8.0/linux.zip",
    )
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


def test_write_manifest_fails_when_source_url_missing(audit, tmp_path, monkeypatch):
    """HIGH-1: write-manifest exit 1 when corresponding_source_url absent (no re-derive)."""
    resolve = {
        "ffmpeg_license": "LGPLv2.1",
        "ffmpeg_version_line": GIT_DESCRIBE_VERSION,
        "ffmpeg_configuration": "--enable-shared",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "resolver_package_version": "2.7",
        "binary_download_url": BINARY_ZIP,
        "download_url": BINARY_ZIP,
        # corresponding_source_url intentionally omitted
        "build_recipe_url": RECIPE_URL,
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


def test_write_manifest_rejects_source_equal_binary_zip(audit, tmp_path, monkeypatch):
    """Gate: corresponding_source_url must not be the platform binary ZIP."""
    resolve = {
        "ffmpeg_license": "LGPLv2.1",
        "ffmpeg_version_line": GIT_DESCRIBE_VERSION,
        "ffmpeg_configuration": "--enable-shared",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "resolver_package_version": "2.7",
        "binary_download_url": BINARY_ZIP,
        "download_url": BINARY_ZIP,
        "corresponding_source_url": BINARY_ZIP,  # invalid
        "source_revision": GIT_REV,
        "build_recipe_url": RECIPE_URL,
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


def test_write_manifest_rejects_release_tarball_for_git_binary(audit, tmp_path, monkeypatch):
    """HIGH-2: write-manifest exit 1 when source is X.Y.Z but binary has -gHASH."""
    resolve = {
        "ffmpeg_license": "LGPLv2.1",
        "ffmpeg_version_line": GIT_DESCRIBE_VERSION,
        "ffmpeg_configuration": "--enable-shared",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "resolver_package_version": "2.7",
        "binary_download_url": BINARY_ZIP,
        "corresponding_source_url": "https://ffmpeg.org/releases/ffmpeg-8.0.1.tar.xz",
        "source_revision": GIT_REV,
        "build_recipe_url": RECIPE_URL,
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


def test_write_manifest_ok_with_git_describe_source(audit, tmp_path, monkeypatch):
    """Happy path: git-describe binary + commit archive source → manifest written."""
    resolve = {
        "ffmpeg_license": "LGPLv2.1",
        "ffmpeg_version_line": GIT_DESCRIBE_VERSION,
        "ffmpeg_configuration": "--enable-shared",
        "ffmpeg_sha256": "a" * 64,
        "ffprobe_sha256": "b" * 64,
        "resolver_package": "static-ffmpeg",
        "resolver_package_version": "2.7",
        "platform_key": "linux",
        "binary_download_url": BINARY_ZIP,
        "download_url": BINARY_ZIP,
        "download_revision": "v8.0",
        "corresponding_source_url": COMMIT_SOURCE,
        "source_revision": GIT_REV,
        "build_recipe_url": RECIPE_URL,
        "recipe_revision": "2.7",
        "binary_provider": "BtbN (github.com/BtbN/FFmpeg-Builds)",
        "ffmpeg_basename": "ffmpeg",
        "ffprobe_basename": "ffprobe",
        "source_package": "static-ffmpeg==2.7",
    }
    resolve_path = tmp_path / "_ffmpeg_resolve.json"
    resolve_path.write_text(__import__("json").dumps(resolve), encoding="utf-8")
    monkeypatch.setattr(audit, "RESOLVE_JSON", resolve_path)
    monkeypatch.setattr(audit, "PYI_DIR", tmp_path)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "vitranscript-sidecar").write_bytes(b"sidecar")
    args = type("A", (), {"mode": "onefile", "dist": str(dist)})()
    rc = audit.cmd_write_manifest(args)
    assert rc == 0
    manifest_path = dist / "sidecar-manifest.json"
    assert manifest_path.is_file()
    manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
    ff = manifest["ffmpeg"]
    assert ff["corresponding_source_url"] == COMMIT_SOURCE
    assert ff["source_revision"] == GIT_REV
    assert ff["build_recipe_url"] == RECIPE_URL
    assert "ffmpeg_bins" not in (ff["build_recipe_url"] or "")
    offer = (dist / "ffmpeg-notices" / "SOURCE_OFFER.txt").read_text(encoding="utf-8")
    assert COMMIT_SOURCE in offer
    assert GIT_REV in offer
    assert RECIPE_URL in offer
