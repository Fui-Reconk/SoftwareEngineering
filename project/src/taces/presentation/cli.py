"""Explicit database initialization for local development and deployment."""

import sqlite3

import click
from flask import Flask

from taces.data.database import StorageError
from taces.business.errors import ServiceError


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Initialize the current schema without deleting existing data."""
        try:
            app.extensions["taces_database"].initialize()
        except (StorageError, sqlite3.Error, OSError) as error:
            raise click.ClickException(f"数据库初始化失败：{error}") from error
        click.echo("数据库初始化完成（identity.db / evaluation.db / metadata.db）。")

    @app.cli.command("upgrade-db")
    def upgrade_db_command() -> None:
        """Explicitly migrate existing databases to the current version."""
        try:
            app.extensions["taces_database"].upgrade()
        except (StorageError, sqlite3.Error, OSError) as error:
            raise click.ClickException(f"数据库升级失败：{error}") from error
        click.echo("数据库升级完成，现有数据已保留。")

    @app.cli.command("create-admin")
    @click.option("--username", prompt="Username", required=True)
    def create_admin_command(username: str) -> None:
        """Create the first administrator; subsequent accounts require an admin."""
        password = click.prompt("Password", hide_input=True, confirmation_prompt=True)
        try:
            account = app.extensions["taces_auth"].bootstrap_admin(username, password)
        except (ServiceError, StorageError, sqlite3.Error, OSError) as error:
            raise click.ClickException(f"管理员创建失败：{error}") from error
        click.echo(f"管理员已创建：{account['username']}（{account['user_id']}）。")
