# import sys
# import os
# sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# from logging.config import fileConfig
# from sqlalchemy import engine_from_config, pool
# from alembic import context

# from db.models import Base
# from config import settings

# config = context.config
# config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# target_metadata = Base.metadata


# def run_migrations_offline() -> None:
#     url = config.get_main_option("sqlalchemy.url")
#     context.configure(
#         url=url,
#         target_metadata=target_metadata,
#         literal_binds=True,
#         dialect_opts={"paramstyle": "named"},
#     )
#     with context.begin_transaction():
#         context.run_migrations()


# def run_migrations_online() -> None:
#     connectable = engine_from_config(
#         config.get_section(config.config_ini_section, {}),
#         prefix="sqlalchemy.",
#         poolclass=pool.NullPool,
#     )
#     with connectable.connect() as connection:
#         context.configure(connection=connection, target_metadata=target_metadata)
#         with context.begin_transaction():
#             context.run_migrations()


# if context.is_offline_mode():
#     run_migrations_offline()
# else:
#     run_migrations_online()

# from dotenv import load_dotenv
# load_dotenv()

# import os
# from logging.config import fileConfig
# from sqlalchemy import engine_from_config, pool
# from alembic import context

# config = context.config

# # Pull DATABASE_URL from environment
# database_url = os.environ.get("DATABASE_URL")
# if not database_url:
#     raise RuntimeError("DATABASE_URL environment variable is not set")
# config.set_main_option("sqlalchemy.url", database_url)

# if config.config_file_name is not None:
#     fileConfig(config.config_file_name)

# from db.models import Base
# target_metadata = Base.metadata


# def run_migrations_offline() -> None:
#     url = config.get_main_option("sqlalchemy.url")
#     context.configure(
#         url=url,
#         target_metadata=target_metadata,
#         literal_binds=True,
#         dialect_opts={"paramstyle": "named"},
#     )
#     with context.begin_transaction():
#         context.run_migrations()


# def run_migrations_online() -> None:
#     connectable = engine_from_config(
#         config.get_section(config.config_ini_section, {}),
#         prefix="sqlalchemy.",
#         poolclass=pool.NullPool,
#     )
#     with connectable.connect() as connection:
#         context.configure(
#             connection=connection,
#             target_metadata=target_metadata,
#         )
#         with context.begin_transaction():
#             context.run_migrations()


# if context.is_offline_mode():
#     run_migrations_offline()
# else:
#     run_migrations_online()


import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

from db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Get URL directly from environment — bypasses configparser entirely
# so special characters like % and @ in passwords are not a problem
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set")


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Create engine directly — never touches configparser
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()