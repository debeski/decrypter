# Project Tracker

## Part 1: Project
### Current Verified Snapshot and current project overview:
- Decrypter is a Docker-based orchestrator for managing SOPS-encrypted secrets and Docker Compose deployments
- Wrapper scripts (`start.sh`, `start.ps1`) call a Docker container that runs `start.py`
- Wrapper scripts run the image-tagged `/app/start.py`; editing the repo file does nothing in target projects until the Docker image is rebuilt/tagged and that tag is what the wrapper launches
- `entrypoint.sh` routes commands: special commands (keygen, encrypt, decrypt, sops) or passes through to Python orchestrator
- Core Python orchestrator at `start.py` handles docker compose operations with health checks and post-start hooks
- `start.py` now streams compose build/pull progress, gathers richer compose/post-start diagnostics, and tolerates initial service discovery failure until secrets are loaded
- `start.py` reads the launcher version from a bundled `VERSION` file, exports it into the Compose process environment, and generates a temporary compose override that injects the same value into every launched service
- Compose/pull progress must update in place on a single terminal line so the fixed Render UI does not scroll away
- Main UI redraws must update the existing rendered block in place; full-screen clear/repaint causes repeated banner output in some terminals
- Verified repaint bug cause: the main renderer was moving the cursor up by the full prior line count instead of `line_count - 1`, which left the top of prior frames behind
- Verified second repaint bug cause: plain `print()` lines emitted during startup/post-start can shift the redraw anchor below the rendered panel and leave prior header lines behind
- `extract_config()` now accepts `DEBUG_STATUS: true`, `DEBUG_STATUS: True`, and quoted forms like `DEBUG_STATUS: "True"`
- `start.py` now catches `KeyboardInterrupt` and exits cleanly with a short interrupt message instead of printing a traceback
- `parse_args()` now treats `-d/--dev` as taking precedence over `-sd/--skip-decrypt`; if both are passed, the explicit skip-decrypt flag is ignored as redundant
- Render rule: `-d/--dev` should show only the dev-mode banner; the bypass warning line is reserved for standalone `-sd/--skip-decrypt`
- Render layout now groups boolean-style mode flags into one compact status bar line, while compose path / target app / migration info remain on separate lines

### Current Project Official Standards:
- Use argparse for CLI argument handling
- Docker Compose operations go through `run_docker_compose()` method
- Render-based UI with section states (idle, running, ok, error)
- Service health monitoring via docker compose ps --format json
- Services without a healthcheck should be treated as ready once Docker reports them as running
- Launcher-owned runtime metadata should be injected centrally in `start.py` rather than requiring per-project compose edits when the value is global to every deployment
- Version source of truth is the repo/image `VERSION` file, not a hardcoded constant inside `start.py`
- Streaming status output must reuse one dynamic line via carriage return and line erase instead of printing new lines
- UI refreshes should use cursor-up plus line erase over the existing block rather than screen clears

### Standards' rules and policies:
- Keep minimal changes, follow existing patterns
- Update README version history for new features

### Cross-Cutting Audits if any:
- None

### Current Project's Known Bugs:
- None currently verified

### Tasks:
- Priority 1:
  - [x] Stream `docker compose up -d` and `docker compose pull` progress so build-heavy services do not look stuck
  - [x] Keep streamed progress on a single overwritten terminal line so the launcher UI does not scroll
  - [x] Redraw the launcher panel in place so the header block does not repeat in terminals that preserve repaint history
  - [x] Fix the renderer cursor-up offset so frame redraw starts on the first existing line instead of one line above it
  - [x] Remove the startup bypass `print()` that was adding an out-of-band line and breaking the next redraw anchor
  - [x] Accept quoted `DEBUG_STATUS` boolean values when parsing compose text for debug mode
  - [x] Catch Ctrl+C and exit cleanly without dumping a Python traceback
  - [x] Normalize `-d` plus `-sd` so dev mode is the only effective mode when both are passed
  - [x] Suppress the redundant bypass warning banner when dev mode is active
  - [x] Collapse dev/debug/bypass state into a single compact header status bar
  - [x] Improve compose failure output using captured command output plus `docker compose ps/logs` diagnostics when available
  - [x] Treat running services with no healthcheck as ready during health monitoring
  - [x] Make early service discovery non-fatal when compose config still depends on decrypted secrets
  - [x] Pass the current Decrypter version into Compose and every launched service without requiring deployed projects to add a new env entry
  - [x] Load the injected Decrypter version from `VERSION` so the image and runtime env share one source of truth
  - [x] Move streaming progress messages to a dedicated line below the state circles to prevent overwriting
  - [x] Add dynamic waiting/failing status output during the `monitor_health` loop so stuck containers are clearly identified
  - [ ] Manually verify startup against a compose project with a service `build:` step
  - [ ] Manually verify a launched container can read `DECRYPTER_VERSION`
  - [ ] Manually verify failure output for a container that exits with code 1 and for a failing `post_start` command

