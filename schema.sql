-- ============================================================================
-- Schema: Sistema IoT + IA para Carcinicultura (Shrimp Farming)
-- Banco: PostgreSQL + TimescaleDB
-- Versão: 1.0
-- Data: 2026-03-17
-- ============================================================================

-- ============================================================================
-- 1. EXTENSÕES
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- 2. TABELAS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Usuários do sistema
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(255) NOT NULL UNIQUE,
    name        VARCHAR(200) NOT NULL,
    role        VARCHAR(20)  NOT NULL CHECK (role IN ('admin', 'operator', 'viewer')),
    farm_id     UUID,  -- FK adicionada após criação de farms
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE users IS 'Usuários do sistema — administradores, operadores e visualizadores das fazendas.';

-- ----------------------------------------------------------------------------
-- Fazendas
-- ----------------------------------------------------------------------------
CREATE TABLE farms (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(200) NOT NULL,
    location    VARCHAR(300) NOT NULL,
    area_ha     DECIMAL(10,2) NOT NULL CHECK (area_ha > 0),
    owner_id    UUID NOT NULL REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE farms IS 'Fazendas de camarão cadastradas no sistema. Cada fazenda possui múltiplos viveiros.';

-- FK de users -> farms (referência circular resolvida com ALTER)
ALTER TABLE users
    ADD CONSTRAINT fk_users_farm
    FOREIGN KEY (farm_id) REFERENCES farms(id);

-- ----------------------------------------------------------------------------
-- Viveiros (Ponds)
-- ----------------------------------------------------------------------------
CREATE TABLE ponds (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id     UUID NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    area_m2     DECIMAL(10,2) NOT NULL CHECK (area_m2 > 0),
    depth_m     DECIMAL(4,2) NOT NULL CHECK (depth_m > 0 AND depth_m <= 5),
    system_type VARCHAR(50) NOT NULL CHECK (system_type IN ('tradicional', 'bioflocos', 'raceway')),
    status      VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'maintenance', 'drained')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (farm_id, name)
);

COMMENT ON TABLE ponds IS 'Viveiros de cultivo de camarão. Cada viveiro pertence a uma fazenda e pode operar em diferentes sistemas de produção.';

-- ----------------------------------------------------------------------------
-- Dispositivos IoT
-- ----------------------------------------------------------------------------
CREATE TABLE devices (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pond_id           UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    device_type       VARCHAR(50) NOT NULL CHECK (device_type IN ('multiparameter_sensor', 'ph_sensor', 'do_sensor', 'temperature_sensor', 'turbidity_sensor', 'weather_station', 'camera', 'actuator_controller')),
    firmware_version  VARCHAR(20),
    mac_address       VARCHAR(17) NOT NULL UNIQUE CHECK (mac_address ~ '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$'),
    last_seen         TIMESTAMPTZ,
    status            VARCHAR(20) NOT NULL DEFAULT 'online' CHECK (status IN ('online', 'offline', 'maintenance', 'decommissioned')),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE devices IS 'Dispositivos IoT instalados nos viveiros — sensores de qualidade da água, estações meteorológicas, câmeras e controladores de atuadores.';

-- ----------------------------------------------------------------------------
-- Leituras de Sensores (Hypertable TimescaleDB)
-- ----------------------------------------------------------------------------
CREATE TABLE sensor_readings (
    id                      BIGSERIAL,
    timestamp               TIMESTAMPTZ NOT NULL,
    pond_id                 UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    device_id               UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    temperature             DECIMAL(5,2)  CHECK (temperature BETWEEN -5 AND 50),
    ph                      DECIMAL(4,2)  CHECK (ph BETWEEN 0 AND 14),
    salinity                DECIMAL(6,2)  CHECK (salinity BETWEEN 0 AND 100),
    dissolved_oxygen        DECIMAL(5,2)  CHECK (dissolved_oxygen BETWEEN 0 AND 30),
    turbidity               DECIMAL(7,2)  CHECK (turbidity >= 0),
    tds                     DECIMAL(8,2)  CHECK (tds >= 0),
    electrical_conductivity DECIMAL(8,2)  CHECK (electrical_conductivity >= 0),

    PRIMARY KEY (timestamp, id)
);

COMMENT ON TABLE sensor_readings IS 'Leituras dos sensores de qualidade da água em tempo real. Tabela particionada por tempo (hypertable TimescaleDB) para alto volume de ingestão e consultas temporais eficientes.';

-- Converter para hypertable TimescaleDB, particionando por timestamp a cada 7 dias
SELECT create_hypertable('sensor_readings', 'timestamp',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ----------------------------------------------------------------------------
-- Ciclos de Cultivo
-- ----------------------------------------------------------------------------
CREATE TABLE cycles (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pond_id           UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    start_date        DATE NOT NULL,
    end_date          DATE CHECK (end_date IS NULL OR end_date >= start_date),
    species           VARCHAR(100) NOT NULL DEFAULT 'Litopenaeus vannamei',
    strain            VARCHAR(100),
    stocking_density  DECIMAL(10,2) NOT NULL CHECK (stocking_density > 0),
    initial_biomass   DECIMAL(10,2) CHECK (initial_biomass >= 0),
    system_type       VARCHAR(50) NOT NULL CHECK (system_type IN ('tradicional', 'bioflocos', 'raceway')),
    status            VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'completed', 'aborted')),
    notes             TEXT
);

