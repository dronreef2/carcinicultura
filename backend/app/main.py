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
import urllib.parse
import urllib.request
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

import paho.mqtt.client as mqtt
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import criar_schema, fechar_conexao, async_session, get_session
from app.models import (
    TelemetriaPayload,
    LeituraSensor,
    UltimaLeitura,
    Viveiro,
    Alerta,
    ComandoAtuador,
    ComandoAtuadorRequest,
)

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
MQTT_TOPIC_TELEMETRY = "farm/+/pond/+/telemetry"
MQTT_TOPIC_ACTUATOR_ACK = "farm/+/pond/+/actuator/+/ack"
ACTUATOR_MQTT_TOPIC_TEMPLATE = os.getenv(
    "ACTUATOR_MQTT_TOPIC_TEMPLATE",
    "farm/{farm_id}/pond/{pond_id}/actuator/{actuator_type}/set",
)

# Notificacao Telegram (opcional)
TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").strip().lower() in {
    "1", "true", "yes", "on"
}
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TELEGRAM_MIN_SEVERITY = os.getenv("TELEGRAM_MIN_SEVERITY", "warning").strip().lower()

# Origens CORS configuráveis via env (separadas por vírgula, ou "*" para todas)
_cors_origins_raw = os.getenv("CORS_ORIGINS", "*")
CORS_ORIGINS: list[str] = (
    ["*"] if _cors_origins_raw.strip() == "*"
    else [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
)

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

SEVERIDADE_ORDEM = {
    "warning": 1,
    "critical": 2,
}

COMANDOS_ATUADOR_VALIDOS = {"on", "off", "pulse"}
SOURCES_COMANDO_VALIDAS = {"manual", "auto"}


def deve_notificar_telegram(severidade: str) -> bool:
    """Retorna se a severidade atual deve gerar notificacao no Telegram."""
    if not TELEGRAM_ENABLED:
        return False

    limiar = TELEGRAM_MIN_SEVERITY if TELEGRAM_MIN_SEVERITY in SEVERIDADE_ORDEM else "warning"
    nivel_alerta = SEVERIDADE_ORDEM.get(severidade, 0)
    nivel_limiar = SEVERIDADE_ORDEM[limiar]
    return nivel_alerta >= nivel_limiar


def enviar_telegram_sync(alerta: Alerta) -> None:
    """Envia notificacao para Telegram usando a API HTTP oficial do bot."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("[ALERTA] Telegram habilitado, mas TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nao foram configurados.")
        return

    texto = (
        f"[IoT Camarao] ALERTA {alerta.severidade.upper()}\n"
        f"Viveiro: {alerta.pond_id}\n"
        f"Temperatura: {alerta.temperatura:.2f} C\n"
        f"Mensagem: {alerta.mensagem}\n"
        f"Horario: {alerta.timestamp.isoformat()}"
    )

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    body = urllib.parse.urlencode(
        {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": texto,
        }
    ).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=8) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"Falha ao enviar Telegram (status={resp.status})")


async def notificar_telegram(alerta: Alerta) -> None:
    """Dispara notificacao de alerta para Telegram de forma nao bloqueante."""
    if not deve_notificar_telegram(alerta.severidade):
        return

    try:
        await asyncio.to_thread(enviar_telegram_sync, alerta)
        logger.info(f"[ALERTA] Notificacao Telegram enviada para {alerta.pond_id} ({alerta.severidade}).")
    except Exception as e:
        logger.error(f"[ALERTA] Falha ao enviar Telegram: {e}")


async def obter_farm_id_por_viveiro(pond_id: str) -> Optional[str]:
    """Busca o farm_id do viveiro para compor tópicos MQTT de comando."""
    async with async_session() as session:
        result = await session.execute(
            text("SELECT farm_id FROM ponds WHERE id = :pond_id LIMIT 1"),
            {"pond_id": pond_id},
        )
        row = result.fetchone()
        return row.farm_id if row else None


async def registrar_comando_atuador(
    command_id: str,
    pond_id: str,
    actuator_type: str,
    command: str,
    source: str,
    status: str,
    details: Optional[str],
) -> ComandoAtuador:
    """Persiste um comando de atuador e retorna o registro criado."""
    async with async_session() as session:
        result = await session.execute(
            text("""
                INSERT INTO actuator_commands (command_id, pond_id, actuator_type, command, source, status, details)
                VALUES (:command_id, :pond_id, :actuator_type, :command, :source, :status, :details)
                RETURNING id, command_id, pond_id, actuator_type, command, source, status, details, created_at
            """),
            {
                "command_id": command_id,
                "pond_id": pond_id,
                "actuator_type": actuator_type,
                "command": command,
                "source": source,
                "status": status,
                "details": details,
            },
        )
        await session.commit()
        row = result.fetchone()

    return ComandoAtuador(
        id=row.id,
        command_id=row.command_id,
        pond_id=row.pond_id,
        actuator_type=row.actuator_type,
        command=row.command,
        source=row.source,
        status=row.status,
        details=row.details,
        created_at=row.created_at,
    )


def publicar_comando_mqtt(topic: str, payload: dict) -> tuple[bool, str]:
    """Publica comando no broker MQTT e retorna (sucesso, detalhe)."""
    if not mqtt_client or not mqtt_client.connected():
        return False, "MQTT offline"

    info = mqtt_client.publish(topic, json.dumps(payload), qos=0, retain=False)
    if info.rc == mqtt.MQTT_ERR_SUCCESS:
        return True, "MQTT publish ok"
    return False, f"MQTT publish falhou (rc={info.rc})"

# ─── Event loop referência (preenchida no startup) ──────────────────────────────

loop_principal: Optional[asyncio.AbstractEventLoop] = None

# ─── Cliente MQTT (paho-mqtt em thread separada) ───────────────────────────────


def ao_conectar_mqtt(client, userdata, flags, reason_code, properties):
    """Callback executado quando conecta ao broker MQTT."""
    logger.info(f"[MQTT] Conectado ao broker (rc={reason_code})")
    client.subscribe(MQTT_TOPIC_TELEMETRY)
    client.subscribe(MQTT_TOPIC_ACTUATOR_ACK)
    logger.info(f"[MQTT] Inscrito no tópico: {MQTT_TOPIC_TELEMETRY}")
    logger.info(f"[MQTT] Inscrito no tópico: {MQTT_TOPIC_ACTUATOR_ACK}")


def parse_topic_ack_atuador(topic: str) -> Optional[dict]:
    """Extrai dados do tópico de ACK: farm/{farm}/pond/{pond}/actuator/{type}/ack."""
    partes = topic.split("/")
    if len(partes) != 7:
        return None
    if partes[0] != "farm" or partes[2] != "pond" or partes[4] != "actuator" or partes[6] != "ack":
        return None

    return {
        "farm_id": partes[1],
        "pond_id": partes[3],
        "actuator_type": partes[5],
    }


async def processar_ack_atuador(topic: str, payload: dict):
    """Atualiza status do comando de atuador com base no ACK do firmware."""
    dados_topic = parse_topic_ack_atuador(topic)
    if not dados_topic:
        logger.warning(f"[MQTT] Tópico de ACK inválido: {topic}")
        return

    command = str(payload.get("command", "")).strip().lower()
    command_id = str(payload.get("command_id", "")).strip()
    ack_status = str(payload.get("status", "")).strip().lower()
    source = str(payload.get("source", "firmware")).strip().lower() or "firmware"
    message = str(payload.get("message", "")).strip() or "ack"
    device_id = str(payload.get("device_id", "unknown")).strip() or "unknown"
    timestamp = str(payload.get("timestamp", ""))

    if not command:
        logger.warning(f"[MQTT] ACK sem comando: {payload}")
        return

    novo_status = "confirmed" if ack_status == "ok" else "error"
    detalhe_ack = (
        f" | ack_status={ack_status or 'unknown'} source={source} device={device_id} "
        f"ts={timestamp} msg={message}"
    )

    async with async_session() as session:
        if command_id:
            result = await session.execute(
                text("""
                    UPDATE actuator_commands
                    SET
                        status = :novo_status,
                        details = COALESCE(details, '') || :detalhe_ack
                    WHERE command_id = :command_id
                      AND pond_id = :pond_id
                    RETURNING id
                """),
                {
                    "novo_status": novo_status,
                    "detalhe_ack": detalhe_ack,
                    "command_id": command_id,
                    "pond_id": dados_topic["pond_id"],
                },
            )
        else:
            # Fallback de compatibilidade para comandos antigos sem command_id
            result = await session.execute(
                text("""
                    UPDATE actuator_commands
                    SET
                        status = :novo_status,
                        details = COALESCE(details, '') || :detalhe_ack
                    WHERE id = (
                        SELECT id
                        FROM actuator_commands
                        WHERE pond_id = :pond_id
                          AND actuator_type = :actuator_type
                          AND command = :command
                          AND status IN ('pending', 'sent')
                        ORDER BY created_at DESC
                        LIMIT 1
                    )
                    RETURNING id
                """),
                {
                    "novo_status": novo_status,
                    "detalhe_ack": detalhe_ack,
                    "pond_id": dados_topic["pond_id"],
                    "actuator_type": dados_topic["actuator_type"],
                    "command": command,
                },
            )
        row = result.fetchone()
        await session.commit()

    if row:
        logger.info(
            f"[ATUADOR] ACK aplicado no comando id={row.id} pond={dados_topic['pond_id']} "
            f"actuator={dados_topic['actuator_type']} status={novo_status}"
        )
    else:
        logger.warning(
            f"[ATUADOR] ACK sem comando pendente compatível: pond={dados_topic['pond_id']} "
            f"actuator={dados_topic['actuator_type']} command={command}"
        )


def ao_receber_mensagem(client, userdata, msg):
    """
    Callback executado ao receber uma mensagem MQTT.

    Valida o JSON, salva no banco e notifica WebSockets conectados.
    Roda em thread do paho-mqtt, então agenda tarefas no event loop principal.
    """
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        logger.info(f"[MQTT] Recebido de {msg.topic}: {payload}")

        # ACK de atuador vindo do firmware
        if msg.topic.endswith("/ack") and "/actuator/" in msg.topic:
            if loop_principal and loop_principal.is_running():
                asyncio.run_coroutine_threadsafe(
                    processar_ack_atuador(msg.topic, payload),
                    loop_principal,
                )
            return

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
    1. Insere no banco de dados (TimescaleDB) — ignora duplicatas
    2. Verifica thresholds e registra alertas quando necessário
    3. Notifica clientes WebSocket conectados ao viveiro
    """
    ts = datetime.fromtimestamp(telemetria.timestamp, tz=timezone.utc)

    # Insere no banco com tratamento de erro e rollback explícito
    async with async_session() as session:
        try:
            await session.execute(
                text("""
                    INSERT INTO sensor_readings (timestamp, pond_id, device_id, temperature, dissolved_oxygen)
                    VALUES (:ts, :pond_id, :device_id, :temperature, :dissolved_oxygen)
                    ON CONFLICT DO NOTHING
                """),
                {
                    "ts": ts,
                    "pond_id": telemetria.pond_id,
                    "device_id": telemetria.device_id,
                    "temperature": telemetria.temperature,
                    "dissolved_oxygen": telemetria.dissolved_oxygen,
                },
            )
            await session.commit()

            logger.info(
                f"[DB] Inserido: {telemetria.pond_id} → {telemetria.temperature}°C @ {ts.isoformat()}"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"[DB] Falha ao inserir leitura de {telemetria.pond_id}: {e}")
            return

    # Verifica thresholds e registra alerta se necessário
    alerta = await verificar_alertas(telemetria.pond_id, telemetria.temperature, ts)
    if not alerta and telemetria.dissolved_oxygen is not None:
        alerta = await verificar_alertas_od(telemetria.pond_id, telemetria.dissolved_oxygen, ts)

    # Monta payload WebSocket (inclui alerta se houver)
    ws_payload: dict = {
        "tipo": "leitura",
        "pond_id": telemetria.pond_id,
        "temperature": telemetria.temperature,
        "dissolved_oxygen": telemetria.dissolved_oxygen,
        "timestamp": ts.isoformat(),
        "device_id": telemetria.device_id,
    }
    if alerta:
        ws_payload["alerta"] = {
            "severidade": alerta.severidade,
            "mensagem": alerta.mensagem,
        }

    # Notifica via WebSocket
    await ws_manager.enviar_para_viveiro(telemetria.pond_id, ws_payload)


async def verificar_alertas(pond_id: str, temperatura: float, ts: datetime) -> Optional[Alerta]:
    """
    Verifica se a temperatura ultrapassa os thresholds definidos nas regras de alerta.
    Persiste o alerta no banco e retorna o objeto de alerta (ou None se dentro da faixa).
    """
    async with async_session() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT min_warning, min_critical, max_warning, max_critical
                    FROM alert_rules
                    WHERE (pond_id = :pond_id OR pond_id = '*')
                      AND parametro = 'temperature'
                      AND ativo = TRUE
                    ORDER BY pond_id DESC
                    LIMIT 1
                """),
                {"pond_id": pond_id},
            )
            regra = result.fetchone()
        except Exception as e:
            logger.error(f"[ALERTA] Erro ao consultar regras: {e}")
            return None

    if not regra:
        return None

    min_warn = float(regra.min_warning) if regra.min_warning is not None else None
    min_crit = float(regra.min_critical) if regra.min_critical is not None else None
    max_warn = float(regra.max_warning) if regra.max_warning is not None else None
    max_crit = float(regra.max_critical) if regra.max_critical is not None else None

    severidade = None
    mensagem = None

    if min_crit is not None and temperatura <= min_crit:
        severidade = "critical"
        mensagem = f"Temperatura CRÍTICA (fria): {temperatura:.1f}°C ≤ {min_crit}°C"
    elif max_crit is not None and temperatura >= max_crit:
        severidade = "critical"
        mensagem = f"Temperatura CRÍTICA (quente): {temperatura:.1f}°C ≥ {max_crit}°C"
    elif min_warn is not None and temperatura < min_warn:
        severidade = "warning"
        mensagem = f"Temperatura baixa: {temperatura:.1f}°C < {min_warn}°C"
    elif max_warn is not None and temperatura > max_warn:
        severidade = "warning"
        mensagem = f"Temperatura alta: {temperatura:.1f}°C > {max_warn}°C"

    if not severidade:
        return None

    alerta = Alerta(
        pond_id=pond_id,
        severidade=severidade,
        mensagem=mensagem,
        temperatura=temperatura,
        timestamp=ts,
    )

    # Persiste o alerta no banco
    async with async_session() as session:
        try:
            await session.execute(
                text("""
                    INSERT INTO alerts (pond_id, severidade, mensagem, temperatura, created_at)
                    VALUES (:pond_id, :severidade, :mensagem, :temperatura, :created_at)
                """),
                {
                    "pond_id": pond_id,
                    "severidade": severidade,
                    "mensagem": mensagem,
                    "temperatura": temperatura,
                    "created_at": ts,
                },
            )
            await session.commit()
            logger.warning(f"[ALERTA] {severidade.upper()} em {pond_id}: {mensagem}")
        except Exception as e:
            await session.rollback()
            logger.error(f"[ALERTA] Falha ao persistir alerta: {e}")

    # Notifica por Telegram (opcional)
    await notificar_telegram(alerta)

    return alerta


async def verificar_alertas_od(pond_id: str, dissolved_oxygen: float, ts: datetime) -> Optional[Alerta]:
    """
    Verifica thresholds de OD (dissolved_oxygen) e registra alerta quando necessário.
    Usa os mesmos campos de armazenamento de alerta do módulo 1 para manter compatibilidade.
    """
    async with async_session() as session:
        try:
            result = await session.execute(
                text("""
                    SELECT min_warning, min_critical, max_warning, max_critical
                    FROM alert_rules
                    WHERE (pond_id = :pond_id OR pond_id = '*')
                      AND parametro = 'dissolved_oxygen'
                      AND ativo = TRUE
                    ORDER BY pond_id DESC
                    LIMIT 1
                """),
                {"pond_id": pond_id},
            )
            regra = result.fetchone()
        except Exception as e:
            logger.error(f"[ALERTA] Erro ao consultar regras de OD: {e}")
            return None

    if not regra:
        return None

    min_warn = float(regra.min_warning) if regra.min_warning is not None else None
    min_crit = float(regra.min_critical) if regra.min_critical is not None else None
    max_warn = float(regra.max_warning) if regra.max_warning is not None else None
    max_crit = float(regra.max_critical) if regra.max_critical is not None else None

    severidade = None
    mensagem = None

    if min_crit is not None and dissolved_oxygen <= min_crit:
        severidade = "critical"
        mensagem = f"OD CRÍTICO: {dissolved_oxygen:.1f} mg/L ≤ {min_crit} mg/L"
    elif max_crit is not None and dissolved_oxygen >= max_crit:
        severidade = "critical"
        mensagem = f"OD CRÍTICO (alto): {dissolved_oxygen:.1f} mg/L ≥ {max_crit} mg/L"
    elif min_warn is not None and dissolved_oxygen < min_warn:
        severidade = "warning"
        mensagem = f"OD baixo: {dissolved_oxygen:.1f} mg/L < {min_warn} mg/L"
    elif max_warn is not None and dissolved_oxygen > max_warn:
        severidade = "warning"
        mensagem = f"OD alto: {dissolved_oxygen:.1f} mg/L > {max_warn} mg/L"

    if not severidade:
        return None

    alerta = Alerta(
        pond_id=pond_id,
        severidade=severidade,
        mensagem=mensagem,
        temperatura=dissolved_oxygen,
        timestamp=ts,
    )

    async with async_session() as session:
        try:
            await session.execute(
                text("""
                    INSERT INTO alerts (pond_id, severidade, mensagem, temperatura, created_at)
                    VALUES (:pond_id, :severidade, :mensagem, :temperatura, :created_at)
                """),
                {
                    "pond_id": pond_id,
                    "severidade": severidade,
                    "mensagem": mensagem,
                    "temperatura": dissolved_oxygen,
                    "created_at": ts,
                },
            )
            await session.commit()
            logger.warning(f"[ALERTA] {severidade.upper()} em {pond_id}: {mensagem}")
        except Exception as e:
            await session.rollback()
            logger.error(f"[ALERTA] Falha ao persistir alerta de OD: {e}")

    await notificar_telegram(alerta)
    return alerta


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
    version="1.1.0",
    lifespan=lifespan,
)

# Habilita CORS — origens configuráveis via variável de ambiente CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
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
    limit: int = Query(default=1000, ge=1, le=5000, description="Limite máximo de registros"),
    session: AsyncSession = Depends(get_session),
):
    """
    Retorna as leituras de sensor de um viveiro nas últimas N horas.
    Padrão: últimas 24 horas. Máximo: 168 horas (7 dias).
    O parâmetro `limit` controla o número máximo de pontos retornados (padrão 1000).
    """
    desde = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await session.execute(
        text("""
            SELECT id, timestamp, pond_id, device_id, temperature, dissolved_oxygen
            FROM sensor_readings
            WHERE pond_id = :pond_id AND timestamp >= :desde
            ORDER BY timestamp ASC
            LIMIT :limit
        """),
        {"pond_id": pond_id, "desde": desde, "limit": limit},
    )
    rows = result.fetchall()
    return [
        LeituraSensor(
            id=r.id,
            timestamp=r.timestamp,
            pond_id=r.pond_id,
            device_id=r.device_id,
            temperature=float(r.temperature) if r.temperature else 0,
            dissolved_oxygen=float(r.dissolved_oxygen) if r.dissolved_oxygen is not None else None,
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


@app.get("/api/ponds/{pond_id}/alerts", response_model=list[Alerta])
async def listar_alertas(
    pond_id: str,
    hours: int = Query(default=24, ge=1, le=168, description="Horas de histórico (1-168)"),
    limit: int = Query(default=50, ge=1, le=500, description="Limite máximo de alertas"),
    session: AsyncSession = Depends(get_session),
):
    """
    Retorna os alertas de temperatura gerados para um viveiro nas últimas N horas.
    """
    desde = datetime.now(timezone.utc) - timedelta(hours=hours)

    result = await session.execute(
        text("""
            SELECT pond_id, severidade, mensagem, temperatura, reconhecido, created_at
            FROM alerts
            WHERE pond_id = :pond_id AND created_at >= :desde
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"pond_id": pond_id, "desde": desde, "limit": limit},
    )
    rows = result.fetchall()
    return [
        Alerta(
            pond_id=r.pond_id,
            severidade=r.severidade,
            mensagem=r.mensagem,
            temperatura=float(r.temperatura),
            timestamp=r.created_at,
            reconhecido=r.reconhecido,
        )
        for r in rows
    ]


