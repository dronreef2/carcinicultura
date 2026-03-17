# 🦐 Smart Shrimp Farm — Sistema IoT + IA para Carcinicultura

Sistema de automação para criação de camarão com monitoramento em tempo real, controle automático de aeradores e modelos preditivos de IA.

## 📋 Visão Geral

| Componente | Tecnologia | Status |
|-----------|-----------|--------|
| **Firmware** | ESP32 + Arduino (C++) | 🟡 Módulo 1 |
| **Backend** | Python/FastAPI + MQTT | 🟡 Módulo 1 |
| **Banco de Dados** | PostgreSQL + TimescaleDB | 🟡 Módulo 1 |
| **Dashboard** | HTML/JS + Chart.js | 🟡 Módulo 1 |
| **ML/IA** | Python (scikit-learn, XGBoost) | ⚪ Módulo 4 |

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────┐
│           CAMADA DE APLICAÇÃO                    │
│  Dashboard SPA (React/Next.js) · PWA Mobile     │
│  Notificações: WhatsApp · Telegram · SMS        │
├─────────────────────────────────────────────────┤
│           CAMADA DE NUVEM / BACKEND              │
│  Broker MQTT · FastAPI · PostgreSQL/TimescaleDB  │
│  Serviço de Regras · Analytics/ML                │
├─────────────────────────────────────────────────┤
│           CAMADA DE COMUNICAÇÃO                  │
│  MQTT + TLS · HTTP REST · Wi-Fi / 4G LTE        │
├─────────────────────────────────────────────────┤
│           CAMADA DE CAMPO (EDGE)                 │
│  ESP32 · Sensores (Temp, pH, OD, Sal, Turb)     │
│  Atuadores: Aeradores · Bombas · Alimentadores   │
└─────────────────────────────────────────────────┘
```

## 📂 Estrutura do Repositório

```
├── firmware/               # Código do ESP32
│   └── esp32-sensor/       # Módulo 1: sensor de temperatura
│       ├── main.ino
│       └── config.example.h
├── backend/                # Backend FastAPI + MQTT
│   ├── app/
│   │   ├── main.py         # API + subscriber MQTT
│   │   ├── models.py       # Modelos Pydantic
│   │   └── database.py     # Conexão TimescaleDB
│   ├── mosquitto/          # Config do broker MQTT
│   ├── docker-compose.yml
│   ├── Dockerfile
│   └── requirements.txt
├── dashboard/              # Dashboard web
│   └── index.html          # SPA com Chart.js
├── docs/                   # Documentação
│   └── smart-shrimp-farm-docs.docx
├── schema.sql              # Esquema completo do banco
└── README.md
```

## 🚀 Quick Start (Módulo 1)

### Pré-requisitos
- Docker + Docker Compose
- Arduino IDE (para o firmware)
- ESP32 + Sensor DS18B20

### 1. Subir o backend
```bash
cd backend
docker compose up -d
```

### 2. Testar sem hardware (simulação)
```bash
# Publicar dado de teste no MQTT
docker exec mosquitto mosquitto_pub \
  -t "farm/F01/pond/P01/telemetry" \
  -u "shrimp" -P "shrimp123" \
  -m '{"timestamp":1710000000,"pond_id":"P01","temperature":28.5,"device_id":"esp32-sim"}'
```

### 3. Acessar o dashboard
Abra `dashboard/index.html` no navegador.

### 4. Carregar firmware no ESP32
1. Copie `config.example.h` para `config.h`
2. Preencha credenciais WiFi e MQTT
3. Faça upload via Arduino IDE

Veja instruções detalhadas em [README-MODULO1.md](./README-MODULO1.md).

## 📊 Módulos de Desenvolvimento

| Módulo | Descrição | Prioridade |
|--------|-----------|-----------|
| **1** | Protótipo mínimo: 1 sensor + nuvem + dashboard | P1 🔴 |
| **2** | Mais sensores (pH, OD, sal) + aeradores automáticos | P2 🟠 |
| **3** | Coleta estruturada de produção e manejo | P2 🟠 |
| **4** | Primeiros modelos de IA (regressão + classificação) | P2 🟠 |
| **5** | Recomendações avançadas + digital twin | P3 🔵 |

Veja as [issues](https://github.com/dronreef2/carcinicultura/issues) para o backlog detalhado.

## 🐛 Parâmetros Monitorados

| Parâmetro | Faixa Ideal (L. vannamei) | Crítico |
|-----------|--------------------------|---------|
| Temperatura | 26–32 °C | < 24 ou > 34 |
| pH | 7.0–8.5 | < 6.5 ou > 9.5 |
| OD | > 4 mg/L | < 3 mg/L |
| Salinidade | 15–35 ppt | < 5 ou > 45 |
| Turbidez | 30–80 NTU | > 200 |

## 📄 Documentação

- [Documentação Técnica Completa](./docs/smart-shrimp-farm-docs.docx) — PRD com arquitetura, modelo de dados, backlog e especificações
- [Esquema SQL](./schema.sql) — Banco de dados PostgreSQL + TimescaleDB
- [README Módulo 1](./README-MODULO1.md) — Guia detalhado do protótipo

## 📝 Licença

MIT