COMMENT ON TABLE cycles IS 'Ciclos de cultivo de camarão. Cada ciclo representa um período completo de povoamento até a despesca em um viveiro específico.';

-- ----------------------------------------------------------------------------
-- Eventos de Manejo
-- ----------------------------------------------------------------------------
CREATE TABLE management_events (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pond_id     UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    cycle_id    UUID REFERENCES cycles(id) ON DELETE SET NULL,
    event_type  VARCHAR(50) NOT NULL CHECK (event_type IN (
        'feeding', 'water_exchange', 'probiotic', 'aerator_on', 'aerator_off',
        'pump_on', 'pump_off', 'liming', 'fertilization'
    )),
    details     JSONB,
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL
);

COMMENT ON TABLE management_events IS 'Registro de eventos de manejo nos viveiros — alimentação, troca de água, aplicação de probióticos, acionamento de aeradores e bombas, calagem e fertilização.';

-- ----------------------------------------------------------------------------
-- Biometrias
-- ----------------------------------------------------------------------------
CREATE TABLE biometrics (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id          UUID NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    timestamp         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    avg_weight_g      DECIMAL(8,3) NOT NULL CHECK (avg_weight_g > 0),
    sample_size       INT NOT NULL CHECK (sample_size > 0),
    survival_estimate DECIMAL(5,2) CHECK (survival_estimate BETWEEN 0 AND 100),
    length_cm         DECIMAL(5,2) CHECK (length_cm > 0),
    notes             TEXT
);

COMMENT ON TABLE biometrics IS 'Dados de biometria dos camarões — peso médio, tamanho e estimativa de sobrevivência ao longo do ciclo de cultivo.';

-- ----------------------------------------------------------------------------
-- Despescas (Harvests)
-- ----------------------------------------------------------------------------
CREATE TABLE harvests (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_id            UUID NOT NULL REFERENCES cycles(id) ON DELETE CASCADE,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    harvest_weight_kg   DECIMAL(10,2) NOT NULL CHECK (harvest_weight_kg > 0),
    survival_rate       DECIMAL(5,2) CHECK (survival_rate BETWEEN 0 AND 100),
    avg_final_weight_g  DECIMAL(8,3) CHECK (avg_final_weight_g > 0),
    price_per_kg        DECIMAL(8,2) CHECK (price_per_kg >= 0),
    destination         VARCHAR(200),
    total_revenue       DECIMAL(12,2) CHECK (total_revenue >= 0),
    notes               TEXT
);

COMMENT ON TABLE harvests IS 'Registro de despescas — peso total colhido, sobrevivência, peso médio final, preço, destino e receita total do ciclo.';

-- ----------------------------------------------------------------------------
-- Alertas
-- ----------------------------------------------------------------------------
CREATE TABLE alerts (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pond_id     UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    alert_type  VARCHAR(50) NOT NULL,
    severity    VARCHAR(20) NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    parameter   VARCHAR(50),
    value       DECIMAL,
    threshold   DECIMAL,
    message     TEXT NOT NULL,
    handled     BOOLEAN NOT NULL DEFAULT FALSE,
    handled_at  TIMESTAMPTZ,
    handled_by  UUID REFERENCES users(id) ON DELETE SET NULL,

    CONSTRAINT chk_handled_consistency CHECK (
        (handled = FALSE AND handled_at IS NULL AND handled_by IS NULL) OR
        (handled = TRUE AND handled_at IS NOT NULL)
    )
);

