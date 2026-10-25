# Orbit Platform Handbook

*Synthetic documentation for a fictional product. Safe to redistribute.*

## 1. Plans and limits

Orbit has three plans. **Starter** includes 3 projects, 10 GB of object storage and
50,000 API calls per month. **Team** includes 25 projects, 250 GB of storage and
2,000,000 API calls per month. **Enterprise** removes project limits and is billed
on committed usage.

API calls above the monthly allowance are billed at 0.40 USD per 1,000 calls on
Starter and 0.18 USD per 1,000 calls on Team. Overage is never charged without a
usage alert being sent first.

## 2. Authentication

Orbit supports two authentication methods: **project API keys** and **OAuth 2.0
device flow**. Project API keys are scoped to a single project and never expire
automatically; they must be rotated manually. OAuth access tokens expire after
60 minutes and refresh tokens after 30 days of inactivity.

An API key prefix identifies its environment: `orb_live_` for production and
`orb_test_` for the sandbox. Test keys cannot read production data.

## 3. Rate limits

The default rate limit is 120 requests per minute per project on Starter and 600
requests per minute on Team. Bursts of up to twice the limit are permitted for 10
seconds. When a limit is exceeded the API returns HTTP 429 with a `Retry-After`
header expressed in seconds.

Rate limits are enforced per project, not per API key, so adding keys does not
increase throughput.

## 4. Data retention

Event logs are retained for 30 days on Starter and 180 days on Team. Deleted
projects enter a 14-day soft-delete window during which they can be restored by
an account owner. After 14 days the data is purged and cannot be recovered.

Backups are taken every 6 hours and stored in a separate region. Point-in-time
restore is available on Team and Enterprise only, with a granularity of 5 minutes.

## 5. Regions and residency

Orbit runs in four regions: `us-east`, `eu-west`, `ap-south` and `ap-southeast`.
A project's region is chosen at creation time and **cannot be changed
afterwards**; migrating requires exporting and re-importing into a new project.

EU projects keep all customer data inside `eu-west`, including backups.

## 6. Webhooks

Webhooks retry failed deliveries 5 times with exponential backoff over roughly
one hour. A delivery is considered failed if the endpoint does not return a 2xx
status within 10 seconds. After 5 failures the webhook is marked `suspended` and
must be re-enabled manually.

Payloads are signed with HMAC-SHA256 using the webhook secret, in the
`Orbit-Signature` header.

## 7. Support and SLA

Starter includes community support only. Team includes email support with a
first-response target of 1 business day. Enterprise adds a 99.9% uptime SLA and a
4-hour response target for severity-1 incidents.

SLA credits are capped at 30% of the monthly invoice and must be claimed within
30 days of the incident.
