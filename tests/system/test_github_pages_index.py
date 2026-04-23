"""Tests for the GitHub Pages simple-index generator."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_index_module() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[2] / "bin" / "build_github_pages_index.py"
    )
    spec = importlib.util.spec_from_file_location("engram_pages_index", script_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load Pages index script: {script_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_release_distribution_links_filter_github_release_assets() -> None:
    """Only Engram wheel and sdist assets from non-draft version releases count."""

    index = _load_index_module()
    releases = [
        {
            "tag_name": "v0.1.0",
            "draft": False,
            "assets": [
                {
                    "name": "engram-0.1.0-py3-none-any.whl",
                    "browser_download_url": "https://example.test/wheel",
                    "digest": "sha256:" + "a" * 64,
                },
                {
                    "name": "engram-0.1.0.tar.gz",
                    "browser_download_url": "https://example.test/sdist",
                },
                {
                    "name": "engram-0.1.0-py3-none-any.whl.sigstore",
                    "browser_download_url": "https://example.test/signature",
                },
                {
                    "name": "other-0.1.0-py3-none-any.whl",
                    "browser_download_url": "https://example.test/other",
                },
            ],
        },
        {
            "tag_name": "not-a-release",
            "draft": False,
            "assets": [
                {
                    "name": "engram-9.9.9-py3-none-any.whl",
                    "browser_download_url": "https://example.test/not-release",
                }
            ],
        },
        {
            "tag_name": "v0.0.1",
            "draft": True,
            "assets": [
                {
                    "name": "engram-0.0.1-py3-none-any.whl",
                    "browser_download_url": "https://example.test/draft",
                }
            ],
        },
    ]

    links = index.release_distribution_links(releases, package_name="engram")

    assert links == [
        index.DistributionLink(
            filename="engram-0.1.0-py3-none-any.whl",
            url="https://example.test/wheel",
            sha256="a" * 64,
        ),
        index.DistributionLink(
            filename="engram-0.1.0.tar.gz",
            url="https://example.test/sdist",
        ),
    ]


def test_local_distribution_links_compute_hashes_and_release_urls(
    tmp_path: Path,
) -> None:
    """Current local dist files should get GitHub Release URLs and SHA-256 hashes."""

    index = _load_index_module()
    wheel = tmp_path / "engram-0.2.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel-bytes")
    ignored = tmp_path / "engram-0.2.0-py3-none-any.whl.sigstore"
    ignored.write_bytes(b"signature")

    links = index.local_distribution_links(
        tmp_path,
        package_name="engram",
        repo="VanL/engram",
        tag_name="v0.2.0",
    )

    assert links == [
        index.DistributionLink(
            filename="engram-0.2.0-py3-none-any.whl",
            url=(
                "https://github.com/VanL/engram/releases/download/"
                "v0.2.0/engram-0.2.0-py3-none-any.whl"
            ),
            sha256=hashlib.sha256(b"wheel-bytes").hexdigest(),
        )
    ]


def test_local_distribution_links_url_escape_tag_and_filename(tmp_path: Path) -> None:
    """Release download URLs should escape path segments safely."""

    index = _load_index_module()
    wheel = tmp_path / "engram-0.2.0+local-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    links = index.local_distribution_links(
        tmp_path,
        package_name="engram",
        repo="VanL/engram",
        tag_name="candidate/v0.2.0",
    )

    assert len(links) == 1
    assert (
        links[0].url == "https://github.com/VanL/engram/releases/download/"
        "candidate%2Fv0.2.0/engram-0.2.0%2Blocal-py3-none-any.whl"
    )


def test_merge_distribution_links_prefers_current_local_dist() -> None:
    """Freshly built local dists should override stale API data for same filename."""

    index = _load_index_module()
    api_link = index.DistributionLink(
        filename="engram-0.2.0-py3-none-any.whl",
        url="https://example.test/old",
    )
    local_link = index.DistributionLink(
        filename="engram-0.2.0-py3-none-any.whl",
        url="https://example.test/current",
        sha256="b" * 64,
    )

    assert index.merge_distribution_links([api_link], [local_link]) == [local_link]


def test_github_pages_base_url_from_repo() -> None:
    """The landing page install example should derive the Pages URL from the repo."""

    index = _load_index_module()

    assert (
        index.github_pages_base_url("VanL/engram") == "https://vanl.github.io/engram/"
    )
    assert index.github_pages_base_url("invalid") is None


def test_write_pages_site_generates_pep503_shape(tmp_path: Path) -> None:
    """The generated Pages site should expose root and project simple indexes."""

    index = _load_index_module()
    links = [
        index.DistributionLink(
            filename="engram-0.1.0-py3-none-any.whl",
            url="https://example.test/engram-0.1.0-py3-none-any.whl",
            sha256="c" * 64,
        )
    ]

    index.write_pages_site(
        tmp_path,
        package_name="engram",
        links=links,
        pages_base_url="https://vanl.github.io/engram/",
    )

    landing_page = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert (tmp_path / ".nojekyll").read_text(encoding="utf-8") == ""
    simple_root = (tmp_path / "simple" / "index.html").read_text(encoding="utf-8")
    project_page = (tmp_path / "simple" / "engram" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "https://vanl.github.io/engram/simple/engram/" in landing_page
    assert '<a href="engram/">engram</a>' in simple_root
    assert "engram-0.1.0-py3-none-any.whl" in project_page
    assert "#sha256=" + "c" * 64 in project_page


def test_main_builds_index_from_api_and_local_dist(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """The CLI should combine historic API assets and current local dist files."""

    index = _load_index_module()
    dist_dir = tmp_path / "dist"
    site_dir = tmp_path / "site"
    dist_dir.mkdir()
    (dist_dir / "engram-0.2.0-py3-none-any.whl").write_bytes(b"current")
    monkeypatch.setattr(
        index,
        "fetch_github_releases",
        lambda *, repo, token, api_base: [
            {
                "tag_name": "v0.1.0",
                "draft": False,
                "assets": [
                    {
                        "name": "engram-0.1.0-py3-none-any.whl",
                        "browser_download_url": "https://example.test/old-wheel",
                    }
                ],
            }
        ],
    )

    exit_code = index.main(
        [
            "--repo",
            "VanL/engram",
            "--tag",
            "v0.2.0",
            "--dist-dir",
            str(dist_dir),
            "--site-dir",
            str(site_dir),
            "--require-local-dist",
        ]
    )

    project_page = (site_dir / "simple" / "engram" / "index.html").read_text(
        encoding="utf-8"
    )

    assert exit_code == 0
    assert "https://example.test/old-wheel" in project_page
    assert "engram-0.2.0-py3-none-any.whl" in project_page
    assert "#sha256=" + hashlib.sha256(b"current").hexdigest() in project_page
