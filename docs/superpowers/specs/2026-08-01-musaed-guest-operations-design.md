# MUSAED Guest Operations Design

Date: 2026-08-01  
Owner approval: 2026-08-01

## Purpose

Make MUSAED reliable for early check-in and apartment-shopping conversations, then replace the Discord guest mood report with an evidence-based 0–10 guest-health score.

The system must use Hostaway facts for operational decisions. Claude may interpret guest language and draft natural replies, but it must not decide whether a night is occupied, quote unverified availability, or override a manager decision.

## Scope

This change covers:

- Early-check-in intent detection, availability checks, alternative-unit searches, manager approval, and guest replies.
- Apartment-search qualification, live matching, and direct verified suggestions.
- Off-hours wording and the configured end of the working day.
- The Discord `/guest` and `/guests` current-stay report.
- Dedicated Claude model selection and MUSAED evaluation cases.

It does not change booking modification, payment, cancellation, cleaning, pricing-write, or Hostaway reservation-write behavior.

## Design choice

Use deterministic decision functions around the existing Hostaway and Discord paths. Claude receives computed facts and writes the guest-facing language.

Two rejected alternatives:

1. A prompt-only patch would leave availability, escalation, and scoring vulnerable to inconsistent model output.
2. A separate MUSAED service would create a large deployment change inside a live single-process bot.

The selected approach keeps the change local to the current assistant flow while making every risky decision testable without network access.

## Early check-in

### Intent detection

Inspect the latest inbound guest message, not the entire conversation. Detect:

- Explicit early-entry language in Arabic and English.
- Requests that name a time before the official 3:00 PM check-in, such as `أقدر أدخل الساعة ١٢؟` and `Can I check in at noon?`.
- Common Arabic digit, English digit, AM/PM, noon, morning, and Saudi conversational variants.

The detector returns the requested time when available. A message about an old early-check-in request must not retrigger the flow.

### Hostaway facts

Build one early-check-in context from the reservation arrival date and listing:

- Requested arrival date and time.
- Previous calendar night state: `free`, `occupied`, `blocked`, or `unknown`.
- The reservation before arrival, when one exists.
- The reservation after the requested stay, when one exists.
- Alternative listings whose previous night and complete requested stay are available.

An empty or failed Hostaway response is `unknown`. It must not be converted to `occupied` or `free`.

Internal Discord cards may show the previous and next guests' names, reservation dates, and checkout/check-in timing. Guest-facing messages must never identify another guest.

### Decision flow

1. If the previous night is free, tell the guest the request appears possible but needs manager approval. Create a manager decision card.
2. If the previous night is occupied or blocked, do not promise early entry in the original unit. Search alternatives before mentioning another unit.
3. If verified alternatives exist, send the best one to three immediately. Include requirements matched, live stay total, average nightly price, and any honest difference. State that changing apartments requires manager approval.
4. If no verified alternative exists, explain that early check-in is unavailable and retain the official 3:00 PM check-in time.
5. If Hostaway facts are unknown, make no availability claim. Escalate for a manual check.
6. When a guest chooses an alternative, create the same manager decision card for that unit.

### Manager decision card

The card shows:

- Guest, current unit, proposed unit when applicable, stay dates, and requested time.
- Previous-night state.
- Previous and next reservation summaries.
- The exact guest message and the reply that will be sent.

Actions:

- `Approve early check-in`
- `Reject early check-in`

Approve opens a private confirmation showing the consequence. `Confirm and send` atomically records the decision, sends the prepared approval, closes the request, and disables both actions.

Reject first asks for a reason: previous guest, cleaning schedule, staff unavailable, requested time unavailable, or a custom reason. It then opens the same private confirmation. `Confirm rejection and send` records the reason, sends it to the guest, closes the request, and disables both actions.

Each decision uses the existing cross-process one-time lock and outbound-message deduplication. A second click reports who already decided and sends nothing.

## Apartment-search qualification

Recognize broad shopping language, including generic messages such as `أبي شقة اليوم`, `أبحث عن سكن بالرياض`, and `I need an apartment tonight`.

Extract requirements from the full conversation:

- Check-in and check-out dates.
- Number of guests.
- Bedrooms.
- Preferred area or an explicit no preference.
- Nightly budget.
- Must-have features or an explicit none.

Ask for every missing requirement in one short message. Do not repeat answered questions. When all requirements are known, search Hostaway and send the best one to three verified matches directly.

