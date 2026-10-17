"""User-triggered updates from Vector1239/atlas main, built away from live data."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

REPOSITORY = "Vector1239/atlas"
BUSY = {"checking", "preparing", "building", "installing", "restarting"}


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


class Updater:
    def __init__(self, root, resources, bundle=None, desktop_pid=None, backend_pid=None, state_dir=None):
        self.root = Path(root).resolve()
        self.resources = Path(resources).resolve()
        self.bundle = Path(bundle).resolve() if bundle else None
        self.desktop_pid = desktop_pid
        self.backend_pid = backend_pid
        self.state_dir = Path(state_dir) if state_dir else self.root / "germany-life-hermes/state"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.status_file = self.state_dir / "atlas_update.json"
        self.log_file = self.state_dir / "atlas-update.log"
        self.version = read_json(self.resources / "package.json", {}).get("version", "unknown")
        self.revision = read_json(self.resources / "build-info.json", {}).get("revision")
        self.guard = threading.Lock()

    def status(self):
        value = read_json(self.status_file, {"phase": "idle", "message": "Check for updates from GitHub main."})
        if value.get("phase") in BUSY and not alive(value.get("worker_pid")):
            value.update(phase="error", message="The update was interrupted. Check for updates to try again.")
        return {**value, "installed_revision": self.revision, "supported": sys.platform == "darwin" and self.bundle is not None,
                "running": value.get("phase") in BUSY, "repository": REPOSITORY}

    def write(self, phase, message, **extra):
        previous = read_json(self.status_file, {})
        value = {**previous, "phase": phase, "message": message, "worker_pid": os.getpid(), **extra}
        tmp = self.status_file.with_name(f".atlas_update.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(value))
        tmp.chmod(0o600)
        tmp.replace(self.status_file)
        print(message, flush=True)

    def launch(self, action):
        if action not in ("check", "install"):
            raise ValueError("Unknown update action.")
        if not self.status()["supported"]:
            raise ValueError("Open the installed Atlas Mac app to use updates.")
        with self.guard:
            if self.status()["running"]:
                raise ValueError("An update is already in progress.")
            # Copy the helper so replacing the app cannot remove its running code.
            helper = self.state_dir / "atlas_update_worker.py"
            shutil.copy2(Path(__file__), helper)
            self.write("checking" if action == "check" else "preparing",
                       "Checking GitHub…" if action == "check" else "Preparing the update…", error="")
            command = [sys.executable, "-u", str(helper), action, "--root", str(self.root),
                       "--resources", str(self.resources), "--bundle", str(self.bundle),
                       "--desktop-pid", str(self.desktop_pid or 0), "--backend-pid", str(self.backend_pid or 0)]
            try:
                with self.log_file.open("a") as log:
                    subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
            except Exception:
                self.write("error", "The update helper could not start.")
                raise

    def run(self, args, cwd=None, timeout=120, capture=False):
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GH_PROMPT_DISABLED": "1", "CI": "true"}
        result = subprocess.run([str(arg) for arg in args], cwd=cwd or self.root, env=env,
                                stdout=subprocess.PIPE if capture else None,
                                stderr=subprocess.PIPE if capture else None, text=True, timeout=timeout)
        if result.returncode:
            if capture and result.stderr:
                print(result.stderr[-3000:], file=sys.stderr, flush=True)
            raise RuntimeError(f"{Path(str(args[0])).name} failed (exit {result.returncode}). See the update log.")
        return result.stdout.strip() if capture else ""

    def git(self, *args, **kwargs):
        return self.run(["/usr/bin/git", *args], **kwargs)

    def validate_checkout(self):
        if Path(self.git("rev-parse", "--show-toplevel", capture=True)).resolve() != self.root:
            raise ValueError("The Atlas checkout could not be found.")
        origin = self.git("remote", "get-url", "origin", capture=True).removesuffix(".git").rstrip("/")
        if origin not in (f"https://github.com/{REPOSITORY}", f"git@github.com:{REPOSITORY}", f"ssh://git@github.com/{REPOSITORY}"):
            raise ValueError(f"Updates require origin to point to {REPOSITORY} on GitHub.")

    def fetch(self):
        gh = shutil.which("gh") or "/opt/homebrew/bin/gh"
        if not Path(gh).exists():
            raise ValueError("Install GitHub CLI and sign in with gh auth login to access this private repository.")
        self.git("-c", "credential.helper=", "-c", f"credential.helper=!{shlex.quote(gh)} auth git-credential",
                 "fetch", "--no-tags", "origin", "+refs/heads/main:refs/remotes/origin/main", timeout=90)

    def ancestor(self, older, newer):
        result = subprocess.run(["/usr/bin/git", "merge-base", "--is-ancestor", older, newer],
                                cwd=self.root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return result.returncode == 0

    def inspect(self):
        self.validate_checkout()
        self.fetch()
        target = self.git("rev-parse", "origin/main", capture=True)
        manifest = json.loads(self.git("show", f"{target}:app/package.json", capture=True))
        version = manifest["version"]
        branch = self.git("branch", "--show-current", capture=True)
        dirty = bool(self.git("status", "--porcelain", "--untracked-files=normal", capture=True))
        current = self.git("rev-parse", "HEAD", capture=True)
        available = target != self.revision
        if self.revision and self.ancestor(target, self.revision):
            available = False  # Do not replace a newer local build with an older main.
        can_install = branch == "main" and not dirty and self.ancestor(current, target)
        blocked = ""
        if dirty:
            blocked = "Commit or stash your local source changes before updating. Your work has not been changed."
        elif branch != "main":
            blocked = "Switch the Atlas checkout to main before updating."
        elif not self.ancestor(current, target):
            blocked = "Your local main has diverged from GitHub. Resolve it before updating."
        return {"available": available, "latest_version": version, "latest_revision": target,
                "installed_revision": self.revision, "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "can_install": can_install, "blocked_reason": blocked, "checkout_revision": current}

    def check(self):
        self.write("checking", "Checking GitHub…", error="")
        info = self.inspect()
        message = f"An update to Atlas {info['latest_version']} is available." if info["available"] else "Atlas is up to date."
        self.write("available" if info["available"] else "current", message, **info)
        return info

    def wait_for_exit(self, pid, timeout=25):
        if not pid or int(pid) <= 0:
            return
        until = time.monotonic() + timeout
        while alive(pid):
            if time.monotonic() >= until:
                raise RuntimeError("Atlas did not close in time. Reopen it and try updating again.")
            time.sleep(.2)

    def launch_app(self):
        executable = self.bundle / "Contents/MacOS/Atlas"
        with self.log_file.open("a") as log:
            proc = subprocess.Popen([str(executable)], stdout=log, stderr=log, start_new_session=True,
                                    env={**os.environ, "ATLAS_OPEN_UPDATES": "1"})
        return proc

    def wait_for_health(self, version, revision=None, timeout=40):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            runtime = read_json(self.state_dir / "atlas_runtime.json", {})
            if runtime.get("pid") != self.backend_pid and isinstance(runtime.get("port"), int):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{runtime['port']}/api/health", timeout=1) as response:
                        health = json.load(response)
                    if health.get("version") == version and (revision is None or health.get("revision") == revision):
                        return
                except (OSError, ValueError):
                    pass
            time.sleep(.3)
        raise RuntimeError("The updated app did not become ready. The previous version will be restored.")

    def install(self):
        self.write("preparing", "Checking the update before building…", error="")
        info = self.inspect()
        if not info["available"]:
            self.write("current", "Atlas is up to date.", **info)
            return
        if not info["can_install"]:
            raise ValueError(info["blocked_reason"])
        if not self.bundle or self.bundle.suffix != ".app" or not os.access(self.bundle.parent, os.W_OK):
            raise ValueError("Atlas cannot replace its installed app. Check that you can write to its Applications folder.")
        original_info = plistlib.loads((self.bundle / "Contents/Info.plist").read_bytes())
        if original_info.get("CFBundleIdentifier") != "local.atlas.assistant":
            raise ValueError("The installed app is not the expected Atlas bundle.")
        npm = shutil.which("npm") or "/opt/homebrew/bin/npm"
        if not Path(npm).exists():
            raise ValueError("Install Node.js to build Atlas updates.")
        target = info["latest_revision"]
        temp = Path(tempfile.mkdtemp(prefix="atlas-update-"))
        checkout = temp / "source"
        staging = None
        try:
            self.git("worktree", "add", "--detach", str(checkout), target)
            app_source = checkout / "app"
            self.write("building", "Installing the update’s build tools…", **info)
            self.run([npm, "ci"], cwd=app_source, timeout=600)
            self.write("building", "Building the new Atlas interface…")
            self.run([npm, "run", "build"], cwd=app_source, timeout=180)
            self.write("building", "Packaging the Mac app…")
            self.run([npm, "run", "package"], cwd=app_source, timeout=600)
            candidate = app_source / "release/Atlas-darwin-arm64/Atlas.app"
            manifest = plistlib.loads((candidate / "Contents/Info.plist").read_bytes())
            build = read_json(candidate / "Contents/Resources/app/build-info.json", {})
            if manifest.get("CFBundleIdentifier") != "local.atlas.assistant" or manifest.get("CFBundleShortVersionString") != info["latest_version"] or build.get("revision") != target:
                raise ValueError("The built app did not match the requested update.")
            self.run(["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(candidate)], timeout=120)
            self.run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(candidate)], timeout=60)
            # Recheck before touching the checkout or closing the running app.
            if self.git("rev-parse", "HEAD", capture=True) != info["checkout_revision"] or self.git("status", "--porcelain", capture=True):
                raise ValueError("The source checkout changed during the build. Your work is preserved; check for updates again.")
            staging = Path(tempfile.mkdtemp(prefix=".atlas-update-", dir=self.bundle.parent))
            staged_app = staging / "Atlas.app"
            self.run(["/usr/bin/ditto", str(candidate), str(staged_app)], timeout=120)
            self.write("installing", "Installing the update. Atlas will restart shortly…")
            # Fast-forward only: never reset, stash, clean, or overwrite user source changes.
            self.git("merge", "--ff-only", target)
            self.activate(staged_app, staging / "previous.app", info)
            self.run(["/bin/bash", str(self.root / "germany-life-hermes/install.sh"), "docker"], timeout=30)
            self.write("complete", "Atlas updated successfully.", available=False, can_install=False, error="")
        finally:
            if checkout.exists():
                with contextlib.suppress(Exception):
                    self.git("worktree", "remove", "--force", str(checkout), timeout=60)
            shutil.rmtree(temp, ignore_errors=True)
            if staging and not (staging / "previous.app").exists():
                shutil.rmtree(staging, ignore_errors=True)

    def activate(self, staged_app, backup, info):
        if alive(self.desktop_pid):
            os.kill(int(self.desktop_pid), signal.SIGTERM)
        self.wait_for_exit(self.desktop_pid)
        self.wait_for_exit(self.backend_pid)
        self.bundle.rename(backup)
        launched = None
        try:
            staged_app.rename(self.bundle)
            self.write("restarting", "Opening the updated Atlas…")
            launched = self.launch_app()
            self.wait_for_health(info["latest_version"], info["latest_revision"])
        except Exception:
            if launched and launched.poll() is None:
                launched.terminate()
                with contextlib.suppress(subprocess.TimeoutExpired):
                    launched.wait(timeout=10)
            if self.bundle.exists():
                self.bundle.rename(backup.parent / "failed.app")
            backup.rename(self.bundle)
            self.launch_app()
            raise
        shutil.rmtree(backup)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "install"))
    for name in ("root", "resources", "bundle"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--desktop-pid", type=int, default=0)
    parser.add_argument("--backend-pid", type=int, default=0)
    args = parser.parse_args()
    updater = Updater(args.root, args.resources, args.bundle, args.desktop_pid, args.backend_pid)
    with (updater.state_dir / "atlas-update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            updater.check() if args.action == "check" else updater.install()
        except Exception as exc:
            updater.write("error", str(exc), error=str(exc))


if __name__ == "__main__":
    main()
