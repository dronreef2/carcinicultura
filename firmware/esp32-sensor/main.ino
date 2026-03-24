/**
 * ╔══════════════════════════════════════════════════════════════════════════════╗
 * ║  Firmware ESP32 — Sensor de Temperatura para Carcinicultura                ║
 * ║  Módulo 1: Leitura DS18B20 → MQTT → Backend                               ║
 * ╚══════════════════════════════════════════════════════════════════════════════╝
 *
 * Lê a temperatura da água do viveiro via sensor DS18B20 (protocolo OneWire)
 * e publica os dados via MQTT no formato JSON a cada 60 segundos.
 *
 * Hardware necessário:
 *   - ESP32 DevKit V1
 *   - Sensor DS18B20 à prova d'água
 *   - Resistor pull-up de 4.7kΩ entre DATA e VCC
 *
 * Bibliotecas necessárias (instalar via Arduino IDE):
 *   - OneWire           (por Jim Studt)
 *   - DallasTemperature (por Miles Burton)
 *   - PubSubClient      (por Nick O'Leary)
 *   - ArduinoJson       (por Benoît Blanchon)
 *
 * Autor: Sistema IoT Camarão
 * Data: 2026-03-17
 */

#include <WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ArduinoJson.h>
#include <esp_task_wdt.h>
#include <time.h>

#include "config.h"

// Valores padrão para manter compatibilidade com config.h antigos
#ifndef AERATOR_RELAY_PIN
#define AERATOR_RELAY_PIN 16
#endif

#ifndef AERATOR_ACTIVE_LEVEL
#define AERATOR_ACTIVE_LEVEL HIGH
#endif

#ifndef AERATOR_PULSE_DEFAULT_S
#define AERATOR_PULSE_DEFAULT_S 10
#endif

// ─── Objetos globais ───────────────────────────────────────────────────────────

// Barramento OneWire no pino configurado
OneWire oneWire(SENSOR_PIN);

// Gerenciador de sensores Dallas (DS18B20)
DallasTemperature sensors(&oneWire);

// Clientes de rede
WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

// ─── Variáveis de controle ─────────────────────────────────────────────────────

unsigned long ultimaPublicacao = 0;  // Timestamp da última publicação
unsigned long ultimoPiscaLed = 0;    // Controle do pisca-LED
bool ledLigado = false;              // Estado atual do LED
int tentativasWifi = 0;              // Contador de reconexões WiFi
int tentativasMqtt = 0;              // Contador de reconexões MQTT
bool aeradorLigado = false;          // Estado atual do aerador (relé)

// Tópico MQTT montado em tempo de execução
char topicoMqtt[128];
char topicoMqttComando[128];
char topicoMqttAck[128];

// Protótipos
unsigned long obterTimestamp();

// ─── Funções auxiliares ────────────────────────────────────────────────────────

/**
 * piscarLed — Pisca o LED indicador brevemente para sinalizar publicação
 * @param vezes   Número de piscadas
 * @param duracaoMs Duração de cada piscada em milissegundos
 */
void piscarLed(int vezes, int duracaoMs) {
  for (int i = 0; i < vezes; i++) {
    digitalWrite(LED_PIN, HIGH);
    delay(duracaoMs);
    digitalWrite(LED_PIN, LOW);
    if (i < vezes - 1) {
      delay(duracaoMs);
    }
  }
}

/**
 * definirAerador — Atualiza o estado físico do relé do aerador
 */
void definirAerador(bool ligar, const char* origem) {
  aeradorLigado = ligar;
  digitalWrite(AERATOR_RELAY_PIN, ligar ? AERATOR_ACTIVE_LEVEL : !AERATOR_ACTIVE_LEVEL);
  Serial.printf("[AERADOR] %s via %s\n", ligar ? "LIGADO" : "DESLIGADO", origem);
}

/**
 * pulsarAerador — Liga por alguns segundos e depois desliga
 */
void pulsarAerador(int duracaoS, const char* origem) {
  if (duracaoS <= 0) {
    duracaoS = AERATOR_PULSE_DEFAULT_S;
  }

  Serial.printf("[AERADOR] Pulso solicitado (%ds) via %s\n", duracaoS, origem);
  definirAerador(true, origem);

  unsigned long inicio = millis();
  unsigned long duracaoMs = (unsigned long)duracaoS * 1000UL;
  while (millis() - inicio < duracaoMs) {
    delay(100);
    esp_task_wdt_reset();
  }

  definirAerador(false, origem);
}

