-- Creates a dedicated database for the MLflow tracking server.
-- The nbaforecast application database is created by POSTGRES_DB in docker-compose.yml.
-- This script runs automatically on first postgres container startup via
-- /docker-entrypoint-initdb.d/ and is a no-op on subsequent starts.
--
-- \set ON_ERROR_STOP causes psql to exit non-zero on failure, which aborts the
-- postgres container init and surfaces the error clearly rather than silently
-- letting the container start without the mlflow database.
\set ON_ERROR_STOP on
CREATE DATABASE mlflow;
