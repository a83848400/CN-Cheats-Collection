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
body_text = "Auto‑translated cheats from chinese‑build branch\nREADME from master branch.\nContains translated json/shn cheats, mc4 files are untouched."

print(f"zip文件路径: {zip_path}")
print(f"文件是否存在: {os.path.exists(zip_path)}")
if os.path.exists(zip_path):
    stat_info = os.stat(zip_path)
    print(f"zip大小(bytes): {stat_info.st_size}")

try:
    existing_release = repo.get_release(tag)
    print(f"Release {tag} already exists, skip create.")
except Exception:
    print(f"Creating new release tag:{tag}")
    new_release = repo.create_git_release(
        tag,
        name=title,
        message=body_text,
        draft=False,
        prerelease=False
    )
    new_release.upload_asset(path=zip_path, content_type="application/zip")
    print(f"✅ Release created successfully: {tag}")
