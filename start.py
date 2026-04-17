#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import json
import re
import shlex
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse

# ─────────────────────────────────────────────
# State Constants
# ─────────────────────────────────────────────

IDLE = "idle"
RUNNING = "running"
OK = "ok"
ERROR = "error"

SERVICE_NOT_SEEN = "not_seen"
SERVICE_STARTING = "starting"
SERVICE_HEALTHY = "healthy"
SERVICE_FAILED = "failed"

ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
ERROR_KEYWORDS = (
    "error",
    "failed",
    "denied",
    "exception",
    "traceback",
    "invalid",
    "not found",
    "exit code",
    "exited with code",
    "no such",
    "unhealthy",
    "permission",
)
PROGRESS_KEYWORDS = (
    "building",
    "pulling",
    "creating",
    "created",
    "starting",
    "started",
    "waiting",
    "healthy",
    "built",
    "loaded",
    "exporting",
    "extracting",
    "downloading",
    "transferring",
)


# ─────────────────────────────────────────────
# Launcher
# ─────────────────────────────────────────────

class DockerComposeLauncher:
    def __init__(self):
        self.app_url = "http://localhost"
        self.enc_file = "./secrets.enc"
        self.loaded_secrets: List[str] = []
        self.debug_mode = False
        self.no_migrate = False
        self.force_makemigrations = False
        self.skip_decrypt = False
        self.compose_file = None
        self.compose_dev_file = None
        self.dev_mode = False
        self.target_app = None
        self.update_images = False
        self.pull_service = None
        self.down_mode = False
        self.down_volumes = False
        self.last_progress_message = ""
        self.last_runtime_diagnostic = ""
        self.last_render_line_count = 0

        self.sections = {
            "secrets": IDLE,
            "pull": IDLE,
            "compose": IDLE,
            "health": IDLE,
            "post_start": IDLE,
        }

        self.services: List[str] = []
        self.service_state: Dict[str, str] = {}

    # ─────────────────────────────────────────
    # Rendering
    # ─────────────────────────────────────────

    def render(self, error_message: str = None):
        lines: List[str] = [
            "",
            "🛡️  DECRYPTER - Orchestrator for Docker Compose",
            "█████████████████████████████████████████████████",
        ]
        active_flags: List[str] = []
        if self.dev_mode:
            active_flags.append("\033[91m🛠️  DEV MODE\033[0m")
        if self.debug_mode:
            active_flags.append("\033[93m🪲  DEBUG MODE\033[0m")
        if self.skip_decrypt and not self.dev_mode:
            active_flags.append("\033[93m⚠️  BYPASS DECRYPTION\033[0m")
        if self.no_migrate:
            active_flags.append("\033[93m⏭️  SKIP MIGRATIONS\033[0m")
        if self.force_makemigrations:
            active_flags.append("\033[93m🔄 FORCE MIGRATIONS\033[0m")
        if self.compose_file:
            active_flags.append(f"📂  CUSTOM COMPOSE")
        if self.target_app:
            active_flags.append(f"🎯  TARGET APP")
        if active_flags:
            lines.append("  •  ".join(active_flags))
        lines.extend(
            [
                f"🌐 BASE URL: {self.app_url}",
                "█████████████████████████████████████████████████",
                "",
            ]
        )

        def icon(state):
            return {
                IDLE: "⠿",
                RUNNING: "⟳",
                OK: "✔",
                ERROR: "✖",
            }[state]

        lines.append(f"{icon(self.sections['secrets'])} Decrypt Secrets")
        if self.update_images:
            pull_label = "Pull Images"
            if isinstance(self.pull_service, str):
                pull_label += f" ({self.pull_service})"
            lines.append(f"{icon(self.sections['pull'])} {pull_label}")
        lines.extend(
            [
                f"{icon(self.sections['compose'])} Start Compose",
                f"{icon(self.sections['health'])} Health Check",
                f"{icon(self.sections['post_start'])} Post-Start Tasks",
                "",
                "   " + " ".join(self.service_icon(s) for s in self.services) if self.services else "",
            ]
        )

        if error_message:
            lines.append("\033[91m✖ ERROR:\033[0m")
            for line in str(error_message).splitlines():
                lines.append(f"  {line}")

        total_lines = max(self.last_render_line_count, len(lines))

        if self.last_render_line_count > 1:
            print(f"\r\033[{self.last_render_line_count - 1}F", end="")
        elif self.last_render_line_count == 1:
            print("\r", end="")

        for index in range(total_lines):
            line = lines[index] if index < len(lines) else ""
            end = "\n" if index < total_lines - 1 else ""
            print(f"\033[2K{line}", end=end)

        self.last_render_line_count = len(lines)
        print("", end="", flush=True)

    def service_icon(self, svc: str) -> str:
        return {
            SERVICE_NOT_SEEN: "⚪",
            SERVICE_STARTING: "🟡",
            SERVICE_HEALTHY: "🟢",
            SERVICE_FAILED: "🔴",
        }[self.service_state.get(svc, SERVICE_NOT_SEEN)]

    # ─────────────────────────────────────────
    # Utilities
    # ─────────────────────────────────────────

    def parse_args(self):
        """Parse command line arguments"""
        parser = argparse.ArgumentParser(description="Launch Docker environment with secrets")
        parser.add_argument('-k', '--key', help='AGE secret key')
        parser.add_argument('-f', '--file', help='Specify an alternate compose file')
        parser.add_argument('-d', '--dev', action='store_true', help='Development mode: uses compose.dev.yml override and reads .secrets/.env directly (no decryption)')
        parser.add_argument('-nm', '--no-migrate', action='store_true', help='Bypass post-start migration tasks')
        parser.add_argument('-mm', '--make-migrations', action='store_true', help='Force making migrations during post-start tasks')
        parser.add_argument('-a', '--app', help='Target app for initialization (passed to migrator)')
        parser.add_argument('-sd', '--skip-decrypt', action='store_true', help='Bypass decryption and read .secrets/.env directly')
        parser.add_argument('-u', '--update', nargs='?', const=True, help='Force docker compose pull before starting')
        parser.add_argument('--down', action='store_true', help='Run docker compose down instead of up')
        parser.add_argument('-v', '--volumes', action='store_true', help='Remove volumes when using --down')
        parser.add_argument('key_positional', nargs='?', help='AGE secret key (positional)')

        args = parser.parse_args()
        if args.dev:
            # Dev mode already implies skip-decrypt semantics, so an explicit
            # -sd/--skip-decrypt flag is redundant and should be ignored.
            args.skip_decrypt = False

        return args

    def run_command(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=sys.platform == "win32",
                env=env,
            )
            return result.returncode == 0, result.stdout, result.stderr
        except KeyboardInterrupt:
            raise
        except subprocess.TimeoutExpired as e:
            return False, e.stdout or "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def run_command_streaming(
        self,
        cmd: List[str],
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        progress_callback=None,
    ) -> Tuple[bool, str, str]:
        output_lines: List[str] = []
        started_at = time.time()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                shell=sys.platform == "win32",
                env=env,
                bufsize=1,
            )
        except Exception as e:
            return False, "", str(e)

        try:
            while True:
                if timeout and time.time() - started_at > timeout:
                    process.kill()
                    output = "\n".join(output_lines).strip()
                    return False, output, f"Command timed out after {timeout} seconds"

                line = process.stdout.readline() if process.stdout else ""
                if line:
                    clean_line = line.rstrip("\r\n")
                    output_lines.append(clean_line)
                    if progress_callback:
                        progress_callback(clean_line)
                    continue

                if process.poll() is not None:
                    break

                time.sleep(0.1)
        except KeyboardInterrupt:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise
        finally:
            remainder = process.stdout.read() if process.stdout else ""
            if remainder:
                for line in remainder.splitlines():
                    output_lines.append(line)
                    if progress_callback:
                        progress_callback(line)

            if process.stdout:
                process.stdout.close()

        output = "\n".join(output_lines).strip()
        return process.returncode == 0, output, ""

    def build_compose_base_args(self) -> List[str]:
        base_args = []
        if self.compose_file:
            base_args.extend(["-f", self.compose_file])
        elif self.dev_mode:
            # In dev mode, use both compose.yml and compose.dev.yml
            base_args.extend(["-f", "compose.yml", "-f", "compose.dev.yml"])
        return base_args

    def build_compose_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if self.dev_mode and not self.compose_file:
            # compose.yml expects this substitution in dev mode
            env["NGINX_PORT"] = "81"
        env.setdefault("BUILDKIT_PROGRESS", "plain")
        return env

    def get_compose_commands(self, args: List[str]) -> List[List[str]]:
        base_args = self.build_compose_base_args()
        return [
            ["docker", "compose"] + base_args + args,
            ["docker-compose"] + base_args + args,
        ]

    def should_fallback_to_docker_compose(self, stdout: str, stderr: str) -> bool:
        combined = f"{stdout}\n{stderr}".lower()
        return "is not a docker command" in combined

    def run_docker_compose(
        self,
        args: List[str],
        timeout: Optional[float] = None,
    ) -> Tuple[bool, str, str]:
        env = self.build_compose_env()
        commands = self.get_compose_commands(args)

        success, out, err = self.run_command(commands[0], timeout=timeout, env=env)
        if success or not self.should_fallback_to_docker_compose(out, err):
            return success, out, err
        return self.run_command(commands[1], timeout=timeout, env=env)

    def run_docker_compose_streaming(
        self,
        args: List[str],
        timeout: Optional[float] = None,
        progress_callback=None,
    ) -> Tuple[bool, str, str]:
        env = self.build_compose_env()
        commands = self.get_compose_commands(args)

        success, out, err = self.run_command_streaming(
            commands[0],
            timeout=timeout,
            env=env,
            progress_callback=progress_callback,
        )
        if success or not self.should_fallback_to_docker_compose(out, err):
            return success, out, err
        return self.run_command_streaming(
            commands[1],
            timeout=timeout,
            env=env,
            progress_callback=progress_callback,
        )

    def sanitize_output(self, text: str) -> str:
        return ANSI_ESCAPE_RE.sub("", text or "").replace("\r", "\n")

    def summarize_output(self, *texts: str, max_lines: int = 10) -> str:
        lines: List[str] = []
        seen = set()

        for text in texts:
            for raw_line in self.sanitize_output(text).splitlines():
                line = raw_line.strip()
                if not line or line in seen:
                    continue
                seen.add(line)
                lines.append(line)

        if not lines:
            return ""

        matched = [line for line in lines if any(keyword in line.lower() for keyword in ERROR_KEYWORDS)]
        selected = matched[-max_lines:] if matched else lines[-max_lines:]
        return "\n".join(selected)

    def build_failure_detail(self, stdout: str = "", stderr: str = "", diagnostics: str = "") -> str:
        details: List[str] = []
        command_summary = self.summarize_output(stderr, stdout)
        if command_summary:
            details.append(command_summary)
        diagnostics = diagnostics.strip()
        if diagnostics:
            details.append(diagnostics)
        if not details:
            details.append("Docker Compose did not return a detailed error.")
        return "\n\n".join(details)

    def parse_compose_json_output(self, text: str) -> List[Dict[str, str]]:
        payload = self.sanitize_output(text).strip()
        if not payload:
            return []

        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        if isinstance(parsed, dict):
            return [parsed]

        items: List[Dict[str, str]] = []
        for line in payload.splitlines():
            line = line.strip().rstrip(",")
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                items.append(item)
        return items

    def extract_progress_message(self, raw_line: str) -> Optional[str]:
        line = self.sanitize_output(raw_line).strip()
        if not line:
            return None

        lower = line.lower()
        if line.startswith("#") or line.startswith("[+]") or "=>" in line:
            return line
        if any(keyword in lower for keyword in PROGRESS_KEYWORDS):
            return line
        return None

    def emit_progress(self, label: str, raw_line: str):
        message = self.extract_progress_message(raw_line)
        if not message or message == self.last_progress_message:
            return
        self.last_progress_message = message
        print(f"\r\033[2K   [{label}] {message}", end="", flush=True)

    def get_compose_ps_entries(self, include_all: bool = False) -> Tuple[bool, List[Dict[str, str]], str]:
        args = ["ps"]
        if include_all:
            args.append("--all")
        args.extend(["--format", "json"])

        ok, out, err = self.run_docker_compose(args, timeout=10)
        if not ok:
            return False, [], self.build_failure_detail(out, err)
        return True, self.parse_compose_json_output(out), ""

    def collect_service_diagnostics(self, include_logs: bool = True) -> str:
        ok, services, detail = self.get_compose_ps_entries(include_all=True)
        if not ok:
            return detail

        issues: List[str] = []
        failed_services: List[str] = []

        for service in services:
            name = service.get("Service") or service.get("Name") or "unknown"
            state = str(service.get("State", "")).lower()
            health = str(service.get("Health", "")).lower()
            exit_code = str(service.get("ExitCode", "")).strip()

            if state in {"exited", "dead"} or health == "unhealthy":
                message = f"{name}: state={state or 'unknown'}"
                if health:
                    message += f", health={health}"
                if exit_code and exit_code != "0":
                    message += f", exit_code={exit_code}"
                issues.append(message)
                failed_services.append(name)
            elif state == "restarting":
                issues.append(f"{name}: state=restarting")

        sections: List[str] = []
        if issues:
            sections.append("Service state:\n" + "\n".join(f"- {issue}" for issue in issues))

        if include_logs:
            for service_name in failed_services[:3]:
                ok, out, err = self.run_docker_compose(
                    ["logs", "--no-color", "--tail", "25", service_name],
                    timeout=15,
                )
                summary = self.summarize_output(out, err, max_lines=12)
                if summary:
                    sections.append(f"{service_name} logs:\n{summary}")

        return "\n\n".join(section for section in sections if section.strip())

    # ─────────────────────────────────────────
    # Steps
    # ─────────────────────────────────────────

    def extract_config(self):
        files = [self.compose_file] if self.compose_file else ["compose.yml", "docker-compose.yml"]
        # In dev mode, also check compose.dev.yml for overrides
        if self.dev_mode and Path("compose.dev.yml").exists():
            files.append("compose.dev.yml")
        for file in files:
            p = Path(file)
            if not p.exists():
                continue

            text = p.read_text()
            if m := re.search(r"BASE_URL:\s*(.+)", text):
                self.app_url = m.group(1).strip(" '\"")
            if m := re.search(r"DEBUG_STATUS:\s*['\"]?(true|false)['\"]?", text, re.I):
                self.debug_mode = m.group(1).lower() == "true"

    def parse_post_start_commands(self) -> List[Tuple[str, str]]:
        """
        Parse compose.yml to find post_start commands.
        Returns a list of (service_name, command) tuples.
        """
        commands = []
        
        files = [self.compose_file] if self.compose_file else ["compose.yml", "docker-compose.yml"]
        for file in files:
            p = Path(file)
            if not p.exists():
                continue
            
            text = p.read_text()
            lines = text.splitlines()
            current_service = None
            in_post_start = False
            
            for line in lines:
                # Basic indentation-based parsing for services
                # Matches "  service_name:" (2 spaces indent)
                m_svc = re.match(r"^  ([a-zA-Z0-9_-]+):", line)
                if m_svc:
                    current_service = m_svc.group(1)
                    in_post_start = False
                    continue

                if not current_service:
                    continue

                # Check for post_start block
                if "post_start:" in line:
                    in_post_start = True
                    continue

                # Check for command inside post_start
                # Matches "      - command: ..." (variable spaces)
                if in_post_start:
                    # If indentation drops back to service level or section level, stop
                    if re.match(r"^\S", line) or re.match(r"^  \S", line):
                        in_post_start = False
                        continue
                        
                    m_cmd = re.search(r"-\s+command:\s+(.+)$", line)
                    if m_cmd:
                        cmd = m_cmd.group(1).strip()
                        # Allow shell expansion if needed, but here we just take the string
                        commands.append((current_service, cmd))

        return commands

    def run_post_start_hooks(self) -> Tuple[bool, str]:
        if self.no_migrate:
            print("\n   [Skip] Post-start tasks (Bypass requested)")
            return True, ""

        commands = self.parse_post_start_commands()

        for service, cmd in commands:
            # Only run if service is running
            if self.service_state.get(service) != SERVICE_HEALTHY:
                print(f"\nSkipping post_start for unhealthy service: {service}")
                continue

            # Dynamic argument injection for migrator
            if "manage.py migrator" in cmd:
                 if self.target_app:
                      cmd += f" -a {self.target_app}"
                 if self.force_makemigrations:
                      cmd += " -mm"

            print(f"\n   [Exec] {service}: {cmd}")
            try:
                exec_args = ["exec", service] + shlex.split(cmd, posix=sys.platform != "win32")
            except ValueError as e:
                return False, f"{service}: could not parse post_start command `{cmd}`\n{e}"
            
            ok, out, err = self.run_docker_compose(exec_args)
            if not ok:
                detail = self.build_failure_detail(out, err)
                return False, f"{service}: post_start command failed\nCommand: {cmd}\n\n{detail}"
        return True, ""


    def load_secrets(self, key: str) -> bool:
        os.environ["SOPS_AGE_KEY"] = key
        ok, out, _ = self.run_command(
            ["sops", "-d", "--input-type", "dotenv", "--output-type", "dotenv", self.enc_file],
            timeout=10
        )
        if not ok:
            return False

        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ[k] = v.strip("'\"")
                self.loaded_secrets.append(k)
        return True

    def load_secrets_from_file(self) -> bool:
        env_path = Path(".secrets/.env")
        if not env_path.exists():
            print(f"Error: {env_path} not found.")
            return False
            
        try:
            content = env_path.read_text(encoding='utf-8')
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#') or "=" not in line:
                    continue
                
                k, v = line.split("=", 1)
                os.environ[k] = v.strip("'\"")
                self.loaded_secrets.append(k)
            return True
        except Exception as e:
            print(f"Error reading secrets file: {e}")
            return False

    def discover_services(self) -> bool:
        ok, out, err = self.run_docker_compose(["config", "--services"], timeout=10)
        if not ok:
            self.last_runtime_diagnostic = self.build_failure_detail(out, err)
            return False
        self.services = [s for s in out.splitlines() if s]
        self.service_state = {s: SERVICE_NOT_SEEN for s in self.services}
        self.last_runtime_diagnostic = ""
        return True

    def update_service_states(self) -> bool:
        ok, services, detail = self.get_compose_ps_entries()
        if not ok:
            self.last_runtime_diagnostic = detail
            return False

        seen = set()
        for svc in services:
            try:
                name = svc["Service"]
                state = str(svc.get("State", "")).lower()
                health = str(svc.get("Health", "")).lower()
                exit_code = str(svc.get("ExitCode", "")).strip()

                seen.add(name)

                if state == "running":
                    if not health or health == "healthy":
                        self.service_state[name] = SERVICE_HEALTHY
                    elif health == "starting":
                        self.service_state[name] = SERVICE_STARTING
                    else:
                        self.service_state[name] = SERVICE_FAILED
                elif state in {"created", "restarting", "starting"}:
                    self.service_state[name] = SERVICE_STARTING
                elif state in {"exited", "dead"} or (exit_code and exit_code != "0"):
                    self.service_state[name] = SERVICE_FAILED
                else:
                    self.service_state[name] = SERVICE_NOT_SEEN
            except Exception:
                continue

        for s in self.services:
            if s not in seen:
                self.service_state[s] = SERVICE_NOT_SEEN
        self.last_runtime_diagnostic = ""
        return True

    def launch_containers(self) -> Tuple[bool, str, str]:
        self.last_progress_message = ""
        return self.run_docker_compose_streaming(
            ["up", "-d"],
            progress_callback=lambda line: self.emit_progress("Compose", line),
        )

    def down_containers(self) -> Tuple[bool, str]:
        down_args = ["down"]
        if self.down_volumes:
            down_args.append("-v")
        ok, _, err = self.run_docker_compose(down_args)
        return ok, err

    def pull_images(self) -> Tuple[bool, str, str]:
        pull_args = ["pull"]
        if isinstance(self.pull_service, str):
            pull_args.append(self.pull_service)
        self.last_progress_message = ""
        return self.run_docker_compose_streaming(
            pull_args,
            progress_callback=lambda line: self.emit_progress("Pull", line),
        )

    def monitor_health(self) -> Tuple[bool, str]:
        timeout = 180
        deadline = time.time() + timeout
        last_snapshot: Optional[Tuple[str, ...]] = None

        while time.time() < deadline:
            if not self.update_service_states():
                return False, self.last_runtime_diagnostic or "Failed to inspect compose service state."

            snapshot = tuple(self.service_state.get(s, SERVICE_NOT_SEEN) for s in self.services)
            if snapshot != last_snapshot:
                deadline = time.time() + timeout
                last_snapshot = snapshot

            print("\r   " + " ".join(self.service_icon(s) for s in self.services), end="", flush=True)

            if all(self.service_state[s] == SERVICE_HEALTHY for s in self.services):
                return True, ""

            time.sleep(0.5)

        unhealthy = [
            f"{service} ({self.service_state.get(service, SERVICE_NOT_SEEN)})"
            for service in self.services
            if self.service_state.get(service) != SERVICE_HEALTHY
        ]
        details = ""
        if unhealthy:
            details = "Containers failed to become healthy: " + ", ".join(unhealthy)
        diagnostics = self.collect_service_diagnostics()
        if diagnostics:
            details = f"{details}\n\n{diagnostics}".strip()
        return False, details or "Containers failed to become healthy before the timeout."

    def cleanup(self):
        for k in self.loaded_secrets:
            os.environ.pop(k, None)
        os.environ.pop("SOPS_AGE_KEY", None)

    def handle_interrupt(self):
        if self.last_render_line_count or self.last_progress_message:
            print("\r\033[2K", end="")
        print("\nInterrupted by user. Exiting cleanly.", flush=True)

    # ─────────────────────────────────────────
    # Main Orchestrator
    # ─────────────────────────────────────────

    def run(self):
        try:
            args = self.parse_args()
            self.no_migrate = args.no_migrate
            self.force_makemigrations = args.make_migrations
            self.dev_mode = args.dev
            # Dev mode implies skip_decrypt - read .secrets/.env directly
            self.skip_decrypt = args.skip_decrypt or self.dev_mode
            self.compose_file = args.file
            self.target_app = args.app
            if args.update:
                self.update_images = True
                if isinstance(args.update, str):
                    self.pull_service = args.update
            self.down_mode = args.down
            self.down_volumes = args.volumes

            self.extract_config()

            # Try to discover services early so the status row is available,
            # but keep going if compose config still depends on secrets.
            self.discover_services()

            # Handle down mode early (no secrets needed, no health checks, etc.)
            if self.down_mode:
                print("🛑 Stopping and removing containers...")
                if self.down_volumes:
                    print("   (Volumes will be removed)")
                ok, err = self.down_containers()
                if not ok:
                    print(f"✖ Failed to stop containers:\n  {err.strip()}")
                    sys.exit(1)
                print("✅ Containers stopped")
                return

            # Get initial state when service discovery succeeded
            if self.services:
                self.update_service_states()
            self.render()

            # Secrets
            self.sections["secrets"] = RUNNING
            self.render()
            
            # Priority: --key flag > positional argument > ENV > Input
            if self.skip_decrypt:
                if not self.load_secrets_from_file():
                    self.sections["secrets"] = ERROR
                    self.render("Failed to load secrets from file")
                    sys.exit(1)
            else:
                key = args.key or args.key_positional or os.environ.get("SOPS_AGE_KEY") or input("Paste AGE key: ").strip()
                
                if not self.load_secrets(key):
                    self.sections["secrets"] = ERROR
                    self.render("Failed to decrypt secrets")
                    sys.exit(1)
            self.sections["secrets"] = OK

            # Pull (Optional)
            if self.update_images:
                self.sections["pull"] = RUNNING
                self.render()
                ok, out, err = self.pull_images()
                if not ok:
                    self.sections["pull"] = ERROR
                    detail = self.build_failure_detail(out, err)
                    self.render(f"Failed to pull images\n\n{detail}")
                    sys.exit(1)
                self.sections["pull"] = OK

            # Compose
            self.sections["compose"] = RUNNING
            self.render()
            if not self.discover_services():
                self.sections["compose"] = ERROR
                self.render(
                    "Failed to read compose services\n\n"
                    + (self.last_runtime_diagnostic or "Check the compose file and environment values.")
                )
                sys.exit(1)

            ok, out, err = self.launch_containers()
            if not ok:
                self.sections["compose"] = ERROR
                diagnostics = self.collect_service_diagnostics()
                detail = self.build_failure_detail(out, err, diagnostics)
                self.render(f"Failed to start containers\n\n{detail}")
                sys.exit(1)
            self.sections["compose"] = OK
            
            # Health
            self.sections["health"] = RUNNING
            self.render()

            health_ok, health_detail = self.monitor_health()
            if not health_ok:
                self.sections["health"] = ERROR
                self.render(health_detail)
                sys.exit(1)
            self.sections["health"] = OK

            # Post-Start Hooks
            self.sections["post_start"] = RUNNING
            self.render()
            hooks_ok, hooks_detail = self.run_post_start_hooks()
            if not hooks_ok:
                self.sections["post_start"] = ERROR
                self.render(f"Failed to execute post_start commands\n\n{hooks_detail}")
                # We don't exit here, as the app might still be running, but we mark error
            else:
                self.sections["post_start"] = OK
            
            self.render()

            print("\n🎉 Environment ready")

        except KeyboardInterrupt:
            self.handle_interrupt()
            raise SystemExit(130)
        finally:
            self.cleanup()


def main():
    DockerComposeLauncher().run()


if __name__ == "__main__":
    main()
