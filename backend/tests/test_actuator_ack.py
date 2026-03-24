"""
Testes de ACK de atuador — correlação por command_id

Valida que o backend prioriza command_id para atualizar o comando correto,
e mantém fallback para comandos legados sem command_id.
"""

import asyncio
import sys
import types


def _garantir_stub_paho():
    if "paho.mqtt.client" in sys.modules:
        return

    paho_mod = types.ModuleType("paho")
    mqtt_mod = types.ModuleType("paho.mqtt")
    client_mod = types.ModuleType("paho.mqtt.client")

    class _DummyClient:
        pass

    class _DummyCallbackApiVersion:
        VERSION2 = 2

    client_mod.Client = _DummyClient
    client_mod.CallbackAPIVersion = _DummyCallbackApiVersion
    client_mod.MQTTv5 = 5
    client_mod.MQTT_ERR_SUCCESS = 0

    paho_mod.mqtt = mqtt_mod
    mqtt_mod.client = client_mod

    sys.modules["paho"] = paho_mod
    sys.modules["paho.mqtt"] = mqtt_mod
    sys.modules["paho.mqtt.client"] = client_mod


_garantir_stub_paho()

from app import main


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, row=None):
        self.row = row
        self.last_query = None
        self.last_params = None
        self.commit_called = False

    async def execute(self, query, params):
        self.last_query = str(query)
        self.last_params = params
        return _FakeResult(self.row)

    async def commit(self):
        self.commit_called = True


class _FakeSessionFactory:
    def __init__(self, session):
        self.session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_ack_usa_command_id_quando_disponivel(monkeypatch):
    session = _FakeSession(row=type("Row", (), {"id": 123})())
    monkeypatch.setattr(main, "async_session", _FakeSessionFactory(session))

    topic = "farm/farm-01/pond/pond-01/actuator/aerator/ack"
    payload = {
        "command": "on",
        "command_id": "cmd-123",
        "status": "ok",
        "source": "manual",
        "device_id": "esp32-01",
        "timestamp": "2026-03-24T10:00:00Z",
        "message": "executed",
    }

    asyncio.run(main.processar_ack_atuador(topic, payload))

    assert session.commit_called is True
    assert "WHERE command_id = :command_id" in session.last_query
    assert session.last_params["command_id"] == "cmd-123"
    assert session.last_params["pond_id"] == "pond-01"
    assert session.last_params["novo_status"] == "confirmed"


def test_ack_fallback_sem_command_id(monkeypatch):
    session = _FakeSession(row=type("Row", (), {"id": 456})())
    monkeypatch.setattr(main, "async_session", _FakeSessionFactory(session))

    topic = "farm/farm-01/pond/pond-01/actuator/aerator/ack"
    payload = {
        "command": "pulse",
        "status": "error",
        "source": "auto",
        "device_id": "esp32-01",
        "timestamp": "2026-03-24T10:01:00Z",
        "message": "command_invalid",
    }

    asyncio.run(main.processar_ack_atuador(topic, payload))

    assert session.commit_called is True
    assert "WHERE id = (" in session.last_query
    assert session.last_params["pond_id"] == "pond-01"
    assert session.last_params["actuator_type"] == "aerator"
    assert session.last_params["command"] == "pulse"
    assert session.last_params["novo_status"] == "error"
