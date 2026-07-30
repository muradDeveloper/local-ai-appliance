#!/usr/bin/env bash
# Archived: original init script including mem0 database/user setup.
# mem0 was removed from the stack because mem0ai/mem0 is a Python library image
# with no HTTP server, and the server/ image only supports OpenAI/Anthropic/Gemini.
# Restore this if a memory service with native Ollama support is added in future.
set -Eeuo pipefail

psql --set ON_ERROR_STOP=on --username "$POSTGRES_USER" <<-SQL
  CREATE USER ${OPENWEBUI_DB_USER} WITH PASSWORD '${OPENWEBUI_DB_PASSWORD}';
  CREATE DATABASE ${OPENWEBUI_DB_NAME} OWNER ${OPENWEBUI_DB_USER};

  CREATE USER ${AUTHENTIK_DB_USER} WITH PASSWORD '${AUTHENTIK_DB_PASSWORD}';
  CREATE DATABASE ${AUTHENTIK_DB_NAME} OWNER ${AUTHENTIK_DB_USER};

  CREATE USER ${MEM0_DB_USER} WITH PASSWORD '${MEM0_DB_PASSWORD}';
  CREATE DATABASE ${MEM0_DB_NAME} OWNER ${MEM0_DB_USER};
  \connect ${MEM0_DB_NAME}
  CREATE EXTENSION IF NOT EXISTS vector;
SQL