COMMENT ON TABLE alerts IS 'Alertas gerados pelo sistema de monitoramento — parâmetros fora da faixa ideal, falhas de equipamentos e condições críticas nos viveiros.';

-- ----------------------------------------------------------------------------
-- Predições (Modelo IA)
-- ----------------------------------------------------------------------------
CREATE TABLE predictions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pond_id         UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    cycle_id        UUID REFERENCES cycles(id) ON DELETE SET NULL,
    target          VARCHAR(50) NOT NULL CHECK (target IN ('ph_next_day', 'do_next_day', 'production_level')),
    predicted_value DECIMAL NOT NULL,
    confidence      DECIMAL(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    model_version   VARCHAR(50) NOT NULL,
    features_used   JSONB
);

COMMENT ON TABLE predictions IS 'Predições geradas pelos modelos de inteligência artificial — previsão de pH, oxigênio dissolvido e nível de produção com base nos dados históricos.';

-- ----------------------------------------------------------------------------
-- Comandos de Atuadores
-- ----------------------------------------------------------------------------
CREATE TABLE actuator_commands (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    pond_id         UUID NOT NULL REFERENCES ponds(id) ON DELETE CASCADE,
    actuator_type   VARCHAR(50) NOT NULL CHECK (actuator_type IN ('aerator', 'pump', 'feeder')),
    command         VARCHAR(20) NOT NULL CHECK (command IN ('on', 'off', 'pulse')),
    source          VARCHAR(20) NOT NULL CHECK (source IN ('auto', 'manual', 'prediction')),
    acknowledged    BOOLEAN NOT NULL DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,

    CONSTRAINT chk_ack_consistency CHECK (
        (acknowledged = FALSE AND acknowledged_at IS NULL) OR
        (acknowledged = TRUE AND acknowledged_at IS NOT NULL)
    )
);

COMMENT ON TABLE actuator_commands IS 'Comandos enviados aos atuadores (aeradores, bombas, alimentadores) — podem ser manuais, automáticos ou baseados em predições da IA.';

-- ----------------------------------------------------------------------------
-- Regras de Alerta
-- ----------------------------------------------------------------------------
CREATE TABLE alert_rules (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    farm_id             UUID NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
    parameter           VARCHAR(50) NOT NULL,
    min_value           DECIMAL,
    max_value           DECIMAL,
    critical_min        DECIMAL,
    critical_max        DECIMAL,
    hysteresis_minutes  INT NOT NULL DEFAULT 5 CHECK (hysteresis_minutes >= 0),
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT chk_min_max CHECK (min_value IS NULL OR max_value IS NULL OR min_value < max_value),
    CONSTRAINT chk_critical_range CHECK (critical_min IS NULL OR critical_max IS NULL OR critical_min < critical_max),
    CONSTRAINT chk_critical_wider CHECK (
        (critical_min IS NULL OR min_value IS NULL OR critical_min <= min_value) AND
        (critical_max IS NULL OR max_value IS NULL OR critical_max >= max_value)
    ),

    UNIQUE (farm_id, parameter)
);

COMMENT ON TABLE alert_rules IS 'Regras configuráveis de alerta por fazenda — faixas mínimas e máximas (aviso e crítico) para cada parâmetro de qualidade da água.';

-- ============================================================================
-- 3. ÍNDICES
-- ============================================================================

-- sensor_readings: índice composto para consultas por viveiro e período
CREATE INDEX idx_sensor_readings_pond_time
    ON sensor_readings (pond_id, timestamp DESC);

-- management_events: índice para consultas por viveiro e período
CREATE INDEX idx_management_events_pond_time
    ON management_events (pond_id, timestamp);

-- management_events: índice para consultas por ciclo
CREATE INDEX idx_management_events_cycle
    ON management_events (cycle_id);

-- alerts: índice para alertas pendentes por viveiro
CREATE INDEX idx_alerts_pond_handled_time
    ON alerts (pond_id, handled, timestamp);

