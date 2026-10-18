"""Atlas's connection to Hermes. Hermes owns the agent and the local model; Atlas only asks.

- Gateway: the background service. Atlas starts/stops it with the `hermes gateway` CLI and runs
  chat turns through its API server (POST /v1/runs, SSE events, stop, approvals).
- Model server: the llama.cpp router Hermes manages (~/.hermes/runtimes/llamacpp/server.json).
  Atlas reads its status, loads/unloads Gemma, and sends plain completions for tool-free work
  such as briefs and translations.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

TERMINAL_EVENTS = {"run.completed", "run.failed", "run.cancelled", "run.interrupted"}


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def _request(url, *, key="", body=None, timeout=10.0, stream=False):
    headers = {"Accept": "text/event-stream" if stream else "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    response = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout)
    if stream:
        return response
    with response:
        raw = response.read()
    return json.loads(raw) if raw else {}


# ---------------------------------------------------------------- gateway + API server

def read_env() -> dict:
    values = {}
    try:
        lines = (hermes_home() / ".env").read_text().splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name.strip().removeprefix("export ").strip()] = value.strip().strip("'\"")
    return values


def api_config() -> dict:
    env = read_env()
    try:
        port = int(env.get("API_SERVER_PORT") or 8642)
    except ValueError:
        port = 8642
    enabled = env.get("API_SERVER_ENABLED", "").lower() in ("1", "true", "yes", "on")
    return {"enabled": enabled and bool(env.get("API_SERVER_KEY")), "key": env.get("API_SERVER_KEY", ""),
            "base": f"http://127.0.0.1:{port}"}


def enable_api() -> bool:
    """Turn on the gateway's API server for Atlas (owner-only .env). True when something changed."""
    path = hermes_home() / ".env"
    current = read_env()
    wanted = {"API_SERVER_ENABLED": "true", "API_SERVER_KEY": current.get("API_SERVER_KEY") or secrets.token_urlsafe(32)}
    if all(current.get(k) == v for k, v in wanted.items()):
        return False
    try:
        lines = path.read_text().splitlines()
    except OSError:
        lines = []
    kept = [line for line in lines if line.split("=", 1)[0].strip().removeprefix("export ").strip() not in wanted]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(".env.atlas-tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write("\n".join(kept + [f"{k}={v}" for k, v in wanted.items()]) + "\n")
    os.replace(tmp, path)
    return True


class Gateway:
    def __init__(self, binary):
        self.binary = Path(binary)

    def healthy(self, timeout=0.5) -> bool:
        cfg = api_config()
        if not cfg["enabled"]:
            return False
        try:
            return _request(cfg["base"] + "/health", timeout=timeout).get("status") == "ok"
        except Exception:
            return False

    def _cli(self, *args, timeout=60):
        if not self.binary.exists() and not shutil.which("hermes"):
            raise ValueError("Hermes is not installed. Install it first (see SETUP-macOS.md).")
        binary = str(self.binary) if self.binary.exists() else shutil.which("hermes")
        result = subprocess.run([binary, *args], capture_output=True, text=True, timeout=timeout)
        return result.returncode, (result.stdout + result.stderr).strip()

    def start(self, wait=45.0):
        if self.healthy():
            return
        if not api_config()["enabled"]:
            raise ValueError("Connect Atlas to Hermes first (Settings → Hermes → Connect).")
        code, output = self._cli("gateway", "start")
        if code:
            raise ValueError("The Hermes gateway service could not start. If it isn't installed yet, run "
                             "`hermes gateway install` once in Terminal. " + output[-300:])
        until = time.monotonic() + wait
        while time.monotonic() < until:
            if self.healthy():
                return
            time.sleep(1)
        raise TimeoutError("The Hermes gateway started but its API did not answer. Check `hermes gateway status`.")

    def stop(self):
        code, output = self._cli("gateway", "stop")
        if code and self.healthy():
            raise ValueError("The Hermes gateway did not stop: " + output[-300:])

    def restart(self):
        code, output = self._cli("gateway", "restart", timeout=90)
        if code:
            raise ValueError("The Hermes gateway did not restart: " + output[-300:])


# ---------------------------------------------------------------- agent runs

def create_run(text, *, session_id, instructions="", model="", provider="", reasoning=""):
    cfg = api_config()
    body = {"input": text, "session_id": session_id}
    if instructions:
        body["instructions"] = instructions
    if model:
        body.update(model=model, provider=provider or "llamacpp")
    if reasoning:
        body["model_options"] = {"reasoning_effort": reasoning}
    return _request(cfg["base"] + "/v1/runs", key=cfg["key"], body=body, timeout=30)["run_id"]


def run_events(run_id, read_timeout=120.0):
    """Yield the run's SSE events (dicts) until a terminal one. Keepalive comments are skipped."""
    cfg = api_config()
    response = _request(f"{cfg['base']}/v1/runs/{urllib.parse.quote(run_id)}/events", key=cfg["key"],
                        timeout=read_timeout, stream=True)
    with response:
        data = []
        for raw in response:
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line and data:
                try:
                    event = json.loads("\n".join(data))
                except ValueError:
                    event = None
                data = []
                if isinstance(event, dict):
                    yield event
                    if event.get("event") in TERMINAL_EVENTS:
                        return


def stop_run(run_id):
    cfg = api_config()
    _request(f"{cfg['base']}/v1/runs/{urllib.parse.quote(run_id)}/stop", key=cfg["key"], body={}, timeout=10)


def decline_pending(run_id) -> list[str]:
    """Answer approval/clarify prompts Atlas has no UI for: deny commands, ask to continue."""
    cfg = api_config()
    status = _request(f"{cfg['base']}/v1/runs/{urllib.parse.quote(run_id)}", key=cfg["key"], timeout=10)
    handled = []
    for control in status.get("pending_controls", []) or []:
        identity = {"request_id": control.get("prompt_id"), "execution_generation": control.get("execution_generation")}
        if control.get("kind") == "approval":
            _request(f"{cfg['base']}/v1/runs/{urllib.parse.quote(run_id)}/approval", key=cfg["key"],
                     body={**identity, "choice": "deny"}, timeout=10)
            handled.append("approval")
        elif control.get("kind") == "clarify":
            _request(f"{cfg['base']}/v1/runs/{urllib.parse.quote(run_id)}/clarify", key=cfg["key"],
                     body={**identity, "answer": "Atlas can't answer follow-up questions mid-task. Continue with your best judgement and state any assumption."},
                     timeout=10)
            handled.append("clarify")
    return handled


# ---------------------------------------------------------------- managed model server

def model_id(filename) -> str:
    return Path(filename).stem


def staged(filename) -> bool:
    return (hermes_home() / "models" / filename).is_file()


def router():
    """(root URL, api key) of Hermes's model server, or None when it isn't running."""
    try:
        state = json.loads((hermes_home() / "runtimes/llamacpp/server.json").read_text())
    except (OSError, ValueError):
        return None
    base = str(state.get("base_url") or "")
    if not base.startswith("http://127.0.0.1:") and not base.startswith("http://localhost:"):
        return None
    return base.rsplit("/v1", 1)[0].rstrip("/"), str(state.get("api_key") or "")


def model_state(mid, timeout=1.0) -> str:
    """ready | loading | stopped | not_staged | offline."""
    endpoint = router()
    if endpoint is None:
        return "offline"
    try:
        rows = _request(endpoint[0] + "/models", key=endpoint[1], timeout=timeout).get("data", [])
    except Exception:
        return "offline"
    for row in rows:
        if row.get("id") == mid:
            value = (row.get("status") or {}).get("value", "")
            return "ready" if value in ("loaded", "ready") else "loading" if value == "loading" else "stopped"
    return "not_staged"


def load(mid, timeout=600):
    endpoint = router()
    if endpoint is None:
        raise ValueError("Hermes's model server is not running. Start the Hermes gateway first.")
    _request(endpoint[0] + "/models/load", key=endpoint[1], body={"model": mid}, timeout=timeout)


def unload(mid):
    endpoint = router()
    if endpoint is not None:
        _request(endpoint[0] + "/models/unload", key=endpoint[1], body={"model": mid}, timeout=120)


def busy(mid):
    """True while any slot is generating (a chat, brief or scheduled job); None when unknown."""
    endpoint = router()
    if endpoint is None:
        return None
    try:
        slots = _request(f"{endpoint[0]}/slots?model={urllib.parse.quote(mid)}&autoload=false",
                         key=endpoint[1], timeout=2)
    except Exception:
        return None
    return any(isinstance(slot, dict) and slot.get("is_processing") for slot in slots) if isinstance(slots, list) else None


def complete(mid, payload, *, timeout=120, stream=False):
    """OpenAI-style chat completion on the managed model (no agent, no tools)."""
    endpoint = router()
    if endpoint is None:
        raise ValueError("Hermes's model server is not running. Start the Hermes gateway first.")
    return _request(endpoint[0] + "/v1/chat/completions", key=endpoint[1],
                    body={**payload, "model": mid, "stream": stream}, timeout=timeout, stream=stream)
