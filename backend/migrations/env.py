from alembic import context
from app.db import Base, engine

config = context.config


def run(connection):
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError(
        "Use an online database connection to migrate legacy data safely"
    )
elif config.attributes.get("connection") is not None:
    run(config.attributes["connection"])
else:
    with engine.connect() as connection:
        run(connection)
