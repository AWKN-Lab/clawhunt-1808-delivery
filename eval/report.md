# Eval report (#1808 task 1/5)

- generated_at: `2026-11-07T04:56:50.455646+00:00`
- duration_s: `52.52`
- mode: sqlite + mock LLM (no network)
- kb_docs/kb_chunks: `9/27`
- conclusion: **PASS**

## Dataset

| split | cases |
|---|---|
| booking | 210 |
| policy | 45 |
| negative | 30 |
| injection | 15 |
| total | 300 |
| policy_topics | 9 |

## Metrics

| metric | value | threshold | gate |
|---|---|---|---|
| extraction_accuracy | 1.0 | 0.95 | PASS |
| qa_accuracy | 1.0 | 0.9 | PASS |
| violations | 0 | 0 | PASS |
| injection_blocked | 15/15 | 15/15 | PASS |
| minor_immediate | 8/8 | 8/8 | PASS |
| pii_in_model_requests | 0 | 0 | PASS |
| negative_pass_rate | 1.0 | - | - |
| minor_immediate | 8/8 | - | - |
| injection_blocked | 15/15 | - | - |
| pii_in_model_requests | 0 | 0 | PASS |

## Failures (first 5 per split)

- booking: none
- policy: none
- negative: none
- injection: none
