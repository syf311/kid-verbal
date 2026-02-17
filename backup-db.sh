#!/bin/bash
# Backup verbal.db from OCI instance to local OneDrive folder
# Usage: ./backup-db.sh [oci-ip] [ssh-key-path]

OCI_IP="${1:-161.33.47.226}"
SSH_KEY="${2:-/Users/yfshao/oci/ssh-key-2026-01-12.key}"
REMOTE_DB_PATH="~/kid-verbal/verbal.db"
LOCAL_BACKUP_DIR="$HOME/onedrive/personal/twotwo/kid-verbal"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$LOCAL_BACKUP_DIR"

echo "Using SSH key: $SSH_KEY"
echo "Downloading verbal.db from opc@$OCI_IP..."
scp -i "$SSH_KEY" "opc@$OCI_IP:$REMOTE_DB_PATH" "$LOCAL_BACKUP_DIR/verbal_$TIMESTAMP.db"

if [ $? -eq 0 ]; then
    echo "Backup complete: $LOCAL_BACKUP_DIR/verbal_$TIMESTAMP.db"
else
    echo "Failed to download database from opc@$OCI_IP"
    exit 1
fi
