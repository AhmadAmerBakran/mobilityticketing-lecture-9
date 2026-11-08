# The last seat

PostgreSQL 17. Tested with two separate connections on 8 November 2026.
The fixture was reset between cases, after both transactions had ended. The supplied check.sql passed as well.

Recorded run: https://github.com/AhmadAmerBakran/mobilityticketing-lecture-9/actions/runs/42489085626

## Two-session results

RC means READ COMMITTED, RR means REPEATABLE READ, and S means SERIALIZABLE. The last column is reserved_seats / booking rows for the named trip. Wait events were checked through pg_stat_activity, not inferred from elapsed time. "none" means no recorded wait or error.

The order codes are:

R: A and B both read availability; A writes and commits; B writes using its original value.
J: A and B read; A updates and inserts; B inserts and tries the increment while A is open; A commits; B rolls back after the error.
C: A books T-LAST; B books the same trip and waits; A commits; B finishes.
X: Same order as C, except A rolls back.
O: A books T-LAST and stays open; B books T-OTHER; A commits; B commits.
I: A books with an advisory lock; B reads a stale count and updates without that advisory lock; A commits; B finishes.
D: A locks T-LAST, B locks T-OTHER, then each requests the other's row.
P: Both read the count; A updates; B attempts the optimistic update; A commits or rolls back; B checks the outcome and retries if appropriate.
F: A successful booking is replayed, followed by altered, full, cancelled and missing-trip requests.
Z: A gets a booking ID and rolls back its surrounding transaction.
U: A inserts a request and stays open; B uses the same request ID; A commits or rolls back; B finishes.

| Experiment | Level | Order | B waits for | SQLSTATE / result | Trip | Reserved / bookings |
| --- | --- | --- | --- | --- | --- | --- |
| Unsafe read then write | RC | R | none | none | T-LAST | 1 / 2 |
| Increment without capacity condition | RC | J | transactionid | 23514 | T-LAST | 1 / 1 |
| Conditional update, A commits | RC | C | transactionid | P0001 | T-LAST | 1 / 1 |
| Conditional update, A rolls back | RC | X | transactionid | none | T-LAST | 1 / 1 |
| Conditional update, other trip | RC | O | none | none | T-OTHER | 1 / 1 |
| Row lock, A commits | RC | C | transactionid | P0001 | T-LAST | 1 / 1 |
| Row lock, A rolls back | RC | X | transactionid | none | T-LAST | 1 / 1 |
| Row lock, other trip | RC | O | none | none | T-OTHER | 1 / 1 |
| Table lock, A commits | RC | C | relation | P0001 | T-LAST | 1 / 1 |
| Table lock, A rolls back | RC | X | relation | none | T-LAST | 1 / 1 |
| Table lock, other trip | RC | O | relation | none | T-OTHER | 1 / 1 |
| Advisory lock, A commits | RC | C | advisory | P0001 | T-LAST | 1 / 1 |
| Advisory lock, A rolls back | RC | X | advisory | none | T-LAST | 1 / 1 |
| Advisory lock, other trip | RC | O | none | none | T-OTHER | 1 / 1 |
| Optimistic function, A commits | RC | C | transactionid | 40001 | T-LAST | 1 / 1 |
| Optimistic function, A rolls back | RC | X | transactionid | none | T-LAST | 1 / 1 |
| Optimistic function, other trip | RC | O | none | none | T-OTHER | 1 / 1 |
| Unsafe write bypasses advisory lock | RC | I | transactionid | none | T-LAST | 1 / 2 |
| Opposite row-lock order | RC | D | both sessions | 40P01 | T-LAST | 0 / 0 |
| Optimistic count, A commits | RC | P | transactionid | zero rows, retry succeeds | T-TWO | 2 / 2 |
| Optimistic count, last seat, A commits | RC | P | transactionid | zero rows, retry finds full | T-LAST | 1 / 1 |
| Optimistic count, last seat, A rolls back | RC | P | transactionid | none | T-LAST | 1 / 1 |
| Original unsafe sequence | RR | R | none | 40001 | T-LAST | 1 / 1 |
| Original unsafe sequence | S | R | none | 40001 | T-LAST | 1 / 1 |
| Replay, changed data and unavailable trips | RC | F | none | 23505, P0001, 23503 | T-LAST | 1 / 1 |
| Returned ID followed by rollback | RC | Z | none | none | T-LAST | 0 / 0 |
| Same request, A commits | RC | U | transactionid | none, same booking ID | T-TWO | 1 / 1 |
| Same request, A rolls back | RC | U | transactionid | none, B books | T-TWO | 1 / 1 |
| Same request, different passenger, A commits | RC | U | transactionid | 23505 | T-TWO | 1 / 1 |
| Same request, different passenger, A rolls back | RC | U | transactionid | none, B books | T-TWO | 1 / 1 |

## What happened

At READ COMMITTED both unsafe sessions read reserved_seats = 0. A wrote 1 and committed. B used its old value and also wrote 1. Both inserts committed, leaving two booking rows and a counter of 1. BEGIN and COMMIT kept each session's operations together; they did not make the earlier read safe. The CHECK only enforces 0 <= reserved_seats <= capacity. It does not compare the counter to the number of rows in bookings.

Replacing the stale assignment with reserved_seats = reserved_seats + 1 made B wait for A, then fail with 23514. Rolling back B also removed its inserted booking. The counter constraint prevents going above capacity but does not, by itself, guarantee that the booking count agrees. If B's insert had committed separately, the CHECK failure would not undo that insert.