-- predictions: índice para predições por viveiro e período
CREATE INDEX idx_predictions_pond_time
    ON predictions (pond_id, timestamp);

-- actuator_commands: índice para comandos por viveiro e período
CREATE INDEX idx_actuator_commands_pond_time
    ON actuator_commands (pond_id, timestamp);

-- Índices adicionais para chaves estrangeiras frequentemente consultadas
CREATE INDEX idx_ponds_farm ON ponds (farm_id);
CREATE INDEX idx_devices_pond ON devices (pond_id);
CREATE INDEX idx_cycles_pond ON cycles (pond_id);
CREATE INDEX idx_biometrics_cycle ON biometrics (cycle_id);
CREATE INDEX idx_harvests_cycle ON harvests (cycle_id);

-- ============================================================================
-- 4. VIEWS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- v_pond_latest_readings: última leitura de cada viveiro
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_pond_latest_readings AS
SELECT DISTINCT ON (sr.pond_id)
    sr.pond_id,
    p.name                  AS pond_name,
    f.name                  AS farm_name,
    sr.timestamp,
    sr.device_id,
    sr.temperature,
    sr.ph,
    sr.salinity,
    sr.dissolved_oxygen,
    sr.turbidity,
    sr.tds,
    sr.electrical_conductivity,
    EXTRACT(EPOCH FROM (NOW() - sr.timestamp)) / 60 AS minutes_since_reading
FROM sensor_readings sr
JOIN ponds p ON p.id = sr.pond_id
JOIN farms f ON f.id = p.farm_id
ORDER BY sr.pond_id, sr.timestamp DESC;

COMMENT ON VIEW v_pond_latest_readings IS 'Última leitura dos sensores de cada viveiro — visão rápida do estado atual de todos os viveiros.';

-- ----------------------------------------------------------------------------
-- v_active_alerts: alertas pendentes ordenados por severidade
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_active_alerts AS
SELECT
    a.id,
    a.timestamp,
    a.pond_id,
    p.name          AS pond_name,
    f.name          AS farm_name,
    a.alert_type,
    a.severity,
    a.parameter,
    a.value,
    a.threshold,
    a.message,
    EXTRACT(EPOCH FROM (NOW() - a.timestamp)) / 60 AS minutes_open
FROM alerts a
JOIN ponds p ON p.id = a.pond_id
JOIN farms f ON f.id = p.farm_id
WHERE a.handled = FALSE
ORDER BY
    CASE a.severity
        WHEN 'critical' THEN 1
        WHEN 'warning'  THEN 2
        WHEN 'info'     THEN 3
    END,
    a.timestamp DESC;

COMMENT ON VIEW v_active_alerts IS 'Alertas ativos (não tratados) ordenados por severidade — painel de atenção imediata para operadores.';

-- ----------------------------------------------------------------------------
-- v_cycle_summary: resumo de cada ciclo com métricas de produção
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_cycle_summary AS
SELECT
    c.id                    AS cycle_id,
    c.pond_id,
    p.name                  AS pond_name,
    f.name                  AS farm_name,
    p.area_m2,
    c.species,
    c.strain,
    c.start_date,
    c.end_date,
    c.status,
    c.stocking_density,
    c.initial_biomass,
    c.system_type,
    -- Duração em dias
    COALESCE(c.end_date, CURRENT_DATE) - c.start_date AS duration_days,
    -- Dados de despesca
    h.harvest_weight_kg,
    h.survival_rate,
    h.avg_final_weight_g,
    h.price_per_kg,
    h.total_revenue,
    -- Produtividade (kg/ha)
    CASE WHEN p.area_m2 > 0 AND h.harvest_weight_kg IS NOT NULL
        THEN ROUND((h.harvest_weight_kg / (p.area_m2 / 10000))::NUMERIC, 2)
        ELSE NULL
    END AS productivity_kg_per_ha,
    -- Total de ração fornecida (soma do campo details->>'quantity_kg' dos eventos de alimentação)
    COALESCE(feed.total_feed_kg, 0) AS total_feed_kg,
    -- FCR (Feed Conversion Ratio)
    CASE WHEN h.harvest_weight_kg > 0 AND feed.total_feed_kg > 0
        THEN ROUND((feed.total_feed_kg / h.harvest_weight_kg)::NUMERIC, 2)
        ELSE NULL
    END AS fcr,
    -- Última biometria
    lb.latest_avg_weight_g,
    lb.latest_sample_date
