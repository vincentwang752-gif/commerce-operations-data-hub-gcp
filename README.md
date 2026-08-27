# Commerce Operations Data Hub: Shopify + GA4 + Airtable + Google Cloud

English | [简体中文](README.zh-CN.md)

A reusable commerce operations data hub that combines Shopify orders, GA4 behavior, ad and creator touchpoints, VOC surveys, and customer lifecycle data in Airtable, with Google Cloud providing secure ingestion and scheduled synchronization.

The repository contains reusable code, a sanitized data model, field dictionary, metric definitions, interface design, and runbooks. It deliberately excludes production records, tokens, URLs, project IDs, analytics property IDs, and Airtable internal IDs.

## Architecture

```mermaid
flowchart LR
    Shopify --> OrderSync[Order sync on Cloud Run]
    GA4[GA4 Data API] --> GA4Sync[Daily GA4 sync]
    Forms[Google Forms / Sheets] --> Apps[Apps Script] --> VOC[VOC sync]
    Ads[Google Ads / Meta Ads] --> AdJobs[Ad ingestion]
    Creators[Creator links / coupons / partnership ads] --> Attribution[Attribution rules]
    OrderSync --> Airtable[(Airtable operations layer)]
    GA4Sync --> BigQuery[(BigQuery history layer)]
    GA4Sync --> Airtable
    VOC --> Airtable
    VOC --> Klaviyo
    AdJobs --> Airtable
    Attribution --> Airtable
```

## What is included

- `services/shopify-order-sync`: Shopify Flow, Admin GraphQL, Airtable upsert, webhook and reconciliation.
- `services/ga4-airtable-sync`: daily T-4 GA4 extraction, BigQuery merge and Airtable upsert.
- `services/voc-survey-sync`: two-stage survey completion, eligible-order validation, Klaviyo events and lifecycle updates.
- `architecture`: data flow, data model, attribution rules and Airtable Interface design.
- `schema/airtable-schema.json`: complete sanitized metadata for 11 Airtable tables and 333 fields.
- `docs`: metric definitions, deployment, operations, privacy and Chinese data dictionary.

## Source-of-truth policy

- Shopify: orders, refunds and net revenue.
- GA4: on-site behavior and analytics-platform attribution.
- Ad platforms: spend and platform-reported conversions.
- Airtable: explainable touchpoints, creator relationships, campaign metadata, VOC stages and human review.

Differences among platforms are retained and reconciled rather than overwritten. A GA4/Shopify mismatch is not automatically treated as an order-sync defect.

## Security

- Keep secrets in Google Secret Manager.
- Keep Cloud Run private and grant narrow invoker roles.
- Never commit production IDs, customer records or survey answers.
- Never send PII in GA4 event parameters or UTM values.
- Treat Airtable as an operations layer, not an unlimited warehouse.

See [the Chinese README](README.zh-CN.md) for the complete project guide.

## License

[MIT](LICENSE)
