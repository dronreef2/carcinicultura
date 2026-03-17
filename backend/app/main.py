"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  Backend FastAPI — IoT Camarão Módulo 1                                    ║
║  Recebe telemetria MQTT, armazena no TimescaleDB, serve API + WebSocket    ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import criar_schema, fechar_conexao, async_session, get_session
from app.models import TelemetriaPayload, LeituraSensor, UltimaLeitura, Viveiro

# ─── Configuração de logging ───────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("camarao.backend")

# ─── Configurações MQTT via variáveis de ambiente ───────────────────────────────

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "camarao")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "mqtt_senha_segura")
MQTT_TOPIC = "farm/+/pond/+/telemetry"

# ─── Gerenciador de WebSockets ativos ──────────────────────────────────────────


class GerenciadorWebSocket:
    """Gerencia conexões WebSocket ativas agrupadas por viveiro."""

    def __init__(self):
        # Mapa: pond_id → conjunto de websockets conectados
        self.conexoes: dict[str, set[WebSocket]] = {}

    async def conectar(self, pond_id: str, websocket: WebSocket):
        """Registra uma nova conexão WebSocket para um viveiro."""
        await websocket.accept()
        if pond_id not in self.conexoes:
            self.conexoes[pond_id] = set()
        self.conexoes[pond_id].add(websocket)
        logger.info(f"[WS] Nova conexão para {pond_id} (total: {len(self.conexoes[pond_id])})")

    def desconectar(self, pond_id: str, websocket: WebSocket):
        """Remove uma conexão WebSocket encerrada."""
        if pond_id in self.conexoes:
            self.conexoes[pond_id].discard(websocket)
            if not self.conexoes[pond_id]:
                del self.conexoes[pond_id]
            logger.info(f"[WS] Conexão encerrada para {pond_id}")

    async def enviar_para_viveiro(self, pond_id: str, dados: dict):
        """Envia dados para todos os WebSockets conectados a um viveiro."""
        if pond_id not in self.conexoes:
            return

        desconectados = set()
        for ws in self.conexoes[pond_id]:
            try:
                await ws.send_json(dados)
            except Exception:
                desconectados.add(ws)

        # Remove conexões quebradas
        for ws in desconectados:
            self.conexoes[pond_id].discard(ws)


ws_manager = GerenciadorWebSocket()

# ─── Event loop referência (preenchida no startup) ──────────────────────────────

loop_principal: Optional[asyncio.AbstractEventLoop] = None

# ─── Cliente MQTT (paho-mqtt em thread separada) ───────────────────────────────


def ao_conectar_mqtt(client, userdata, flags, reason_code, properties):
    """Callback executado quando conecta ao broker MQTT."""
    logger.info(f"[MQTT] Conectado ao broker (rc={reason_code})")
    client.subscribe(MQTT_TOPIC)
    logger.info(f"[MQTT] Inscrito no tópico: {MQTT_TOPIC}")


def ao_receber_mensagem(client, userdata, msg):
    """
    Callback executado ao receber uma mensagem MQTT.

    Valida o JSON, salva no banco e notifica WebSockets conectados.
    Roda em thread do paho-mqtt, então agenda tarefas no event loop principal.
    """
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"[MQTT] Recebido de {msg.topic}: {payload}")

        # Valida o payload com Pydantic
        telemetria = TelemetriaPayload(**payload)

        # Agenda a inserção no banco (assíncrona) no event loop do FastAPI
        if loop_principal and loop_principal.is_running():
            asyncio.run_coroutine_threadsafe(
                processar_telemetria(telemetria),
                loop_principal,
            )

    except json.JSONDecodeError:
        logger.error(f"[MQTT] JSON inválido: {msg.payload}")
    except Exception as e:
        logger.error(f"[MQTT] Erro ao processar mensagem: {e}")


async def processar_telemetria(telemetria: TelemetriaPayload):
    """
    Processa uma leitura de telemetria:
    1. Insere no banco de dados (TimescaleDB)
    2. Notifica clientes WebSocket conectados ao viveiro
    """
    ts = datetime.fromtimestamp(telemetria.timestamp, tz=timezone.utc)

    # Insere no banco
    async with async_session() as session:
        await session.execute(
            text("""
                INSERT INTO sensor_readings (timestamp, pond_id, device_id, temperature)
                VALUES (:ts, :pond_id, :device_id, :temperature)
            """),
            {
                "ts": ts,
                "pond_id": telemetria.pond_id,
                "device_id": telemetria.device_id,
                "temperature": telemetria.temperature,
            },
        )
        await session.commit()

    logger.info(
        f"[DB] Inserido: {telemetria.pond_id} → {telemetria.temperature}°C @ {ts.isoformat()}"
    )

    # Notifica via WebSocket
    await ws_manager.enviar_para_viveiro(
        telemetria.pond_id,
        {
            "tipo": "leitura",
            "pond_id": telemetria.pond_id,
            "temperature": telemetria.temperature,
            "timestamp": ts.isoformat(),
            "device_id": telemetria.device_id,
        },
    )