FROM cycles c
JOIN ponds p ON p.id = c.pond_id
JOIN farms f ON f.id = p.farm_id
LEFT JOIN LATERAL (
    SELECT
        SUM(hv.harvest_weight_kg) AS harvest_weight_kg,
        AVG(hv.survival_rate)     AS survival_rate,
        AVG(hv.avg_final_weight_g) AS avg_final_weight_g,
        AVG(hv.price_per_kg)      AS price_per_kg,
        SUM(hv.total_revenue)     AS total_revenue
    FROM harvests hv
    WHERE hv.cycle_id = c.id
) h ON TRUE
LEFT JOIN LATERAL (
    SELECT
        SUM((me.details->>'quantity_kg')::DECIMAL) AS total_feed_kg
    FROM management_events me
    WHERE me.cycle_id = c.id
      AND me.event_type = 'feeding'
      AND me.details ? 'quantity_kg'
) feed ON TRUE
LEFT JOIN LATERAL (
    SELECT
        b.avg_weight_g AS latest_avg_weight_g,
        b.timestamp    AS latest_sample_date
    FROM biometrics b
    WHERE b.cycle_id = c.id
    ORDER BY b.timestamp DESC
    LIMIT 1
) lb ON TRUE;

COMMENT ON VIEW v_cycle_summary IS 'Resumo completo dos ciclos de cultivo — produtividade (kg/ha), taxa de conversão alimentar (FCR), duração, dados de despesca e última biometria.';

-- ----------------------------------------------------------------------------
-- v_daily_averages: médias diárias de cada parâmetro por viveiro
-- ----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_daily_averages AS
SELECT
    time_bucket('1 day', sr.timestamp) AS day,
    sr.pond_id,
    p.name AS pond_name,
    COUNT(*)                                AS reading_count,
    ROUND(AVG(sr.temperature)::NUMERIC, 2)             AS avg_temperature,
    ROUND(MIN(sr.temperature)::NUMERIC, 2)             AS min_temperature,
    ROUND(MAX(sr.temperature)::NUMERIC, 2)             AS max_temperature,
    ROUND(AVG(sr.ph)::NUMERIC, 2)                      AS avg_ph,
    ROUND(MIN(sr.ph)::NUMERIC, 2)                      AS min_ph,
    ROUND(MAX(sr.ph)::NUMERIC, 2)                      AS max_ph,
    ROUND(AVG(sr.salinity)::NUMERIC, 2)                AS avg_salinity,
    ROUND(AVG(sr.dissolved_oxygen)::NUMERIC, 2)        AS avg_dissolved_oxygen,
    ROUND(MIN(sr.dissolved_oxygen)::NUMERIC, 2)        AS min_dissolved_oxygen,
    ROUND(MAX(sr.dissolved_oxygen)::NUMERIC, 2)        AS max_dissolved_oxygen,
    ROUND(AVG(sr.turbidity)::NUMERIC, 2)               AS avg_turbidity,
    ROUND(AVG(sr.tds)::NUMERIC, 2)                     AS avg_tds,
    ROUND(AVG(sr.electrical_conductivity)::NUMERIC, 2) AS avg_electrical_conductivity
FROM sensor_readings sr
JOIN ponds p ON p.id = sr.pond_id
GROUP BY time_bucket('1 day', sr.timestamp), sr.pond_id, p.name
ORDER BY day DESC, sr.pond_id;

COMMENT ON VIEW v_daily_averages IS 'Médias diárias dos parâmetros de qualidade da água por viveiro — útil para análise de tendências e relatórios de acompanhamento.';

-- ============================================================================
-- 5. DADOS DE EXEMPLO
-- ============================================================================

-- Usuário administrador
INSERT INTO users (id, email, name, role) VALUES
    ('a1b2c3d4-e5f6-7890-abcd-ef1234567890', 'carlos.silva@fazendamarinhos.com.br', 'Carlos Silva', 'admin');

-- Fazenda
INSERT INTO farms (id, name, location, area_ha, owner_id) VALUES
    ('f0a1b2c3-d4e5-6789-0abc-def123456789',
     'Fazenda Marinhos do Nordeste',
     'Aracati, Ceará, Brasil',
     25.00,
     'a1b2c3d4-e5f6-7890-abcd-ef1234567890');

