"""
Banco de Dados — IoT Camarão Módulo 1

Gerencia a conexão com o TimescaleDB e cria as tabelas necessárias.
Usa asyncpg via SQLAlchemy para operações assíncronas.
"""

import logging
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

logger = logging.getLogger("camarao.database")

# URL de conexão com o banco
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://camarao:camarao_db_senha_segura@localhost:5432/camarao_iot"
)

# Engine assíncrono do SQLAlchemy
engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    echo=False,
)

# Fábrica de sessões
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """Gera uma sessão do banco de dados para injeção de dependência."""
    async with async_session() as session:
        yield session


async def criar_schema():
    """
    Cria as tabelas e a hypertable no TimescaleDB.
    Executado uma vez na inicialização do backend.
    """
    async with engine.begin() as conn:
        logger.info("Criando schema do banco de dados...")

        # Habilita a extensão TimescaleDB
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
        logger.info("Extensão TimescaleDB habilitada.")

        # Tabela de viveiros
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS ponds (
                id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                farm_id VARCHAR(50) NOT NULL DEFAULT 'farm-01',
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            COMMENT ON TABLE ponds IS 'Viveiros de camarão cadastrados no sistema';
        """))
        logger.info("Tabela 'ponds' criada/verificada.")

        # Tabela de leituras de sensor (será convertida em hypertable)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id BIGSERIAL,
                timestamp TIMESTAMPTZ NOT NULL,
                pond_id VARCHAR(50) NOT NULL,
                device_id VARCHAR(50) NOT NULL,
                temperature DECIMAL(5,2),
                PRIMARY KEY (id, timestamp)
            );
        """))
        logger.info("Tabela 'sensor_readings' criada/verificada.")

        # Converte para hypertable do TimescaleDB (particionada por timestamp)
        # O migrate_data permite rodar mesmo se a tabela já tiver dados
        await conn.execute(text("""
            SELECT create_hypertable(
                'sensor_readings',
                by_range('timestamp'),
                if_not_exists => TRUE,
                migrate_data => TRUE
            );
        """))
        logger.info("Hypertable 'sensor_readings' configurada.")

        # Índice composto para consultas por viveiro + tempo
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_readings_pond_time
            ON sensor_readings (pond_id, timestamp DESC);
        """))
        logger.info("Índice 'idx_readings_pond_time' criado/verificado.")

        # Insere viveiros padrão se não existirem
        await conn.execute(text("""
            INSERT INTO ponds (id, name, farm_id)
            VALUES
                ('pond-01', 'Viveiro 1', 'farm-01'),
                ('pond-02', 'Viveiro 2', 'farm-01')
            ON CONFLICT (id) DO NOTHING;
        """))
        logger.info("Viveiros padrão inseridos.")

        # Tabela de alertas gerados pelo sistema
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alerts (
                id BIGSERIAL PRIMARY KEY,
                pond_id VARCHAR(50) NOT NULL,
                severidade VARCHAR(20) NOT NULL DEFAULT 'warning',
                mensagem TEXT NOT NULL,
                temperatura DECIMAL(5,2),
                reconhecido BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_pond_created
            ON alerts (pond_id, created_at DESC);
        """))
        logger.info("Tabela 'alerts' criada/verificada.")

        # Tabela de regras de alerta por viveiro
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS alert_rules (
                id SERIAL PRIMARY KEY,
                pond_id VARCHAR(50) NOT NULL DEFAULT '*',
                parametro VARCHAR(50) NOT NULL DEFAULT 'temperature',
                min_warning DECIMAL(6,2),
                min_critical DECIMAL(6,2),
                max_warning DECIMAL(6,2),
                max_critical DECIMAL(6,2),
                ativo BOOLEAN NOT NULL DEFAULT TRUE,
                UNIQUE (pond_id, parametro)
            );

            INSERT INTO alert_rules (pond_id, parametro, min_warning, min_critical, max_warning, max_critical)
            VALUES ('*', 'temperature', 24.0, 22.0, 32.0, 34.0)
            ON CONFLICT (pond_id, parametro) DO NOTHING;
        """))
        logger.info("Tabela 'alert_rules' e regras padrão criadas/verificadas.")

    logger.info("Schema do banco de dados pronto!")


async def fechar_conexao():
    """Encerra o pool de conexões ao desligar o backend."""
    await engine.dispose()
    logger.info("Conexão com o banco encerrada.")
