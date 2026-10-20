"""Liveness and storage readiness are deliberately separate probes."""

from flask import Blueprint, current_app, jsonify


health = Blueprint("health", __name__)


@health.get("/health")
def health_check():
    return jsonify(data={"service": "taces", "status": "ok"})


@health.get("/ready")
def readiness_check():
    current_app.extensions["taces_database"].check_ready()
    return jsonify(data={"service": "taces", "status": "ready"})
