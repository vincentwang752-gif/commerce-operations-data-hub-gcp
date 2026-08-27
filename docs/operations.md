# Operations runbook

## First real order checklist

When the first customer order arrives after activation, check the layers in this order:

1. Shopify Flow run history shows the workflow was triggered.
2. The HTTP action returned a 2xx response.
3. API Gateway request count increased and shows no authentication rejection.
4. Cloud Run logs contain a successful `/flow/shopify` request.
5. Airtable contains one record whose `Order ID` matches Shopify.
6. Revenue, currency, customer email, SKU list, and fulfillment status match the Shopify order.

Do not create a duplicate test order solely to validate the pipeline. An authenticated invalid-ID request is sufficient for pre-launch connectivity; the first real order validates field mapping.

## Common failures

| Symptom | Most likely cause | First check |
|---|---|---|
| API Gateway returns 401/403 before Cloud Run logs appear | Missing, invalid, or unrestricted API key configuration | Flow `x-api-key` header and API-key API target |
| Cloud Run returns 401 | Missing or mismatched Flow token | Flow header and Secret Manager version mounted by Cloud Run |
| Cloud Run returns 400 | Flow sent an empty or malformed Shopify order ID | Flow request body Liquid expression |
| Cloud Run returns 403 from the platform | Gateway service account lacks `roles/run.invoker` | Cloud Run service-level IAM policy |
| Cloud Run returns 502 | Shopify or Airtable rejected/timed out | Cloud Run exception log and upstream API status |
| Record is missing but the HTTP request succeeded | Airtable field/schema mismatch or wrong base/table ID | Cloud Run logs and Airtable target IDs |
| Duplicate Airtable records | `Order ID` is not stable/unique or manually altered | Primary field and upsert lookup formula |
| Attribution differs from GA4 or ad platforms | Different identity, window, consent, and attribution rules | Treat each platform as its own measurement source |

## Safe retry behavior

The write path is idempotent on Shopify `Order ID`. Replaying a Flow run or sending the same order ID again updates the existing Airtable record instead of intentionally creating another one.

## Credential rotation

### Flow token

1. Add a new Secret Manager version.
2. Deploy a new Cloud Run revision that mounts the new version.
3. Replace the `X-Shopify-Flow-Token` value in Shopify Flow.
4. Perform the invalid-ID verification.
5. Disable old secret versions after confirming traffic uses the new version.

### API key

1. Create a new key restricted to the same API Gateway managed service.
2. Replace the Flow `x-api-key` value.
3. Perform the invalid-ID verification.
4. Delete or disable the old key.

### Shopify and Airtable tokens

Rotate them in their source platform, add new Secret Manager versions, and deploy a Cloud Run revision with the new versions. Never place token values in environment files committed to Git.

## Monitoring

At minimum, alert on:

- Cloud Run 5xx responses.
- API Gateway 401/403 spikes.
- No successful syncs during periods when Shopify reports orders.
- Airtable API rate-limit or schema errors.

For larger stores, decouple ingestion and Airtable writes with Pub/Sub or Cloud Tasks so Shopify-facing requests remain fast during Airtable throttling.
