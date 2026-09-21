---
name: web-qa
description: Report-only browser QA for a running web app. Routes a QA request to smoke, acceptance, regression, exploratory, visual, accessibility, or UI-to-backend checking, runs the smoke pass itself, and returns an evidence-backed report with per-check status and coverage. Use when asked to QA a web build, verify a page against a spec or ticket, check a local or staging site before a release, or produce pass/fail evidence for a web UI. Does not fix code, file issues, or commit.
compatibility: Prime Agent with the browser-use Python skill (await browser_use.run), Chrome or Chromium, and an approved local, staging, or explicitly authorized target.
---

# Web QA

Check a running web app against a named reference and report what the evidence shows.
This skill reports only. It does not edit application code, file issues, or commit.

## Open when you need

| Open when you need to... | Read |
|---|---|
| write the report, assign a check status, count coverage, or track the budget | `references/evidence-contract.md` |
| write the browser task, output schema, ready condition, extra captures, or handle a run error | `references/browser-task-recipes.md` |

## Step 1: preflight

Fill the report header from what the request already gives you. Ask only for a gap that blocks
the requested work, and put every gap in one message.

| Item | Accept | When the request does not say |
|---|---|---|
| Target | one base URL that is local, staging, or explicitly authorized | ask, this is the one gap that blocks every run |
| Build | build id, commit, or version | record `build unknown` and continue |
| Profile, viewport, theme | named profile, pixel viewport, named theme | choose a reproducible default, announce it, and record it: profile `web-qa`, 1280x800, the app's default theme |
| Reference | named spec, ticket, design, requirement, or accepted prior behavior, with a version or date | ask only when the request wants acceptance against it; otherwise report observations and mark acceptance checks `Unknown` |
| Authority | read-only, or named test accounts and test data you may change | stay read-only and mark data-changing checks `Blocked`; ask only when the requested scope needs a write |
| Access | saved login profile, backend or log readback, instrumentation | mark the checks that need it `Blocked` and run the rest |
| Budget | minutes, calls, total steps, aggregate USD cap | announce the default below, record it, and start |
| Platform | desktop web or mobile web viewport | native iOS or Android is `Blocked`; this suite drives Chrome only |

A missing build id, viewport, theme, or budget confirmation never blocks a browser check. A
missing target URL does, and so does missing authority for a write the user asked for.

Default budget, announced rather than negotiated: 20 minutes, 6 browser calls, 150 steps in
total, and 3.00 USD in total, with `max_steps=25`, `timeout_ms=180_000`, and `max_cost_usd=0.5`
on each call. Set each call's limits to the smaller of the per-call default and what remains.
Stop when the remainder cannot cover another safe call. Do not extend a budget silently.

Production targets: read-only navigation, only with explicit user approval in this session.
Never submit a form, place an order, or send a message there.

## Step 2: route

Classify the request, then use the matching row. The default route is the smoke pass.

| Request | Route | Fallback when that skill is unavailable |
|---|---|---|
| "QA this build", pre-release check, unclear scope | smoke pass in step 3 (default) | none needed |
| find unknown defects, open-ended exploration, "try to break it" | `web-dogfood` | run the smoke pass, then one bounded exploration charter inside this budget; mark wider exploration `Not run` |
| compare against a design or other named visual reference, responsive or theme checks | `web-visual-qa` | capture the named states and report measured observations only; mark visual acceptance `Not run` |
| keyboard, screen-reader, accessible-name, reading-order, or contrast audit | `web-accessibility-qa` | report only the DOM and AX facts you captured; mark conformance `Not run` |
| saved state, retries, duplicate submits, races, partial failure | `web-interaction-qa` | report only what an independent readback proves; otherwise `Unknown` |
| file issues or tickets from findings | the separate `qa` skill, after this report | say so; this skill never files |
| re-check an earlier defect, or confirm a fix | smoke pass limited to the named requirements, with the regression rules in `references/evidence-contract.md` | none needed |

Misroute recovery: if the selected route cannot be evidenced inside the budget, stop it, mark
its scope `Not run`, and say so. Never swap in an easier scope and present it as the requested one.

## Step 3: smoke pass

1. Write the check list first. Each check needs an id, the expected result with its source and
   version, a page-ready condition, and the evidence that would settle it.