/**
 * publicarAckComando — Publica confirmação de execução do comando do aerador
 */
void publicarAckComando(const char* comando,
                        const char* commandId,
                        const char* source,
                        const char* status,
                        const char* message,
                        int duracaoS) {
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] ACK não enviado: cliente MQTT desconectado.");
    return;
  }

  StaticJsonDocument<256> doc;
  doc["timestamp"] = obterTimestamp();
  doc["farm_id"] = FARM_ID;
  doc["pond_id"] = POND_ID;
  doc["device_id"] = DEVICE_ID;
  doc["actuator_type"] = "aerator";
  doc["command"] = comando;
  if (commandId != nullptr && strlen(commandId) > 0) {
    doc["command_id"] = commandId;
  }
  doc["source"] = source;
  doc["status"] = status;
  doc["message"] = message;
  doc["aerator_state"] = aeradorLigado ? "on" : "off";
  if (duracaoS > 0) {
    doc["duration_s"] = duracaoS;
  }

  char payload[256];
  size_t tamanho = serializeJson(doc, payload, sizeof(payload));

  bool ok = mqttClient.publish(topicoMqttAck, payload, false);
  if (ok) {
    Serial.printf("[MQTT] ACK publicado (%d bytes): %s\n", tamanho, payload);
  } else {
    Serial.println("[MQTT] ERRO ao publicar ACK de comando.");
  }
}

/**
 * aoReceberComandoMqtt — Processa comandos de atuador vindos do backend
 * Payload esperado:
 *   {"command":"on|off|pulse","source":"manual|auto","duration_s":10}
 */
void aoReceberComandoMqtt(char* topic, byte* payload, unsigned int length) {
  Serial.printf("[MQTT] Comando recebido em %s (%u bytes)\n", topic, length);

  if (strcmp(topic, topicoMqttComando) != 0) {
    Serial.println("[MQTT] Tópico ignorado (não corresponde ao comando do aerador).");
    return;
  }

  if (length == 0 || length >= 256) {
    Serial.println("[MQTT] Payload de comando inválido (tamanho). Ignorando.");
    publicarAckComando("unknown", "", "backend", "error", "payload_size_invalid", 0);
    return;
  }

  char buffer[256];
  memcpy(buffer, payload, length);
  buffer[length] = '\0';

  StaticJsonDocument<256> doc;
  DeserializationError err = deserializeJson(doc, buffer);
  if (err) {
    Serial.printf("[MQTT] JSON inválido em comando de atuador: %s\n", err.c_str());
    publicarAckComando("unknown", "", "backend", "error", "json_invalid", 0);
    return;
  }

  const char* comando = doc["command"] | "";
  const char* commandId = doc["command_id"] | "";
  const char* source = doc["source"] | "backend";
  int duracaoS = doc["duration_s"] | AERATOR_PULSE_DEFAULT_S;

  if (strcmp(comando, "on") == 0) {
    definirAerador(true, source);
    publicarAckComando(comando, commandId, source, "ok", "executed", 0);
  } else if (strcmp(comando, "off") == 0) {
    definirAerador(false, source);
    publicarAckComando(comando, commandId, source, "ok", "executed", 0);
  } else if (strcmp(comando, "pulse") == 0) {
    pulsarAerador(duracaoS, source);
    publicarAckComando(comando, commandId, source, "ok", "executed", duracaoS);
  } else {
    Serial.printf("[AERADOR] Comando inválido: %s\n", comando);
    publicarAckComando(comando, commandId, source, "error", "command_invalid", 0);
  }
}

/**
 * conectarWifi — Estabelece ou restabelece a conexão WiFi
 *
 * Tenta conectar indefinidamente com intervalo de 500ms entre tentativas.
 * Reseta o watchdog a cada iteração para evitar reinício durante conexão lenta.
 */
void conectarWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;  // Já está conectado, não faz nada
  }

  Serial.println("[WiFi] Conectando...");
  Serial.printf("[WiFi] SSID: %s\n", WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tentativas = 0;
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    esp_task_wdt_reset();  // Alimenta o watchdog enquanto espera

    tentativas++;
    if (tentativas > 60) {  // 30 segundos sem conexão → reinicia o ESP32
      Serial.println("\n[WiFi] FALHA — reiniciando ESP32...");
      ESP.restart();
    }
  }

  tentativasWifi++;
  Serial.printf("\n[WiFi] Conectado! IP: %s (conexão #%d)\n",
                WiFi.localIP().toString().c_str(), tentativasWifi);

  // Configura o NTP para obter timestamp correto
  configTime(-3 * 3600, 0, "pool.ntp.org", "time.nist.gov");
  Serial.println("[NTP] Sincronizando relógio...");
}

/**
 * conectarMqtt — Estabelece ou restabelece a conexão com o broker MQTT
 *
 * Tenta até 5 vezes com intervalo de 5 segundos. Se todas falharem,
 * retorna false e a próxima tentativa ocorre no loop principal.
 */
bool conectarMqtt() {
  if (mqttClient.connected()) {
    return true;  // Já está conectado
  }

  Serial.printf("[MQTT] Conectando ao broker %s:%d...\n", MQTT_HOST, MQTT_PORT);

  for (int i = 0; i < 5; i++) {
    // Tenta conectar com credenciais e identificador único
    if (mqttClient.connect(MQTT_CLIENT, MQTT_USER, MQTT_PASSWORD)) {
      tentativasMqtt++;
      Serial.printf("[MQTT] Conectado! (conexão #%d)\n", tentativasMqtt);

      // Reinscreve no tópico de comando a cada reconexão
      if (mqttClient.subscribe(topicoMqttComando, 0)) {
        Serial.printf("[MQTT] Inscrito em comando de atuador: %s\n", topicoMqttComando);
      } else {
        Serial.printf("[MQTT] ERRO ao inscrever em comando de atuador: %s\n", topicoMqttComando);
      }
      return true;
    }

    Serial.printf("[MQTT] Falha (rc=%d). Tentativa %d/5...\n",
                  mqttClient.state(), i + 1);
    delay(5000);
    esp_task_wdt_reset();
  }

  Serial.println("[MQTT] Não foi possível conectar ao broker.");
  return false;
}

/**
 * lerTemperatura — Lê a temperatura do sensor DS18B20
 *
 * @return Temperatura em graus Celsius, ou -127 em caso de erro
 */
float lerTemperatura() {
  sensors.requestTemperatures();  // Solicita leitura a todos os sensores
  float temperatura = sensors.getTempCByIndex(0);  // Pega o primeiro sensor

  if (temperatura == DEVICE_DISCONNECTED_C) {
    Serial.println("[SENSOR] ERRO — Sensor DS18B20 desconectado!");
    return -127.0;
  }

  return temperatura;
}

/**
 * obterTimestamp — Retorna o epoch time atual via NTP
 *
 * @return Timestamp Unix (segundos desde 1970-01-01)
 */
unsigned long obterTimestamp() {
  time_t agora;
  time(&agora);
  return (unsigned long)agora;
}

/**
 * publicarTelemetria — Monta e publica o JSON de telemetria via MQTT
 *
 * @param temperatura Valor da temperatura lida do sensor
 * @return true se a publicação foi bem-sucedida
 */
bool publicarTelemetria(float temperatura) {
  // Monta o documento JSON
  StaticJsonDocument<256> doc;
  doc["timestamp"] = obterTimestamp();
  doc["pond_id"] = POND_ID;
  doc["device_id"] = DEVICE_ID;
  doc["temperature"] = serialized(String(temperatura, 2));

  // Serializa para string
  char payload[256];
  size_t tamanho = serializeJson(doc, payload, sizeof(payload));

  // Publica no tópico MQTT
  bool sucesso = mqttClient.publish(topicoMqtt, payload, false);

  if (sucesso) {
    Serial.printf("[MQTT] Publicado (%d bytes): %s\n", tamanho, payload);
    piscarLed(2, 100);  // 2 piscadas rápidas = sucesso
  } else {
    Serial.println("[MQTT] ERRO ao publicar telemetria!");
    piscarLed(5, 50);   // 5 piscadas rápidas = erro
  }

  return sucesso;
}

// ─── Setup ─────────────────────────────────────────────────────────────────────

