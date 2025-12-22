from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from os import getenv
from pathlib import Path
config=context.config
DB_URL=getenv("WL_DB_URL","sqlite:///./data/db.sqlite3")
config.set_main_option("sqlalchemy.url",DB_URL)
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
import sys
sys.path.append(str(Path(__file__).resolve().parents[1]))
from db import Base
from models import User,Wallet,Transaction,KycUpload,Audit,PaperTrade,PaperAccount,PaperLedger
target_metadata=Base.metadata
def run_migrations_offline():
    context.configure(url=DB_URL,target_metadata=target_metadata,literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
def run_migrations_online():
    connectable=engine_from_config(config.get_section(config.config_ini_section),prefix="sqlalchemy.",poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection,target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
