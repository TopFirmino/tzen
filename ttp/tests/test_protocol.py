"""Integration against a freshly compiled C target, using CRC-protected frames."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from ttp.python import ttp
from ttp.python.master import TtpProcessMaster

ROOT = Path(__file__).resolve().parents[2]


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ttp_integration_')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.exe = Path(cls.temp.name) / 'ttp_slave.exe'
        subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'ttp/C'), '-I', str(ROOT / 'ttp/C/generated'),
                        '-I', str(ROOT / 'nanopb'),
                        *[str(ROOT / p) for p in ('ttp/C/slave_main.c', 'ttp/C/ttp.c',
                          'ttp/C/generated/ttp.pb.c', 'nanopb/pb_common.c',
                          'nanopb/pb_decode.c', 'nanopb/pb_encode.c')],
                        '-o', str(cls.exe)], check=True)

    def setUp(self):
        self.master = TtpProcessMaster(self.exe)
        self.master.start()
        self.addCleanup(self.master.close)

    def test_discovery_and_both_executions(self):
        self.assertEqual(self.master.get_manifest(), ['sample_test_1', 'sample_test_2'])
        self.assertEqual(self.master.get_test_info(1).total_steps, 2)
        for index in (0, 1):
            events = list(self.master.execute_test(index, run_id=100+index))
            self.assertEqual(events[0].status, ttp.RESULT_OK)
            test_events = [m.test_event for m in events if m.WhichOneof('payload') == 'test_event']
            self.assertTrue(all(e.run_id == 100+index and e.test_index == index for e in test_events))
            self.assertEqual([e.step.step_number for e in test_events if e.WhichOneof('event') == 'step'], [1, 2])
            self.assertEqual(test_events[-1].WhichOneof('event'), 'finished')
            self.assertEqual(test_events[-1].finished.status, ttp.TestFinishedEvent.SUCCESS)

    def test_result_codes_and_sequence_correlation(self):
        requests = [(ttp.make_get_test_info(2), ttp.RESULT_ERR_INDEX),
                    (ttp.make_execute_test(2, 9), ttp.RESULT_ERR_INDEX),
                    (ttp.make_abort_test(9), ttp.RESULT_ERR_NOT_FOUND),
                    (ttp.make_sync_release(9, 1), ttp.RESULT_ERR_NOT_FOUND),
                    (ttp.HostToTarget(), ttp.RESULT_ERR_INVALID)]
        seqs = []
        for command, expected in requests:
            response = self.master.request(command)
            self.assertEqual(response.seq_id, command.seq_id)
            self.assertEqual(response.status, expected)
            self.assertIsNone(response.WhichOneof('payload'))
            seqs.append(response.seq_id)
        self.assertEqual(seqs, [1, 2, 3, 4, 5])
        self.master._next_seq = 0xFFFFFFFF
        self.assertEqual(self.master.request(ttp.make_get_tests()).seq_id, 0xFFFFFFFF)
        self.assertEqual(self.master.request(ttp.make_get_tests()).seq_id, 1)

    def test_wait_busy_wrong_release_and_abort(self):
        self.assertEqual(self.master.request(ttp.make_execute_test(1, 42)).status, ttp.RESULT_OK)
        # request() must preserve the log, step, and sync preceding this response.
        self.assertEqual(self.master.request(ttp.make_execute_test(0, 43)).status, ttp.RESULT_ERR_BUSY)
        self.assertEqual(self.master.get_test_info(1).index, 1)
        self.assertEqual(self.master.release_sync(42, 2).status, ttp.RESULT_ERR_NOT_FOUND)
        self.assertEqual(self.master.release_sync(43, 1).status, ttp.RESULT_ERR_NOT_FOUND)
        self.assertEqual(self.master.abort_test(43).status, ttp.RESULT_ERR_NOT_FOUND)
        self.assertEqual(self.master.abort_test(42).status, ttp.RESULT_OK)
        events = [self.master.receive() for _ in range(4)]
        self.assertEqual([m.WhichOneof('payload') for m in events], ['log', 'test_event', 'test_event', 'test_event'])
        self.assertEqual(events[2].test_event.WhichOneof('event'), 'sync')
        self.assertEqual(events[-1].test_event.finished.status, ttp.TestFinishedEvent.ABORTED)
        self.assertEqual(events[-1].test_event.run_id, 42)
        self.assertEqual(self.master.abort_test(42).status, ttp.RESULT_ERR_NOT_FOUND)
        self.assertEqual(self.master.release_sync(42, 1).status, ttp.RESULT_ERR_NOT_FOUND)
        self.assertEqual(list(self.master.execute_test(0))[-1].test_event.finished.status, 0)

    def test_manual_release_and_zero_run_id(self):
        stream = self.master.execute_test(1, run_id=0, auto_release=False)
        for _ in range(4):
            event = next(stream)
        self.assertEqual(event.test_event.WhichOneof('event'), 'sync')
        self.assertEqual(self.master.release_sync(0, 1).status, ttp.RESULT_OK)
        remaining = list(stream)
        self.assertEqual(remaining[-1].test_event.WhichOneof('event'), 'finished')
        self.assertEqual(remaining[-1].test_event.run_id, 0)

    def test_corrupt_zero_sequence_and_oversized_frames_are_discarded(self):
        raw = ttp.cobs_decode(ttp.encode_frame(ttp.make_execute_test(1, 99, seq_id=1))[1:-1])
        bad = bytearray(raw)
        bad[-1] ^= 1
        self.master.process.stdin.write(b'\x00' + ttp.cobs_encode(bad) + b'\x00')
        self.master.process.stdin.write(ttp.encode_frame(ttp.make_execute_test(1, 99)))
        self.master.process.stdin.write(b'\x00' + b'\x01'*150 + b'\x00')
        self.master.process.stdin.flush()
        # Only the following valid request gets a reply; no test was started.
        self.assertEqual(self.master.request(ttp.make_get_tests()).status, ttp.RESULT_OK)
        self.assertEqual(list(self.master.execute_test(0))[-1].test_event.finished.status, 0)


if __name__ == '__main__':
    unittest.main()
