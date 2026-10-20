"""Explicit database initialization for local development and deployment."""

import sqlite3

import click
from flask import Flask

from taces.data.database import StorageError


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Initialize the eight core tables without deleting existing data."""
        try:
            app.extensions["taces_database"].initialize()
        except (StorageError, sqlite3.Error, OSError) as error:
            raise click.ClickException(f"数据库初始化失败：{error}") from error
        click.echo("数据库初始化完成（identity.db / evaluation.db / metadata.db）。")