Each result includes:

- Apartment name and Airbnb link when available.
- Live availability for the complete stay.
- Total stay price and average nightly price before tax and platform fees.
- Requirements matched.
- The closest honest difference when no exact match exists.

Never show an unavailable listing as a result. If the live lookup fails, apologize and escalate instead of sending catalog or starting-price data as if it were live.

## Off-hours

Working hours become 11:00 AM through 12:00 midnight in the Riyadh timezone.

MUSAED continues answering questions supported by verified facts. When a question requires a manager or employee, it:

- Apologizes that the team is outside working hours.
- States that the team returns at 11:00 AM.
- Preserves and escalates the request for the next shift.
- Avoids repeating the same holding message for the same unresolved topic.

## Guest score commands

Keep `/guests` and add `/guest` as an equivalent slash command. Existing text-command aliases remain intact.

Analyze every current in-house guest across the entire current-stay conversation. Recent and unresolved evidence receives the most weight.

### Score

Start at 10 and apply non-overlapping deductions based on:

- Open complaint or access failure.
- Upset or sarcastic language.
- Repeated unanswered request.
- Open promise.
- Open escalation.
- Slow or missing team response.
- A resolved issue that still affected the stay.

Objective facts constrain the model result:

- An open severe complaint cannot score above 3.
- An open promise or escalation cannot score above 6.
- A neutral logistics question alone causes no deduction.
- A resolved issue may recover but cannot be displayed as a perfect stay without clear positive evidence afterward.

The analyzer returns the score, a short Arabic reason, supporting guest quote when available, issue status, and confidence. Unknown or failed analysis is labelled as insufficient evidence rather than silently scored as normal.

### Discord output

- Sort lowest scores first.
- Show total guests and score bands.
- A 10/10 guest gets one compact roster line.
- Every score below 10 shows the reason, evidence, resolved/open state, last team responder, and WhatsApp link when available.
- Keep the current Arabic-first operational tone and fit Discord message limits through the existing long-message channel path.

## Model routing

Add dedicated settings without changing models used by unrelated systems:

- `GUEST_DRAFT_MODEL`, default `claude-sonnet-5`.
- `GUEST_ANALYSIS_MODEL`, default `claude-sonnet-5`.

Short JSON and guest-message calls disable adaptive thinking and use response limits large enough for Sonnet 5's tokenizer. Existing Haiku and Sonnet 4.6 defaults remain for unrelated background work.

The existing MUSAED evaluation harness will receive cases for time-based early-check-in wording, current-unit availability, alternative offers, apartment qualification, off-hours escalation, privacy, and non-repetition.

## Failure handling

- Hostaway unknown: escalate, make no availability statement.
- Anthropic failure: keep the request pending for a human; do not send an empty or guessed reply.
- Discord restart: persistent custom IDs resolve the stored decision when possible; an unrecoverable old card explains that it needs manual handling.
- Double click or overlapping bot copies: only the first atomic decision may send.
- Rate limits: reuse the existing availability cache and bounded parallel lookups.

## Testing

Write failing tests before production changes for:

- Natural early-check-in time phrases and latest-message scoping.
- Free, occupied, blocked, and unknown previous-night states.
- Privacy-safe guest replies and detailed internal summaries.
- Approve and reject confirmation, rejection reasons, and duplicate-decision suppression.
- Alternative search eligibility and ranking.
- Qualification completeness, no repeated questions, direct verified results, and API failure.
- Midnight work cutoff and the 11:00 AM return message.
- Guest-score deductions, caps, sorting, insufficient evidence, and rendering.
- Sonnet 5 request payload behavior.

Run the repository's complete verification routine before committing implementation and pushing to GitHub.

## Files

- `bot.py`: decision logic, Hostaway context, Discord views, commands, off-hours, and model routing.
- `golden_set.seed.jsonl`: corrected and expanded MUSAED behavior cases.
- `tests/test_musaed_early_checkin.py`: early-check-in and decision-flow tests.
- `tests/test_musaed_apartment_search.py`: qualification and verified-match tests.
- `tests/test_ops_commands_render.py`: 0–10 guest-score rendering tests.
- `tests/test_guest_score.py`: scoring and objective-cap tests.
- `docs/superpowers/specs/2026-08-01-musaed-guest-operations-design.md`: this specification.
- `docs/superpowers/plans/2026-08-01-musaed-guest-operations.md`: implementation plan.
