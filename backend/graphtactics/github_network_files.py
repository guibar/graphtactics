"""
Upload network files to GitHub releases.

This script uploads .graphml and .gpkg files to a GitHub release.
Customize the REPO, TAG, and FILES_TO_UPLOAD as needed.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from github import Github, GithubException

from .app import AVAILABLE_NETWORKS

# Load environment variables from .env file
load_dotenv()

# Configuration - modify these variables
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = "NEOTac/backend"
RELEASE_TAG = "osm-networks-v1.0"
RELEASE_NAME = "Network Files v1.0."
RELEASE_DESCRIPTION = "Pre-generated network files some areas"

# Directory containing network files
NETWORK_DIR = Path(__file__).parent.parent / "data" / "networks"

# Files to upload (modify this list)
FILES_TO_UPLOAD = [f"{name}.graphml" for name in AVAILABLE_NETWORKS] + [f"{name}.gpkg" for name in AVAILABLE_NETWORKS]


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
        upload_files_to_release(release, FILES_TO_UPLOAD, NETWORK_DIR)

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
