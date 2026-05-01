# 🚀 Decrypter Orchestrator for Docker Compose

A fully containerized multi-tool for securely managing SOPS encryption and safely deploying Docker Compose multi-container projects out of the box.

Because the tool runs entirely via Docker, you do not need to repeatedly install `sops`, `age`, Python, or Docker Compose plugins on your host system.

> [!NOTE]
> Cross-Platform Usage: The commands in this documentation often show `./start.sh` which is intended for Linux/macOS. For Windows systems, you should simply use the PowerShell equivalent `.\start.ps1` (or `./start.ps1`).

***

## 📦 Quick Start (Usage)
To use this orchestrator in another project, **you do not need to clone this entire repository** (unless you want to build and use your own custom image).

Simply grab the `start.sh` (or `start.ps1`) file, drop it into the root directory of your target project, and you're good to go! The script acts as a portable, standalone entrypoint that automatically pulls and interacts with the pre-built Docker environment.

### Updating the Decrypter Image

To update the Decrypter Docker image to the latest version, use the `--update` flag on the wrapper script:

**Linux/macOS:**
```bash
./start.sh --update
```

**Windows PowerShell:**
```powershell
./start.ps1 --update
```

This will show your current version, pull the latest image, and display the newly installed version.

### Command Surface
Decrypter has two command layers:

- **Entrypoint shortcuts**: `keygen`, `encrypt`, `decrypt`, and `sops` are handled by `entrypoint.sh` before the Python orchestrator starts. These are convenience commands for common fixed-path secret operations.
- **Orchestrator flags**: options such as `--encrypt`, `--decrypt`, `--down`, `-u`, `-d`, and `-f` are parsed by `start.py`. Use these when you need deployment behavior or configurable encrypt/decrypt input and output paths.

***
## 🛠 Compilation (Global Setup)
If `start.py` receives an update or an improvement, rebuild the image from this directory to bump the generic target for all your projects.

The wrapper scripts in this repo launch the `debeski/decrypter:compose` image tag. If you change `start.py`, rebuild that tag or retag your custom build to `:compose`, otherwise target projects will keep running the old bundled `/app/start.py`.

```bash
# Example custom build
docker build -t username/decrypter:$(cat VERSION) .
docker tag username/decrypter:$(cat VERSION) username/decrypter:latest

# Rebuild the tag used by the bundled wrapper scripts
docker build -t debeski/decrypter:compose .
```

***

## 🔒 Managing Secrets (Entrypoint Shortcuts)

The image includes `age` and `sops` out of the box, offering simple entrypoint shortcuts to natively encrypt your `.env` files straight from the wrapper script.

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

This shortcut wraps `.secrets/.env` into `secrets.enc`.

### 3. Decrypting to Edit
If you ever want to update an existing `secrets.enc` file back into `.secrets/.env` to modify it, pass your private key to the shortcut:

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

### 4. Passphrase-based Encryption (No Keys Required)

If you prefer not to manage AGE keys, you can encrypt and decrypt using a passphrase instead. This uses SOPS's built-in passphrase mode.

**Encrypt with a passphrase:**
```bash
./start.sh encrypt --passphrase "my secret phrase"
```

**Decrypt with a passphrase:**
```bash
./start.sh decrypt --passphrase "my secret phrase"
```

If you omit the passphrase, you'll be prompted to enter it securely:
```bash
./start.sh encrypt --passphrase
# Enter passphrase: (hidden input)
```

The orchestrator also supports passphrase mode for deployments:
```bash
./start.sh -p "my secret phrase"
``` 

***

## 🚀 App-Update Deployment (Orchestrator Mode)

Once your `secrets.enc` is ready and your project's `compose.yml` is populated, starting the environment using the native Deploy orchestrator is trivial.

Provide your private key (`SOPS_AGE_KEY`) directly to the shell wrapper. Unknown entrypoint commands and all flags are forwarded to the internal Python orchestration script.

**Option A: Command-line Flags (Recommended):**
```bash
./start.sh -k "AGE-SECRET-KEY-10x..." ...
```