-- Vincular usuário à fazenda
UPDATE users
SET farm_id = 'f0a1b2c3-d4e5-6789-0abc-def123456789'
WHERE id = 'a1b2c3d4-e5f6-7890-abcd-ef1234567890';

-- Operador
INSERT INTO users (id, email, name, role, farm_id) VALUES
    ('b2c3d4e5-f6a7-8901-bcde-f12345678901', 'ana.oliveira@fazendamarinhos.com.br', 'Ana Oliveira', 'operator', 'f0a1b2c3-d4e5-6789-0abc-def123456789');

-- Viveiros
INSERT INTO ponds (id, farm_id, name, area_m2, depth_m, system_type, status) VALUES
    ('11111111-1111-1111-1111-111111111111',
     'f0a1b2c3-d4e5-6789-0abc-def123456789',
     'Viveiro A1', 5000.00, 1.20, 'bioflocos', 'active'),
    ('22222222-2222-2222-2222-222222222222',
     'f0a1b2c3-d4e5-6789-0abc-def123456789',
     'Viveiro B1', 8000.00, 1.50, 'tradicional', 'active');

-- Dispositivos
INSERT INTO devices (id, pond_id, device_type, firmware_version, mac_address, last_seen, status) VALUES
    ('d1111111-1111-1111-1111-111111111111',
     '11111111-1111-1111-1111-111111111111',
     'multiparameter_sensor', 'v2.4.1', 'AA:BB:CC:DD:EE:01', NOW() - INTERVAL '2 minutes', 'online'),
    ('d2222222-2222-2222-2222-222222222222',
     '22222222-2222-2222-2222-222222222222',
     'multiparameter_sensor', 'v2.4.1', 'AA:BB:CC:DD:EE:02', NOW() - INTERVAL '5 minutes', 'online'),
    ('d3333333-3333-3333-3333-333333333333',
     '11111111-1111-1111-1111-111111111111',
     'actuator_controller', 'v1.8.0', 'AA:BB:CC:DD:EE:03', NOW() - INTERVAL '1 minute', 'online');

-- Ciclos de cultivo
INSERT INTO cycles (id, pond_id, start_date, end_date, species, strain, stocking_density, initial_biomass, system_type, status, notes) VALUES
    ('c1111111-1111-1111-1111-111111111111',
     '11111111-1111-1111-1111-111111111111',
     '2026-01-15', NULL, 'Litopenaeus vannamei', 'Speedline - Alta Genetics',
     120.00, 3.60, 'bioflocos', 'active',
     'Ciclo 1/2026 - Viveiro A1 - PL12 da Aquatec'),
    ('c2222222-2222-2222-2222-222222222222',
     '22222222-2222-2222-2222-222222222222',
     '2025-10-01', '2025-12-20', 'Litopenaeus vannamei', 'Vannamei SPF',
     80.00, 2.40, 'tradicional', 'completed',
     'Ciclo 2/2025 - Viveiro B1 - Bom desempenho');

-- Leituras de sensores (últimas horas do Viveiro A1)
INSERT INTO sensor_readings (timestamp, pond_id, device_id, temperature, ph, salinity, dissolved_oxygen, turbidity, tds, electrical_conductivity) VALUES
    (NOW() - INTERVAL '4 hours',  '11111111-1111-1111-1111-111111111111', 'd1111111-1111-1111-1111-111111111111', 28.50, 7.80, 25.30, 5.20, 42.10, 1850.00, 38500.00),
    (NOW() - INTERVAL '3 hours',  '11111111-1111-1111-1111-111111111111', 'd1111111-1111-1111-1111-111111111111', 28.80, 7.75, 25.28, 5.10, 43.50, 1855.00, 38520.00),
    (NOW() - INTERVAL '2 hours',  '11111111-1111-1111-1111-111111111111', 'd1111111-1111-1111-1111-111111111111', 29.10, 7.70, 25.25, 4.90, 44.80, 1860.00, 38550.00),
    (NOW() - INTERVAL '1 hour',   '11111111-1111-1111-1111-111111111111', 'd1111111-1111-1111-1111-111111111111', 29.40, 7.65, 25.22, 4.70, 46.20, 1870.00, 38600.00),
    (NOW() - INTERVAL '30 minutes','11111111-1111-1111-1111-111111111111', 'd1111111-1111-1111-1111-111111111111', 29.60, 7.60, 25.20, 4.50, 47.00, 1875.00, 38620.00);

