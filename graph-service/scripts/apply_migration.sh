#!/bin/bash

# Graph Service Database Migration Script
# This script applies the graph service schema to all PostgreSQL shards via pgdog

set -e

echo "==================================="
echo "Graph Service Database Migration"
echo "==================================="

# Configuration
PGDOG_HOST="${PGDOG_HOST:-localhost}"
PGDOG_PORT="${PGDOG_PORT:-6432}"
PGDOG_USER="${PGDOG_USER:-instagram_user}"
PGDOG_DB="${PGDOG_DB:-instagram}"
MIGRATION_FILE="../migrations/001_create_follows_table.sql"

# Check if psql is available
if ! command -v psql &> /dev/null; then
    echo "Error: psql is not installed"
    echo "Please install PostgreSQL client"
    exit 1
fi

# Check if migration file exists
if [ ! -f "$MIGRATION_FILE" ]; then
    echo "Error: Migration file not found: $MIGRATION_FILE"
    exit 1
fi

echo "Migration file: $MIGRATION_FILE"
echo "Target: ${PGDOG_USER}@${PGDOG_HOST}:${PGDOG_PORT}/${PGDOG_DB}"
echo ""

# Prompt for password
read -sp "Enter PostgreSQL password: " PGPASSWORD
echo ""
export PGPASSWORD

# Apply migration
echo ""
echo "Applying migration..."
psql -h "$PGDOG_HOST" -p "$PGDOG_PORT" -U "$PGDOG_USER" -d "$PGDOG_DB" -f "$MIGRATION_FILE"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Migration applied successfully!"
    echo ""
    echo "Verifying tables..."
    psql -h "$PGDOG_HOST" -p "$PGDOG_PORT" -U "$PGDOG_USER" -d "$PGDOG_DB" -c "\dt follows"
    psql -h "$PGDOG_HOST" -p "$PGDOG_PORT" -U "$PGDOG_USER" -d "$PGDOG_DB" -c "\dt user_graph_stats"
    echo ""
    echo "Migration complete!"
else
    echo ""
    echo "✗ Migration failed!"
    exit 1
fi

unset PGPASSWORD