**Option B: Environmental Exposure:**
```bash
export SOPS_AGE_KEY="AGE-SECRET-KEY-..."
./start.sh -mm
```

### CLI Reference

| Argument | Meaning |
| --- | --- |
| `-h`, `--help` | Show CLI help and exit. |
| `-k`, `--key` | AGE private key for decrypt/deploy, or AGE public key for `--encrypt`. |
| `-p`, `--passphrase` | Use a passphrase instead of AGE keys for encryption/decryption. |
| positional key | Optional AGE key alternative to `-k`. |
| `-f`, `--file` | Use an alternate Compose file instead of `compose.yml`. |
| `-d`, `--dev` | Development mode: use `compose.yml` plus `compose.dev.yml`, read `.secrets/.env` directly, and skip decryption. |
| `-sd`, `--skip-decrypt` | Read `.secrets/.env` directly without decrypting `secrets.enc`. |
| `-nm`, `--no-migrate` | Skip post-start migration tasks. |
| `-mm`, `--make-migrations` | Force migration generation during post-start migrator commands. |
| `-a`, `--app` | Pass a target app name to the migrator post-start command. |
| `-u`, `--update [SERVICE]` | Run `docker compose pull` before startup; optionally pull only one service. |
| `-b`, `--build` | Start Compose with `docker compose up -d --build`. |
| `--down` | Run `docker compose down` instead of startup. |
| `-v`, `--volumes` | Remove volumes when used with `--down`. |
| `--encrypt` | Encrypt a plaintext dotenv file and exit without starting containers. |
| `--decrypt` | Decrypt an encrypted dotenv file and exit without starting containers. |
| `-i`, `--input` | Input path for `--encrypt` or `--decrypt`. |
| `-o`, `--output` | Output path for `--encrypt` or `--decrypt`. |
| `--version` | Print the bundled Decrypter version and exit. |

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

### 🔓 Decrypt
To decrypt `secrets.enc` and print the plaintext to stdout (without starting any containers), use the `--decrypt` flag:

```bash
./start.sh --decrypt -k "AGE-SECRET-KEY-..."
```

To write the output to a file instead of stdout, use `-o`:
```bash
./start.sh --decrypt -k "AGE-SECRET-KEY-..." -o .secrets/.env
```

To decrypt a different input file, use `-i`:
```bash
./start.sh --decrypt -k "AGE-SECRET-KEY-..." -i other.enc
```

You can also use the positional key or `SOPS_AGE_KEY` env var:
```bash
export SOPS_AGE_KEY="AGE-SECRET-KEY-..."
./start.sh --decrypt
```

**Using a passphrase instead of a key:**
```bash
./start.sh --decrypt -p "my passphrase"
```

### 🔒 Encrypt
To encrypt `.secrets/.env` into `secrets.enc` (without starting any containers), use the `--encrypt` flag with your **public** key:

```bash
./start.sh --encrypt -k "age1..."
```

To specify custom input/output paths, use `-i` and `-o`:
```bash
./start.sh --encrypt -k "age1..." -i .secrets/.env.prod -o secrets.prod.enc
```

You can also use the positional key or `SOPS_AGE_PUBLIC_KEY` env var:
```bash
export SOPS_AGE_PUBLIC_KEY="age1..."
./start.sh --encrypt
```

**Using a passphrase instead of a key:**
```bash
./start.sh --encrypt -p "my passphrase"
```

### Stopping Environment
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

### Notes
- `DEBUG_STATUS` parsing is case-insensitive in the launcher. `true`, `True`, `"True"`, and `'false'` are all understood when the compose file is scanned for the debug banner.
- Compose build/pull activity and detailed health check states are streamed into the launcher UI as a live single-line status instead of looking stalled during long image operations or waiting periods.
- Every launched service automatically receives `DECRYPTER_VERSION` as a runtime environment variable. Decrypter also exports the same variable to Compose itself, so projects can reference it for interpolation without adding a separate host env var.
- The launcher reads its version from the bundled `VERSION` file in the image, so update that file when cutting a new release.
