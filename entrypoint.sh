#!/bin/bash
set -e

CMD="$1"

if [ "$CMD" = "keygen" ]; then
    echo "Generating new AGE key..."
    mkdir -p .secrets
    OUTPUT_FILE=".secrets/.key"
    if [ ! -z "$2" ]; then
        OUTPUT_FILE="$2"
    fi
    # Generate key to file (suppress age-keygen's own stdout to avoid stale/mismatched output)
    age-keygen -o "$OUTPUT_FILE" >/dev/null
    # Derive public key FROM the written file so it always matches what's on disk
    PUBLIC_KEY=$(age-keygen -y "$OUTPUT_FILE")
    echo "Public key: $PUBLIC_KEY"
    echo "Key saved to: $OUTPUT_FILE"

elif [ "$CMD" = "encrypt" ]; then
    # Syntax: encrypt [PUBLIC_KEY] or encrypt --passphrase [PASSPHRASE]
    PUBLIC_KEY=""
    PASSPHRASE=""

    # Check for --passphrase flag
    if [ "$2" = "--passphrase" ] || [ "$2" = "-p" ]; then
        PASSPHRASE="${3:-}"
        if [ -z "$PASSPHRASE" ]; then
            read -s -p "Enter passphrase: " PASSPHRASE
            echo
        fi
        echo "Encrypting .secrets/.env into secrets.enc using passphrase..."
        export SOPS_AGE_PASSPHRASE="$PASSPHRASE"
        exec sops -e --passphrase --input-type dotenv --output ./secrets.enc ./.secrets/.env
    else
        PUBLIC_KEY="$2"
        if [ -z "$PUBLIC_KEY" ]; then
            echo "Error: Missing public key or --passphrase flag."
            echo "Usage: ./start.sh encrypt <PUBLIC_KEY>"
            echo "       ./start.sh encrypt --passphrase [PASSPHRASE]"
            exit 1
        fi
        echo "Encrypting .secrets/.env into secrets.enc using provided public key..."
        exec sops -e -a "$PUBLIC_KEY" --input-type dotenv --output ./secrets.enc ./.secrets/.env
    fi

elif [ "$CMD" = "decrypt" ]; then
    # Syntax: decrypt [PRIVATE_KEY] or decrypt --passphrase [PASSPHRASE]
    PRIVATE_KEY=""
    PASSPHRASE=""

    # Check for --passphrase flag
    if [ "$2" = "--passphrase" ] || [ "$2" = "-p" ]; then
        PASSPHRASE="${3:-}"
        if [ -z "$PASSPHRASE" ]; then
            read -s -p "Enter passphrase: " PASSPHRASE
            echo
        fi
        echo "Decrypting secrets.enc into .secrets/.env using passphrase..."
        export SOPS_AGE_PASSPHRASE="$PASSPHRASE"
        exec sops -d --input-type dotenv --output-type dotenv --output ./.secrets/.env ./secrets.enc
    else
        PRIVATE_KEY="$2"
        if [ -n "$PRIVATE_KEY" ]; then
            export SOPS_AGE_KEY="$PRIVATE_KEY"
        fi

        if [ -z "$SOPS_AGE_KEY" ]; then
            echo "Error: Missing private key or --passphrase flag."
            echo "Usage: ./start.sh decrypt <PRIVATE_KEY>"
            echo "       ./start.sh decrypt --passphrase [PASSPHRASE]"
            exit 1
        fi
        echo "Decrypting secrets.enc into .secrets/.env using provided private key..."
        exec sops -d --input-type dotenv --output-type dotenv --output ./.secrets/.env ./secrets.enc
    fi

elif [ "$CMD" = "sops" ]; then
    shift
    exec sops "$@"

else
    # Default orchestrator behavior
    exec python /app/start.py "$@"
fi
