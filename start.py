#!/usr/bin/env python3

import os
import sys
import subprocess
import time
import json
import re
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
        self.target_app = None
        self.update_images = False
        self.pull_service = None
        self.down_mode = False
        self.down_volumes = False

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
        print("\033[H\033[J", end="")

        print("████████████████████████████████████████")
        print("🚀 START - ENCRYPTED COMPOSE LAUNCHER")
        if self.debug_mode:
            print("DEBUG MODE: ON")
            
        if self.skip_decrypt:
            print("\033[93m⚠  RUNNING IN BYPASS MODE (Decryption Skipped)\033[0m")
        if self.compose_file:
            print(f"ℹ  Using Compose File: {self.compose_file}")
        if self.no_migrate:
            print("ℹ  Skipping Migrations")
        if self.target_app:
            print(f"ℹ  Target App: {self.target_app}")
            
        print(f"BASE URL: {self.app_url}")
        print("████████████████████████████████████████\n")

        def icon(state):
            return {
                IDLE: "⠿",
                RUNNING: "⟳",
                OK: "✔",
                ERROR: "✖",
            }[state]

        print(f"{icon(self.sections['secrets'])} Decrypt Secrets")
        if self.update_images:
            pull_label = "Pull Images"
            if isinstance(self.pull_service, str):
                pull_label += f" ({self.pull_service})"
            print(f"{icon(self.sections['pull'])} {pull_label}")
        print(f"{icon(self.sections['compose'])} Start Compose")

        print(f"{icon(self.sections['health'])} Health Check")
        print(f"{icon(self.sections['post_start'])} Post-Start Tasks")
        print("")

        if self.services:
            print("   " + " ".join(self.service_icon(s) for s in self.services), end="", flush=True)

        if error_message:
            print("\n✖ ERROR:")
            print(f"  {error_message}")

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
        parser.add_argument('-nm', '--no-migrate', action='store_true', help='Bypass post-start migration tasks')
        parser.add_argument('-mm', '--make-migrations', action='store_true', help='Force making migrations during post-start tasks')
        parser.add_argument('-a', '--app', help='Target app for initialization (passed to migrator)')
        parser.add_argument('-sd', '--skip-decrypt', action='store_true', help='Bypass decryption and read .secrets/.env directly')
        parser.add_argument('-u', '--update', nargs='?', const=True, help='Force docker compose pull before starting')
        parser.add_argument('--down', action='store_true', help='Run docker compose down instead of up')
        parser.add_argument('-v', '--volumes', action='store_true', help='Remove volumes when using --down')
        parser.add_argument('key_positional', nargs='?', help='AGE secret key (positional)')
        
        return parser.parse_args()

    def run_command(self, cmd: List[str], timeout: Optional[float] = None) -> Tuple[bool, str, str]:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=sys.platform == "win32"
            )
            return result.returncode == 0, result.stdout, result.stderr
        except subprocess.TimeoutExpired as e:
            return False, e.stdout or "", f"Command timed out after {timeout} seconds"
        except Exception as e:
            return False, "", str(e)

    def run_docker_compose(self, args: List[str], timeout: Optional[float] = None) -> Tuple[bool, str, str]:
        base_args = []
        if self.compose_file:
            base_args.extend(["-f", self.compose_file])
            
        success, out, err = self.run_command(["docker", "compose"] + base_args + args, timeout=timeout)
        if success or "is not a docker command" not in err.lower():
            return success, out, err
        return self.run_command(["docker-compose"] + base_args + args, timeout=timeout)

    # ─────────────────────────────────────────
    # Steps
    # ─────────────────────────────────────────

    def extract_config(self):
        files = [self.compose_file] if self.compose_file else ["compose.yml", "docker-compose.yml"]
        for file in files:
            p = Path(file)
            if not p.exists():
                continue

            text = p.read_text()
            if m := re.search(r"BASE_URL:\s*(.+)", text):
                self.app_url = m.group(1).strip(" '\"")
            if m := re.search(r"DEBUG_STATUS:\s*(true|false)", text, re.I):
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

    def run_post_start_hooks(self) -> bool:
        if self.no_migrate:
            print("\n   [Skip] Post-start tasks (Bypass requested)")
            return True

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
            # Split command line carefully - simplistic splitting here
            # For complex commands, we might need shlex but keeping it simple as per requirements
            # Executing via docker compose exec
            exec_args = ["exec", service] + cmd.split()
            
            ok, out, err = self.run_docker_compose(exec_args)
            if not ok:
                print(f"   Failed: {err.strip()}")
                return False
        return True


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
        ok, out, _ = self.run_docker_compose(["config", "--services"], timeout=10)
        if not ok:
            return False
        self.services = [s for s in out.splitlines() if s]
        self.service_state = {s: SERVICE_NOT_SEEN for s in self.services}
        return True

    def update_service_states(self) -> bool:
        ok, out, _ = self.run_docker_compose(["ps", "--format", "json"], timeout=10)
        if not ok:
            return False

        seen = set()
        for line in out.splitlines():
            try:
                svc = json.loads(line)
                name = svc["Service"]
                state = svc["State"].lower()
                health = svc.get("Health", "").lower()

                seen.add(name)

                if state == "running" and health == "healthy":
                    self.service_state[name] = SERVICE_HEALTHY
                elif state == "running":
                    self.service_state[name] = SERVICE_STARTING
                elif state == "exited":
                    self.service_state[name] = SERVICE_FAILED
            except:
                pass

        for s in self.services:
            if s not in seen:
                self.service_state[s] = SERVICE_NOT_SEEN
        return True

    def launch_containers(self) -> Tuple[bool, str]:
        ok, _, err = self.run_docker_compose(["up", "-d"])
        return ok, err

    def down_containers(self) -> Tuple[bool, str]:
        down_args = ["down"]
        if self.down_volumes:
            down_args.append("-v")
        ok, _, err = self.run_docker_compose(down_args)
        return ok, err

    def pull_images(self) -> Tuple[bool, str]:
        pull_args = ["pull"]
        if isinstance(self.pull_service, str):
            pull_args.append(self.pull_service)
        ok, _, err = self.run_docker_compose(pull_args)
        return ok, err

    def monitor_health(self) -> bool:
        timeout = 180
        deadline = time.time() + timeout
        last_snapshot: Optional[Tuple[str, ...]] = None

        while time.time() < deadline:
            if not self.update_service_states():
                return False

            snapshot = tuple(self.service_state.get(s, SERVICE_NOT_SEEN) for s in self.services)
            if snapshot != last_snapshot:
                deadline = time.time() + timeout
                last_snapshot = snapshot

            print("\r   " + " ".join(self.service_icon(s) for s in self.services), end="", flush=True)

            if all(self.service_state[s] == SERVICE_HEALTHY for s in self.services):
                return True

            time.sleep(0.5)

        return False

    def cleanup(self):
        for k in self.loaded_secrets:
            os.environ.pop(k, None)
        os.environ.pop("SOPS_AGE_KEY", None)

    # ─────────────────────────────────────────
    # Main Orchestrator
    # ─────────────────────────────────────────

    def run(self):
        try:
            args = self.parse_args()
            self.no_migrate = args.no_migrate
            self.force_makemigrations = args.make_migrations
            self.skip_decrypt = args.skip_decrypt
            self.compose_file = args.file
            self.target_app = args.app
            if args.update:
                self.update_images = True
                if isinstance(args.update, str):
                    self.pull_service = args.update
            self.down_mode = args.down
            self.down_volumes = args.volumes

            self.extract_config()

            # ✅ Discover services immediately so circles are visible
            if not self.discover_services():
                self.render("Failed to read compose services")
                sys.exit(1)

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

            # Get initial state
            self.update_service_states()
            self.render()

            # Secrets
            self.sections["secrets"] = RUNNING
            self.render()
            
            # Priority: --key flag > positional argument > ENV > Input
            if args.skip_decrypt:
                print("   [Bypass] Decryption skipped. Loading .secrets/.env directly...")
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
                ok, err = self.pull_images()
                if not ok:
                    self.sections["pull"] = ERROR
                    self.render(f"Failed to pull images:\n  {err.strip()}")
                    sys.exit(1)
                self.sections["pull"] = OK

            # Compose
            self.sections["compose"] = RUNNING
            self.render()
            if not self.discover_services():
                self.sections["compose"] = ERROR
                self.render("Failed to read compose services")
                sys.exit(1)

            ok, err = self.launch_containers()
            if not ok:
                self.sections["compose"] = ERROR
                self.render(f"Failed to start containers:\n  {err.strip()}")
                sys.exit(1)
            self.sections["compose"] = OK
            
            # Health
            self.sections["health"] = RUNNING
            self.render()

            if not self.monitor_health():
                self.sections["health"] = ERROR
                unhealthy = [s for s, state in self.service_state.items() if state != SERVICE_HEALTHY]
                self.render(f"Containers failed to become healthy: {', '.join(unhealthy)}")
                sys.exit(1)
            self.sections["health"] = OK

            # Post-Start Hooks
            self.sections["post_start"] = RUNNING
            self.render()
            if not self.run_post_start_hooks():
                self.sections["post_start"] = ERROR
                self.render("Failed to execute post_start commands")
                # We don't exit here, as the app might still be running, but we mark error
            else:
                self.sections["post_start"] = OK
            
            self.render()

            print("\n🎉 Environment ready")

        finally:
            self.cleanup()


def main():
    DockerComposeLauncher().run()


if __name__ == "__main__":
    main()