def iniciar_mqtt():
    """Cria e inicia o cliente MQTT em thread separada."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="camarao-backend",
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
    client.on_connect = ao_conectar_mqtt
    client.on_message = ao_receber_mensagem

    # Reconexão automática
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        client.loop_start()  # Inicia a thread de rede do paho-mqtt
        logger.info(f"[MQTT] Cliente iniciado → {MQTT_HOST}:{MQTT_PORT}")
    except Exception as e:
        logger.error(f"[MQTT] Falha ao conectar: {e}")
        logger.warning("[MQTT] O backend continuará sem MQTT. Reconexão automática ativa.")
        # Tenta reconectar em background
        client.loop_start()

    return client


# ─── Ciclo de vida da aplicação ─────────────────────────────────────────────────

mqtt_client: Optional[mqtt.Client] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia startup e shutdown da aplicação."""
    global loop_principal, mqtt_client

    logger.info("=" * 60)
    logger.info("  IoT Camarão — Backend Módulo 1 — Iniciando...")
    logger.info("=" * 60)

    # Salva referência ao event loop principal
    loop_principal = asyncio.get_running_loop()

    # Cria o schema do banco
    await criar_schema()

    # Inicia o cliente MQTT
    mqtt_client = iniciar_mqtt()

    yield  # Aplicação rodando

    # Shutdown
    logger.info("Encerrando backend...")
    if mqtt_client:
        mqtt_client.loop_stop()
        mqtt_client.disconnect()
    await fechar_conexao()
    logger.info("Backend encerrado.")


# ─── Aplicação FastAPI ──────────────────────────────────────────────────────────

app = FastAPI(
    title="IoT Camarão — API",
    description="API do sistema IoT para monitoramento de viveiros de camarão",
    version="1.0.0",
    lifespan=lifespan,
)

# Habilita CORS para o dashboard acessar a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Endpoints da API ──────────────────────────────────────────────────────────


@app.get("/api/health")
async def health_check():
    """Verifica se o backend está funcionando."""
    return {"status": "ok", "servico": "IoT Camarão Backend"}


@app.get("/api/ponds", response_model=list[Viveiro])
async def listar_viveiros(session: AsyncSession = Depends(get_session)):
    """Retorna todos os viveiros cadastrados."""
    result = await session.execute(
        text("SELECT id, name, status FROM ponds ORDER BY name")
    )
    rows = result.fetchall()
    return [Viveiro(id=r.id, name=r.name, status=r.status) for r in rows]


@app.get("/api/ponds/{pond_id}/readings", response_model=list[LeituraSensor])
async def listar_leituras(
    pond_id: str,
    hours: int = Query(default=24, ge=1, le=168, description="Horas de histórico (1-168)"),
    session: AsyncSession = Depends(get_session),
):
    """
    Retorna as leituras de sensor de um viveiro nas últimas N horas.
    Padrão: últimas 24 horas. Máximo: 168 horas (7 dias).
    """
    desde = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await session.execute(
        text("""
            SELECT id, timestamp, pond_id, device_id, temperature
            FROM sensor_readings
            WHERE pond_id = :pond_id AND timestamp >= :desde
            ORDER BY timestamp ASC
        """),
        {"pond_id": pond_id, "desde": desde},
    )
    rows = result.fetchall()
    return [
        LeituraSensor(
            id=r.id,
            timestamp=r.timestamp,
            pond_id=r.pond_id,
            device_id=r.device_id,
            temperature=float(r.temperature) if r.temperature else 0,
        )
        for r in rows
    ]


@app.get("/api/ponds/{pond_id}/latest", response_model=UltimaLeitura)
async def ultima_leitura(
    pond_id: str,
    session: AsyncSession = Depends(get_session),
):
    """
    Retorna a última leitura de um viveiro junto com estatísticas de 24h
    (mínima, máxima, média, total de leituras).
    """
    desde_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    # Última leitura
    result_ultima = await session.execute(
        text("""
            SELECT timestamp, temperature, device_id
            FROM sensor_readings
            WHERE pond_id = :pond_id
            ORDER BY timestamp DESC
            LIMIT 1
        """),
        {"pond_id": pond_id},
    )
    ultima = result_ultima.fetchone()

    if not ultima:
        return UltimaLeitura(
            pond_id=pond_id,
            temperature=0,
            timestamp=datetime.now(timezone.utc),
        )

    # Estatísticas 24h
    result_stats = await session.execute(
        text("""
            SELECT
                MIN(temperature) as min_temp,
                MAX(temperature) as max_temp,
                AVG(temperature) as avg_temp,
                COUNT(*) as total
            FROM sensor_readings
            WHERE pond_id = :pond_id AND timestamp >= :desde
        """),
        {"pond_id": pond_id, "desde": desde_24h},
    )
    stats = result_stats.fetchone()

    return UltimaLeitura(
        pond_id=pond_id,
        temperature=float(ultima.temperature),
        timestamp=ultima.timestamp,
        min_24h=float(stats.min_temp) if stats.min_temp else None,
        max_24h=float(stats.max_temp) if stats.max_temp else None,
        avg_24h=round(float(stats.avg_temp), 2) if stats.avg_temp else None,
        total_leituras_24h=stats.total,
    )


# ─── WebSocket para streaming em tempo real ─────────────────────────────────────


@app.websocket("/ws/ponds/{pond_id}")
async def websocket_viveiro(websocket: WebSocket, pond_id: str):
    """
    WebSocket para receber leituras de um viveiro em tempo real.
    O dashboard se conecta aqui para atualizar o gráfico ao vivo.
    """
    await ws_manager.conectar(pond_id, websocket)

    try:
        while True:
            # Mantém a conexão aberta; aguarda mensagens do cliente (ping/pong)
            data = await websocket.receive_text()
            # Cliente pode enviar "ping" para manter a conexão viva
            if data == "ping":
                await websocket.send_json({"tipo": "pong"})
    except WebSocketDisconnect:
        ws_manager.desconectar(pond_id, websocket)
    except Exception as e:
        logger.error(f"[WS] Erro na conexão {pond_id}: {e}")
        ws_manager.desconectar(pond_id, websocket)
