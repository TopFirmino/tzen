"""Harness framing regressions, independent of protobuf codecs."""
import unittest
from ttp.python import ttp
from tzen import framing


class FramingTests(unittest.TestCase):
    def test_interoperability_and_zero_crc_bytes(self):
        zero_crc_message = next(
            ttp.make_get_test_info(i) for i in range(65536)
            if 0 in framing.cobs_decode(framing.encode_frame(ttp.make_get_test_info(i))[1:-1])[-2:])
        messages = [ttp.HostToTarget(), ttp.make_get_tests(),
                    zero_crc_message, ttp.make_execute_test(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF),
                    ttp.make_abort_test(1), ttp.make_sync_release(1, 1),
                    ttp.TargetToHost(),
                    ttp.TargetToHost(seq_id=1, status=ttp.RESULT_ERR_BUSY),
                    ttp.TargetToHost(seq_id=1, tests_count=ttp.GetTestsResp(total_tests=2)),
                    ttp.TargetToHost(seq_id=0xFFFFFFFF, test_info=ttp.GetTestInfoResp(
                        index=0xFFFFFFFF, name='x'*31, total_steps=0xFFFFFFFF)),
                    ttp.TargetToHost(log=ttp.LogEvent(level=ttp.LogEvent.ERROR, message='x'*63)),
                    ttp.TargetToHost(seq_id=0xFFFFFFFF, status=ttp.RESULT_ERR_INVALID,
                        test_event=ttp.TestEvent(run_id=0xFFFFFFFF, test_index=0xFFFFFFFF,
                        step=ttp.TestStepEvent(step_number=0xFFFFFFFF, success=True))),
                    ttp.TargetToHost(test_event=ttp.TestEvent(run_id=1, sync=ttp.SyncWaitEvent(sync_id=1))),
                    ttp.TargetToHost(test_event=ttp.TestEvent(run_id=1,
                        finished=ttp.TestFinishedEvent(status=ttp.TestFinishedEvent.ABORTED)))]
        saw_zero = False
        for message in messages:
            frame = framing.encode_frame(message)
            body = frame[1:-1]
            self.assertNotIn(0, body)
            raw = framing.cobs_decode(body)
            saw_zero |= 0 in raw[-2:]
            self.assertEqual(framing.decode_frame(body, type(message)), message)
        self.assertTrue(saw_zero)

    def test_every_single_bit_corruption(self):
        frame = framing.encode_frame(ttp.make_execute_test(123, 1))
        raw = framing.cobs_decode(frame[1:-1])
        for index in range(len(raw)):
            for bit in range(8):
                damaged = bytearray(raw)
                damaged[index] ^= 1 << bit
                body = framing.cobs_encode(damaged)
                with self.assertRaisesRegex(ValueError, 'CRC16 mismatch'):
                    framing.decode_frame(body)

    def test_missing_truncated_and_malformed_frames(self):
        raw = framing.cobs_decode(framing.encode_frame(ttp.make_get_test_info(123))[1:-1])
        bodies = [b'', b'\x00', b'\x03\x01', b'\x02\x00',
                  framing.cobs_encode(b'\x01'), framing.cobs_encode(raw[:-1]),
                  framing.cobs_encode(raw[:-2])]
        for body in bodies:
            with self.assertRaises(ValueError):
                framing.decode_frame(body)

