# Privacy Classifier Eval Fixtures — ADR-0008 §15

Frozen test set for `tools/privacy_classifier.py` (proposed in ADR-0008, NOT YET IMPLEMENTED).

## Coverage target

| Class      | Count target | Purpose                                    |
|------------|--------------|--------------------------------------------|
| public     | 50           | Catch false positives — public stays public |
| private    | 50           | PII shapes, financial sub-thresholds       |
| sensitive  | 50           | Faith / family / kid-named / health        |
| edge-case  | 50           | Mixed signals, scripture refs, allow-list  |
| **Total**  | **200**      |                                            |

**Acceptance:** ≥ 95% precision AND ≥ 95% recall on every class. Weekly cron runs the full suite and PAGEs on drift > 5% WoW.

## Fixture format

Each fixture is a single JSON file with this shape:

```json
{
  "id": "F-XXXX",
  "class": "public | private | sensitive",
  "category": "area-tag | kid-name | family-name | biomarker | faith-term | financial | pii-email | scripture-ref | edge-case",
  "payload": {
    "text": "...",
    "fields": {"area": "faith"}
  },
  "hints": {
    "caller_asserted_class": null
  },
  "expected_reasons": ["area:faith"],
  "expected_egress": {
    "to_lxc": "allow",
    "to_desktop": "allow",
    "to_vps": "hard_deny",
    "to_broker": "hard_deny",
    "to_openrouter": "hard_deny"
  },
  "notes": "Standard area-tag sensitive — matches tier 2 rule area-faith."
}
```

## Naming

Files: `F-<NNNN>-<short-slug>.json` where:
- `0001-0050` = public
- `0051-0100` = private
- `0101-0150` = sensitive
- `0151-0200` = edge-case

## How to run (once classifier ships)

```bash
set -a && source .env && set +a
python3 -m pytest tests/test_privacy_classifier_eval.py -v
# OR for the eval-suite specifically:
python3 evals/run_eval.py --suite comms_privacy
```

## What to add when contributing a fixture

1. Real-world-ish payload (sanitized — fake names where applicable).
2. The expected class — pre-decided, not "let the classifier decide and pin that".
3. Every rule_id that should fire (multi-tier matches stack).
4. Egress policy expectation per peer.
5. Notes explaining why this fixture exists (which bug class it guards).

## Anti-patterns

- ❌ Fixtures lifted from real-life faith/family/health content — even sanitized, this corrupts the eval set's neutrality.
- ❌ Adversarial prompt-injection strings that try to coerce the classifier into outputting `public`. These belong in `evals/comms_privacy_redteam/` (separate suite).
- ❌ Locale-specific patterns (US-shape phone numbers as the only test) — add international variants.

## Update cadence

The fixture set is a frozen test contract. Adding fixtures = grow the suite. Changing expected values on an existing fixture = bug or rule change → audit trail required (commit msg references ADR or rule version).
