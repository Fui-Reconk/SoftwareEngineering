"""SQLite access and transactions spanning three physically separate files.

No Flask dependency. Connections belong to one operation and are always closed.
Rollback journals are required for SQLite's attached-database atomic commit.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterator


SCHEMA_VERSION = 3
CORE_TABLES = {
    "main": {"course", "dimension", "budget_ledger", "audit_log"},
    "identity": {"student", "enroll_code"},
    "evaluation": {"rating", "open_text"},
}
VERSION_TWO_TABLES = {
    **CORE_TABLES,
    "identity": CORE_TABLES["identity"] | {"account", "auth_session", "login_throttle"},
}
TABLES = {
    **VERSION_TWO_TABLES,
    "main": VERSION_TWO_TABLES["main"] | {"course_state", "privacy_policy", "agg_result"},
    "identity": VERSION_TWO_TABLES["identity"] | {"code_state"},
}
SCHEMA_DIR = Path(__file__).with_name("schema")


class StorageError(RuntimeError):
    """Storage is missing or incompatible with this application version."""


@dataclass(frozen=True)
class DatabasePaths:
    metadata: Path
    identity: Path
    evaluation: Path

    @classmethod
    def in_directory(cls, directory: Path) -> "DatabasePaths":
        directory = Path(directory).resolve()
        return cls(
            metadata=directory / "metadata.db",
            identity=directory / "identity.db",
            evaluation=directory / "evaluation.db",
        )

    def items(self) -> tuple[tuple[str, Path], ...]:
        return (
            ("main", self.metadata),
            ("identity", self.identity),
            ("evaluation", self.evaluation),
        )


class Database:
    def __init__(self, directory: Path, timeout: float = 5.0) -> None:
        self.paths = DatabasePaths.in_directory(directory)
        self.timeout = timeout

    @contextmanager
    def _connect(
        self, *, read_only: bool = False, create: bool = False
    ) -> Iterator[sqlite3.Connection]:
        if create:
            self.paths.metadata.parent.mkdir(parents=True, exist_ok=True)
        elif not all(path.is_file() for _, path in self.paths.items()):
            raise StorageError("Database files are missing; run init-db first")
        mode = "rwc" if create else ("ro" if read_only else "rw")
        connection = sqlite3.connect(
            self.paths.metadata.as_uri() + f"?mode={mode}",
            uri=True,
            timeout=self.timeout,
            isolation_level=None,
        )
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            # REPLACE fires delete guards only with recursive triggers enabled.
            # Set this on every connection so existing audit rows stay immutable.
            connection.execute("PRAGMA recursive_triggers = ON")
            for schema, path in self.paths.items():
                if schema != "main":
                    connection.execute(
                        f"ATTACH DATABASE ? AS {schema}",
                        (path.as_uri() + f"?mode={mode}",),
                    )
                # schema names are fixed internal constants, never user input.
                journal = connection.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0]
                if journal.lower() != "delete":
                    raise StorageError("Rollback journal mode DELETE is required")
                connection.execute(f"PRAGMA {schema}.synchronous = FULL")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            yield connection
        finally:
            # close() rolls back any unfinished transaction, including a failed COMMIT.
            connection.close()

    @staticmethod
    def _schema_version(connection: sqlite3.Connection, *, allow_empty: bool = False) -> int:
        """Recognize complete, matching versions before any schema changes."""
        versions = {
            schema: connection.execute(f"PRAGMA {schema}.user_version").fetchone()[0]
            for schema in TABLES
        }
        if len(set(versions.values())) != 1:
            raise StorageError("Database schema versions are incompatible across files")
        version = versions["main"]
        if version not in (0, 1, 2, SCHEMA_VERSION):
            raise StorageError("Database schema version is incompatible")
        expected_tables = CORE_TABLES if version == 1 else (VERSION_TWO_TABLES if version == 2 else TABLES)
        for schema, expected in expected_tables.items():
            actual = {
                row[0]
                for row in connection.execute(
                    f"SELECT name FROM {schema}.sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if allow_empty and version == 0 and not actual:
                continue
            if version == 0 or not expected.issubset(actual):
                raise StorageError("Database schema is not initialized or is incompatible")
        return version

    @classmethod
    def _validate_schema(cls, connection: sqlite3.Connection) -> None:
        if cls._schema_version(connection) != SCHEMA_VERSION:
            raise StorageError("Database schema requires an upgrade; run upgrade-db first")

    @staticmethod
    def _execute_schema(connection: sqlite3.Connection, filenames: tuple[str, ...]) -> None:
        # Execute complete statements individually; executescript() would commit
        # the existing transaction before running the supplied DDL.
        for filename in filenames:
            buffer = ""
            for line in (SCHEMA_DIR / filename).read_text(encoding="utf-8").splitlines(keepends=True):
                buffer += line
                if sqlite3.complete_statement(buffer):
                    connection.execute(buffer)
                    buffer = ""
            if buffer.strip():
                raise StorageError("Incomplete schema initialization script")
        for schema in TABLES:
            connection.execute(f"PRAGMA {schema}.user_version = {SCHEMA_VERSION}")

    def initialize(self) -> None:
        """Create the current schema atomically; existing versions require upgrade()."""
        with self._connect(create=True) as connection:
            # Keep schema validation and DDL under the same write lock.
            connection.execute("BEGIN IMMEDIATE")
            version = self._schema_version(connection, allow_empty=True)
            if version in (1, 2):
                raise StorageError("Database schema requires an upgrade; run upgrade-db first")
            if version == 0:
                self._execute_schema(
                    connection, ("metadata.sql", "identity.sql", "evaluation.sql", "auth.sql", "workflow.sql")
                )
            self._validate_schema(connection)
            connection.commit()

    def upgrade(self) -> None:
        """Migrate a complete version-one database, preserving all existing rows."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            version = self._schema_version(connection)
            if version == 1:
                self._execute_schema(connection, ("auth.sql", "workflow.sql"))
            elif version == 2:
                self._execute_schema(connection, ("workflow.sql",))
            self._validate_schema(connection)
            connection.commit()

    def check_ready(self) -> None:
        with self.read_current():
            pass

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """A consistent read snapshot; missing files are never silently created."""
        with self._connect(read_only=True) as connection:
            connection.execute("BEGIN")
            try:
                yield connection
            finally:
                connection.rollback()

    @contextmanager
    def read_current(self) -> Iterator[sqlite3.Connection]:
        """Validate the current schema inside the business operation's snapshot."""
        with self.read() as connection:
            self._validate_schema(connection)
            yield connection

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize writes, commit together, and roll back all three files on failure."""
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_schema(connection)
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
