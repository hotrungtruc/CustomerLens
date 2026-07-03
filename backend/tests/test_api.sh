#!/bin/bash
# Test the customer_profile PUT endpoint
set -e

TOKEN=$(curl -s -X POST http://localhost:8000/api/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

echo "Token: $TOKEN"

echo "--- Testing PUT /api/customer_profile ---"
curl -v -X PUT http://localhost:8000/api/customer_profile \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"id":"test_0beb8992","source_id":"test_0beb8992","name":"Trung Truc Ho","phone":"0924692823","email":"test@test.com","rank":"Guest"}'

echo ""
echo "--- Done ---"
