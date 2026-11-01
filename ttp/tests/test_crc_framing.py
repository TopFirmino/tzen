"""CRC framing regression tests. Run: python -m unittest discover -s ttp/tests -v"""
import subprocess
import tempfile
import unittest
from pathlib import Path

from ttp.python import ttp

ROOT = Path(__file__).resolve().parents[2]


class CrcFramingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ttp_crc_')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        harness = folder / 'crc_bridge.c'
        harness.write_text(r'''
#include <assert.h>
#include <stdio.h>
#include "../src/ttp.c"
int main(int argc, char **argv) {
    uint8_t body[TTP_MAX_FRAME_SIZE], frame[TTP_MAX_FRAME_SIZE];
    size_t length = 0, size = 0, i;
    unsigned int value;
    HostToTarget host;
    TargetToHost target;
    Ttp_Status_t status;
    assert(crc16((const uint8_t *)"123456789", 9) == 0x29B1);
    assert(argc == 3);
    while (argv[1][length * 2] != '\0') {
        assert(length < sizeof(body));
        assert(sscanf(argv[1] + length * 2, "%2x", &value) == 1);
        body[length++] = (uint8_t)value;
    }
    status = argv[2][0] == 'h'
        ? Ttp_DecodeHostToTargetFrame(&host, body, length)
        : Ttp_DecodeTargetToHostFrame(&target, body, length);
    printf("%d\n", (int)status);
    if (status == TTP_STATUS_OK) {
        assert((argv[2][0] == 'h'
            ? Ttp_EncodeHostToTargetFrame(&host, frame, sizeof(frame), &size)
            : Ttp_EncodeTargetToHostFrame(&target, frame, sizeof(frame), &size)) == TTP_STATUS_OK);
        for (i = 0; i < size; i++) printf("%02x", frame[i]);
        printf("\n");
        assert((argv[2][0] == 'h'
            ? Ttp_EncodeHostToTargetFrame(&host, frame, size - 1, &size)
            : Ttp_EncodeTargetToHostFrame(&target, frame, size - 1, &size)) != TTP_STATUS_OK);
        assert(size == 0);
    }
    return 0;
}
''')
        cls.exe = folder / 'crc_bridge.exe'
        subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'ttp/C/inc'), '-I', str(ROOT / 'ttp/C/generated'),
                        '-I', str(ROOT / 'nanopb'),
                        str(harness), str(ROOT / 'ttp/C/generated/ttp.pb.c'),
                        *[str(ROOT / 'nanopb' / p) for p in
                          ('pb_common.c', 'pb_decode.c', 'pb_encode.c')],
                        '-o', str(cls.exe)], check=True)

    def bridge(self, body, direction="host"):
        return subprocess.check_output([str(self.exe), body.hex(), direction], text=True).splitlines()

    def test_interoperability_and_zero_crc_bytes(self):
        zero_crc_message = next(
            ttp.make_get_test_info(i) for i in range(65536)
            if 0 in ttp.cobs_decode(ttp.encode_frame(ttp.make_get_test_info(i))[1:-1])[-2:])
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
            frame = ttp.encode_frame(message)
            body = frame[1:-1]
            self.assertNotIn(0, body)
            raw = ttp.cobs_decode(body)
            saw_zero |= 0 in raw[-2:]
            self.assertEqual(ttp.decode_frame(body, type(message)), message)
            self.assertEqual(self.bridge(body, 'host' if isinstance(message, ttp.HostToTarget) else 'target'), ['0', frame.hex()])
        self.assertTrue(saw_zero)

    def test_every_single_bit_corruption(self):
        frame = ttp.encode_frame(ttp.make_execute_test(123, 1))
        raw = ttp.cobs_decode(frame[1:-1])
        for index in range(len(raw)):
            for bit in range(8):
                damaged = bytearray(raw)
                damaged[index] ^= 1 << bit
                body = ttp.cobs_encode(damaged)
                with self.assertRaisesRegex(ValueError, 'CRC16 mismatch'):
                    ttp.decode_frame(body)
                self.assertEqual(self.bridge(body), ['6'])  # TTP_STATUS_CRC_FAILED

    def test_missing_truncated_and_malformed_frames(self):
        raw = ttp.cobs_decode(ttp.encode_frame(ttp.make_get_test_info(123))[1:-1])
        bodies = [b'', b'\x00', b'\x03\x01', b'\x02\x00',
                  ttp.cobs_encode(b'\x01'), ttp.cobs_encode(raw[:-1]),
                  ttp.cobs_encode(raw[:-2])]
        for body in bodies:
            with self.assertRaises(ValueError):
                ttp.decode_frame(body)
            self.assertNotEqual(self.bridge(body)[0], '0')


if __name__ == '__main__':
    unittest.main()
