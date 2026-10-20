# TruthLens — Real-world provider benchmark, review batch 02

**Status:** Source-assessed by assistant, **PENDING independent reviewer approval**.
Date of preliminary checks: 20 October 2026.

This batch selects **six of the 26 currently PENDING cases** after the first
four Constitution / RA 9346 reference verdicts were independently confirmed
by the TruthLens project reviewer. No new cases are approved here, no inference
requests are executed, and no claim records or databases are modified.

The six are intentionally more challenging than the first four. Three are
written in Filipino; two examine whether supplied evidence is **insufficient**
rather than true or false; and two involve true factual premises mixed with
false or overgeneralized conclusions. These are constructed test statements,
**not identified real social-media posts**.

## Review checklist by case

### A. ELECTIONS — Filipino dates (2 cases)

Primary source: [COMELEC, 2022 National and Local Elections](https://www.comelec.gov.ph/?r=2022NLE).
Specific corroboration: [COMELEC, *Hakbang sa Pagboto*](https://www.comelec.gov.ph/?r=2022NLE%2FVoterEducation%2FHakbangsaPagboto).
The COMELEC information page describes May 9, 2022 as the election date,
consistent with Republic Act No. 7166's second-Monday-of-May schedule.
The voter education document specifically addresses the May 9 election.

1. `elections_2022_support` — "Itinakda ng COMELEC ang pambansa at lokal
   na halalan sa Pilipinas sa Mayo 9, 2022."
   - **Provisional FACT**: the official election date was May 9, 2022.
   - *Nuance*: election timing was legislated; the claim's "itinakda ng
     COMELEC" might imply COMELEC selected the date autonomously. Review
     wording against the legal and administrative distinction.

2. `elections_2022_contradict` — "Itinakda ng COMELEC ang pambansa at lokal
   na halalan sa Pilipinas sa Mayo 19, 2022."
   - **Provisional FAKE**: the official date was May 9, not May 19.
   - Apply the same "itinakda" wording caveat as in the support case.

Both are linked to **one underlying COMELEC election timetable**. They are
not independent evidence observations.

### B. HEALTH — dossier evidence is insufficient (1 case)

Primary source: [WHO Director-General opening remarks — March 11, 2020](https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing-on-covid-19---11-march-2020).

3. `health_source_insufficient` — "On March 11, 2020, every patient with
   COVID-19 worldwide received the same antiviral medication."
   - **Provisional UNVERIFIED from this dossier**: WHO's contemporaneous
     briefing discusses case counts, spread, the pandemic assessment and
     public-health response. It does **not** provide patient-level
     antiviral-treatment records.
   - *Meaning*: evidence supplied to TruthLens cannot establish or disprove
     the universal claim. It would be incorrect to treat this as an assertion
     that WHO globally confirmed all treatments to be identical.
   - *Corpus correction*: the original draft said WHO's "briefing reported"
     uniform medication; because the full speech did not report it, that
     changed the test into whether a document contains a statement. The
     corpus now states the underlying patient-treatment claim instead.

### C. DISASTERS — Filipino evidence insufficiency (1 case)

Primary source: [PAGASA extreme-weather seminar presentation](https://pubfiles.pagasa.dost.gov.ph/pressrelease/JPOW_Seminar_2016-Extreme_Wx_Events.pdf),
notably slide/page 4 (zero-indexed page 3), recording Typhoon
Yolanda/Haiyan on November 6–9, 2013, and slide/page 7 (zero-indexed page 6).

4. `ph_disaster_source_insufficient` — "Lahat ng pamilyang naapektuhan ng
   Yolanda ay nakatanggap ng eksaktong 20,000 piso sa loob ng 24 oras matapos
   ang bagyo."
   - **Provisional UNVERIFIED from this dossier**: the PAGASA source
     documents the storm but provides no household-level disbursement or aid
     data. Neither payment nor nonpayment to all households follows.
   - *Corpus correction*: "within 24 hours" now explicitly means after the
     typhoon, eliminating an unclear timeframe.
   - Reviewer should assess whether this deliberately irrelevant dossier
     is a fair test of appropriate abstention versus a weak retrieval result.

### D. TECHNOLOGY — mixed true/false context (1 case)

Primary source: [Apple's original iPhone introduction, Jan. 9, 2007](https://www.apple.com/uk/newsroom/2007/01/09Apple-Reinvents-the-Phone-with-iPhone/),
especially "Pricing & Availability".

5. `technology_iphone_contradict` — "Apple unveiled the iPhone in January
   2007 and it became available in US stores that same day."
   - Source agrees the iPhone was introduced January 9, 2007, **but**
     specified US availability starting **June 2007**.
   - **Provisional MISLEADING (DISPUTED)** because a genuine announcement
     is combined with a false same-day-sale claim.
   - **FAKE is also defensible** if TruthLens evaluates the compound claim
     as an explicit factual contradiction. Require deliberate reviewer
     adjudication, including explanation of our exact verdict taxonomy.
   - Do not automatically approve the draft MISLEADING label.

### E. ENVIRONMENT — mixed true/false context (1 case)

Primary source: [NOAA, *What is coral bleaching?*](https://oceanservice.noaa.gov/facts/coral_bleach.html).

6. `environment_coral_contradict` — "Warm ocean water can cause coral
   bleaching, so every coral that bleaches is already dead."
   - NOAA confirms warm water **can** trigger bleaching, but bleached
     corals are not necessarily dead and can sometimes recover.
   - **Provisional MISLEADING (DISPUTED)** because the cause is correct
     but the claimed invariable consequence is wrong.
   - **FAKE is also defensible** based on direct contradiction of the
     "every bleached coral is dead" assertion. Review taxonomy explicitly;
     consider a second reviewer if the boundary remains disputed.

## Approval boundaries

**No six-case labels are automatically approved.** A reviewer should inspect
the primary source, confirm the dossier fairly captures it, then approve,
revise, or reject EACH case's label. In particular, a missing statement is
not evidence that the underlying universal fact is false; a source about
weather is not an aid distribution register; and compound statements need
a consistent TruthLens rubric.

After approval, the JSON case `review` entries in
`api/tests/fixtures/realworld_verification_cases.json` can receive status
APPROVED, `approved_verdict`, `reviewer`, `reviewed_at`, a rationale
of at least 20 characters, and `source_checked: true`. The benchmark runner
must remain blind to both proposed and approved labels when constructing
the model prompt. Any still-unapproved cases are excluded from scored runs.

Suggested next gate: get independent approval for the two elections cases and
the two dossier-insufficiency cases first, and resolve the two ambiguous
MISLEADING/FAKE labels explicitly before including them in scoring. A 4-case
selection can be scored without approving the other two.

## Local verification after pulling this review packet

From `backend/truthlens_backend`:

```powershell
..\.venv\Scripts\python.exe .\manage.py test `
  api.tests.verification.test_realworld_verification_benchmark `
  api.tests.verification.test_cloudflare_provider_evaluation `
  --settings=truthlens_backend.test_settings `
  --keepdb

..\.venv\Scripts\python.exe .\manage.py evaluate_realworld_verification_providers
```

The dry-run approval counts should remain **4 approved, 26 pending**.
No network/inference calls are needed for this stage.
