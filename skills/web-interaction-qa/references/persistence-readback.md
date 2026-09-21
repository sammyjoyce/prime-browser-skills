# Persistence readback

Use this to prove, or refuse to claim, that an action changed stored state.

## Contents

1. Channel table
2. Identity and counts
3. Unknown against Blocked
4. Cache and replica traps
5. Recording the channel

## Channel table

Ranked by what they prove. Use the strongest channel the user made available.

| Channel | How it runs | Proves | Limits |
|---|---|---|---|
| authoritative store query | a command or query the user supplies and authorizes, run outside the browser | the row or document exists with those values | needs credentials and a user-approved command |
| service API read | a read endpoint called through a channel the user approved | the service returns the stored value | may read a cache or a replica |
| admin or second-user view | a separate browser run signed in with an approved account | the value is visible to another viewer | still a UI, and it can hide fields |
| fresh-session reload | a second browser run with a clean start that opens the record | the value survived the session and the client cache | not the store itself |
| in-page client state | reading the app store inside the same run | client state only | not persistence evidence |
| success toast or redirect | observed in the same run | the client rendered a result | proves nothing about storage |

A persistence claim needs one of the top four channels. The bottom two never carry it.

## Proof boundaries

Name the boundary each claim reaches. These are different claims, and one of them does not imply
the next:

| Boundary | Claim it supports |
|---|---|
| browser behavior | the client rendered a state |
| request sent | the client sent a request with these fields |
| request completed | the server answered with this status |
| durable write | the store holds the record now |
| async work finished | a queue, job, or worker completed its part |
| final reconciliation | the UI shows what the store holds after a fresh read |

Write the boundary beside every persistence row. "It saved" with no boundary is not a result.

## Identity and counts

Return all of these from the flow, then compare them after the readback:

| Item | Why |
|---|---|
| created or changed identifier | ties the readback to this action |
| unique marker inside the data | proves which run and attempt wrote it |
| record count before the action | gives the duplicate check a baseline |
| record count after the action | shows created, missing, or duplicated rows |
| server timestamp of the record | separates a fresh write from an older one |
| the exact field values compared | stops a shallow "it exists" claim |

A readback that finds a record but does not compare the values is a partial result. Report which
fields were compared and which were not.

Join the action, the request, and the record by identifier, not by wall clock. Use timing only as
a stated inference, and record clock skew between the browser and the server as a note rather than
as a defect.

## Unknown against Blocked

| Situation | Status |
|---|---|
| action ran, no authoritative channel available | Unknown, and name the missing channel |
| action ran, readback attempted, record not found | Fail, with the query and the timestamp |
| action ran, readback returned a different value than expected | Fail |
| readback channel exists but credentials or permission are missing | Blocked |
| action never ran because authorization was refused | Blocked |
| action never ran because the budget stopped | Blocked |
| check planned but never attempted | Not run |
| readback result ambiguous, for example an eventually consistent store with no read-your-write guarantee | Unknown, with the retry attempts recorded |

Never convert Unknown into Pass by pointing at the UI message.

## Cache and replica traps

- A reload in the same browser profile can serve a client cache. Use a fresh profile or a
  cache-busting read when the value matters.
- An API read may hit a replica. Ask the user which reads are read-your-write, and record the
  answer.
- Eventual consistency needs a bounded wait with a stated condition and a retry count, not a
  fixed sleep. Record how many reads were needed.
- A service worker can serve stale content. Check for one before calling a stale value a defect.

## Recording the channel

Every persistence row in the report carries: channel used, who authorized it, the query or
endpoint in a form the user can rerun, the timestamp, and the compared fields. A row without a
channel is not a persistence result.