The conditional UPDATE makes the capacity decision in the same statement as the increment. When A commits the last seat, B waits and then updates zero rows. When A rolls back, B can take the seat. Zero updated rows means that the row did not meet the condition; it does not say whether the trip is full, cancelled, missing, or changed while waiting. Reading first is not a substitute for that condition.

FOR UPDATE only holds up bookings of the same trip. The exclusive table lock also blocks T-OTHER; the recorded wait event was relation. The advisory lock used keys (9009, 1), (9009, 2), (9009, 3), and (9009, 4) for T-LAST, T-TWO, T-CANCELLED, and T-OTHER. Cooperating sessions waited on advisory. An unsafe writer which ignored that lock still overwrote the counter after waiting on a normal row update lock, producing two bookings for one seat. A lock convention cannot protect a path which does not follow it. Longer transactions make other bookings wait longer.

The deadlock test acquired row locks in opposite orders and PostgreSQL cancelled one operation with 40P01. Its transaction was rolled back so the other could finish. Booking code that needs several locks should acquire them in a consistent order and retry the whole aborted transaction.

With the optimistic count check, both sessions read 0. On T-TWO, B's old-value UPDATE affected zero rows after A committed. In a new transaction B read 1 and successfully booked the second seat. On T-LAST the retry found the trip full. If A rolled back, B's pending update succeeded. The optimistic check still waited for an UPDATE lock. Comparing only the count cannot detect 0 -> 1 -> 0 between observations (ABA). A version column increased on every relevant change would detect that history without relying on the current count. The exercise schema was not changed.

Under both REPEATABLE READ and SERIALIZABLE, the original stale update failed with 40001. B rolled back and started a new transaction, repeated the availability read, and found no seat; repeating just the stale UPDATE would make the decision using an obsolete value. These two tests look alike because both transactions change the same row. REPEATABLE READ can still permit write skew across separate rows; SERIALIZABLE gives a stronger guarantee for transactions that finish successfully. Protecting one shared counter does not prove that every multi-row business rule is safe.

For 40001, the application should repeat the full transaction, including fresh reads and the booking decision. A bounded retry policy, for example three attempts with a short randomized delay, prevents indefinite retries. After that, return a retryable error or tell the passenger the booking could not be confirmed. A payment should not be made inside the retry loop: repeating an external charge is not rolled back by PostgreSQL.

The final function inserts using ON CONFLICT (request_id) DO NOTHING, checks an existing request's passenger and trip, and only increments the trip counter for a new booking. The unique constraint coordinates simultaneous requests with the same ID; the guarded trip UPDATE coordinates different requests for the same last seat. A pre-insert SELECT without a unique constraint would leave a race. Returning an ID before the caller commits is not proof the booking is durable. The checked rollback left neither a booking nor a counter increment. An exact replay returns the old ID even when full or cancelled. A changed passenger or trip is rejected. New full, cancelled and missing-trip requests do not change stored data.

## AI review

Model: GPT-6.

Prompt supplied after implementing the booking function:

"Review this PostgreSQL 17 booking operation for concurrency and request retries. The schema has trips(id primary key, status checked as Scheduled or Cancelled, capacity > 0, reserved_seats between 0 and capacity) and bookings(id identity primary key, request_id unique and not null, passenger_id not null, trip_id referencing trips). The full definitions are database/setup.sql. The final lab09.book function in sql/book.sql first INSERTs the request using ON CONFLICT (request_id) DO NOTHING. If the ID exists, it reads the saved booking, rejects changed passenger/trip with 23505 or returns its ID. For a new ID it runs UPDATE trips SET reserved_seats = reserved_seats + 1 WHERE status = 'Scheduled' AND reserved_seats < capacity; no row means reject. This is one caller-managed transaction.

Here is a two-session result at READ COMMITTED: A BEGIN, SELECT lab09.book('repeat-A','passenger-A','T-TWO') and keeps the transaction open. B BEGIN and calls the same function with the same arguments; B waits on transactionid. A COMMIT; B returns A's booking ID and COMMIT. Final T-TWO: reserved_seats 1, booking rows 1. Identify a concurrency or retry case this does not cover. Give an exact A/B schedule and expected counts and SQLSTATE."

Relevant review response:

"Try the same request ID with a different passenger while A is uncommitted. B must wait for the unique-key outcome. If A commits, B must reject the conflicting payload without changing the counter. If A rolls back, B should be able to insert the request and take the seat. Test both outcomes, rather than assuming the first insertion always wins."

Prediction before testing: after A commits, B gets 23505 and T-TWO has 1 reservation and 1 booking. After A rolls back, B succeeds and T-TWO still has 1 reservation and 1 booking.

Executed sequence: A used BEGIN and SELECT lab09.book('repeat-A', 'passenger-A', 'T-TWO'); B began and called lab09.book('repeat-A', 'passenger-B', 'T-TWO') before A finished. B waited on transactionid. With A COMMIT, B returned 23505 and rolled back. With A ROLLBACK, B returned a booking ID and committed. Both final counts were 1 / 1.

The suggestion was useful and the implementation passed, so no function change was necessary. The two distinct outcomes were verified through actual PostgreSQL transactions, not just the model's prediction. Other application failures, such as a network interruption after commit, still need integration-level testing.
