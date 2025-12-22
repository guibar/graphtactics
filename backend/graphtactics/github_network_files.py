"""
Upload network files to GitHub releases.

This script uploads .graphml and .gpkg files to a GitHub release.
Customize the REPO, TAG, and FILES_TO_UPLOAD as needed.
"""

from pathlib import Path

import requests
from github import Github, GithubException

from .config import (
    ALL_NETWORK_FILES,
    GITHUB_TOKEN,
    NETWORK_DIR,
    RELEASE_DESCRIPTION,
    RELEASE_NAME,
    RELEASE_TAG,
    REPO_NAME,
)


def create_or_get_release(repo, tag: str, name: str, description: str):
    """
    Create a new release or get existing one.

    Args:
        repo: GitHub repository object
        tag: Release tag name
        name: Release name
        description: Release description

    Returns:
        GitHub release object
    """
    try:
        # Try to get existing release
        release = repo.get_release(tag)
        print(f"Found existing release: {tag}")
        return release
    except GithubException:
        # Create new release if it doesn't exist
        print(f"Creating new release: {tag}")
        release = repo.create_git_release(tag=tag, name=name, message=description, draft=False, prerelease=False)
        return release


def upload_files_to_release(release, files: list[str], network_dir: Path):
    """
    Upload files to a GitHub release.

    Args:
        release: GitHub release object
        files: List of filenames to upload
        network_dir: Directory containing the files
    """
    for filename in files:
        file_path = network_dir / filename

        if not file_path.exists():
            print(f"⚠️  File not found: {file_path}")
            continue

        # Check if asset already exists
        existing_assets = [asset.name for asset in release.get_assets()]
        if filename in existing_assets:
            print(f"⚠️  Asset already exists: {filename} (skipping)")
            continue

        print(f"📤 Uploading {filename}...")
        try:
            release.upload_asset(str(file_path), label=filename, content_type="application/octet-stream")
            print(f"✅ Uploaded {filename}")
        except GithubException as e:
            print(f"❌ Failed to upload {filename}: {e}")


def download_files(file_prefix: str, cache_dir: Path = NETWORK_DIR) -> bool:
    """Download network files from GitHub releases if available.

    Args:
        file_prefix: Network identifier (filename prefix)
        cache_dir: Directory to save the files

    Returns:
        True if files were successfully downloaded, False otherwise
    """
    graphml_path = cache_dir / f"{file_prefix}.graphml"
    gpkg_path = cache_dir / f"{file_prefix}.gpkg"

    try:
        # Initialize GitHub client (read-only, no token needed for public repos)
        g = Github()

        # Get repository
        repo = g.get_repo(REPO_NAME)

        release = repo.get_release(RELEASE_TAG)

        # Find and download the assets
        graphml_asset = None
        gpkg_asset = None

        for asset in release.get_assets():
            if asset.name == f"{file_prefix}.graphml":
                graphml_asset = asset
            elif asset.name == f"{file_prefix}.gpkg":
                gpkg_asset = asset

        if not graphml_asset or not gpkg_asset:
            print(f"⚠️ Assets not found for '{file_prefix}' in release {RELEASE_TAG}")
            return False

        # Download graphml
        print(f"📥 Downloading {graphml_asset.name}...")
        response = requests.get(graphml_asset.browser_download_url)
        response.raise_for_status()
        graphml_path.write_bytes(response.content)

        # Download gpkg
        print(f"📥 Downloading {gpkg_asset.name}...")
        response = requests.get(gpkg_asset.browser_download_url)
        response.raise_for_status()
        gpkg_path.write_bytes(response.content)

        print(f"✅ Successfully downloaded files for '{file_prefix}' from GitHub")
        return True

    except GithubException as e:
        print(f"❌ GitHub error for '{file_prefix}': {e}")
    except Exception as e:
        print(f"❌ Failed to download from GitHub for '{file_prefix}': {e}")

    # Clean up partial downloads (only reached if exception occurred)
    if graphml_path.exists():
        graphml_path.unlink()
    if gpkg_path.exists():
        gpkg_path.unlink()
    return False


def main():
    """Main entry point."""
    # Check for GitHub token
    if not GITHUB_TOKEN:
        print("❌ Error: GITHUB_TOKEN environment variable not set")
        print("   Set it with: export GITHUB_TOKEN='your_token_here'")
        return 1

    # Initialize GitHub client
    print("🔗 Connecting to GitHub...")
    g = Github(GITHUB_TOKEN)

    try:
        # Get repository
        repo = g.get_repo(REPO_NAME)
        print(f"📦 Repository: {repo.full_name}")

        # Create or get release
        release = create_or_get_release(repo, RELEASE_TAG, RELEASE_NAME, RELEASE_DESCRIPTION)

        # Upload files
        print(f"\n📁 Network directory: {NETWORK_DIR}")
        upload_files_to_release(release, ALL_NETWORK_FILES, NETWORK_DIR)

        # Print download URLs
        print("\n✅ Done! Files available at:")
        for asset in release.get_assets():
            print(f"   {asset.browser_download_url}")

        return 0

    except GithubException as e:
        print(f"❌ GitHub error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
