# Deploy gratuito (frontend + backend) em VM Always Free

Este guia sobe o sistema completo com Docker Compose:
- Backend FastAPI
- Banco TimescaleDB
- Broker MQTT Mosquitto
- Dashboard Streamlit

Arquivos usados:
- `deploy/docker-compose.free.yml`
- `deploy/docker-compose.free.secure.yml` (recomendado em produção)
- `deploy/.env.free.example`
- `streamlit-dashboard/Dockerfile`
- `deploy/docker-compose.cloudflare.yml` (opcional, HTTPS)

## 1. Criar VM gratuita

Opcao recomendada: Oracle Cloud Always Free (VM ARM ou AMD).

Requisitos minimos:
- 2 vCPU
- 6 GB RAM (ou maior, se disponivel)
- Ubuntu 22.04 LTS

## 2. Preparar servidor

```bash
sudo apt-get update
sudo apt-get install -y git ca-certificates curl

# Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Docker Compose plugin
sudo apt-get install -y docker-compose-plugin
```

## 3. Clonar projeto e configurar env

```bash
git clone <SEU_REPO_GIT> carcinicultura
cd carcinicultura

cp deploy/.env.free.example deploy/.env.free
```

Edite `deploy/.env.free` e troque pelo menos:
- `POSTGRES_PASSWORD`
- `MQTT_PASSWORD`
- `CORS_ORIGINS` (coloque o dominio do dashboard em producao)

## 4. Subir stack em producao

```bash
cd deploy
docker compose -f docker-compose.free.yml --env-file .env.free up -d --build
```

Verificar status:

```bash
docker compose -f docker-compose.free.yml ps
```

Ver logs:

```bash
docker compose -f docker-compose.free.yml logs -f backend
docker compose -f docker-compose.free.yml logs -f dashboard
docker compose -f docker-compose.free.yml logs -f mosquitto
```

## 5. Testar endpoints

API health:

```bash
curl http://<IP_DA_VM>:8000/api/health
```

Dashboard:

- Abra `http://<IP_DA_VM>:8501`
- No sidebar, deixe `Fonte de dados = Auto (tenta API)`

MQTT (ESP32):
- Host: `<IP_DA_VM>`
- Porta: `1883`
- Usuario/senha: valores em `deploy/.env.free`

## 6. Liberar portas no firewall da VM

Portas necessarias:
- 1883/TCP (MQTT do ESP32)
- 8000/TCP (API)
- 8501/TCP (Dashboard)
- 9001/TCP (MQTT WebSocket, opcional)

Se usar UFW:

```bash
sudo ufw allow 1883/tcp
sudo ufw allow 8000/tcp
sudo ufw allow 8501/tcp
sudo ufw allow 9001/tcp
sudo ufw enable
```

## 7. HTTPS gratuito (recomendado)

Opcoes gratuitas:
- Cloudflare Tunnel (nao precisa abrir porta 80/443)
- Caddy/Nginx + Let's Encrypt (requer dominio apontado para a VM)

Sugestao pratica:
1. Publicar primeiro com IP para validar ponta a ponta.
2. Depois adicionar HTTPS e dominio.

Ativacao rapida com Cloudflare Tunnel:

```bash
cd deploy
docker compose \
	-f docker-compose.free.yml \
	-f docker-compose.cloudflare.yml \
	--env-file .env.free up -d
```

Ativacao recomendada em producao (HTTPS + superficie reduzida):

```bash
cd deploy
docker compose \
	-f docker-compose.free.secure.yml \
	--env-file .env.free up -d
```

Guia detalhado:
- `docs/deploy-https-cloudflare-tunnel.md`

## 8. Operacao basica

Atualizar aplicacao:

```bash
cd ~/carcinicultura
git pull
cd deploy
docker compose -f docker-compose.free.yml --env-file .env.free up -d --build
```

Parar stack:

```bash
cd ~/carcinicultura/deploy
docker compose -f docker-compose.free.yml --env-file .env.free down
```

## 9. Observacoes importantes

- O dashboard ja integra com API real e faz fallback para simulacao.
- Para producao real, mantenha `DASHBOARD_DATA_SOURCE=auto` ou `api`.
- Se usar `api` e o backend cair, o dashboard nao mostra fallback.
- O arquivo `schema.sql` e mais completo que o schema atual do backend; isso nao impede deploy do modulo 1, mas deve ser alinhado em uma evolucao futura.
