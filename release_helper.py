#!/usr/bin/env python3
import os
from github import Github

token = os.environ["GITHUB_TOKEN"]
repo_name = os.environ["GITHUB_REPOSITORY"]
tag = os.environ["TAG_NAME"]
zip_path = "CN-Cheats-Collection.zip"

g = Github(token)
repo = g.get_repo(repo_name)
title = f"CN‑Cheats‑Collection {tag}"
body_text = "Auto‑translated cheats from chinese‑build branch"

try:
    existing_release = repo.get_release(tag)
    print(f"Release {tag} already exists, skip create.")
except Exception:
    print(f"Start create new release tag:{tag}")
    new_release = repo.create_git_release(
        tag_name=tag,
        name=title,
        body=body_text,
        draft=False,
        prerelease=False
    )
    new_release.upload_asset(path=zip_path, content_type="application/zip")
    print(f"✅ Release created successfully: {tag}")
