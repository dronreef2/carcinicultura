# HTTPS gratis com Cloudflare Tunnel

Este guia adiciona HTTPS e dominio sem abrir porta 80/443.

Pre-requisito:
- Stack base ja em execucao com deploy/docker-compose.free.yml

Arquivos usados:
- deploy/docker-compose.free.yml
- deploy/docker-compose.free.secure.yml
- deploy/docker-compose.cloudflare.yml
- deploy/.env.free

## 1. Criar tunnel no Cloudflare

1. Entre no painel Cloudflare Zero Trust.
2. Acesse Networks > Tunnels > Create tunnel.
3. Escolha Cloudflared.
4. Copie o token do tunnel.

## 2. Configurar hostnames publicos

No mesmo tunnel, crie public hostnames:
- app.seudominio.com -> http://dashboard:8501
- api.seudominio.com -> http://backend:8000

Observacao:
- O nome dashboard e backend sao os nomes dos servicos Docker.
- O cloudflared acessa esses servicos pela rede interna do Compose.

## 3. Adicionar token no env

No arquivo deploy/.env.free, adicione:

CLOUDFLARE_TUNNEL_TOKEN=cole_o_token_aqui

## 4. Subir stack com tunnel (modo padrao)

Com a stack base ativa, execute:

cd deploy
docker compose \
  -f docker-compose.free.yml \
  -f docker-compose.cloudflare.yml \
  --env-file .env.free up -d

## 5. Modo recomendado (compose seguro dedicado)

No modo recomendado, backend/dashboard/db nao expoem portas publicas.
O acesso externo acontece somente pelo Cloudflare Tunnel.

```bash
cd deploy
docker compose \
  -f docker-compose.free.secure.yml \
  --env-file .env.free up -d
```

## 6. Validar

Ver container:

docker compose \
  -f docker-compose.free.secure.yml \
  --env-file .env.free ps

Ver logs do tunnel:

docker compose \
  -f docker-compose.free.secure.yml \
  --env-file .env.free logs -f cloudflared

Teste no navegador:
- https://app.seudominio.com
- https://api.seudominio.com/api/health

## 7. Recomendações de seguranca

1. Ajuste CORS_ORIGINS no deploy/.env.free para o dominio final do app.
2. Em producao, use `docker-compose.free.secure.yml`.
3. Troque as senhas padrao de banco e MQTT.

## 8. Opcional: reduzir superficie exposta

Se for operar apenas com Cloudflare Tunnel, evite expor portas HTTP de backend/dashboard.

Mantenha 1883 aberto apenas se o ESP32 publicar direto por IP publico.
