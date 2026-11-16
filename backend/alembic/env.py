from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
import os
from app.core.db import Base
import app.models
config = context.config
if config.config_file_name: fileConfig(config.config_file_name)
target_metadata = Base.metadata
def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata,
                      literal_binds=True, dialect_opts={"paramstyle":"named"})
    with context.begin_transaction(): context.run_migrations()
def run_migrations_online():
    section = config.get_section(config.config_ini_section)
    section["sqlalchemy.url"] = os.getenv("MIGRATION_DATABASE_URL", section["sqlalchemy.url"])
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata,
                          compare_type=True, transaction_per_migration=True)
        with context.begin_transaction(): context.run_migrations()
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
