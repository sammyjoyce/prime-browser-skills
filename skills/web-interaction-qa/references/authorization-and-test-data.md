# Authorization and test data

Use this before any run that changes state. It decides what the run may do, with which values,
and what happens to the data afterwards.

## Contents

1. Authorization record
2. Action classes
3. Test data rules
4. Production rules
5. Cleanup and leftover state

## Authorization record

Write these lines into the report header before the first write action:

```text
environment: <staging host or local app>, named safe to mutate by <user>
authorized actions: <exact list, for example create draft order, edit own profile name>
forbidden actions: <payments, emails, deletions, third-party calls, anything not listed>
test account: <account id or label>, supplied by <user>
data markers: <run id used in every created value>
cleanup: <who deletes the records and when>
```

An action outside the authorized list needs a new approval before it runs. Approval for one
action is not approval for its retry with different data, for a bulk repeat, or for a similar
action on another record.

## Action classes

| Class | Examples | Rule |
|---|---|---|
| read-only | open a page, read a list, read a record | allowed inside the approved environment |
| reversible write | create a draft, edit a test record, toggle a test setting | allowed when listed, with cleanup planned |
| hard-to-reverse write | delete, publish, send, pay, invite, change a permission | only with explicit written authorization naming the action |
| external side effect | email, SMS, webhook, payment provider, third-party API | treat as hard-to-reverse, and confirm the target is a test sandbox |
| unlisted | anything else | stop and ask |

Never submit a form to discover what it does. Read the form, state the expected effect, and ask.

## Test data rules

1. Use values the user approved, or generate values only when the user allowed generation.
2. Put a unique marker in every created value, such as `qa-<run-id>-<attempt>`. The marker is
   what makes a duplicate, a leftover, or a race outcome provable later.
3. Never use real customer names, real emails that reach people, or real payment details.
4. Keep credentials out of the task text. Sign in through the saved profile, or have the user run
   the headed login first.
5. Record the exact values used in the report, except secrets.
6. Use a new marker for each attempt so two attempts never share an identity.

## Production rules

- Default target is local or staging. Production is not a default, ever.
- On production, read-only checks may be allowed. A write needs written authorization naming the
  action, the record, and the time window.
- A protected production form with no authorization is Blocked. Report what the form appears to
  do from reading it, and stop.
- Never disable a guard, bypass a confirmation, or reuse a session token to get around a block.

## Cleanup and leftover state

1. Plan cleanup before the action, including who can delete the record.
2. Do not delete anything you did not create, and do not delete outside the approved list.
3. When cleanup is not authorized, list every record you created with its id and marker under
   `state left behind`.
4. A failed or timed-out run can still have written data. Read the store before you conclude
   anything, and report what you found.
5. Report cleanup status per record: done, pending, or not authorized.
