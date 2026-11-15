-- Local Compose only. Production roles and passwords are managed separately.
CREATE ROLE rag_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT CONNECT ON DATABASE enterprise_rag TO rag_runtime;
