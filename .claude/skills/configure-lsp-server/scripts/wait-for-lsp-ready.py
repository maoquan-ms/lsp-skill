#!/usr/bin/env python3
"""
Wait for jdtls (Java LSP) to finish indexing a project.

Starts jdtls, sends LSP initialize/initialized, monitors progress
notifications, and exits when the server reports readiness. This warms
the jdtls workspace cache so subsequent LSP starts are faster.

Usage:
    python3 wait-for-lsp-ready.py --project-dir /path/to/java/project
    python3 wait-for-lsp-ready.py --project-dir . --timeout 600
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# ── helpers ──────────────────────────────────────────────────────────

def info(msg):
    print(f"\033[1;32m[INFO]\033[0m  {msg}", flush=True)

def warn(msg):
    print(f"\033[1;33m[WARN]\033[0m  {msg}", flush=True)

def error(msg):
    print(f"\033[1;31m[ERROR]\033[0m {msg}", file=sys.stderr, flush=True)

# ── JSON-RPC / LSP transport ────────────────────────────────────────

def encode_message(obj: dict) -> bytes:
    body = json.dumps(obj).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n"
    return header.encode("ascii") + body


def read_message(stream) -> dict | None:
    """Read one LSP message from *stream* (blocking)."""
    headers = {}
    while True:
        line = stream.readline()
        if not line:
            return None  # EOF
        line = line.strip()
        if line == b"":
            break
        if b":" in line:
            key, _, val = line.partition(b":")
            headers[key.strip().lower()] = val.strip()
    length = int(headers.get(b"content-length", 0))
    if length == 0:
        return None
    body = b""
    while len(body) < length:
        chunk = stream.read(length - len(body))
        if not chunk:
            return None
        body += chunk
    return json.loads(body)

# ── LSP Client ──────────────────────────────────────────────────────

class MinimalLSPClient:
    """Minimal LSP client that monitors jdtls indexing progress."""

    def __init__(self, project_dir: str, jdtls_cmd: str = "jdtls",
                 timeout: int = 300):
        self.project_dir = os.path.abspath(project_dir)
        self.jdtls_cmd = jdtls_cmd
        self.timeout = timeout
        self._request_id = 0
        self._proc = None
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._init_done = threading.Event()
        self._active_progress_tokens: set = set()
        self._last_status = ""
        self._last_activity = time.time()
        self._diagnostics_received = False
        self._error_msg = None

    # ── lifecycle ────────────────────────────────────────────────────

    def run(self) -> bool:
        """Start jdtls, wait for indexing, return True if ready."""
        info(f"Starting jdtls for project: {self.project_dir}")
        try:
            self._proc = subprocess.Popen(
                [self.jdtls_cmd],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.project_dir,
            )
        except FileNotFoundError:
            error(f"'{self.jdtls_cmd}' not found. Install it first.")
            return False

        # Start stderr reader (for debug)
        stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        stderr_thread.start()

        # Send initialize
        self._send_initialize()

        # Read messages in a loop
        reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        reader_thread.start()

        # Wait for init response
        if not self._init_done.wait(timeout=30):
            error("Timed out waiting for initialize response")
            self._shutdown()
            return False

        # Send initialized notification
        self._send_notification("initialized", {})
        info("LSP initialized, waiting for indexing to complete...")

        # Wait for readiness
        ready = self._ready.wait(timeout=self.timeout)
        if ready:
            info("Indexing complete! Waiting for cache flush...")
            time.sleep(3)  # let background writes finish
            self._shutdown()
            return True
        else:
            error(f"Timed out after {self.timeout}s waiting for indexing")
            self._print_timeout_diagnostics()
            self._shutdown()
            return False

    # ── initialize ───────────────────────────────────────────────────

    def _send_initialize(self):
        root_uri = Path(self.project_dir).as_uri()
        self._send_request("initialize", {
            "processId": os.getpid(),
            "rootUri": root_uri,
            "rootPath": self.project_dir,
            "capabilities": {
                "workspace": {
                    "workspaceFolders": True,
                    "configuration": True,
                    "didChangeConfiguration": {
                        "dynamicRegistration": True,
                    },
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True,
                    },
                    "completion": {
                        "completionItem": {
                            "snippetSupport": False,
                        },
                    },
                    "hover": {"contentFormat": ["plaintext"]},
                    "definition": {"dynamicRegistration": True},
                    "references": {"dynamicRegistration": True},
                    "implementation": {"dynamicRegistration": True},
                    "documentSymbol": {"dynamicRegistration": True},
                    "publishDiagnostics": {"relatedInformation": True},
                },
                "window": {
                    "workDoneProgress": True,
                    "showMessage": {
                        "messageActionItem": {"additionalPropertiesSupport": False},
                    },
                },
            },
            "workspaceFolders": [
                {"uri": root_uri, "name": os.path.basename(self.project_dir)},
            ],
        })

    # ── message sending ──────────────────────────────────────────────

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send_request(self, method: str, params: dict) -> int:
        rid = self._next_id()
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        self._write(msg)
        return rid

    def _send_notification(self, method: str, params: dict):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._write(msg)

    def _send_response(self, req_id, result):
        msg = {"jsonrpc": "2.0", "id": req_id, "result": result}
        self._write(msg)

    def _send_error_response(self, req_id, code: int, message: str):
        msg = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        self._write(msg)

    def _write(self, msg: dict):
        if self._proc and self._proc.stdin:
            data = encode_message(msg)
            try:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    # ── message reading ──────────────────────────────────────────────

    def _read_loop(self):
        while self._proc and self._proc.poll() is None:
            msg = read_message(self._proc.stdout)
            if msg is None:
                break
            self._handle_message(msg)

        # Process exited
        if self._proc:
            rc = self._proc.poll()
            if rc is not None and rc != 0 and not self._ready.is_set():
                self._error_msg = f"jdtls exited with code {rc}"
                error(self._error_msg)
                self._ready.set()  # unblock waiter

    def _read_stderr(self):
        """Drain stderr to prevent pipe blocking."""
        while self._proc and self._proc.poll() is None:
            line = self._proc.stderr.readline()
            if not line:
                break
            # Silently consume stderr

    # ── message handling ─────────────────────────────────────────────

    def _handle_message(self, msg: dict):
        self._last_activity = time.time()

        # Response to our request
        if "id" in msg and "method" not in msg:
            self._handle_response(msg)
            return

        method = msg.get("method", "")

        # Server→client requests (need a response)
        if "id" in msg:
            self._handle_server_request(msg["id"], method, msg.get("params", {}))
            return

        # Notifications
        self._handle_notification(method, msg.get("params", {}))

    def _handle_response(self, msg: dict):
        if msg.get("id") == 1:  # initialize response
            info("Initialize response received")
            self._init_done.set()

    def _handle_server_request(self, req_id, method: str, params: dict):
        """Respond to server→client requests with safe defaults."""
        if method == "window/workDoneProgress/create":
            self._send_response(req_id, None)
        elif method == "client/registerCapability":
            self._send_response(req_id, None)
        elif method == "client/unregisterCapability":
            self._send_response(req_id, None)
        elif method == "workspace/configuration":
            items = params.get("items", [])
            self._send_response(req_id, [None] * len(items))
        elif method == "workspace/workspaceFolders":
            root_uri = Path(self.project_dir).as_uri()
            self._send_response(req_id, [
                {"uri": root_uri, "name": os.path.basename(self.project_dir)},
            ])
        elif method == "window/showMessageRequest":
            self._send_response(req_id, None)
        else:
            # Unknown request — respond with method-not-found
            self._send_error_response(req_id, -32601, f"Method not supported: {method}")

    def _handle_notification(self, method: str, params: dict):
        if method == "language/status":
            self._on_language_status(params)
        elif method == "$/progress":
            self._on_progress(params)
        elif method == "textDocument/publishDiagnostics":
            self._diagnostics_received = True
        elif method == "window/logMessage":
            pass  # silently consume
        elif method == "window/showMessage":
            msg_text = params.get("message", "")
            if msg_text:
                info(f"Server message: {msg_text}")

    def _on_language_status(self, params: dict):
        status_type = params.get("type", "")
        message = params.get("message", "")
        self._last_status = f"{status_type}: {message}"

        if status_type == "Starting" or "Starting" in message:
            info(f"Language server starting: {message}")
        elif status_type == "Message":
            info(f"Status: {message}")
        elif "ServiceReady" in message or status_type == "Started":
            info(f"Service ready! ({message})")
            self._ready.set()

    def _on_progress(self, params: dict):
        token = params.get("token", "")
        value = params.get("value", {})
        kind = value.get("kind", "")

        if kind == "begin":
            title = value.get("title", "")
            self._active_progress_tokens.add(token)
            info(f"Progress started: {title}")
        elif kind == "report":
            message = value.get("message", "")
            percentage = value.get("percentage")
            parts = []
            if message:
                parts.append(message)
            if percentage is not None:
                parts.append(f"{percentage}%")
            if parts:
                info(f"Progress: {' - '.join(parts)}")
        elif kind == "end":
            message = value.get("message", "")
            self._active_progress_tokens.discard(token)
            info(f"Progress done: {message}")

            # Fallback: if all progress tokens are done and we haven't
            # received ServiceReady yet, check after a quiet period
            if not self._active_progress_tokens and not self._ready.is_set():
                threading.Timer(10.0, self._check_quiet_ready).start()

    def _check_quiet_ready(self):
        """If no progress tokens are active for a while, assume ready."""
        if self._ready.is_set():
            return
        if not self._active_progress_tokens:
            elapsed_quiet = time.time() - self._last_activity
            if elapsed_quiet >= 8:
                info("No active progress for 10s — assuming indexing complete (fallback)")
                self._ready.set()

    # ── shutdown ─────────────────────────────────────────────────────

    def _shutdown(self):
        if not self._proc or self._proc.poll() is not None:
            return
        try:
            self._send_request("shutdown", {})
            time.sleep(1)
            self._send_notification("exit", {})
            self._proc.wait(timeout=5)
        except Exception:
            pass
        finally:
            if self._proc.poll() is None:
                self._proc.terminate()
                try:
                    self._proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self._proc.kill()

    # ── diagnostics on timeout ───────────────────────────────────────

    def _print_timeout_diagnostics(self):
        warn("=== Timeout Diagnostics ===")
        warn(f"  Last status: {self._last_status or '(none)'}")
        warn(f"  Active progress tokens: {len(self._active_progress_tokens)}")
        if self._active_progress_tokens:
            for t in self._active_progress_tokens:
                warn(f"    - {t}")
        warn(f"  Diagnostics received: {self._diagnostics_received}")
        warn(f"  Time since last activity: {time.time() - self._last_activity:.1f}s")
        warn("Suggestions:")
        warn("  - Try increasing --timeout for very large projects")
        warn("  - Run 'mvn install' or 'gradle build' to resolve dependencies first")
        warn("  - Check Java version: jdtls requires JDK 17+")


# ── main ─────────────────────────────────────────────────────────────

def find_jdtls_cmd() -> str:
    """Resolve jdtls command from config or PATH."""
    # Check repo-level config
    for config_path in [".github/lsp.json", os.path.expanduser("~/.copilot/lsp-config.json")]:
        if os.path.isfile(config_path):
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                java_cfg = cfg.get("lspServers", {}).get("java", {})
                cmd = java_cfg.get("command", "")
                if cmd:
                    return cmd
            except (json.JSONDecodeError, IOError):
                pass
    return "jdtls"


def main():
    parser = argparse.ArgumentParser(
        description="Wait for jdtls to finish indexing a Java project"
    )
    parser.add_argument(
        "--project-dir", "-p",
        default=".",
        help="Path to the Java project root (default: current directory)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=300,
        help="Max seconds to wait for indexing (default: 300)",
    )
    parser.add_argument(
        "--jdtls-cmd",
        default=None,
        help="jdtls command (default: auto-detect from lsp.json or 'jdtls')",
    )
    args = parser.parse_args()

    project_dir = os.path.abspath(args.project_dir)
    if not os.path.isdir(project_dir):
        error(f"Project directory not found: {project_dir}")
        sys.exit(1)

    jdtls_cmd = args.jdtls_cmd or find_jdtls_cmd()

    client = MinimalLSPClient(
        project_dir=project_dir,
        jdtls_cmd=jdtls_cmd,
        timeout=args.timeout,
    )

    success = client.run()
    if success:
        info("jdtls is ready. Workspace cache has been warmed.")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