@app.patch("/api/ponds/{pond_id}/alerts/{alert_id}/acknowledge")
async def reconhecer_alerta(
    pond_id: str,
    alert_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Marca um alerta como reconhecido (acknowledge)."""
    result = await session.execute(
        text("""
            UPDATE alerts
            SET reconhecido = TRUE
            WHERE id = :alert_id AND pond_id = :pond_id
            RETURNING id
        """),
        {"alert_id": alert_id, "pond_id": pond_id},
    )
    updated = result.fetchone()
    if not updated:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    await session.commit()
    return {"status": "ok", "alert_id": alert_id}


@app.post("/api/ponds/{pond_id}/actuators/aerator/commands", response_model=ComandoAtuador)
async def acionar_aerador(
    pond_id: str,
    payload: ComandoAtuadorRequest,
):
    """
    Registra e publica comando de aerador via MQTT.
    Comandos suportados: on, off, pulse.
    """
    command = payload.command.strip().lower()
    source = payload.source.strip().lower()

    if command not in COMANDOS_ATUADOR_VALIDOS:
        raise HTTPException(status_code=400, detail="Comando inválido. Use: on, off ou pulse")

    if source not in SOURCES_COMANDO_VALIDAS:
        raise HTTPException(status_code=400, detail="Source inválido. Use: manual ou auto")

    if command == "pulse" and payload.duration_s is None:
        raise HTTPException(status_code=400, detail="duration_s é obrigatório para comando pulse")

    farm_id = await obter_farm_id_por_viveiro(pond_id)
    if not farm_id:
        raise HTTPException(status_code=404, detail="Viveiro não encontrado")

    actuator_type = "aerator"
    topic = ACTUATOR_MQTT_TOPIC_TEMPLATE.format(
        farm_id=farm_id,
        pond_id=pond_id,
        actuator_type=actuator_type,
    )

    mqtt_payload = {
        "command_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "farm_id": farm_id,
        "pond_id": pond_id,
        "actuator_type": actuator_type,
        "command": command,
        "source": source,
    }
    if payload.duration_s is not None:
        mqtt_payload["duration_s"] = payload.duration_s

    publicado, detalhe = publicar_comando_mqtt(topic, mqtt_payload)
    status = "sent" if publicado else "pending"
    details = f"{detalhe}; topic={topic}; payload={json.dumps(mqtt_payload)}"

    comando = await registrar_comando_atuador(
        command_id=mqtt_payload["command_id"],
        pond_id=pond_id,
        actuator_type=actuator_type,
        command=command,
        source=source,
        status=status,
        details=details,
    )

    return comando


@app.get("/api/ponds/{pond_id}/actuators/commands", response_model=list[ComandoAtuador])
async def listar_comandos_atuador(
    pond_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Limite máximo de comandos"),
    session: AsyncSession = Depends(get_session),
):
    """Lista histórico de comandos de atuadores de um viveiro."""
    result = await session.execute(
        text("""
            SELECT id, command_id, pond_id, actuator_type, command, source, status, details, created_at
            FROM actuator_commands
            WHERE pond_id = :pond_id
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"pond_id": pond_id, "limit": limit},
    )
    rows = result.fetchall()
    return [
        ComandoAtuador(
            id=r.id,
            command_id=r.command_id,
            pond_id=r.pond_id,
            actuator_type=r.actuator_type,
            command=r.command,
            source=r.source,
            status=r.status,
            details=r.details,
            created_at=r.created_at,
        )
        for r in rows
    ]


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
