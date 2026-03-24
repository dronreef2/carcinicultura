"""
Testes unitários — IoT Camarão Módulo 1

Valida modelos Pydantic, lógica de classificação de alertas
e a lógica auxiliar do backend sem necessidade de banco de dados.
"""

import pytest
from datetime import datetime, timezone

from pydantic import ValidationError

from app.models import (
    TelemetriaPayload,
    LeituraSensor,
    UltimaLeitura,
    Viveiro,
    Alerta,
    ComandoAtuadorRequest,
    ComandoAtuador,
)


# ─── TelemetriaPayload ─────────────────────────────────────────────────────────

class TestTelemetriaPayload:
    def test_payload_valido(self):
        t = TelemetriaPayload(
            timestamp=1710000000,
            pond_id="pond-01",
            device_id="esp32-01",
            temperature=28.5,
        )
        assert t.pond_id == "pond-01"
        assert t.temperature == 28.5

    def test_temperatura_minima_invalida(self):
        with pytest.raises(ValidationError):
            TelemetriaPayload(
                timestamp=1710000000,
                pond_id="pond-01",
                device_id="esp32-01",
                temperature=-20.0,  # abaixo do limite ge=-10
            )

    def test_temperatura_maxima_invalida(self):
        with pytest.raises(ValidationError):
            TelemetriaPayload(
                timestamp=1710000000,
                pond_id="pond-01",
                device_id="esp32-01",
                temperature=70.0,  # acima do limite le=60
            )

    def test_pond_id_vazio_invalido(self):
        with pytest.raises(ValidationError):
            TelemetriaPayload(
                timestamp=1710000000,
                pond_id="",  # min_length=1
                device_id="esp32-01",
                temperature=28.5,
            )

    def test_device_id_vazio_invalido(self):
        with pytest.raises(ValidationError):
            TelemetriaPayload(
                timestamp=1710000000,
                pond_id="pond-01",
                device_id="",  # min_length=1
                temperature=28.5,
            )

    def test_temperatura_nos_limites(self):
        t_min = TelemetriaPayload(
            timestamp=1710000000,
            pond_id="pond-01",
            device_id="esp32-01",
            temperature=-10.0,
        )
        assert t_min.temperature == -10.0

        t_max = TelemetriaPayload(
            timestamp=1710000000,
            pond_id="pond-01",
            device_id="esp32-01",
            temperature=60.0,
        )
        assert t_max.temperature == 60.0


# ─── UltimaLeitura ────────────────────────────────────────────────────────────

class TestUltimaLeitura:
    def test_sem_estatisticas(self):
        ts = datetime.now(timezone.utc)
        u = UltimaLeitura(pond_id="pond-01", temperature=29.0, timestamp=ts)
        assert u.min_24h is None
        assert u.max_24h is None
        assert u.avg_24h is None
        assert u.total_leituras_24h == 0

    def test_com_estatisticas(self):
        ts = datetime.now(timezone.utc)
        u = UltimaLeitura(
            pond_id="pond-01",
            temperature=29.0,
            timestamp=ts,
            min_24h=26.5,
            max_24h=31.2,
            avg_24h=28.8,
            total_leituras_24h=24,
        )
        assert u.min_24h == 26.5
        assert u.max_24h == 31.2
        assert u.total_leituras_24h == 24


# ─── Viveiro ──────────────────────────────────────────────────────────────────

class TestViveiro:
    def test_status_padrao(self):
        v = Viveiro(id="pond-01", name="Viveiro 1")
        assert v.status == "active"

    def test_status_personalizado(self):
        v = Viveiro(id="pond-02", name="Viveiro 2", status="inactive")
        assert v.status == "inactive"


# ─── Alerta ───────────────────────────────────────────────────────────────────

class TestAlerta:
    def test_alerta_warning(self):
        ts = datetime.now(timezone.utc)
        a = Alerta(
            pond_id="pond-01",
            severidade="warning",
            mensagem="Temperatura alta: 33.5°C > 32.0°C",
            temperatura=33.5,
            timestamp=ts,
        )
        assert a.severidade == "warning"
        assert a.reconhecido is False

    def test_alerta_critical(self):
        ts = datetime.now(timezone.utc)
        a = Alerta(
            pond_id="pond-01",
            severidade="critical",
            mensagem="Temperatura CRÍTICA (quente): 35.0°C ≥ 34.0°C",
            temperatura=35.0,
            timestamp=ts,
        )
        assert a.severidade == "critical"
        assert a.temperatura == 35.0

    def test_alerta_reconhecido(self):
        ts = datetime.now(timezone.utc)
        a = Alerta(
            pond_id="pond-01",
            severidade="warning",
            mensagem="Temperatura baixa: 23.5°C < 24.0°C",
            temperatura=23.5,
            timestamp=ts,
            reconhecido=True,
        )
        assert a.reconhecido is True


# ─── Classificação de temperatura (lógica do dashboard replicada) ─────────────

def classificar_temperatura(temp: float) -> str:
    """Replica a lógica de classificação do dashboard."""
    if temp >= 26 and temp <= 32:
        return "temp-ideal"
    if (temp >= 24 and temp < 26) or (temp > 32 and temp <= 34):
        return "temp-warning"
    return "temp-critical"


class TestClassificacaoTemperatura:
    def test_faixa_ideal(self):
        assert classificar_temperatura(26.0) == "temp-ideal"
        assert classificar_temperatura(29.0) == "temp-ideal"
        assert classificar_temperatura(32.0) == "temp-ideal"

    def test_faixa_warning_baixo(self):
        assert classificar_temperatura(24.0) == "temp-warning"
        assert classificar_temperatura(25.9) == "temp-warning"

    def test_faixa_warning_alto(self):
        assert classificar_temperatura(32.1) == "temp-warning"
        assert classificar_temperatura(34.0) == "temp-warning"

    def test_faixa_critical_baixo(self):
        assert classificar_temperatura(23.9) == "temp-critical"
        assert classificar_temperatura(10.0) == "temp-critical"

    def test_faixa_critical_alto(self):
        assert classificar_temperatura(34.1) == "temp-critical"
        assert classificar_temperatura(40.0) == "temp-critical"


# ─── Comando de atuador ───────────────────────────────────────────────────────

class TestComandoAtuador:
    def test_request_valido(self):
        cmd = ComandoAtuadorRequest(command="on", source="manual")
        assert cmd.command == "on"
        assert cmd.source == "manual"

    def test_request_pulse_com_duracao(self):
        cmd = ComandoAtuadorRequest(command="pulse", source="auto", duration_s=30)
        assert cmd.duration_s == 30

    def test_request_duracao_invalida(self):
        with pytest.raises(ValidationError):
            ComandoAtuadorRequest(command="pulse", source="auto", duration_s=0)

    def test_response_model(self):
        ts = datetime.now(timezone.utc)
        row = ComandoAtuador(
            id=1,
            command_id="4a2670aa-8cc8-4ef5-9706-e5a16d78e469",
            pond_id="pond-01",
            actuator_type="aerator",
            command="on",
            source="manual",
            status="sent",
            details="MQTT publish ok",
            created_at=ts,
        )
        assert row.actuator_type == "aerator"
        assert row.status == "sent"
        assert row.command_id is not None
