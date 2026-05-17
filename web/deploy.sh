#!/usr/bin/env bash
# deploy.sh — executar na VPS como root após clonar o repo
# Uso: bash deploy.sh
set -euo pipefail

DOMAIN="educator.yaatoro.com"
EMAIL="hiagofdss900@gmail.com"

echo "==> Instalando dependências"
apt-get update -q
apt-get install -y -q docker.io docker-compose-v2 certbot

echo "==> Obtendo certificado SSL (Let's Encrypt)"
# Para o nginx temporariamente se estiver rodando
docker compose down 2>/dev/null || true

certbot certonly --standalone \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  -d "$DOMAIN"

echo "==> Gerando secrets"
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "ATENÇÃO: edite o arquivo .env com os valores reais antes de continuar."
  echo "  SECRET_KEY      → python3 -c \"import secrets; print(secrets.token_hex(32))\""
  echo "  ENCRYPTION_KEY  → python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  echo "  POSTGRES_PASSWORD → senha forte"
  echo "  ADMIN_SECRET    → python3 -c \"import secrets; print(secrets.token_hex(24))\""
  echo "  LITELLM_MASTER_KEY → master key do LiteLLM"
  echo ""
  read -p "Pressione ENTER após editar o .env..."
fi

echo "==> Subindo serviços"
docker compose up -d --build

echo ""
echo "✓ Deploy concluído!"
echo "  Site: https://$DOMAIN"
echo ""
echo "  Renovação automática do SSL (adicionar ao cron):"
echo "  0 3 * * * certbot renew --quiet && docker compose exec nginx nginx -s reload"
