# Evidence examples

Templates for one persistence and duplicate-submit cycle. Values inside angle brackets are
placeholders. Only real run output belongs in a report.

## Contents

1. Check rows
2. Task text
3. Output schema
4. Result handling after the run
5. Readback step
6. Report rows
7. Anti-pattern and correction

## Check rows

| Check | Action | Approved data | Expected stored result | Readback channel |
|---|---|---|---|---|
| create saves | submit the new-contact form once | name `qa-<run-id>-a1`, email `qa-<run-id>-a1@example.invalid` | one contact row with those values | `<user-supplied query>` |
| survives session | reload in a fresh session | same marker | the contact is visible to a clean session | second browser run |
| double submit | click submit twice quickly | name `qa-<run-id>-a2` | one row, or a rejected second request | count plus request log |

## Task text

```text
Open <https://staging.example.test/contacts> using the saved interaction-qa profile.
1. Wait until table#contacts is visible. Report the current row count and the ids of any row
   whose name starts with qa-<run-id>.
2. Install request instrumentation before acting: wrap window.fetch and
   XMLHttpRequest.prototype.send to record method, URL path, request id or idempotency headers,
   and a timestamp for each call. Report the install time.
3. Open the new-contact form. Enter name qa-<run-id>-a2 and email
   qa-<run-id>-a2@example.invalid. Do not enter any other data.
4. Click the submit control twice within 300 ms, without waiting for the first response.
5. Wait until either a success state or an error state is visible. Report the visible text.
6. Report every recorded request, the row count now, and the ids and names of rows matching
   qa-<run-id>.
7. Capture a PNG of the final list with page.cdp('Page.captureScreenshot', {format:'png'}),
   write it to /abs/evidence/<run-id>/contacts-after-double-submit.png, and return the path.
8. Do not delete anything, do not edit other rows, and do not visit any other page.
```

## Output schema

```python
output_schema = {
    "type": "object",
    "properties": {
        "ready_condition_met": {"type": "boolean"},
        "rows_before": {"type": "integer"},
        "rows_after": {"type": "integer"},
        "matching_records": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                },
                "required": ["id", "name"],
                "additionalProperties": False,
            },
        },
        "requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "path": {"type": "string"},
                    "request_id_header": {"type": "string"},
                    "timestamp_ms": {"type": "number"},
                    "status": {"type": "integer"},
                },
                "required": ["method", "path", "timestamp_ms"],
                "additionalProperties": False,
            },
        },
        "instrumentation_installed_ms": {"type": "number"},
        "visible_result_text": {"type": "string"},
        "captures": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["ready_condition_met", "rows_before", "rows_after", "matching_records",
                 "requests", "instrumentation_installed_ms", "captures"],
    "additionalProperties": False,
}
```

## Result handling after the run

```python
from pathlib import Path

out = result["output"]
created = [r for r in out["matching_records"] if r["name"] == f"qa-{run_id}-a2"]
posts = [r for r in out["requests"] if r["method"] == "POST" and r["path"].endswith("/contacts")]
delta = out["rows_after"] - out["rows_before"]

missing_captures = [p for p in out["captures"]
                    if not (Path(p).is_file() and Path(p).stat().st_size > 0)]
for path in out["captures"]:
    if path not in missing_captures:
        print(await attach_image(path))      # required before describing any capture
```

Reading of the numbers:

| Observed | Status before readback |
|---|---|
| `len(posts) == 2` and `delta == 1` and one created record | duplicate submit handled at the server, still needs the store readback |
| `len(posts) == 2` and `delta == 2` | Fail, duplicate record created |
| `len(posts) == 1` | the client blocked the second click, record which control state did it |
| `out["requests"]` empty | instrumentation missed the calls, mark the duplicate check Unknown |
| run raised `BrowserUseError` | state unknown, read the store before any retry |

## Readback step

```python
# Authoritative readback runs through the channel the user authorized, outside the browser.
# Example shape only; use the user's exact command.
readback = await bash(f"<user-approved query command> --filter name=qa-{run_id}-a2")
```

Record the command, its output, the timestamp, and the fields compared. A second browser run that
reloads the page is a fresh-session readback, and the report must label it as such rather than as
the store.

## Report rows

```text
Header
  scope: contacts create flow, staging
  authorization: <user message id or ticket>, actions: create contact, read contacts
  environment: <https://staging.example.test>  profile: interaction-qa
  model actually used: <value of result["model"]>
  data markers: qa-<run-id>-a1, qa-<run-id>-a2
  evidence: /abs/evidence/<run-id>/   budget: 3 of 5 browser calls, $0.21 of $1.00

Checks
  | check | expected | observed | readback | status |
  | create saves | 1 row with marker a1 | 1 row, fields match | store query 12:04:11Z | Pass |
  | survives session | visible to a clean session | visible | second run, fresh profile | Pass |
  | double submit | 1 row for marker a2 | 2 POSTs, 2 rows | store query 12:06:02Z | Fail |
  | retry after failure | 1 row | not attempted, budget stopped | none | Blocked |
  | concurrent edit | documented conflict rule | no rule supplied | none | Unknown |

Findings
  I1 double submit creates two contacts
     expected source: <spec section 5.1, "submit is idempotent per form session">
     actual: POST /api/contacts at 12:05:58.120Z and 12:05:58.341Z, no request id header,
             rows 41 to 43, store query returned ids <c_8821> and <c_8822>
     severity: high   confidence: high   attempts: 2 of 2 reproduced
     evidence: /abs/evidence/<run-id>/contacts-after-double-submit.png (attached)

State left behind
  created: <c_8820> qa-<run-id>-a1, <c_8821> and <c_8822> qa-<run-id>-a2
  cleanup: pending, deletion not authorized

Coverage
  planned 6, tested 3, failed 1, unknown 1, blocked 1, not run 1
```

## Anti-pattern and correction

Wrong:

```text
Submitted the form and saw "Contact saved". Retried twice, no errors. Persistence works.
Cleaned up afterwards.
```

Problems: persistence claimed from a toast, no record id, no counts, no readback channel, retries
with no attempt record, and a cleanup claim with no ids.

Corrected:

```text
create saves: submitted once with marker qa-<run-id>-a1. UI showed "Contact saved".
  Store query at 12:04:11Z returned id <c_8820> with matching name and email. Pass.
double submit: 2 POSTs recorded, row count 41 to 43, store query returned 2 ids. Fail.
retry after failure: Blocked, budget stopped after 3 browser calls.
State left behind: 3 records listed with ids, cleanup pending, deletion not authorized.
```
