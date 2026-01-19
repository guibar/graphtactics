"""
GitHub Release Manager for Network Data.

This module provides utilities to synchronize road network files (.graphml)
between the local development environment and GitHub Releases. It serves two
primary purposes:
1. CI/CD / Deployment: Uploading local network data to a central repository.
2. Developer Setup: Downloading the necessary network data during
   initialization if local files are missing.

It uses the `PyGithub` library for API interaction and expects configuration
variables (tokens, tags, repo names) from `graphtactics.config`.
"""

from pathlib import Path

import requests
from github import Github, GithubException
from github.GitRelease import GitRelease
from github.Repository import Repository

from .config import (
    ALL_NETWORK_FILES,
    GITHUB_TOKEN,
    NETWORK_DIR,
    RELEASE_DESCRIPTION,
    RELEASE_NAME,
    RELEASE_TAG,
    REPO_NAME,
)


def create_or_get_release(repo: Repository, tag: str, name: str, description: str) -> GitRelease:
    """Ensure a GitHub Release exists for a specific tag.

    If a release with the given tag already exists, it is fetched and returned.
    Otherwise, a new release is created with the provided name and description.

    Args:
        repo: The GitHub Repository object to check/create in.
        tag: The unique version tag (e.g., 'v1.0.0').
        name: The display title for the release.
        description: A markdown-compatible description for the release logs.

    Returns:
        The GitRelease object (either existing or newly created).
    """
    try:
        # Check if the release is already published
        release = repo.get_release(tag)
        print(f"Found existing release: {tag}")
        return release
    except GithubException:
        # If get_release fails, we assume it doesn't exist and create a new one
        print(f"Creating new release: {tag}")
        release = repo.create_git_release(tag=tag, name=name, message=description, draft=False, prerelease=False)
        return release


def upload_files_to_release(release: GitRelease, files: list[str], network_dir: Path) -> None:
    """Upload a list of local files as assets to a specific GitHub Release.

    This function iterates through the provided filenames, checks for their
    existence locally, ensures they are not already uploaded to avoid
    duplicates, and performs the upload.

    Args:
        release: The target GitHub Release object.
        files: List of local filenames (relative to network_dir) to upload.
        network_dir: The local directory path where files are stored.
    """
    # Fetch existing assets once to optimize duplicate checking
    existing_assets: list[str] = [asset.name for asset in release.get_assets()]

    for filename in files:
        file_path = network_dir / filename

        # Skip if file is missing locally
        if not file_path.exists():
            print(f"⚠️  File not found locally: {file_path}")
            continue

        # Prevent duplicate uploads which would cause a GitHub API collision
        if filename in existing_assets:
            print(f"⚠️  Asset already exists on GitHub: {filename} (skipping)")
            continue

        print(f"📤 Uploading {filename}...")
        try:
            # application/octet-stream is used for binary .graphml files
            release.upload_asset(str(file_path), label=filename, content_type="application/octet-stream")
            print(f"✅ Uploaded {filename}")
        except GithubException as e:
            print(f"❌ Failed to upload {filename}: {e}")


def download_files(file_prefix: str, cache_dir: Path = NETWORK_DIR) -> bool:
    """Download network assets from GitHub if they are not already cached.

    This is called by the RoadNetworkFactory when a user requests a network
    that isn't available on their local disk. It uses the GitHub public API.

    Args:
        file_prefix: The identifier of the network (e.g., '60').
        cache_dir: Local path where the downloaded file should be stored.

    Returns:
        True if the file was found and downloaded, False if the download
        failed or the file was not found in the release.
    """
    graphml_path = cache_dir / f"{file_prefix}.graphml"

    try:
        # Initialize GitHub client
        # Note: Unauthenticated requests use a lower rate limit but work for
        # public repository metadata.
        g = Github()

        # Connect to the target repository and specific release version
        repo = g.get_repo(REPO_NAME)
        release = repo.get_release(RELEASE_TAG)

        # Iterate through release assets to find a matching filename
        graphml_asset = None
        for asset in release.get_assets():
            if asset.name == f"{file_prefix}.graphml":
                graphml_asset = asset
                break

        if not graphml_asset:
            print(f"⚠️ Asset not found for '{file_prefix}.graphml' in release {RELEASE_TAG}")
            return False

        # Execute the HTTP GET request to the browser_download_url
        print(f"📥 Downloading {graphml_asset.name}...")
        response = requests.get(graphml_asset.browser_download_url)
        response.raise_for_status()

        # Save the binary content to the local cache directory
        graphml_path.write_bytes(response.content)

        print(f"✅ Successfully downloaded '{file_prefix}.graphml' from GitHub")
        return True

    except GithubException as e:
        print(f"❌ GitHub API error for '{file_prefix}': {e}")
    except Exception as e:
        print(f"❌ Failed to download from GitHub for '{file_prefix}': {e}")

    # Integrity check: remove partial/corrupted files if download failed mid-way
    if graphml_path.exists():
        graphml_path.unlink()
    return False


def main():
    """Main execution routine for uploading network files.

    This should be run as a standalone script (e.g., in a CI workflow or
    manually by a developer) to publish new graph data.
    """
    # Validation: A token is required for WRITE access to the repository
    if not GITHUB_TOKEN:
        print("❌ Error: GITHUB_TOKEN environment variable not set")
        print("   A personal access token with 'repo' scope is required for uploads.")
        return 1

    # Connect using the provided credentials
    print("🔗 Connecting to GitHub...")
    g = Github(GITHUB_TOKEN)

    try:
        # Fetch repository metadata
        repo = g.get_repo(REPO_NAME)
        print(f"📦 Repository: {repo.full_name}")

        # Ensure the release exists before uploading
        release = create_or_get_release(repo, RELEASE_TAG, RELEASE_NAME, RELEASE_DESCRIPTION)

        # Perform the actual binary file uploads
        print(f"\n📁 Scanning local network directory: {NETWORK_DIR}")
        upload_files_to_release(release, ALL_NETWORK_FILES, NETWORK_DIR)

        # Print a summary of all assets currently in the release
        print("\n✅ Upload process complete. Assets available at:")
        for asset in release.get_assets():
            print(f"   {asset.browser_download_url}")

        return 0

    except GithubException as e:
        print(f"❌ GitHub API interaction failed: {e}")
        return 1
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
