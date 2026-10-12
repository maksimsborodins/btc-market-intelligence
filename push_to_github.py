"""
Utility to push the BTC Market Intelligence repository to GitHub.
Can create the repository automatically via GitHub REST API if it doesn't exist yet.
"""

import sys
import os
import json
import urllib.request
import urllib.error
import subprocess

def push_to_github(token: str, repo_name: str = "btc-market-intelligence", private: bool = True):
    token = token.strip()
    if not token:
        print("[ERROR] Token is empty.")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "BTC-Terminal-Agent",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # 1. Get authenticated user
    print("[*] Authenticating with GitHub API...")
    req = urllib.request.Request("https://api.github.com/user", headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            user_data = json.loads(resp.read().decode("utf-8"))
            username = user_data["login"]
            print(f"[+] Authenticated as GitHub user: @{username}")
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Authentication failed (HTTP {e.code}): {e.read().decode('utf-8')}")
        sys.exit(1)

    # 2. Check if repo exists or create it
    repo_url = f"https://api.github.com/repos/{username}/{repo_name}"
    req_repo = urllib.request.Request(repo_url, headers=headers)
    repo_exists = False
    try:
        with urllib.request.urlopen(req_repo) as resp:
            repo_exists = True
            print(f"[+] Repository '{username}/{repo_name}' already exists.")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            repo_exists = False
        else:
            print(f"[WARN] Error checking repo: {e}")

    if not repo_exists:
        print(f"[*] Creating new {'private' if private else 'public'} repository '{repo_name}'...")
        payload = json.dumps({
            "name": repo_name,
            "description": "BTC Market Intelligence v4.1 - Executive Bloomberg-style Terminal & Quant Pipeline",
            "private": private,
            "auto_init": False
        }).encode("utf-8")
        req_create = urllib.request.Request("https://api.github.com/user/repos", data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req_create) as resp:
                created_data = json.loads(resp.read().decode("utf-8"))
                print(f"[+] Repository created successfully: {created_data.get('html_url')}")
        except urllib.error.HTTPError as e:
            print(f"[ERROR] Failed to create repo (HTTP {e.code}): {e.read().decode('utf-8')}")
            sys.exit(1)

    # 3. Setup git remote with authenticated push URL
    git_dir = os.path.dirname(os.path.abspath(__file__))
    remote_auth_url = f"https://{username}:{token}@github.com/{username}/{repo_name}.git"
    public_clone_url = f"https://github.com/{username}/{repo_name}.git"

    # Ensure git executable path
    git_exe = "git"
    local_git = os.path.expanduser(r"~\AppData\Local\Programs\Git\cmd\git.exe")
    if os.path.exists(local_git):
        git_exe = local_git

    # Check existing remote
    remotes = subprocess.run([git_exe, "remote"], cwd=git_dir, capture_output=True, text=True).stdout.split()
    if "origin" in remotes:
        subprocess.run([git_exe, "remote", "set-url", "origin", remote_auth_url], cwd=git_dir, check=True)
    else:
        subprocess.run([git_exe, "remote", "add", "origin", remote_auth_url], cwd=git_dir, check=True)

    print(f"[*] Pushing 'main' branch to GitHub...")
    push_res = subprocess.run([git_exe, "push", "-u", "origin", "main", "--force"], cwd=git_dir, capture_output=True, text=True)
    
    # Clean remote url so token is not stored in plaintext inside .git/config
    subprocess.run([git_exe, "remote", "set-url", "origin", public_clone_url], cwd=git_dir)

    if push_res.returncode == 0:
        print("\n" + "=" * 60)
        print("[SUCCESS] Successfully pushed to GitHub!")
        print(f"Repository URL: https://github.com/{username}/{repo_name}")
        print("=" * 60)
    else:
        print(f"[ERROR] Git push failed:\n{push_res.stderr}")
        sys.exit(push_res.returncode)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        token = sys.argv[1]
        repo_name = sys.argv[2] if len(sys.argv) > 2 else "btc-market-intelligence"
        is_private = sys.argv[3].lower() != "public" if len(sys.argv) > 3 else True
        push_to_github(token, repo_name, is_private)
    else:
        print("Usage: python push_to_github.py <GITHUB_TOKEN> [repo_name] [private/public]")
