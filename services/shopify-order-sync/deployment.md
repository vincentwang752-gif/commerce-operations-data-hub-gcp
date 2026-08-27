# Deployment guide

This guide deploys the service to Google Cloud with a private Cloud Run backend and API Gateway as the public ingress.

## Prerequisites

- A Google Cloud project with billing enabled.
- `gcloud` authenticated to an account that can manage Cloud Run, API Gateway, IAM, Secret Manager, and API keys.
- Shopify Flow access. A Shopify custom app with Admin API order access is optional for the permission-light Flow snapshot path, but required for reconciliation, refund refreshes and ID-only ingestion.
- An Airtable personal access token with record read/write access to the target base.
- The Airtable schema listed in the project README.

Set deployment variables in your shell:

```bash
export PROJECT_ID="your-project-id"
export REGION="your-cloud-run-region"
export GATEWAY_REGION="your-api-gateway-region"
export SERVICE_NAME="shopify-airtable-sync"
export API_ID="shopify-airtable-api"
export API_CONFIG_ID="shopify-airtable-config-v1"
export GATEWAY_ID="shopify-airtable-gateway"
export AIRTABLE_BASE_ID="appXXXXXXXXXXXXXX"
export AIRTABLE_TABLE_ID="tblXXXXXXXXXXXXXX"
export SHOPIFY_STORE_DOMAIN="example-store.myshopify.com"
```

Confirm that `GATEWAY_REGION` is currently offered by API Gateway; its region list is not identical to Cloud Run's.

## 1. Enable APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  apigateway.googleapis.com \
  servicecontrol.googleapis.com \
  servicemanagement.googleapis.com \
  apikeys.googleapis.com \
  --project "$PROJECT_ID"
```

## 2. Create service accounts

Use separate identities for the application runtime and API Gateway.

```bash
gcloud iam service-accounts create shopify-sync-runtime \
  --display-name="Shopify Airtable sync runtime" \
  --project "$PROJECT_ID"

gcloud iam service-accounts create shopify-sync-gateway \
  --display-name="Shopify Airtable API Gateway" \
  --project "$PROJECT_ID"
```

```bash
export RUNTIME_SA="shopify-sync-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
export GATEWAY_SA="shopify-sync-gateway@${PROJECT_ID}.iam.gserviceaccount.com"
```

## 3. Create secrets

Create these Secret Manager secrets and add a value to each:

```text
airtable-token
shopify-admin-access-token
shopify-flow-token
shopify-webhook-secret       # optional
shopify-reconcile-token      # optional
```

Grant the runtime service account access only to the secrets it consumes:

```bash
gcloud secrets add-iam-policy-binding airtable-token \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID"
```

Repeat the binding for the other required secrets.

## 4. Deploy private Cloud Run

```bash
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --service-account "$RUNTIME_SA" \
  --no-allow-unauthenticated \
  --set-env-vars="AIRTABLE_BASE_ID=${AIRTABLE_BASE_ID},AIRTABLE_ORDERS_TABLE=${AIRTABLE_TABLE_ID},SHOPIFY_STORE_DOMAIN=${SHOPIFY_STORE_DOMAIN},SHOPIFY_API_VERSION=2026-07" \
  --set-secrets="AIRTABLE_TOKEN=airtable-token:latest,SHOPIFY_ACCESS_TOKEN=shopify-admin-access-token:latest,SHOPIFY_FLOW_TOKEN=shopify-flow-token:latest"
```

Get the service URL:

```bash
export RUN_URL="$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format='value(status.url)')"
```

Allow only the gateway service account to invoke this Cloud Run service:

```bash
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --member="serviceAccount:${GATEWAY_SA}" \
  --role="roles/run.invoker"
```

## 5. Create API Gateway

Render the OpenAPI template without committing the generated production URL:

```bash
sed "s|YOUR_CLOUD_RUN_URL|${RUN_URL}|g" \
  gateway/openapi.template.yaml > openapi.generated.yaml
```

```bash
gcloud api-gateway apis create "$API_ID" --project "$PROJECT_ID"

gcloud api-gateway api-configs create "$API_CONFIG_ID" \
  --api "$API_ID" \
  --openapi-spec openapi.generated.yaml \
  --backend-auth-service-account "$GATEWAY_SA" \
  --project "$PROJECT_ID"

gcloud api-gateway gateways create "$GATEWAY_ID" \
  --api "$API_ID" \
  --api-config "$API_CONFIG_ID" \
  --location "$GATEWAY_REGION" \
  --project "$PROJECT_ID"
```

Retrieve the gateway hostname:

```bash
gcloud api-gateway gateways describe "$GATEWAY_ID" \
  --location "$GATEWAY_REGION" \
  --project "$PROJECT_ID" \
  --format='value(defaultHostname)'
```

## 6. Create and restrict an API key

Create one key dedicated to Shopify Flow. Restrict it to the managed service created for this API Gateway; do not reuse a browser or analytics key.

```bash
gcloud services api-keys create \
  --display-name="Shopify Flow gateway key" \
  --project "$PROJECT_ID"
```

```bash
export MANAGED_SERVICE="$(gcloud api-gateway apis describe "$API_ID" \
  --project "$PROJECT_ID" \
  --format='value(managedService)')"
```

Update the key with an API target restriction for `${MANAGED_SERVICE}` using the key's resource name returned by `gcloud services api-keys list`.

## 7. Configure Shopify Flow

Follow the exact Flow configuration in the README. If Admin API access is not available, use `shopify-flow-order-payload.json.liquid` as the request body. Retrieve the API key value and `shopify-flow-token` secret only when entering them into Shopify, and do not paste them into tickets, chat, source code, screenshots, or logs.

Turn the workflow on after the endpoint passes the non-writing verification below.

## 8. Non-writing verification

For the optional Admin API path, send an authenticated request with an invalid order ID:

```json
{"order_id":"not-an-order"}
```

Expected result: HTTP `400` with an invalid-order-ID message. That proves the gateway, both authentication layers, and the current Cloud Run revision are connected without writing an Airtable record.

## Optional: reconciliation

The `/reconcile` endpoint queries recently updated Shopify orders and upserts them again. Keep it behind trusted Google Cloud authentication or add it to API Gateway with separate protection. Run it with Cloud Scheduler only if your Shopify scopes and operating model require repair of missed updates.