void setup() {
  // Inicializa a serial para debug
  Serial.begin(115200);
  delay(1000);

  Serial.println("╔══════════════════════════════════════════════════╗");
  Serial.println("║  IoT Camarão — Módulo 1: Sensor de Temperatura  ║");
  Serial.println("╚══════════════════════════════════════════════════╝");
  Serial.printf("Dispositivo: %s | Viveiro: %s | Fazenda: %s\n",
                DEVICE_ID, POND_ID, FARM_ID);

  // Configura o pino do LED como saída
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  // Configura o pino do relé do aerador
  pinMode(AERATOR_RELAY_PIN, OUTPUT);
  definirAerador(false, "startup");

  // Inicializa o sensor DS18B20
  sensors.begin();
  int sensoresEncontrados = sensors.getDeviceCount();
  Serial.printf("[SENSOR] DS18B20 inicializado — %d sensor(es) encontrado(s)\n",
                sensoresEncontrados);

  if (sensoresEncontrados == 0) {
    Serial.println("[SENSOR] ALERTA — Nenhum sensor detectado! Verifique a fiação.");
  }

  // Define a resolução do sensor (12 bits = 0.0625°C, ~750ms de conversão)
  sensors.setResolution(12);

  // Monta o tópico MQTT: farm/{farm_id}/pond/{pond_id}/telemetry
  snprintf(topicoMqtt, sizeof(topicoMqtt),
           "farm/%s/pond/%s/telemetry", FARM_ID, POND_ID);
  Serial.printf("[MQTT] Tópico: %s\n", topicoMqtt);

  // Monta o tópico MQTT de comando do aerador
  snprintf(topicoMqttComando, sizeof(topicoMqttComando),
           "farm/%s/pond/%s/actuator/aerator/set", FARM_ID, POND_ID);
  Serial.printf("[MQTT] Tópico de comando: %s\n", topicoMqttComando);

  // Monta o tópico MQTT de ACK do aerador
  snprintf(topicoMqttAck, sizeof(topicoMqttAck),
           "farm/%s/pond/%s/actuator/aerator/ack", FARM_ID, POND_ID);
  Serial.printf("[MQTT] Tópico de ACK: %s\n", topicoMqttAck);

  // Configura o broker MQTT
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
  mqttClient.setCallback(aoReceberComandoMqtt);
  mqttClient.setBufferSize(512);  // Buffer suficiente para o JSON

  // Conecta ao WiFi
  conectarWifi();

  // Conecta ao broker MQTT
  conectarMqtt();

  // Configura o watchdog timer
  esp_task_wdt_init(WDT_TIMEOUT_S, true);  // Habilita panic (reinício automático)
  esp_task_wdt_add(NULL);                   // Registra a task principal
  Serial.printf("[WDT] Watchdog configurado: %d segundos\n", WDT_TIMEOUT_S);

  // Faz uma leitura inicial para verificar o sensor
  float temp = lerTemperatura();
  if (temp != -127.0) {
    Serial.printf("[SENSOR] Leitura inicial: %.2f °C\n", temp);
  }

  Serial.println("[SISTEMA] Inicialização completa. Entrando no loop principal...\n");
}

// ─── Loop Principal ────────────────────────────────────────────────────────────

void loop() {
  // Alimenta o watchdog — se o loop travar, o ESP32 reinicia automaticamente
  esp_task_wdt_reset();

  // Mantém a conexão WiFi
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Conexão perdida! Reconectando...");
    conectarWifi();
  }

  // Mantém a conexão MQTT
  if (!mqttClient.connected()) {
    Serial.println("[MQTT] Conexão perdida! Reconectando...");
    conectarMqtt();
  }
  mqttClient.loop();  // Processa mensagens MQTT pendentes

  // Verifica se é hora de publicar
  unsigned long agora = millis();
  if (agora - ultimaPublicacao >= PUBLISH_INTERVAL_MS) {
    ultimaPublicacao = agora;

    // Lê a temperatura do sensor
    float temperatura = lerTemperatura();

    if (temperatura != -127.0) {
      // Validação básica — temperatura da água em carcinicultura
      if (temperatura < 0.0 || temperatura > 50.0) {
        Serial.printf("[SENSOR] ALERTA — Leitura suspeita: %.2f °C (fora da faixa 0-50)\n",
                      temperatura);
      }

      // Publica a telemetria
      publicarTelemetria(temperatura);
    } else {
      Serial.println("[SENSOR] Leitura ignorada — sensor retornou erro.");
    }
  }

  // Pequeno delay para não sobrecarregar o loop
  delay(100);
}
