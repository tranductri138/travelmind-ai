#!/bin/bash

IMAGE_NAME="travelmind-ai"
CONTAINER_NAME="travelmind-ai"
NETWORK="travelmind"

# Load DATABASE_URL from .env
DB_URL=$(grep -E '^DATABASE_URL=' .env | cut -d'=' -f2-)
# Convert asyncpg URL to psql-compatible URL
PSQL_URL=$(echo "$DB_URL" | sed 's/+asyncpg//')

# Ensure checkpoint tables have correct schema (safe to run every time)
echo "Checking checkpoint tables..."
docker run --rm --network "$NETWORK" postgres:16-alpine psql "$PSQL_URL" -c "
DO \$\$
BEGIN
    -- Only drop if checkpoints table has wrong column type (BYTEA instead of JSONB)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'checkpoints' AND column_name = 'checkpoint' AND data_type = 'bytea'
    ) THEN
        DROP TABLE IF EXISTS checkpoint_writes;
        DROP TABLE IF EXISTS checkpoint_blobs;
        DROP TABLE IF EXISTS checkpoints;
        DROP TABLE IF EXISTS checkpoint_migrations;
        RAISE NOTICE 'Dropped checkpoint tables with wrong schema. App will recreate on startup.';
    END IF;
END
\$\$;
"

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
  -p 8000:8000 \
  "$IMAGE_NAME"

echo "Container started: http://localhost:8000"
echo "Logs: docker logs -f $CONTAINER_NAME"
