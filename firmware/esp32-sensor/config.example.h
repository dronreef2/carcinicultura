/**
 * config.example.h — Modelo de configuração do firmware ESP32
 *
 * INSTRUÇÕES:
 *   1. Copie este arquivo para "config.h"
 *   2. Preencha os valores com as credenciais reais do seu ambiente
 *   3. Nunca commite o arquivo config.h no repositório
 */

#ifndef CONFIG_H
#define CONFIG_H

// ─── WiFi ──────────────────────────────────────────────────────────────────────
#define WIFI_SSID     "SUA_REDE_WIFI"
#define WIFI_PASSWORD "SUA_SENHA_WIFI"

// ─── Broker MQTT ───────────────────────────────────────────────────────────────
#define MQTT_HOST     "192.168.1.100"   // IP do servidor onde roda o Docker
#define MQTT_PORT     1883
#define MQTT_USER     "camarao"
#define MQTT_PASSWORD "mqtt_senha_segura"
#define MQTT_CLIENT   "esp32-01"        // Deve ser único por dispositivo

// ─── Identificação ─────────────────────────────────────────────────────────────
#define FARM_ID       "farm-01"
#define POND_ID       "pond-01"
#define DEVICE_ID     "esp32-01"

// ─── Hardware ──────────────────────────────────────────────────────────────────
#define SENSOR_PIN    4                 // GPIO do barramento OneWire (DS18B20)
#define LED_PIN       2                 // LED onboard do ESP32 (GPIO 2)

// Controle de atuador (aerador)
#define AERATOR_RELAY_PIN      16       // GPIO ligado ao módulo relé do aerador
#define AERATOR_ACTIVE_LEVEL   HIGH     // HIGH para relé ativo em nível alto; LOW para relé invertido
#define AERATOR_PULSE_DEFAULT_S 10      // Duração padrão para comando "pulse"

// ─── Intervalos (milissegundos) ────────────────────────────────────────────────
#define PUBLISH_INTERVAL_MS  60000      // Intervalo de publicação: 60 segundos
#define SENSOR_READ_DELAY_MS 1000       // Tempo de conversão do DS18B20

// ─── Watchdog ──────────────────────────────────────────────────────────────────
#define WDT_TIMEOUT_S 120              // Timeout do watchdog em segundos

#endif // CONFIG_H