-- Leituras de sensores (últimas horas do Viveiro B1)
INSERT INTO sensor_readings (timestamp, pond_id, device_id, temperature, ph, salinity, dissolved_oxygen, turbidity, tds, electrical_conductivity) VALUES
    (NOW() - INTERVAL '4 hours',  '22222222-2222-2222-2222-222222222222', 'd2222222-2222-2222-2222-222222222222', 27.80, 8.10, 30.50, 6.80, 28.00, 2200.00, 45800.00),
    (NOW() - INTERVAL '3 hours',  '22222222-2222-2222-2222-222222222222', 'd2222222-2222-2222-2222-222222222222', 28.00, 8.05, 30.48, 6.60, 28.50, 2205.00, 45820.00),
    (NOW() - INTERVAL '2 hours',  '22222222-2222-2222-2222-222222222222', 'd2222222-2222-2222-2222-222222222222', 28.30, 8.00, 30.45, 6.40, 29.00, 2210.00, 45850.00),
    (NOW() - INTERVAL '1 hour',   '22222222-2222-2222-2222-222222222222', 'd2222222-2222-2222-2222-222222222222', 28.50, 7.95, 30.42, 6.20, 29.50, 2215.00, 45880.00),
    (NOW() - INTERVAL '30 minutes','22222222-2222-2222-2222-222222222222', 'd2222222-2222-2222-2222-222222222222', 28.70, 7.90, 30.40, 6.00, 30.00, 2220.00, 45900.00);

-- Eventos de manejo
INSERT INTO management_events (timestamp, pond_id, cycle_id, event_type, details, user_id) VALUES
    (NOW() - INTERVAL '6 hours', '11111111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111', 'feeding',
     '{"quantity_kg": 45.0, "feed_type": "ração 35% PB", "method": "automático", "frequency": "4x/dia"}',
     'b2c3d4e5-f6a7-8901-bcde-f12345678901'),
    (NOW() - INTERVAL '5 hours', '11111111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111', 'probiotic',
     '{"product": "Sanolife PRO-W", "dosage_ml": 500, "dilution": "1:10"}',
     'b2c3d4e5-f6a7-8901-bcde-f12345678901'),
    (NOW() - INTERVAL '3 hours', '22222222-2222-2222-2222-222222222222', NULL, 'water_exchange',
     '{"volume_percent": 15, "source": "canal de abastecimento", "reason": "manutenção de qualidade"}',
     'b2c3d4e5-f6a7-8901-bcde-f12345678901'),
    (NOW() - INTERVAL '1 hour', '11111111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111', 'aerator_on',
     '{"aerator_id": "AER-A1-01", "power_hp": 2, "reason": "OD baixo"}',
     'b2c3d4e5-f6a7-8901-bcde-f12345678901');

-- Biometrias do ciclo ativo
INSERT INTO biometrics (cycle_id, timestamp, avg_weight_g, sample_size, survival_estimate, length_cm, notes) VALUES
    ('c1111111-1111-1111-1111-111111111111', '2026-02-01 08:00:00-03', 2.500, 50, 95.00, 4.20, 'Biometria semana 2 - crescimento normal'),
    ('c1111111-1111-1111-1111-111111111111', '2026-02-15 08:00:00-03', 5.800, 50, 92.00, 6.10, 'Biometria semana 4 - bom ganho de peso'),
    ('c1111111-1111-1111-1111-111111111111', '2026-03-01 08:00:00-03', 10.200, 50, 90.00, 8.50, 'Biometria semana 6 - desenvolvimento uniforme'),
    ('c1111111-1111-1111-1111-111111111111', '2026-03-15 08:00:00-03', 14.500, 50, 88.50, 10.20, 'Biometria semana 8 - excelente conversão');

