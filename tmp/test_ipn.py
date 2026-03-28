import hmac
import hashlib
import requests
import json

# Your NowPayments IPN Secret (set this to match your .env for testing)
IPN_SECRET = "your_test_secret" 
URL = "http://localhost:8000/billing/nowpayments-ipn"

payload = {
    "payment_status": "finished",
    "subscription_id": "12345", # Use a real one from your DB if testing live
    "customer_email": "test@example.com"
}

payload_raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
signature = hmac.new(IPN_SECRET.encode('utf-8'), payload_raw, hashlib.sha512).hexdigest()

headers = {
    "x-nowpayments-sig": signature,
    "Content-Type": "application/json"
}

print(f"Sending IPN to {URL}...")
try:
    response = requests.post(URL, data=payload_raw, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
