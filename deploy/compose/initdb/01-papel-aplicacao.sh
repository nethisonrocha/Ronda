#!/bin/sh
# Roda uma única vez, quando o volume do Postgres é criado.
#
# POSTGRES_USER é o dono do banco e das migrations. A aplicação conecta como ronda_app, que
# não é dono das tabelas nem tem BYPASSRLS, portanto fica sujeita às políticas de Row-Level
# Security por tenant.
#
# Sem bit de execução (bind mount no Windows), a imagem faz `source` deste arquivo; por isso
# não há `set -u` aqui, que vazaria para o entrypoint. O ON_ERROR_STOP basta: se o psql
# falhar, o entrypoint (que roda com -e) interrompe a inicialização.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v senha="$RONDA_APP_PASSWORD" <<'SQL'
CREATE ROLE ronda_app LOGIN PASSWORD :'senha' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
GRANT CONNECT ON DATABASE :"DBNAME" TO ronda_app;
GRANT USAGE ON SCHEMA public TO ronda_app;
-- Tabelas e sequências criadas depois pelo dono (migrations) já nascem acessíveis.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ronda_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO ronda_app;
SQL
