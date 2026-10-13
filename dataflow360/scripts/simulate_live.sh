#!/bin/bash
# Simulateur de commandes en temps réel pour DataFlow360
# Envoie des commandes toutes les 3 secondes, dont ~20% de suspectes.
# Usage : bash scripts/simulate_live.sh

API="http://localhost:8000"
KEY="demo-key-change-me-123"

echo "🚀 Simulateur temps réel démarré"
echo "   Ctrl+C pour arrêter"
echo ""

i=0
while true; do
  i=$((i + 1))
  order_id="live-$(date +%s)-$i"
  customer_id="cust-$(shuf -i 1-50 -n 1)"

  # 1 chance sur 5 : événement suspect
  if [ $((RANDOM % 5)) -eq 0 ]; then
    payload=$(cat <<EOF
{
  "event_id": "evt-$order_id",
  "event_type": "order_created",
  "order_id": "$order_id",
  "customer_id": "suspect-$customer_id",
  "order_total_amount": 5000000,
  "currency": "XOF",
  "client_ip": "1.2.3.4",
  "ip_country": "RU",
  "payment_method": "crypto",
  "payment_source_country": "KP",
  "payment_status": "failed",
  "payment_attempt": 5,
  "event_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)
    echo "🚨 Suspect : $order_id"
  else
    payload=$(cat <<EOF
{
  "event_id": "evt-$order_id",
  "event_type": "order_created",
  "order_id": "$order_id",
  "customer_id": "$customer_id",
  "order_total_amount": 50000,
  "currency": "XOF",
  "client_ip": "41.82.0.$i",
  "ip_country": "SN",
  "payment_method": "card",
  "payment_source_country": "SN",
  "payment_status": "approved",
  "payment_attempt": 1,
  "event_timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
)
    echo "✅ Normal : $order_id"
  fi

  curl -s -X POST "$API/webhook/order-created" \
    -H "Content-Type: application/json" \
    -H "X-Tenant-API-Key: $KEY" \
    -d "$payload" > /dev/null

  sleep 3
done