-- Despesca do ciclo concluído
INSERT INTO harvests (cycle_id, timestamp, harvest_weight_kg, survival_rate, avg_final_weight_g, price_per_kg, destination, total_revenue, notes) VALUES
    ('c2222222-2222-2222-2222-222222222222', '2025-12-20 06:00:00-03',
     4800.00, 82.50, 18.200, 32.00, 'Frigorífico Mar & Sol - Fortaleza/CE',
     153600.00, 'Despesca total - boa qualidade, tamanho comercial G1');

-- Regras de alerta
INSERT INTO alert_rules (farm_id, parameter, min_value, max_value, critical_min, critical_max, hysteresis_minutes, enabled) VALUES
    ('f0a1b2c3-d4e5-6789-0abc-def123456789', 'temperature',       26.00, 32.00, 24.00, 34.00, 5,  TRUE),
    ('f0a1b2c3-d4e5-6789-0abc-def123456789', 'ph',                7.00,  8.50,  6.50,  9.00,  10, TRUE),
    ('f0a1b2c3-d4e5-6789-0abc-def123456789', 'dissolved_oxygen',  4.00,  NULL,  3.00,  NULL,  5,  TRUE),
    ('f0a1b2c3-d4e5-6789-0abc-def123456789', 'salinity',          15.00, 35.00, 10.00, 40.00, 15, TRUE),
    ('f0a1b2c3-d4e5-6789-0abc-def123456789', 'turbidity',         NULL,  80.00, NULL,  120.00,10, TRUE);

-- Alertas de exemplo
INSERT INTO alerts (timestamp, pond_id, alert_type, severity, parameter, value, threshold, message, handled, handled_at, handled_by) VALUES
    (NOW() - INTERVAL '45 minutes', '11111111-1111-1111-1111-111111111111',
     'parameter_low', 'warning', 'dissolved_oxygen', 4.50, 4.00,
     'Oxigênio dissolvido no Viveiro A1 em tendência de queda (4.50 mg/L). Atenção requerida.',
     FALSE, NULL, NULL),
    (NOW() - INTERVAL '20 minutes', '11111111-1111-1111-1111-111111111111',
     'parameter_low', 'critical', 'dissolved_oxygen', 4.50, 3.00,
     'Oxigênio dissolvido no Viveiro A1 próximo do nível crítico! Aerador acionado automaticamente.',
     TRUE, NOW() - INTERVAL '18 minutes', 'b2c3d4e5-f6a7-8901-bcde-f12345678901');

-- Predições do modelo
INSERT INTO predictions (timestamp, pond_id, cycle_id, target, predicted_value, confidence, model_version, features_used) VALUES
    (NOW() - INTERVAL '1 hour', '11111111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111',
     'do_next_day', 4.20, 0.8750, 'lstm-do-v3.2',
     '{"inputs": ["temperature", "ph", "salinity", "turbidity", "hour_of_day", "feed_amount_24h"], "lookback_hours": 48}'),
    (NOW() - INTERVAL '1 hour', '11111111-1111-1111-1111-111111111111', 'c1111111-1111-1111-1111-111111111111',
     'ph_next_day', 7.55, 0.9100, 'lstm-ph-v3.2',
     '{"inputs": ["temperature", "ph", "salinity", "dissolved_oxygen", "hour_of_day"], "lookback_hours": 48}'),
    (NOW() - INTERVAL '1 hour', '22222222-2222-2222-2222-222222222222', NULL,
     'production_level', 0.75, 0.8200, 'rf-prod-v2.1',
     '{"inputs": ["avg_temperature_7d", "avg_do_7d", "avg_ph_7d", "stocking_density", "days_of_culture"], "model_type": "random_forest"}');

-- Comandos de atuadores
INSERT INTO actuator_commands (timestamp, pond_id, actuator_type, command, source, acknowledged, acknowledged_at) VALUES
    (NOW() - INTERVAL '1 hour', '11111111-1111-1111-1111-111111111111',
     'aerator', 'on', 'auto', TRUE, NOW() - INTERVAL '59 minutes'),
    (NOW() - INTERVAL '30 minutes', '11111111-1111-1111-1111-111111111111',
     'feeder', 'pulse', 'prediction', TRUE, NOW() - INTERVAL '29 minutes'),
    (NOW() - INTERVAL '10 minutes', '22222222-2222-2222-2222-222222222222',
     'pump', 'on', 'manual', FALSE, NULL);

-- ============================================================================
-- FIM DO SCHEMA
-- ============================================================================
