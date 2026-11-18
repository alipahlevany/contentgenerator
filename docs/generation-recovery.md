# Interrupted generation recovery

The maintenance worker checks every five minutes for running jobs whose
progress has not changed for five minutes. Recovery first takes the same
PostgreSQL advisory lock used by the generation worker. A live worker keeps
that lock, so slow requests are not interrupted or duplicated by maintenance.

An abandoned job is queued on its original generation queue with its saved
counts intact. At most three automatic recoveries are allowed per job;
after that the job needs inspection and an explicit Resume. Both the API
and admin Resume reset this recovery budget without resetting progress.
The admin job details show the recovery count.

Lost continuations and failed recovery publications are also retried when
pending for an hour. Pending drafts that have never run are excluded.
Stopped, completed and failed jobs are not automatically restarted. Existing
historical failed jobs, including job 263, require an explicit Resume.

Saving an output, its fingerprint, delivery records and the progress counter
now uses one database transaction. Callback tasks are published after commit,
so an interruption cannot commit the output without its progress count.
This does not make remote callback delivery exactly-once; existing callback
idempotency and retry behavior still applies.

Deployment requires migration 0059, a worker consuming the `maintenance`
queue, and restarting web, generation workers, maintenance worker and Beat.
Drain active generation before stopping workers. The additive recovery-count
column may remain if application code is rolled back.

Generation recovery tests cover preserved progress, concurrent maintenance,
live worker ownership, abandoned continuations, broker failure, bounded
recovery, user Stop, explicit Resume, transaction rollback, post-commit
delivery scheduling and completion of only the remaining outputs.
