# IoT Camarão — Módulo 1: Sensor de Temperatura

Sistema mínimo de monitoramento de temperatura da água para viveiros de camarão.
ESP32 lê sensor DS18B20 → envia via MQTT → backend armazena no TimescaleDB → dashboard em tempo real.

---

## Arquitetura

```
┌─────────────────────┐         ┌──────────────────────────────────────────────┐
│   VIVEIRO           │         │              SERVIDOR (Docker)               │
│                     │         │                                              │
│  ┌───────────┐      │  MQTT   │  ┌───────────┐    ┌──────────────┐          │
│  │  DS18B20  │──┐   │ ──────► │  │ Mosquitto │───►│ FastAPI      │          │
│  │ (sensor)  │  │   │ :1883   │  │  (broker) │    │ (backend)    │          │
│  └───────────┘  │   │         │  └───────────┘    └──────┬───────┘          │
│                 │   │         │                          │                   │
│  ┌───────────┐  │   │         │                   ┌──────▼───────┐          │
│  │   ESP32   │──┘   │         │                   │ TimescaleDB  │          │
│  │ (MCU)     │      │         │                   │ (PostgreSQL) │          │
│  └───────────┘      │         │                   └──────────────┘          │
│                     │         │                          │                   │
└─────────────────────┘         │                   ┌──────▼───────┐          │
                                │                   │  WebSocket   │          │
                                │                   └──────┬───────┘          │
                                └──────────────────────────┼──────────────────┘
                                                           │
                                                    ┌──────▼───────┐
                                                    │  Dashboard   │
                                                    │  (browser)   │
                                                    └──────────────┘
```

## Fluxo de dados

1. **ESP32** lê temperatura do DS18B20 a cada 60 segundos
2. Publica JSON via **MQTT** no tópico `farm/{id}/pond/{id}/telemetry`
3. **Backend FastAPI** recebe a mensagem, valida e insere no **TimescaleDB**
4. Backend notifica **WebSocket** conectados
5. **Dashboard** atualiza gráfico e métricas em tempo real

---

## Hardware Necessário

| Componente | Quantidade | Observação |
|---|---|---|
| ESP32 DevKit V1 | 1 | Qualquer variante com WiFi |
| DS18B20 à prova d'água | 1 | Versão com cabo (para imersão) |
| Resistor 4.7kΩ | 1 | Pull-up no barramento OneWire |
| Protoboard + jumpers | — | Para protótipo |
| Cabo USB micro/tipo-C | 1 | Para programação e alimentação |

### Diagrama de Ligação

```
        ESP32                     DS18B20
    ┌──────────┐              ┌──────────────┐
    │          │              │              │
    │  3.3V ●──┼──────┬──────┤─● VCC (verm) │
    │          │      │      │              │
    │          │    [4.7kΩ]  │              │
    │          │      │      │              │
    │  GPIO4 ●─┼──────┴──────┤─● DATA (amar)│
    │          │              │              │
    │   GND ●──┼──────────────┤─● GND (preto)│
    │          │              │              │
    └──────────┘              └──────────────┘

    Cores dos fios do DS18B20:
      Vermelho = VCC (3.3V)
      Amarelo  = DATA (sinal)
      Preto    = GND (terra)
```

> **Importante:** O resistor de 4.7kΩ entre VCC e DATA é obrigatório para o protocolo OneWire funcionar corretamente.

---

## Configuração do Firmware (ESP32)

### 1. Instalar Arduino IDE

Baixe em https://www.arduino.cc/en/software

### 2. Adicionar suporte ao ESP32

1. Abra **Arquivo → Preferências**
2. Em "URLs Adicionais para Gerenciador de Placas", adicione:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. Abra **Ferramentas → Placa → Gerenciador de Placas**
4. Pesquise "esp32" e instale **ESP32 by Espressif Systems**

### 3. Instalar bibliotecas

Abra **Ferramentas → Gerenciar Bibliotecas** e instale:

| Biblioteca | Autor | Versão |
|---|---|---|
| OneWire | Jim Studt | 2.3+ |
| DallasTemperature | Miles Burton | 3.9+ |
| PubSubClient | Nick O'Leary | 2.8+ |
| ArduinoJson | Benoît Blanchon | 7.x |

### 4. Configurar credenciais

```bash
cd firmware/esp32-sensor
cp config.example.h config.h
```

Edite `config.h` com os dados da sua rede e servidor:

```c
#define WIFI_SSID     "MinhaRedeWiFi"
#define WIFI_PASSWORD "MinhaSenha123"
#define MQTT_HOST     "192.168.1.100"  // IP do servidor Docker
#define POND_ID       "pond-01"
```

### 5. Upload para o ESP32

1. Conecte o ESP32 via USB
2. Selecione a placa: **Ferramentas → Placa → ESP32 Dev Module**
3. Selecione a porta: **Ferramentas → Porta → /dev/ttyUSB0** (Linux) ou **COMx** (Windows)
4. Clique em **Upload** (seta →)
5. Abra o **Monitor Serial** (115200 baud) para verificar o funcionamento

---

## Configuração do Backend (Docker)

### 1. Pré-requisitos

