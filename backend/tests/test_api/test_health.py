"""Tests for health endpoint."""

import pytest


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_has_status(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()["data"]
        assert "status" in data

    def test_health_has_version(self, client):
        resp = client.get("/api/v1/health")
        data = resp.json()["data"]
        assert "version" in data
