-- Create schemas for each service (logical separation, shared Postgres instance)
CREATE SCHEMA IF NOT EXISTS submission;
CREATE SCHEMA IF NOT EXISTS decisions;
CREATE SCHEMA IF NOT EXISTS approvals;
CREATE SCHEMA IF NOT EXISTS payments;
CREATE SCHEMA IF NOT EXISTS audit;