- Docker e Docker Compose instalados
- Portas livres: 1883 (MQTT), 5432 (PostgreSQL), 8000 (API), 9001 (MQTT WebSocket)

### 2. Gerar senha do Mosquitto

```bash
cd backend

# Gera o arquivo de senhas (substitua 'mqtt_senha_segura' pela sua senha)
docker run --rm -v $(pwd)/mosquitto:/mosquitto/config eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/config/password.txt camarao mqtt_senha_segura
```

### 3. Subir os serviços

```bash
cd backend
docker compose up -d
```

Verifique se todos os containers estão rodando:

```bash
docker compose ps
```

Saída esperada:
```
NAME               STATUS
camarao-mqtt       Up
camarao-db         Up (healthy)
camarao-backend    Up
```

### 4. Verificar logs

```bash
# Todos os serviços
docker compose logs -f

# Apenas o backend
docker compose logs -f backend
```

---

## Testando o Sistema

### Teste 1: Verificar a API

```bash
# Health check
curl http://localhost:8000/api/health

# Listar viveiros
curl http://localhost:8000/api/ponds

# Última leitura
curl http://localhost:8000/api/ponds/pond-01/latest
```

### Teste 2: Simular envio MQTT (sem ESP32)

```bash
# Instale o cliente MQTT
sudo apt install mosquitto-clients  # Linux
# ou: brew install mosquitto        # macOS

# Publique uma leitura de teste
mosquitto_pub \
  -h localhost -p 1883 \
  -u camarao -P mqtt_senha_segura \
  -t "farm/farm-01/pond/pond-01/telemetry" \
  -m '{"timestamp": 1710700000, "pond_id": "pond-01", "device_id": "esp32-test", "temperature": 28.5}'
```

### Teste 3: Abrir o Dashboard

Abra o arquivo `dashboard/index.html` no navegador, ou sirva-o via HTTP:

```bash
cd dashboard
python3 -m http.server 3000
```

Acesse: http://localhost:3000

---

## API — Referência Rápida

| Método | Endpoint | Descrição |
|---|---|---|
| GET | `/api/health` | Verifica status do backend |
| GET | `/api/ponds` | Lista todos os viveiros |
| GET | `/api/ponds/{id}/readings?hours=24` | Leituras históricas (1-168h) |
| GET | `/api/ponds/{id}/latest` | Última leitura + estatísticas 24h |
| WS | `/ws/ponds/{id}` | Stream de leituras em tempo real |

### Exemplo de resposta — `/api/ponds/pond-01/latest`

```json
{
  "pond_id": "pond-01",
  "temperature": 28.5,
  "timestamp": "2026-03-17T14:30:00Z",
  "min_24h": 26.8,
  "max_24h": 30.2,
  "avg_24h": 28.45,
  "total_leituras_24h": 1440
}
```

---

## Resolução de Problemas

### ESP32 não conecta ao WiFi
- Verifique SSID e senha no `config.h`
- Certifique-se de que é uma rede 2.4GHz (ESP32 não suporta 5GHz)
- Aproxime o ESP32 do roteador para teste inicial

### ESP32 não conecta ao MQTT
- Verifique se o container Mosquitto está rodando: `docker compose ps`
- Confirme o IP do servidor no `config.h`
- Teste a conexão: `mosquitto_sub -h <IP> -p 1883 -u camarao -P mqtt_senha_segura -t "#"`
- Verifique se a porta 1883 está aberta no firewall

### Dashboard não mostra dados
- Verifique se o backend está rodando: `curl http://localhost:8000/api/health`
- Confira o console do navegador (F12) para erros de WebSocket
- Verifique se a porta 8000 está acessível

### Sensor DS18B20 retorna -127°C
- Verifique a fiação (VCC, DATA, GND)
- Confirme que o resistor de 4.7kΩ está conectado entre VCC e DATA
- Teste com outro sensor (pode estar defeituoso)
- Verifique se o GPIO correto está configurado no `config.h`

### TimescaleDB não inicia
- Verifique se a porta 5432 não está em uso: `lsof -i :5432`
- Limpe os volumes e recrie: `docker compose down -v && docker compose up -d`

---

## Estrutura do Projeto

```
modulo1/
├── firmware/
│   └── esp32-sensor/
│       ├── main.ino              # Firmware do ESP32
│       ├── config.example.h      # Modelo de configuração
│       └── config.h              # Suas credenciais (não commitar!)
├── backend/
│   ├── docker-compose.yml        # Orquestração dos serviços
│   ├── Dockerfile                # Imagem do backend
│   ├── requirements.txt          # Dependências Python
│   ├── mosquitto/
│   │   ├── mosquitto.conf        # Configuração do broker MQTT
│   │   └── password.txt          # Senhas MQTT (gerar com mosquitto_passwd)
│   └── app/
│       ├── main.py               # Aplicação FastAPI + MQTT subscriber
│       ├── models.py             # Modelos Pydantic
│       └── database.py           # Conexão TimescaleDB + schema
├── dashboard/
│   └── index.html                # Dashboard em tempo real
└── README.md                     # Este arquivo
```

---

## Licença

Projeto educacional para carcinicultura de precisão.
