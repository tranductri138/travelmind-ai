#!/bin/bash

IMAGE_NAME="travelmind-ai"
CONTAINER_NAME="travelmind-ai"
NETWORK="travelmind"

# Load DATABASE_URL from .env
DB_URL=$(grep -E '^DATABASE_URL=' .env | cut -d'=' -f2-)
# Convert asyncpg URL to psql-compatible URL
PSQL_URL=$(echo "$DB_URL" | sed 's/+asyncpg//')

# Create checkpoint tables if not exist
echo "Setting up checkpoint tables..."
docker run --rm --network "$NETWORK" postgres:16-alpine psql "$PSQL_URL" -c "
CREATE TABLE IF NOT EXISTS checkpoints (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    type TEXT,
    checkpoint BYTEA NOT NULL,
    metadata BYTEA NOT NULL DEFAULT '{}',
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS checkpoint_blobs (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    version TEXT NOT NULL,
    type TEXT NOT NULL,
    blob BYTEA,
    PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE IF NOT EXISTS checkpoint_writes (
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    type TEXT,
    blob BYTEA NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
"

if [ $? -ne 0 ]; then
  echo "Warning: Failed to create checkpoint tables. Container may fail to start."
fi

# Build image
echo "Building $IMAGE_NAME..."
docker build -t "$IMAGE_NAME" .

if [ $? -ne 0 ]; then
  echo "Build failed!"
  exit 1
fi

# Remove old container if exists
docker rm -f "$CONTAINER_NAME" 2>/dev/null

# Run with .env file
echo "Running $CONTAINER_NAME..."
docker run -d \
  --name "$CONTAINER_NAME" \
  --env-file .env \
  --network "$NETWORK" \
  "$IMAGE_NAME"

echo "Container started: http://localhost:8000"
echo "Logs: docker logs -f $CONTAINER_NAME"
