# 🚀 Decrypter Orchestrator for Docker Compose

A fully containerized multi-tool for securely managing SOPS encryption and safely deploying Docker Compose multi-container projects out of the box.

Because the tool runs entirely via Docker, you do not need to repeatedly install `sops`, `age`, Python, or Docker Compose plugins on your host system.

> [!NOTE]
> Cross-Platform Usage: The commands in this documentation often show `./start.sh` which is intended for Linux/macOS. For Windows systems, you should simply use the PowerShell equivalent `.\start.ps1` (or `./start.ps1`).

***

## 📦 Quick Start (Usage)
To use this orchestrator in another project, **you do not need to clone this entire repository** (unless you want to build and use your own custom image).

Simply grab the `start.sh` (or `start.ps1`) file, drop it into the root directory of your target project, and you're good to go! The script acts as a portable, standalone entrypoint that automatically pulls and interacts with the pre-built Docker environment.

***
## 🛠 Compilation (Global Setup)
If `start.py` receives an update or an improvement, rebuild the image from this directory to bump the generic target for all your projects.

```bash
# Basic setup - tagged initial release 
docker build -t username/decrypter:1.0.0 .
docker tag username/decrypter:1.0.0 username/decrypter:latest

# If modifications to start.py have been done 
docker build -t username/decrypter:1.0.1 .
docker tag username/decrypter:1.0.1 username/decrypter:latest
```

***

## 🔒 Managing Secrets (Encryption Mode)

The image includes `age` and `sops` out of the box, offering simple router shortcuts to natively encrypt your `.env` files straight from the wrapper script.

### 1. Generating a Key
If you don't have an `age` key yet, generate one easily. The output will automatically map to your host's project folder under `.secrets/.key`.
```bash
./start.sh keygen
```
> [!WARNING]
> Keep your `.key` file perfectly secure! It contains the private key string which is absolutely required to boot your server environments. Do not commit this to Git!

### 2. Encrypting the Environment File
Create your raw environment file at `.secrets/.env` (no quotes around values, empty lines, or spaces inside definitions!). Then extract your `PUBLIC_KEY` from your `.key` file and push it through the orchestrator.

**Linux/macOS:**
```bash
PUBLIC_KEY=$(age-keygen -y .secrets/.key)
./start.sh encrypt "$PUBLIC_KEY"
```

**Windows PowerShell:**
```powershell
$PUBLIC_KEY = age-keygen -y .secrets/.key
./start.ps1 encrypt "$PUBLIC_KEY"
```

This will automatically securely wrap your raw `.secrets/.env` into an encrypted `secrets.enc` file sitting safely in your project directory.

### 3. Decrypting to Edit
If you ever want to update an existing `secrets.enc` file back into `.secrets/.env` to modify it, you just need to pass your private key to the decrypt mode:

**Linux/macOS:**
```bash
./start.sh decrypt "AGE-SECRET-KEY-..."
```

**Windows PowerShell:**
```powershell
./start.ps1 decrypt "AGE-SECRET-KEY-..."
```

> [!TIP]
> Need advanced SOPS interactions? You can run any raw SOPS command via the wrapper: `./start.sh sops -d secrets.enc` 

***

## 🚀 App-Update Deployment (Deploy Mode)

Once your `secrets.enc` is ready and your project's `compose.yml` is populated, starting the environment using the native Deploy orchestrator is trivial.

Provide your private key (`SOPS_AGE_KEY`) directly to the shell wrapper. The wrapper perfectly forwards your CLI flags (`-sd`, `-mm`, `-k`, `-u`) directly to the internal python orchestration script.

**Option A: Command-line Flags (Recommended):**
```bash
./start.sh -k "AGE-SECRET-KEY-10x..." ...
```

**Option B: Environmental Exposure:**
```bash
export SOPS_AGE_KEY="AGE-SECRET-KEY-..."
./start.sh -mm
```

### 🔄 Image Updates
If you need to ensure your local images are in sync with the remote registry before starting, you can use the `-u` or `--update` flag. This will trigger a `docker compose pull` before the deployment begins.

- **Check and pull all images defined in compose:**
  ```bash
  ./start.sh -u
  ```

- **Check and pull only a specific service:**
  ```bash
  ./start.sh -u web
  ```

### 🛑 Stopping Environment
To stop and remove the running containers, use the `--down` flag:

```bash
./start.sh --down
```

To also remove volumes (equivalent to `docker compose down -v`), add the `-v` flag:

```bash
./start.sh --down -v
```

### What happens under the hood?
1. The container mounts natively and identically.
2. It decrypts `secrets.enc` instantly in memory (never written to disk)
3. It spins up the `db`, `redis`, and your internal services across the host system's docker network.
4. It conducts health checks and initiates internal database migrations via `--make-migrations` arguments transparently!

***

## 📜 Version History

- **v1.0.4** - Added `--down` flag to stop containers and `-v` flag to remove volumes when stopping.
- **v1.0.3** - Added `-u` / `--update` flag to force pull container images. Support for specific service targeting (e.g., `-u web`).
- **v1.0.2** - Shifted core target pattern to Docker Compose (`:compose` tag default). Removed container-internal web reachability checks in favor of native health states.
- **v1.0.1** - Added MIT License, detailed project `.gitignore`, and clarified multi-platform Windows (`.ps1`) usage.
- **v1.0.0** - Initial release: Core orchestration for SOPS age encryption and Docker deployment setups.