2. Group checks into one browser run per user-visible flow. Keep a before-and-after comparison
   inside a single run, because each `browser_use.run` call starts a new Chrome and loses open
   tabs and unsaved page state.
3. Run the group, passing the concrete task, schema, limits, and prohibitions in the same call.
   See `references/browser-task-recipes.md`.
4. After each call, write down `steps`, `cost`, elapsed minutes, and the returned paths, then
   update the remaining minutes, calls, steps, and dollars in the ledger.
5. Check that each evidence file exists on disk. A path in a result is not proof of a file.
6. Before stating any visual fact, load the image with `attach_image` and look at it. A child
   agent sends absolute paths to its parent, which calls `attach_image`.
7. Attempt a failing check three times in total, counting the first observation. Write each
   attempt to its own evidence path and never overwrite a failing capture with a later passing
   one. A later pass does not delete an earlier failure. Report it as intermittent with its count.
8. Write the report with `references/evidence-contract.md`.

Stop early and report when the remaining budget cannot cover another safe call, authority or
access is missing, the scope is unsafe, or the environment fails in a way you cannot work around.

## Step 4: call the browser

The browser model defaults to exactly `openai/gpt-6-astra`, and `BROWSER_USE_MODEL` can override
it, so record the model the result reports rather than the assumed default. `run` has no model
parameter, and no follow-up, pause, resize, or download option.

```python
result = await browser_use.run(
    "Open http://localhost:3000/pricing in the given profile. "
    "Wait until the plan cards are visible and the monthly price text is not the word Loading. "
    "Report the heading text, every plan name in order, and each plan's monthly price. "
    "Do not sign in, do not submit any form, and do not change any data.",
    schema={
        "type": "object",
        "properties": {
            "heading": {"type": "string"},
            "plans": {"type": "array", "items": {"type": "string"}},
            "prices": {"type": "array", "items": {"type": "string"}},
            "ready_condition_met": {"type": "boolean"},
        },
        "required": ["heading", "plans", "prices", "ready_condition_met"],
        "additionalProperties": False,
    },
    profile="web-qa",
    max_steps=25,
    timeout_ms=180_000,
    max_cost_usd=0.5,
)
print(result["status"], result["steps"], result["cost"], result.get("model"))
print(result["screenshot_path"], result["artifact_dir"])
```

Every non-completed status raises `browser_use.BrowserUseError`. Catch it, record
`error.status` and `error.message`, and keep `error.result` as partial evidence. Keep every
check that was already evidenced in this run or an earlier one at the status its evidence
supports. Mark a check with insufficient evidence `Unknown`, and mark a check that never ran
because the flow stopped `Blocked`, naming the blocker. A harness timeout or a step-cap stop is
not by itself a product failure. Do not repeat a task that may have already submitted a form or
changed data.

A restriction in task text is an instruction to the browser model, not a sandbox, and that model
can run host JavaScript with filesystem and network access. Use approved environments and test
accounts. Never put a credential in task text. Have the user run `browser_use.login` for a real
account, then verify the signed-in state with a read-only run.

## Step 5: report

Follow `references/evidence-contract.md`. Four rules decide the verdict.

1. `Fail` if any required check failed.
2. `Incomplete` if no required check failed but any required check is `Unknown`, `Blocked`, or `Not run`.
3. `Pass for the stated scope` only when every required check passed with evidence.
4. Never average check results, and never report a readiness score or percentage as a verdict.

## Prohibitions

- Do not edit application code, revert changes, create branches, commit, or file issues.
- Do not create, modify, or delete data outside the authorized test data.
- Do not call a finding a defect without a named source that states the expected behavior, and
  do not invent a `Fail` for a requirement the reference never states. That is out of scope.
- Do not pass a check on empty evidence, a default value, or a helper's success flag. Missing
  evidence is `Unknown` or `Not run`.
- Do not label anything fixed or regressed without re-checking the same requirement and state
  with new evidence. An uncovered or unrepeated check is `Unknown`.
- Do not report a screenshot you have not viewed, or a file you have not confirmed exists.
- Do not drop an intermittent observation because a later attempt passed.
- Do not claim native iOS or Android coverage from a browser viewport.
