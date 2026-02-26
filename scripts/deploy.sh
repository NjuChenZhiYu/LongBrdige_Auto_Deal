#!/bin/bash

# Configuration
SERVER_USER="admin"
SERVER_IP="47.85.136.210"
REMOTE_DIR="/home/admin/.openclaw/workspace/LongBrdige_Auto_Deal"
EXCLUDE_FILE="rsync_exclude.txt"

# Create exclude file
cat > $EXCLUDE_FILE <<EOL
venv
venv_auto_deal
__pycache__
.git
.idea
.DS_Store
logs
*.pyc
config/.env
EOL

echo "Starting deployment to $SERVER_USER@$SERVER_IP..."

# 1. Sync files
echo "Syncing files..."
rsync -avz --exclude-from=$EXCLUDE_FILE ./ $SERVER_USER@$SERVER_IP:$REMOTE_DIR

if [ $? -eq 0 ]; then
    echo "File sync successful!"
else
    echo "Error: File sync failed!"
    rm $EXCLUDE_FILE
    exit 1
fi

# Cleanup
rm $EXCLUDE_FILE

# 2. Restart service remotely (Optional)
echo "Restarting service on remote server..."
ssh $SERVER_USER@$SERVER_IP "cd $REMOTE_DIR && ./scripts/stop_all.sh && ./scripts/start_all.sh"

echo "Deployment completed successfully!"
