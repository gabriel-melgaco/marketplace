import requests
import hmac
import hashlib
import base64
import json
from django.conf import settings


url = "https://api.megdev.com.br/api/logistics/webhooks/melhor-envio"
secret = settings.MELHOR_ENVIO_WEBHOOK_SECRET.encode()

payload = {
    "event": "order.posted",
    "data": {
        "id": "a116234f-3087-4c9a-b623-3a29674c2b3f",
        "protocol": "ORD-202602261925",
        "status": "posted",
        "tracking": "teste_tracking_code",
        "self_tracking": None,
        "user_id": "0000111",
        "tags": [{"tag": "tag1", "url": "https://www.url1.com"}],
        "created_at": "2024-03-29T23:49:26+00:00",
        "paid_at": None,
        "generated_at": None,
        "posted_at": "2024-03-29T23:55:00+00:00",
        "delivered_at": None,
        "canceled_at": None,
        "expired_at": None,
        "tracking_url": "https://www.melhorrastreio.com.br/rastreio/XXXXXXXXX"
    }
}

raw_body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()

signature = base64.b64encode(
    hmac.new(secret, raw_body, hashlib.sha256).digest()
).decode()

headers = {
    "User-Agent": "Melhor Envio Webhooks/1.0",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "X-ME-Signature": signature
}

response = requests.post(url, headers=headers, data=raw_body)

print(response.status_code)
print(response.text)
