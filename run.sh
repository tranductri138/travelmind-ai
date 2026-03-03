#!/bin/bash

IMAGE_NAME="travelmind-ai"
CONTAINER_NAME="travelmind-ai"
NETWORK="travelmind"

# Load DATABASE_URL from .env
DB_URL=$(grep -E '^DATABASE_URL=' .env | cut -d'=' -f2-)
# Convert asyncpg URL to psql-compatible URL
PSQL_URL=$(echo "$DB_URL" | sed 's/+asyncpg//')

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
