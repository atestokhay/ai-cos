import logging

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

_STATEMENT_TIMEOUT_MS = "2000"


class SqlDatabaseProbe:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def is_reachable(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(
                    text("SELECT set_config('statement_timeout', :timeout, true)"),
                    {"timeout": _STATEMENT_TIMEOUT_MS},
                )
                connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError as exc:
            # Only the type: driver messages can contain host and user names.
            logger.warning("Database probe failed: %s", type(exc).__name__)
            return False
