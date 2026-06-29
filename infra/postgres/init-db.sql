-- Creates a dedicated database for the MLflow tracking server.
-- The nbaforecast application database is created by POSTGRES_DB in docker-compose.yml.
-- This script runs automatically on first postgres container startup via
-- /docker-entrypoint-initdb.d/ and is a no-op on subsequent starts.
CREATE DATABASE mlflow;
