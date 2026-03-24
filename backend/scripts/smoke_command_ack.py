"""
Smoke test E2E do fluxo de atuador com command_id.

Fluxo validado:
1) POST /api/ponds/{id}/actuators/aerator/commands
2) Recebe ACK MQTT no tópico do atuador
3) Confere se ACK tem o mesmo command_id
4) Consulta histórico e valida status final do comando
"""

import argparse
import json
import sys
import threading
import time
import urllib.error
import urllib.request

import paho.mqtt.client as mqtt


def _http_json(method: str, url: str, payload: dict | None = None, timeout: int = 10) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url=url, method=method, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test comando -> ACK -> status final")
    parser.add_argument("--backend-url", default="http://localhost:8000", help="Base URL da API")
    parser.add_argument("--pond-id", default="pond-01", help="ID do viveiro")
    parser.add_argument("--farm-id", default="farm-01", help="ID da fazenda")
    parser.add_argument("--actuator-type", default="aerator", help="Tipo de atuador")
    parser.add_argument("--command", choices=["on", "off", "pulse"], default="pulse", help="Comando do atuador")
    parser.add_argument("--source", choices=["manual", "auto"], default="manual", help="Origem do comando")
    parser.add_argument("--duration-s", type=int, default=5, help="Duração para pulse")
    parser.add_argument("--mqtt-host", default="localhost", help="Host MQTT")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="Porta MQTT")
    parser.add_argument("--mqtt-user", default="camarao", help="Usuário MQTT")
    parser.add_argument("--mqtt-password", default="mqtt_senha_segura", help="Senha MQTT")
    parser.add_argument("--timeout", type=int, default=20, help="Timeout total para ACK e status")
    parser.add_argument("--simulate-ack", action="store_true", help="Publica ACK simulado no MQTT (sem firmware)")
    parser.add_argument("--simulate-ack-status", choices=["ok", "error"], default="ok", help="Status do ACK simulado")
    args = parser.parse_args()

    topic_ack = f"farm/{args.farm_id}/pond/{args.pond_id}/actuator/{args.actuator_type}/ack"
    ack_event = threading.Event()
    ack_payload: dict = {}
    command_id_esperado = {"value": ""}

    def on_connect(client, userdata, flags, reason_code, properties):
        client.subscribe(topic_ack)
        print(f"[MQTT] inscrito em {topic_ack}")

    def on_message(client, userdata, msg):
        nonlocal ack_payload
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        cmd_id = str(payload.get("command_id", "")).strip()
        if cmd_id and cmd_id == command_id_esperado["value"]:
            ack_payload = payload
            ack_event.set()

    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id="smoke-command-ack",
        protocol=mqtt.MQTTv5,
    )
    client.username_pw_set(args.mqtt_user, args.mqtt_password)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.mqtt_host, args.mqtt_port, keepalive=30)
        client.loop_start()
    except Exception as exc:
        print(f"[ERRO] Falha ao conectar MQTT: {exc}")
        return 2

    try:
        endpoint_cmd = (
            f"{args.backend_url}/api/ponds/{args.pond_id}/actuators/{args.actuator_type}/commands"
        )
        payload_cmd = {
            "command": args.command,
            "source": args.source,
        }
        if args.command == "pulse":
            payload_cmd["duration_s"] = args.duration_s

        try:
            resposta = _http_json("POST", endpoint_cmd, payload_cmd, timeout=10)
        except urllib.error.URLError as exc:
            print(f"[ERRO] Falha ao chamar backend: {exc}")
            return 3

        command_id = str(resposta.get("command_id", "")).strip()
        if not command_id:
            print("[ERRO] Backend não retornou command_id")
            return 4

        command_id_esperado["value"] = command_id
        print(f"[API] comando criado id={resposta.get('id')} command_id={command_id}")

        if args.simulate_ack:
            ack_simulado = {
                "timestamp": int(time.time()),
                "farm_id": args.farm_id,
                "pond_id": args.pond_id,
                "device_id": "ci-sim",
                "actuator_type": args.actuator_type,
                "command": args.command,
                "command_id": command_id,
                "source": args.source,
                "status": args.simulate_ack_status,
                "message": "simulated_ack",
                "aerator_state": "on" if args.command == "on" else "off",
            }
            if args.command == "pulse":
                ack_simulado["duration_s"] = args.duration_s

            client.publish(topic_ack, json.dumps(ack_simulado), qos=0, retain=False)
            print(f"[MQTT] ACK simulado publicado em {topic_ack} com status={args.simulate_ack_status}")

        recebeu_ack = ack_event.wait(timeout=args.timeout)
        if not recebeu_ack:
            print("[ERRO] Timeout aguardando ACK com command_id correspondente")
            return 5

        print(f"[MQTT] ACK recebido command_id={ack_payload.get('command_id')} status={ack_payload.get('status')}")

        deadline = time.time() + args.timeout
        status_final = None
        while time.time() < deadline:
            endpoint_hist = (
                f"{args.backend_url}/api/ponds/{args.pond_id}/actuators/commands?limit=50"
            )
            historico = _http_json("GET", endpoint_hist, timeout=10)

            if isinstance(historico, list):
                match = next((c for c in historico if c.get("command_id") == command_id), None)
                if match:
                    status_final = str(match.get("status", ""))
                    if status_final in {"confirmed", "error"}:
                        print(f"[API] status final command_id={command_id}: {status_final}")
                        return 0 if status_final == "confirmed" else 6

            time.sleep(1)

        print("[ERRO] Timeout aguardando status final no histórico do backend")
        return 7
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    sys.exit(main())
