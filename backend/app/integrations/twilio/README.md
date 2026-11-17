# Twilio Voice & WhatsApp Webhook Adapter (`R4.3.0`)

`webhooks.py` provides sender normalization (`extract_channel_and_phone` for `whatsapp:+569...` and voice numbers) and cryptographic `X-Twilio-Signature` HMAC-SHA1 request verification (`verify_twilio_signature`).
