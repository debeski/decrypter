# Project Tracker

## Part 1: Project
### Current Verified Snapshot and current project overview:
- Decrypter is a Docker-based orchestrator for managing SOPS-encrypted secrets and Docker Compose deployments
- Wrapper scripts (`start.sh`, `start.ps1`) call a Docker container that runs `start.py`
- `entrypoint.sh` routes commands: special commands (keygen, encrypt, decrypt, sops) or passes through to Python orchestrator
- Core Python orchestrator at `start.py` handles docker compose operations with health checks and post-start hooks

### Current Project Official Standards:
- Use argparse for CLI argument handling
- Docker Compose operations go through `run_docker_compose()` method
- Render-based UI with section states (idle, running, ok, error)
- Service health monitoring via docker compose ps --format json

### Standards' rules and policies:
- Keep minimal changes, follow existing patterns
- Update README version history for new features

### Cross-Cutting Audits if any:
- None

### Current Project's Known Bugs:
- None known

### Tasks:
- Priority 1:
  - [x] Add `--down` argument to `parse_args()` in `start.py`
  - [x] Add `-v` / `--volumes` argument for volume removal
  - [x] Implement `down_containers()` method
  - [x] Add down mode handling in `run()` method (early exit path)
  - [x] Update README with --down and -v documentation
  - [x] Update version history to v1.0.4

- Completed Recently:
  - [x] Added docker compose down functionality with optional volume removal

### Tests:
- Manual verification: `./start.sh --down` should execute `docker compose down`
- Manual verification: `./start.sh --down -v` should execute `docker compose down -v`

### Docs:
- README.md: Usage examples for --down and -v flags
- README.md: Version history updated to v1.0.4

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- `run_docker_compose(args)` - wrapper for docker compose commands
- `run_command(cmd)` - subprocess wrapper with timeout support

### Global Ruleset:
- When adding new compose operations, follow the pattern of `launch_containers()` and `pull_images()`
- Down mode bypasses all normal startup flow (no secrets, no health checks)

### Agent Handoff Rules:
- Check README.md version history for recent changes

### Links To Possibly Helpful Tools and Projects if any:
- None

### References:
- Docker Compose CLI reference: https://docs.docker.com/engine/reference/commandline/compose_down/
