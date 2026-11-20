# Tzen
# Author: L. Furcas
# SPDX-License-Identifier: MPL-2.0

"""Routing over actual framed messages, including events interleaved with ACKs."""
from collections import deque

import pytest
from tzen import (
    SOURCE_TEST,
    Client,
    EventDispatcher,
    ExecutionRef,
    execution_of,
    framing,
)
from tzen.client import TestInfo as RemoteTestInfo
from tzen.execution import CaseRun

from ttp.python import ttp


def log(source=0, run=1, index=0, *, global_=False, text="message"):
    return ttp.TargetToHost(log=ttp.LogEvent(source=source, run_id=run,
        test_index=index, scope=ttp.LogEvent.GLOBAL if global_ else ttp.LogEvent.EXECUTION,
        message=text))


def finished(run=1):
    return ttp.TargetToHost(test_event=ttp.TestEvent(run_id=run,
        finished=ttp.TestFinishedEvent(status=ttp.TestFinishedEvent.SUCCESS)))


class Transport:
    def __init__(self, before_ack=()):
        self.rx = deque()
        self.before_ack = before_ack
        self.writes = 0

    def push(self, *events):
        for event in events:
            self.rx.extend(framing.encode_frame(event))

    def read(self, size):
        return bytes([self.rx.popleft()]) if self.rx else b""

    def write(self, data):
        self.writes += 1
        command = framing.decode_frame(data[1:-1], ttp.HostToTarget)
        self.push(*self.before_ack, ttp.TargetToHost(seq_id=command.seq_id))

    def close(self):
        pass


def test_filters_zero_identity_and_unsubscribe():
    dispatcher = EventDispatcher()
    all_events, correlated, globals_ = [], [], []
    dispatcher.subscribe(all_events.append)
    with dispatcher.subscribe(correlated.append, source=7, execution=ExecutionRef(0, 0)) as sub:
        dispatcher.subscribe(globals_.append, source=7, global_only=True)
        dispatcher.dispatch(log(7, run=0))
        dispatcher.dispatch(log(7, run=0, global_=True))
        dispatcher.dispatch(log(8, run=0))
    sub.close()
    dispatcher.dispatch(log(7, run=0))
    assert len(all_events) == 4 and len(correlated) == len(globals_) == 1
    assert execution_of(correlated[0]) == ExecutionRef(0, 0)
    assert execution_of(globals_[0]) is None


@pytest.mark.parametrize("companion", [False, True])
def test_default_routing_and_late_messages(companion):
    # The inbox must exist BEFORE waiting for ExecuteTest's ACK.
    transport = Transport([log(7, global_=True), log(run=99), log(), finished()])
    client = Client(transport, timeout=0.05)
    custom, late, standard = [], [], []
    client.events.subscribe(custom.append, source=7)
    client.events.subscribe(late.append, execution=ExecutionRef(99, 0))
    client.events.subscribe(standard.append, source=SOURCE_TEST, execution=ExecutionRef(1, 0))
    info = RemoteTestInfo(0, "remote", 1)
    if companion:
        with CaseRun(client, info, 1, lambda event: None, lambda: None) as run:
            pass
        result = run.result
    else:
        result = client.run(info)
    assert result.passed
    assert [event.WhichOneof("payload") for event in result.events] == ["log", "test_event"]
    assert len(custom) == len(late) == len(standard) == 1
    # The worker is finished; subscriptions remain usable without an open run.
    transport.push(log(7, run=1), log(run=1))
    client.receive()
    client.receive()
    assert len(custom) == len(standard) == 2
    assert len(result.events) == 2
    assert len(client.events._subscriptions) == 3  # no leaked internal subscribers


def test_callback_errors_and_recursive_reads_are_explicit():
    transport = Transport()
    client = Client(transport, timeout=0.01)
    with client.events.subscribe(lambda event: client.request(ttp.make_get_tests())):
        transport.push(log(7))
        with pytest.raises(RuntimeError, match="callbacks must not"):
            client.receive()
    assert transport.writes == 0
    transport.push(log(7))
    assert client.receive().log.source == 7


def test_request_dispatches_once_and_preserves_unhandled_events():
    transport = Transport([log(7), log(8)])
    client = Client(transport, timeout=0.05)
    received = []
    client.events.subscribe(received.append, source=7)
    client.request(ttp.make_abort_test(123))
    assert len(received) == 1
    assert client.receive().log.source == 8
    assert len(received) == 1


def test_subscription_cleanup_on_start_failure():
    transport = Transport([ttp.TargetToHost(seq_id=1, status=ttp.RESULT_ERR_BUSY)])
    client = Client(transport)
    with pytest.raises(Exception):
        client.run(RemoteTestInfo(0, "remote", 1))
    assert not client.events._subscriptions


def test_global_traffic_does_not_extend_execution_deadline():
    transport = Transport()
    client = Client(transport, timeout=0.01)
    client.events.subscribe(lambda event: None, source=7)
    transport.before_ack = [log(7, global_=True)] * 20
    with pytest.raises(TimeoutError):
        client.run(RemoteTestInfo(0, "remote", 1), timeout=0.01)
    assert len(client.events._subscriptions) == 1
