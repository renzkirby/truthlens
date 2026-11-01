# URL Safety and Evidence Source Previews

**Status:** implementation branch `feat/url-safety-evidence-previews`

## Goal

Improve the safety and usability of Community evidence URLs without turning source-preview generation into a blocking part of evidence submission.

TruthLens distinguishes three different concerns:

1. whether a submitted value is an acceptable public HTTP(S) URL;
2. whether an external reputation provider reports a known threat;
3. whether the TruthLens backend may safely connect to the URL to extract bounded preview metadata.

These checks are related but are not equivalent. A successful reputation lookup is not a guarantee that a website is safe, and a successful metadata fetch is not evidence that the source is trustworthy or factually correct.

## Submission latency contract

Evidence submission keeps the existing synchronous reputation lookup and database validation. Preview generation is never required before the evidence row is committed.

The flow is:

```text
submit evidence
  -> validate URL syntax/policy
  -> external threat-reputation lookup
  -> persist evidence + safety snapshot
  -> commit transaction
  -> enqueue preview task
  -> return normal evidence response

background
  -> resolve DNS
  -> enforce public-network policy
  -> pinned HTTP(S) fetch
  -> revalidate redirects
  -> extract bounded HTML metadata
  -> persist preview result
```

A slow, unavailable, unsupported, or blocked preview target does not delete the evidence submission.

## User-facing reputation states

Persisted evidence uses:

- `NO_KNOWN_THREATS`: the configured reputation provider returned no known match at check time;
- `KNOWN_THREAT`: the provider reported a known threat and submission is rejected;
- `CHECK_UNAVAILABLE`: the reputation lookup could not be completed; this is neutral and must never be rendered as safe;
- `NOT_CHECKED`: no persisted check exists, primarily for historical evidence.

The UI uses **“No known threats detected”**, not “Safe”. This is deliberately a snapshot claim, not a security guarantee.

## Preview states

- `NOT_REQUESTED`: no preview attempt exists;
- `PENDING`: the evidence committed and preview work is queued;
- `READY`: bounded title/description/site metadata was extracted;
- `UNAVAILABLE`: preview generation failed for a non-policy reason; the original source remains preserved;
- `BLOCKED`: the target violated the network safety policy or is associated with a known threat; the UI does not offer direct opening.

Historical evidence is not network-backfilled by the migration.

## Server-side fetch policy

The preview fetcher does not use an iframe, browser engine, JavaScript, cookies, credentials, subresource loading, or ambient HTTP proxy configuration.

For each URL and every redirect hop it:

- accepts only HTTP on port 80 and HTTPS on port 443;
- rejects credentials in URLs;
- rejects localhost/private naming patterns;
- resolves the hostname itself;
- rejects the destination if any returned address is not globally routable;
- pins the outbound socket to one already-validated address;
- validates HTTPS certificates and SNI against the original hostname;
- handles redirects manually and repeats URL/DNS/network checks for every hop;
- allows at most two redirects;
- limits connect and read timeouts;
- reads at most 256 KiB;
- accepts only HTML/XHTML metadata responses;
- extracts only title, description, and site-name metadata.

The original evidence URL remains the cited source identity. Redirect destinations may be retained as preview metadata but do not replace the submitted source URL.

## DNS rebinding boundary

Validation followed by an ordinary `requests.get(user_url)` would permit a second DNS lookup after validation. The preview fetcher avoids that pattern: it resolves and validates the hostname, then connects directly to the validated socket address while retaining the original hostname for the HTTP Host header and TLS certificate/SNI verification.

DNS resolution itself is performed by the host resolver and therefore remains subject to operating-system resolver behavior. Preview work is asynchronous and bounded by the Celery task time limit.

## URL fidelity

Evidence sources preserve their original query-string ordering and encoding, minus URL fragments. This avoids breaking signed or order-sensitive evidence URLs.

The general URL-verification flow may continue to remove known tracking parameters for claim normalization. Evidence citation and preview fetching deliberately opt out of that cleanup.

## Operational behavior

Preview tasks currently use the default Celery queue. This keeps deployment simple for the defense-period production topology. Because production currently runs a single verification worker, preview work is aggressively bounded and does not retry. A future runtime-capacity phase may place preview/enrichment work on a separate low-priority queue after concurrency testing.

## Trust boundary

A source preview is presentation metadata only. It does not:

- verify the factual claim;
- establish source credibility;
- count as additional evidence;
- change evidence-review status;
- change adjudication readiness;
- replace the Partner Organization's professional evidence assessment.

Partner Organization reviewers still decide source suitability in the Verification Workspace.
