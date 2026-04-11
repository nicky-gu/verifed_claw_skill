#!/usr/bin/env python3 -u
import json, urllib.request, subprocess, os, sys, time, base64
from concurrent.futures import ThreadPoolExecutor, as_completed

CWD = sys.argv[1] if len(sys.argv) > 1 else "."
PAT = os.environ.get("GITHUB_PAGES_PAT", "")
BRANCH = sys.argv[2] if len(sys.argv) > 2 else "main"

# Fallback: read PAT from /etc/environment
if not PAT:
    try:
        with open("/etc/environment") as f:
            for line in f:
                if line.startswith("GITHUB_PAGES_PAT="):
                    PAT = line.strip().split("=", 1)[1]
                    break
    except: pass

# Detect repo from git remote
r = subprocess.run(["git", "remote", "get-url", "origin"],
    capture_output=True, text=True, cwd=CWD)
url = r.stdout.strip()
clean = url.replace("https://", "").replace(".git", "")
if "@" in clean: clean = clean.split("@")[-1]
segments = clean.split("/")
repo_segments = [s for s in segments[1:] if s and s not in ("github.com", "gitee.com")]
repo = "/".join(repo_segments[:2])

API = f"https://api.github.com/repos/{repo}"

print("1. Checking remote...", flush=True)
hdrs = {"Authorization": f"token {PAT}", "Accept": "application/vnd.github.v3+json", "User-Agent": "push/1.0"}
req = urllib.request.Request(f"{API}/git/ref/heads/main", headers=hdrs)
with urllib.request.urlopen(req, timeout=15) as resp:
    ref = json.loads(resp.read())
remote_sha = ref["object"]["sha"]
print(f"   Remote: {remote_sha[:12]}", flush=True)

print("2. Checking local...", flush=True)
local = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=CWD)
local_sha = local.stdout.strip()
print(f"   Local:  {local_sha[:12]}", flush=True)

if remote_sha == local_sha:
    print("Already up to date!")
    sys.exit(0)

print("3. Getting files...", flush=True)
r = subprocess.run(["git", "ls-tree", "-r", "--full-tree", "HEAD"], capture_output=True, cwd=CWD)
tree_lines = [l for l in r.stdout.decode().strip().split("\n") if l.strip()]
print(f"   Files: {len(tree_lines)}", flush=True)

print("4. Reading file contents...", flush=True)
file_data = []
for i, line in enumerate(tree_lines):
    parts = line.split(None, 3)
    mode, blob_sha, path = parts[0], parts[2], parts[3]
    content = subprocess.run(["git", "cat-file", "blob", blob_sha], capture_output=True, cwd=CWD).stdout
    file_data.append((mode, blob_sha, path, content))
    if (i+1) % 200 == 0:
        print(f"   {i+1}/{len(tree_lines)}", flush=True)
print(f"   All {len(file_data)} files read", flush=True)

print("5. Uploading blobs...", flush=True)
results = []
failed = []
start = time.time()

def upload(idx, item):
    mode, blob_sha, path, content = item
    # Check existing
    try:
        req = urllib.request.Request(f"{API}/git/blobs/{blob_sha}", headers=hdrs)
        urllib.request.urlopen(req, timeout=10)
        return path, mode, blob_sha, True
    except:
        pass
    # Upload new
    b64 = base64.b64encode(content).decode()
    data = json.dumps({"content": b64, "encoding": "base64"}).encode()
    req = urllib.request.Request(f"{API}/git/blobs", data=data,
        headers={**hdrs, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            blob = json.loads(resp.read())
            return path, mode, blob["sha"], True
    except Exception as e:
        return path, mode, None, False

with ThreadPoolExecutor(max_workers=8) as ex:
    futures = {ex.submit(upload, i, item): i for i, item in enumerate(file_data)}
    done = 0
    for future in as_completed(futures):
        path, mode, sha, ok = future.result()
        if ok:
            results.append({"path": path, "mode": mode, "type": "blob", "sha": sha})
        else:
            failed.append(path)
        done += 1
        if done % 100 == 0:
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0
            eta = (len(file_data) - done) / rate / 60 if rate > 0 else 0
            print(f"   {done}/{len(file_data)} ({rate:.0f}/s, ETA {eta:.1f}min)", flush=True)

elapsed = time.time() - start
print(f"   Done: {len(results)} ok, {len(failed)} failed, {elapsed:.0f}s", flush=True)

if failed:
    print(f"ERROR: {len(failed)} files failed: {failed[:5]}")
    sys.exit(1)

print("6. Creating tree...", flush=True)
tree_items = results
tree_sha = None
for i in range(0, len(tree_items), 500):
    batch = tree_items[i:i+500]
    data = {"tree": batch}
    if tree_sha: data["base_tree"] = tree_sha
    req = urllib.request.Request(f"{API}/git/trees", data=json.dumps(data).encode(),
        headers={**hdrs, "Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        tr = json.loads(resp.read())
        tree_sha = tr["sha"]
print(f"   Tree: {tree_sha[:12]}", flush=True)

print("7. Creating commit...", flush=True)
msg = f"Full scan data + site updates\n\nIncludes {len(file_data)} files (41 audit chunks + 643 EXTREME details + 39 findings batches + site code)"
data = json.dumps({"message": msg, "parents": [remote_sha], "tree": tree_sha}).encode()
req = urllib.request.Request(f"{API}/git/commits", data=data,
    headers={**hdrs, "Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=30) as resp:
    cr = json.loads(resp.read())
print(f"   Commit: {cr['sha'][:12]}", flush=True)

print("8. Updating ref...", flush=True)
data = json.dumps({"sha": cr["sha"], "force": True}).encode()
req = urllib.request.Request(f"{API}/git/refs/heads/main", data=data,
    headers={**hdrs, "Content-Type": "application/json"}, method="PATCH")
with urllib.request.urlopen(req, timeout=15) as resp:
    rr = json.loads(resp.read())
print(f"   Ref: {rr['object']['sha'][:12]}", flush=True)

print(f"\n✅ Push complete! {len(results)} files in {elapsed:.0f}s", flush=True)
