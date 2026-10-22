# PARTNER-GOV-1 — Final 32-reference Cloudflare accuracy capture

**Phase: PREPARATION AND DRY RUN ONLY.** The user explicitly
approved preparing this final 32-case accuracy evaluation, with a
separate confirmation required after the dry run for any real provider
requests. That second live authorization has **NOT** been given.

No Cloudflare calls, Gemini/Groq fallback, ORM writes, Celery
scheduling, Partner Organization permission changes or production
deployment are performed by the preparatory commands.

## Why this differs from the closed Cloudflare implementation tests

The development integration and targeted routing regressions have
already passed. This packet evaluates the **quality of real AI subject
decisions**, not the Cloudflare provider token-budget performance.
Thirty-two separate synthetic reference claims span all twelve
subjects, cross-domain traps, ambiguous/weak claims, geography,
contradictory statements, prompt injections and out-of-scope cases.
Human approval was user-and-co-dev reported; it does **not** imply
independently authenticated reviewers or representative real-claim
accuracy.

Cloudflare-02 and Cloudflare-03 packets remain permanently locked.
The unrelated 16-trial paired token-budget design remains optional,
not a prerequisite for this accuracy assessment. Prior Cloudflare-03's
single exact-match classification is **excluded** from scoring the
new 32-case capture.

## Fixed evaluation profile

| Setting | Pinned value |
| --- | --- |
| Profile | `gemma4_approved_32_accuracy_v1` |
| Provider/model | Direct Cloudflare / `@cf/google/gemma-4-26b-a4b-it` |
| Case count | Exactly 32 previously human-approved synthetic cases |
| Per-case completion limit | 4096 tokens |
| Timeouts | 3-second connection / 45-second read inactivity |
| Request mode | JSON object, temperature 0.1, streaming false |
| Capacity behavior | `rejectIfBusy=true` |
| Max requests | At most 32 (one per listed case, no retry) |
| Failure handling | Stop after first provider failure or invalid contract |
| Fallback | None |
| Enforcement authority | None |

The completion-token limit is **per call**, not a total quota or
financial spend cap. The HTTP read timeout is not a wall-clock cap.
A failed or incomplete capture cannot be replayed automatically or
resumed using the locked packet. If a failure stops the study before
all 32, the missing cases remain unobserved; the scorer cannot report
a complete-corpus accuracy rate.

Reference provenance fingerprint:
`40974b32aa0d7a32ec201f85bc703c14650c3c34d5bae9dbd01bb83ac53bb6af`

Production classification prompt fingerprint:
`abaf4338206d8a1857c3d682ff6dd971a775f7be45f0b425e8d45d9243756067`

All reference labels and reviewer details remain outside the private
request packet. The source corpus itself must be kept private.

## User-local offline acceptance (PowerShell)

After bringing the CLEAN branch
`feat/ai-rq2-provider-hierarchy` up to date, from
`backend\truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_cloudflare_classification_accuracy_capture `
  api.tests.verification.test_cloudflare_classification_diagnostic `
  api.tests.verification.test_cloudflare_classification_capture `
  api.tests.verification.test_classification_quality_audit `
  api.tests.verification.test_investigation_classifier `
  api.tests.verification.test_ai_rq2_classification_fallback `
  --settings=truthlens_backend.test_settings --keepdb

..\.venv\Scripts\python.exe .\manage.py check
..\.venv\Scripts\python.exe .\manage.py makemigrations --check --dry-run
```

The new offline capture module contains **15 additional mocked
regression tests** for manifest pinning, previous packet reuse
prevention, private export, dry-run/no-network behavior, development
gates, no fallback/retries, failure-stop, simulated 32-response score,
reasoning usage sanitization, and production denial. An isolated
test database may be used by pre-existing Django TestCase tests.
No *live* Cloudflare requests are performed by these tests.

## Prepare one new private package (NO NETWORK)

```powershell
$corpus = "$env:USERPROFILE\Downloads\PARTNER_GOV1_Approved_Reference_Corpus_2026_10_22.json"
$packet32 = "$env:USERPROFILE\Documents\TL-Private-Classification-Accuracy-32-01"

..\.venv\Scripts\python.exe .\manage.py prepare_cloudflare_classification_accuracy `
  --corpus "$corpus" `
  --export-dir "$packet32" `
  --json-summary
```

Expected: `planned_requests=32`,
`max_completion_tokens=4096`, `private_package_created=true`,
`provider_calls=0`, `db_writes=0`,
`enforcement_approved=false`, `live_authorized=false`.
The folder must be **new and outside Git**. It includes
`capture_inputs.json` (all 32 exact claim inputs, no reference
labels), `predictions.json` (empty), and a privacy README.
Do not overwrite, reuse or rename any previous Cloudflare packet.

## Validate new packet (READ ONLY / NO NETWORK)

```powershell
..\.venv\Scripts\python.exe .\manage.py capture_cloudflare_classification_accuracy `
  --corpus "$corpus" `
  --packet-dir "$packet32" `
  --json-summary
```

Expected `status=DRY_RUN_READY_NO_PROVIDER_CALLS`,
32 case IDs, matching corpus+prompt hashes, 4096 token allowance,
45-second read-inactivity timeout, no fallback/retry, zero provider
calls and `live_authorized=false`. A dry run creates no lock or
prediction records, and performs no model inference.

The command also implements a future **explicitly gated live mode**,
but **do not use `--execute-live` or any live flags in this phase**.
This approval was only for preparation. Obtain a new, explicit
authorization naming the maximum 32 direct requests and potential
Cloudflare quota/charges after the user inspects the preflight output.

On later separately approved execution, the private packet permanently
locks before network use and captures complete raw outputs
(`cloudflare_accuracy_raw_responses.json`), scoreable original
prediction strings (`cloudflare_accuracy_predictions.json`), and
sanitized attempt/usage metadata
(`cloudflare_accuracy_attempts.json`). Store all three privately.
Never delete the permanent lock, replay the packet, or publish
private claims/reasoning/credentials. The adapter intentionally
captures only visible model message.content, never private reasoning.

## Real-data scoring, after separately approved execution

```powershell
..\.venv\Scripts\python.exe .\manage.py audit_investigation_classification `
  --corpus "$corpus" `
  --predictions "$packet32\cloudflare_accuracy_predictions.json" `
  --json-summary
```

The existing strict scorer reports exact subject/ABSTAIN matches,
wrong domains, invalid responses or quote mismatches, missing cases,
overclassification, missed classifications, possible authorization
leaks/exclusions and complete-corpus accuracy only when all approved
cases have results. It is a **descriptive audit** and cannot approve
`INVESTIGATION_CLASSIFICATION_MODE=enforce`.

Even 32/32 perfect *synthetic* responses cannot independently prove
safe performance on held-out real claims. Before changing from
`off` or `shadow` to `enforce`, the team must separately agree on
accuracy/risk criteria and real-world validation. Until then PR/merge
remains on hold at the user's request, and production rollout is
not authorized.
