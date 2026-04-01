#!/bin/bash
FILE="/home/ubuntu/connector_generator/backend/workspaces/deployment_log.csv"
WEBHOOK_URL=""

# 1) sanity checks
if [ ! -f "$FILE" ]; then
  echo "Error: File not found: $FILE" >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq not installed (sudo apt-get install -y jq)" >&2
  exit 1
fi
if ! command -v column >/dev/null 2>&1; then
  echo "Error: column not installed (sudo apt-get install -y bsdmainutils || util-linux)" >&2
  exit 1
fi

# 2) align columns for readability
FORMATTED="$(column -t -s, "$FILE")"

# 3) count total number of records (excluding header)
TOTAL_RECORDS=$(( $(wc -l < "$FILE") - 1 ))

# 4) build a simple, markdown-free message (headers + aligned text + total count)
MESSAGE="$FORMATTED

------------------------------------
Total records: $TOTAL_RECORDS"

# 5) JSON-encode the whole message safely so newlines/quotes are correct
JSON_DATA=$(printf "%s" "$MESSAGE" | jq -Rs .)

# 6) send exactly { "data": "<encoded message>" }
curl -s -X POST -H "Content-Type: application/json" \
  -d "{\"data\": ${JSON_DATA}}" \
  "$WEBHOOK_URL"