- Completed Recently:
  - [x] Added docker compose down functionality with optional volume removal
  - [x] Added compose progress streaming and richer diagnostics in `start.py`
  - [x] Added automatic runtime version injection via generated compose override

### Tests:
- Verified: `python -m compileall start.py`
- Recommended: manual Ctrl+C during compose startup to confirm the launcher exits with only the clean interrupt message
- Recommended: manual run of `./start.sh` against a compose file that triggers image build output during `docker compose up -d`
- Recommended: manual run of `./start.sh` followed by `docker compose exec <service> env | grep DECRYPTER_VERSION`
- Recommended: manual run of `./start.sh` with a service that has no healthcheck and should be accepted once running
- Recommended: manual run of `./start.sh` with a failing service / failing `post_start` hook to confirm richer diagnostics

### Docs:
- README.md: Build instructions now explicitly mention rebuilding the `debeski/decrypter:compose` tag used by the wrapper scripts
- README.md: Added notes for live compose progress UI and case-insensitive / quoted `DEBUG_STATUS` parsing
- README.md: Added automatic `DECRYPTER_VERSION` runtime injection note, documented `VERSION` as the source of truth, and version history updated to v1.0.7

## Part 2: Global
### Global Standard Helpers, Shortcuts, Info, etc.:
- `run_docker_compose(args)` - wrapper for docker compose commands
- `run_command(cmd)` - subprocess wrapper with timeout support
- `run_docker_compose_streaming(args)` - compose runner that streams progress lines while capturing output for failures
- `collect_service_diagnostics()` - helper for `docker compose ps --all` plus targeted log tailing on failed services
- `read_decrypter_version()` - reads the bundled `VERSION` file next to `start.py` and falls back to `0.0.0` if unavailable
- `sync_runtime_compose_override()` - writes a temporary compose override that injects `DECRYPTER_VERSION` into every discovered service

### Global Ruleset:
- When adding new compose operations, follow the pattern of `launch_containers()` and `pull_images()`
- Down mode bypasses all normal startup flow (no secrets, no health checks)
- If compose config depends on decrypted env vars, allow initial discovery to fail and retry after secrets are loaded
- If a launcher-owned value should reach all containers, prefer generating a temporary compose override in `start.py` over requiring each project to repeat the same env wiring
- If the launcher version changes, update `VERSION` and rebuild the `debeski/decrypter:compose` image so `/app/VERSION` matches the runtime code

### Agent Handoff Rules:
- Check README.md version history for recent changes
- Re-read `start.py` service-state logic before changing health behavior; services without healthchecks are intentionally treated as ready when running
- Important user correction: progress streaming should preserve the fixed UI and overwrite one line in place, not append scrolling status lines
- Important terminal behavior note: avoid `clear screen`-style full redraws for the main panel; repaint the same block in place instead
- Verify the runtime image tag before debugging behavior: `start.sh` and `start.ps1` launch `debeski/decrypter:compose`, so local `start.py` edits are invisible until that image is rebuilt or retagged locally
- Specific repaint gotcha: when redrawing a block with ANSI `F`, move up `rendered_lines - 1`, not `rendered_lines`
- Second repaint gotcha: avoid bare `print()` calls during interactive panel mode unless the redraw anchor accounts for those extra lines
- Config parsing note: `extract_config()` handles `DEBUG_STATUS` case-insensitively and now tolerates optional single/double quotes around the boolean text
- Interrupt handling note: let `KeyboardInterrupt` propagate out of low-level command runners after child-process cleanup, then convert it to a clean exit at the top-level `run()` path
- Flag precedence note: `-d/--dev` already implies skip-decrypt behavior, so `-sd/--skip-decrypt` is normalized away when both are provided
- UI note: dev mode implies skip-decrypt behavior internally, but the render layer should only show the yellow bypass warning for standalone skip-decrypt mode
- UI note: short mode toggles belong in the shared status bar; longer contextual details such as compose file and target app stay on dedicated lines
- Runtime metadata note: `DECRYPTER_VERSION` is injected two ways on startup: exported to the Compose process env for interpolation and written into a generated override so containers receive it automatically
- Version loading note: the deployed runtime reads `/app/VERSION`, so Dockerfile changes must continue copying `VERSION` into the image alongside `start.py`

### Links To Possibly Helpful Tools and Projects if any:
- None

### References:
- Docker Compose CLI reference: https://docs.docker.com/engine/reference/commandline/compose_down/
