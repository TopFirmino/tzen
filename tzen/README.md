# Python package

```python
from tzen import Client

with Client.serial("COM5", baudrate=115200) as target:
    print(target.discover())
    result = target.run("LED cycle", on_event=lambda event: print(event))
    assert result.passed
```

`discover()` returns TestInfo(index, name, total_steps). `run()` accepts an index
or name and returns TestResult(run_id, test, status, events). Logs, steps, sync
and terminal messages are available to `on_event`. By default sync points are
released automatically; `on_sync(execution_event)` can perform host work and
return True to release or False to abort.

For manual orchestration use `start(index, run_id=None)`, `receive()`,
`release(run_id, sync_id)` and `abort(run_id)`. One thread owns a client and only
one request is outstanding. Sequence IDs wrap through nonzero uint32 values.
Events arriving during a request are preserved in a bounded queue. `CommandError`
exposes the rejected response/result code. CRC or protobuf errors propagate.

The serial transport waits two seconds after open for the Mega's auto-reset,
then clears startup input. Receive operations use deadlines; commands are never
automatically retried because execution acceptance could be ambiguous after a
timeout. `run` attempts abort on an exception, including timeout or callback
failure, but cannot guarantee cleanup after a disconnect. Reconnect/reset if the
stream state is uncertain. A user callback itself must return promptly.

The default request timeout is 5 seconds, run timeout is 15 seconds, and event
bound is 256. Custom transports implement read(size), write(bytes), close();
read must return periodically so the client can enforce deadlines. The codecs
remain in `ttp`, with no dependency on this package or pyserial.
