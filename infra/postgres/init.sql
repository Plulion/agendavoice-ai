-- Ejecutado por el superusuario inicial de la imagen oficial de PostgreSQL.
-- El migrator posee DDL; el runtime no es propietario ni tiene BYPASSRLS.
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

-- La extensión se instala como superusuario durante el bootstrap; el migrator no recibe CREATE sobre la base.
CREATE EXTENSION IF NOT EXISTS btree_gist;
