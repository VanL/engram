#!/usr/bin/env python3
"""Build a GitHub Pages-hosted Python simple index from release assets."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

DEFAULT_API_BASE: Final[str] = "https://api.github.com"
DEFAULT_PACKAGE_NAME: Final[str] = "engram"
HTTP_TIMEOUT_SECONDS: Final[float] = 20.0
RELEASE_ASSET_SUFFIXES: Final[tuple[str, ...]] = (".whl", ".tar.gz")
NORMALIZED_NAME_PATTERN: Final[re.Pattern[str]] = re.compile(r"[-_.]+")
SHA256_DIGEST_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^sha256:([a-fA-F0-9]{64})$"
)


@dataclass(frozen=True)
class DistributionLink:
    """A downloadable Python distribution exposed by the simple index."""

    filename: str
    url: str
    sha256: str | None = None


def normalize_project_name(name: str) -> str:
    """Return the Python Simple API normalized project name."""

    return NORMALIZED_NAME_PATTERN.sub("-", name).lower()


def is_distribution_filename(filename: str, *, package_name: str) -> bool:
    """Return whether a release asset looks like a distribution for this package."""

    normalized_package = normalize_project_name(package_name)
    normalized_filename = normalize_project_name(filename)
    if not normalized_filename.startswith(f"{normalized_package}-"):
        return False
    return filename.endswith(RELEASE_ASSET_SUFFIXES)


def _asset_sha256(asset: dict[str, Any]) -> str | None:
    digest = asset.get("digest")
    if not isinstance(digest, str):
        return None
    match = SHA256_DIGEST_PATTERN.fullmatch(digest)
    if match is None:
        return None
    return match.group(1).lower()


def release_distribution_links(
    releases: list[dict[str, Any]],
    *,
    package_name: str,
    tag_prefix: str = "v",
) -> list[DistributionLink]:
    """Extract distribution links from GitHub Release API payloads."""

    links: list[DistributionLink] = []
    for release in releases:
        tag_name = release.get("tag_name")
        if not isinstance(tag_name, str) or not tag_name.startswith(tag_prefix):
            continue
        if release.get("draft"):
            continue
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            filename = asset.get("name")
            url = asset.get("browser_download_url")
            if not isinstance(filename, str) or not isinstance(url, str):
                continue
            if not is_distribution_filename(filename, package_name=package_name):
                continue
            links.append(
                DistributionLink(
                    filename=filename, url=url, sha256=_asset_sha256(asset)
                )
            )
    return links


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _github_release_download_url(*, repo: str, tag_name: str, filename: str) -> str:
    encoded_tag = urllib_parse.quote(tag_name, safe="")
    encoded_filename = urllib_parse.quote(filename, safe="")
    return (
        f"https://github.com/{repo}/releases/download/{encoded_tag}/{encoded_filename}"
    )


def local_distribution_links(
    dist_dir: Path,
    *,
    package_name: str,
    repo: str,
    tag_name: str,
) -> list[DistributionLink]:
    """Return distribution links for local dist files on the current release tag."""

    links: list[DistributionLink] = []
    if not dist_dir.exists():
        return links
    for path in sorted(item for item in dist_dir.iterdir() if item.is_file()):
        if not is_distribution_filename(path.name, package_name=package_name):
            continue
        links.append(
            DistributionLink(
                filename=path.name,
                url=_github_release_download_url(
                    repo=repo,
                    tag_name=tag_name,
                    filename=path.name,
                ),
                sha256=_sha256_file(path),
            )
        )
    return links


def merge_distribution_links(
    release_links: list[DistributionLink],
    local_links: list[DistributionLink],
) -> list[DistributionLink]:
    """Merge historic and current release links, preferring local hashes."""

    merged = {link.filename: link for link in release_links}
    for link in local_links:
        merged[link.filename] = link
    return [merged[filename] for filename in sorted(merged)]


def _href_with_hash(link: DistributionLink) -> str:
    if link.sha256 is None:
        return link.url
    return f"{link.url}#sha256={link.sha256}"


def _html_page(title: str, body: str) -> str:
    return (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{html.escape(title)}</title>\n"
        "</head>\n"
        "<body>\n"
        f"{body}"
        "</body>\n"
        "</html>\n"
    )


def github_pages_base_url(repo: str) -> str | None:
    """Return the default GitHub Pages project URL for ``owner/repo``."""

    if repo.count("/") != 1:
        return None
    owner, repo_name = repo.split("/", maxsplit=1)
    if not owner or not repo_name:
        return None
    return f"https://{owner.lower()}.github.io/{repo_name}/"


def render_root_page(package_name: str, *, pages_base_url: str | None = None) -> str:
    """Render a human-facing landing page for the GitHub Pages site."""

    normalized = normalize_project_name(package_name)
    escaped_name = html.escape(package_name)
    escaped_normalized = html.escape(normalized)
    find_links_url = (
        f"{pages_base_url.rstrip('/')}/simple/{normalized}/"
        if pages_base_url is not None
        else f"simple/{normalized}/"
    )
    body = (
        f"  <h1>{escaped_name} package index</h1>\n"
        "  <p>This site exposes GitHub Release artifacts through a Python "
        "Simple Repository API index.</p>\n"
        "  <pre><code>"
        f"uv pip install --find-links {html.escape(find_links_url)} "
        f"{html.escape(package_name)}"
        "</code></pre>\n"
        f'  <p><a href="simple/{escaped_normalized}/">Open {escaped_name} simple index</a></p>\n'
    )
    return _html_page(f"{package_name} package index", body)


def render_simple_root(package_name: str) -> str:
    """Render the Simple API root index."""

    normalized = normalize_project_name(package_name)
    escaped = html.escape(normalized)
    body = f'  <a href="{escaped}/">{escaped}</a>\n'
    return _html_page("Simple index", body)


def render_project_page(package_name: str, links: list[DistributionLink]) -> str:
    """Render the Simple API project page."""

    body_lines = []
    for link in links:
        href = html.escape(_href_with_hash(link), quote=True)
        filename = html.escape(link.filename)
        body_lines.append(f'  <a href="{href}">{filename}</a><br>\n')
    body = "".join(body_lines)
    return _html_page(f"Links for {package_name}", body)


def write_pages_site(
    site_dir: Path,
    *,
    package_name: str,
    links: list[DistributionLink],
    pages_base_url: str | None = None,
) -> None:
    """Write a static Pages site containing the Simple API index."""

    normalized = normalize_project_name(package_name)
    project_dir = site_dir / "simple" / normalized
    project_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "simple").mkdir(parents=True, exist_ok=True)

    (site_dir / ".nojekyll").write_text("", encoding="utf-8")
    (site_dir / "index.html").write_text(
        render_root_page(package_name, pages_base_url=pages_base_url),
        encoding="utf-8",
    )
    (site_dir / "simple" / "index.html").write_text(
        render_simple_root(package_name),
        encoding="utf-8",
    )
    (project_dir / "index.html").write_text(
        render_project_page(package_name, links),
        encoding="utf-8",
    )


def fetch_github_releases(
    *,
    repo: str,
    token: str | None,
    api_base: str = DEFAULT_API_BASE,
) -> list[dict[str, Any]]:
    """Fetch all GitHub Releases for a repository."""

    releases: list[dict[str, Any]] = []
    page = 1
    while True:
        url = f"{api_base.rstrip('/')}/repos/{repo}/releases?per_page=100&page={page}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "engram-pages-index-builder",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib_request.Request(url, headers=headers)
        try:
            with urllib_request.urlopen(
                request, timeout=HTTP_TIMEOUT_SECONDS
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib_error.HTTPError as exc:
            raise RuntimeError(
                f"Unable to fetch GitHub Releases: HTTP {exc.code}"
            ) from exc
        except urllib_error.URLError as exc:
            raise RuntimeError(
                f"Unable to fetch GitHub Releases: {exc.reason}"
            ) from exc

        if not isinstance(payload, list):
            raise RuntimeError("GitHub Releases API returned a non-list payload")
        if not payload:
            return releases
        releases.extend(payload)
        page += 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a GitHub Pages Python simple index from release assets"
    )
    parser.add_argument("--package-name", default=DEFAULT_PACKAGE_NAME)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("--dist-dir", type=Path, default=Path("dist"))
    parser.add_argument("--site-dir", type=Path, default=Path("site"))
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument(
        "--require-local-dist",
        action="store_true",
        help="Fail if no local dist files are found for the current release.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Pages simple-index generator."""

    parser = _build_parser()
    args = parser.parse_args(argv)

    repo = args.repo.strip()
    tag_name = args.tag.strip()
    if not repo:
        raise RuntimeError("Repository is required via --repo or GITHUB_REPOSITORY")
    if not tag_name:
        raise RuntimeError("Release tag is required via --tag or GITHUB_REF_NAME")

    releases = fetch_github_releases(
        repo=repo,
        token=args.github_token.strip() or None,
        api_base=args.api_base,
    )
    release_links = release_distribution_links(
        releases,
        package_name=args.package_name,
    )
    local_links = local_distribution_links(
        args.dist_dir,
        package_name=args.package_name,
        repo=repo,
        tag_name=tag_name,
    )
    if args.require_local_dist and not local_links:
        raise RuntimeError(f"No local distributions found in {args.dist_dir}")

    links = merge_distribution_links(release_links, local_links)
    if not links:
        raise RuntimeError("No distribution files found for the simple index")

    write_pages_site(
        args.site_dir,
        package_name=args.package_name,
        links=links,
        pages_base_url=github_pages_base_url(repo),
    )
    print(
        "Generated GitHub Pages simple index: "
        f"{len(links)} files for {args.package_name} in {args.site_dir}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
