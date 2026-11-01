"""Public C/Python protobuf interoperability tests."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from google.protobuf.message import DecodeError

from ttp.python import ttp

ROOT = Path(__file__).resolve().parents[2]


class ProtobufTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='ttp_protobuf_')
        cls.addClassCleanup(cls.temp.cleanup)
        folder = Path(cls.temp.name)
        harness = folder / 'protobuf_bridge.c'
        harness.write_text(r'''
#include <assert.h>
#include <stdio.h>
#include "ttp.h"
int main(int argc, char **argv) {
    uint8_t body[TTP_MAX_MESSAGE_SIZE], frame[TTP_MAX_MESSAGE_SIZE];
    size_t length = 0, size = 0, i;
    unsigned int value;
    HostToTarget host;
    TargetToHost target;
    Ttp_Status_t status;
    assert(argc == 3);
    size = 123;
    assert(Ttp_EncodeHostToTarget(NULL, body, sizeof(body), &size) == TTP_STATUS_INVALID_ARGUMENT);
    assert(size == 0);
    assert(Ttp_EncodeTargetToHost(NULL, body, sizeof(body), &size) == TTP_STATUS_INVALID_ARGUMENT);
    assert(Ttp_DecodeHostToTarget(NULL, body, 0) == TTP_STATUS_INVALID_ARGUMENT);
    assert(Ttp_DecodeTargetToHost(&target, NULL, 0) == TTP_STATUS_INVALID_ARGUMENT);
    while (argv[1][length * 2] != '\0') {
        assert(length < sizeof(body));
        assert(sscanf(argv[1] + length * 2, "%2x", &value) == 1);
        body[length++] = (uint8_t)value;
    }
    status = argv[2][0] == 'h'
        ? Ttp_DecodeHostToTarget(&host, body, length)
        : Ttp_DecodeTargetToHost(&target, body, length);
    printf("%d\n", (int)status);
    if (status == TTP_STATUS_OK) {
        assert((argv[2][0] == 'h'
            ? Ttp_EncodeHostToTarget(&host, frame, sizeof(frame), &size)
            : Ttp_EncodeTargetToHost(&target, frame, sizeof(frame), &size)) == TTP_STATUS_OK);
        for (i = 0; i < size; i++) printf("%02x", frame[i]);
        printf("\n");
        if (size > 0) {
        assert((argv[2][0] == 'h'
            ? Ttp_EncodeHostToTarget(&host, frame, size - 1, &size)
            : Ttp_EncodeTargetToHost(&target, frame, size - 1, &size)) != TTP_STATUS_OK);
        assert(size == 0);
        }
    }
    return 0;
}
''')
        cls.exe = folder / 'protobuf_bridge.exe'
        subprocess.run(['gcc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-I', str(ROOT / 'ttp/C/inc'), '-I', str(ROOT / 'ttp/C/generated'),
                        '-I', str(ROOT / 'nanopb'),
                        str(harness), str(ROOT / 'ttp/C/src/ttp.c'), str(ROOT / 'ttp/C/generated/ttp.pb.c'),
                        *[str(ROOT / 'nanopb' / p) for p in
                          ('pb_common.c', 'pb_decode.c', 'pb_encode.c')],
                        '-o', str(cls.exe)], check=True)

    def bridge(self, body, direction="host"):
        return subprocess.check_output([str(self.exe), body.hex(), direction], text=True).splitlines()

    def test_interoperability(self):
        messages = [ttp.HostToTarget(), ttp.make_get_tests(),
                    ttp.make_get_test_info(123), ttp.make_execute_test(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF),
                    ttp.make_abort_test(1), ttp.make_sync_release(1, 1),
                    ttp.TargetToHost(),
                    ttp.TargetToHost(seq_id=1, status=ttp.RESULT_ERR_BUSY),
                    ttp.TargetToHost(seq_id=1, tests_count=ttp.GetTestsResp(total_tests=2)),
                    ttp.TargetToHost(seq_id=0xFFFFFFFF, test_info=ttp.GetTestInfoResp(
                        index=0xFFFFFFFF, name='x'*31, total_steps=0xFFFFFFFF)),
                    ttp.TargetToHost(seq_id=0xFFFFFFFF, status=ttp.RESULT_ERR_INVALID,
                        log=ttp.LogEvent(level=ttp.LogEvent.ERROR, message='x'*63,
                            run_id=0xFFFFFFFF, test_index=0xFFFFFFFF)),
                    ttp.TargetToHost(seq_id=0xFFFFFFFF, status=ttp.RESULT_ERR_INVALID,
                        test_event=ttp.TestEvent(run_id=0xFFFFFFFF, test_index=0xFFFFFFFF,
                        step=ttp.TestStepEvent(step_number=0xFFFFFFFF, success=True))),
                    ttp.TargetToHost(test_event=ttp.TestEvent(run_id=1, sync=ttp.SyncWaitEvent(sync_id=1))),
                    ttp.TargetToHost(test_event=ttp.TestEvent(run_id=1,
                        finished=ttp.TestFinishedEvent(status=ttp.TestFinishedEvent.ABORTED)))]
        for message in messages:
            payload = ttp.encode_message(message)
            self.assertEqual(ttp.decode_message(payload, type(message)), message)
            self.assertEqual(self.bridge(payload, 'host' if isinstance(message, ttp.HostToTarget) else 'target'), ['0', payload.hex()])

    def test_malformed_protobuf(self):
        for payload in (b'\x08\x80', b'\x12\x05', b'\x00'):
            with self.assertRaises(DecodeError):
                ttp.decode_message(payload)
            self.assertEqual(self.bridge(payload)[0], '4')


if __name__ == '__main__':
    unittest.main()
