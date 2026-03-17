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

// Tópico MQTT montado em tempo de execução
char topicoMqtt[128];

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

  // Configura o broker MQTT
  mqttClient.setServer(MQTT_HOST, MQTT_PORT);
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
