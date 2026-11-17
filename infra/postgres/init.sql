-- Executed by the initial PostgreSQL superuser during container bootstrap.
-- The migrator role owns DDL; the runtime role is neither owner nor superuser and has no BYPASSRLS.
CREATE ROLE agendavoice_migrator LOGIN PASSWORD 'local_migrator_change_me';
CREATE ROLE agendavoice_app LOGIN PASSWORD 'local_app_change_me' NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
GRANT CONNECT ON DATABASE agendavoice TO agendavoice_migrator, agendavoice_app;
GRANT USAGE, CREATE ON SCHEMA public TO agendavoice_migrator;
GRANT USAGE ON SCHEMA public TO agendavoice_app;
ALTER DEFAULT PRIVILEGES FOR ROLE agendavoice_migrator IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO agendavoice_app;
ALTER DEFAULT PRIVILEGES FOR ROLE agendavoice_migrator IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO agendavoice_app;
ALTER DATABASE agendavoice SET timezone TO 'UTC';

-- Installed as superuser during initial bootstrap; the migrator role does not require database-level CREATE privileges.
CREATE EXTENSION IF NOT EXISTS btree_gist;
