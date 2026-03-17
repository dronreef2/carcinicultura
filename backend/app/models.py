"""
Modelos Pydantic — IoT Camarão Módulo 1

Define os esquemas de validação para dados de telemetria,
respostas da API e mensagens WebSocket.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# ─── Telemetria recebida do MQTT ────────────────────────────────────────────────

class TelemetriaPayload(BaseModel):
    """Payload JSON recebido do ESP32 via MQTT."""
    timestamp: int = Field(..., description="Epoch Unix em segundos")
    pond_id: str = Field(..., description="Identificador do viveiro")
    device_id: str = Field(..., description="Identificador do dispositivo")
    temperature: float = Field(..., ge=-10, le=60, description="Temperatura em °C")


# ─── Modelos de resposta da API ─────────────────────────────────────────────────

class LeituraSensor(BaseModel):
    """Leitura individual do sensor retornada pela API."""
    id: int
    timestamp: datetime
    pond_id: str
    device_id: str
    temperature: float

    class Config:
        from_attributes = True


class UltimaLeitura(BaseModel):
    """Última leitura de um viveiro com estatísticas de 24h."""
    pond_id: str
    temperature: float
    timestamp: datetime
    min_24h: Optional[float] = None
    max_24h: Optional[float] = None
    avg_24h: Optional[float] = None
    total_leituras_24h: int = 0


class Viveiro(BaseModel):
    """Dados de um viveiro cadastrado."""
    id: str
    name: str
    status: str = "active"


class EstatisticasViveiro(BaseModel):
    """Estatísticas resumidas de um viveiro."""
    pond_id: str
    leituras_total: int
    temperatura_atual: Optional[float] = None
    temperatura_min_24h: Optional[float] = None
    temperatura_max_24h: Optional[float] = None
    temperatura_media_24h: Optional[float] = None
    ultima_leitura: Optional[datetime] = None


# ─── WebSocket ──────────────────────────────────────────────────────────────────

class MensagemWs(BaseModel):
    """Mensagem enviada via WebSocket para o dashboard."""
    tipo: str = "leitura"
    pond_id: str
    temperature: float
    timestamp: datetime
