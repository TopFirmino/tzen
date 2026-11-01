CC = gcc
CPPFLAGS += -I../../../testharness-c/inc -I../../../testharness-c/cfg
CPPFLAGS += -I../../../ttp/C/inc -I../../../ttp/C/generated -I../../../nanopb
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -g
HOST_CPPFLAGS = -include host_critical_section.h
THREAD_FLAGS = -pthread

TARGET = tzen_host.exe
CODECS = ../../../ttp/C/src/ttp.c ../../../ttp/C/generated/ttp.pb.c ../../../nanopb/pb_common.c ../../../nanopb/pb_encode.c ../../../nanopb/pb_decode.c
SOURCES = main.c protocol_cases.c host_critical_section.c ../../../testharness-c/src/tzen.c $(CODECS)
HEADERS = host_critical_section.h ../../../testharness-c/inc/tzen.h ../../../testharness-c/cfg/tzen_cfg.h ../../../ttp/C/inc/ttp.h ../../../ttp/C/generated/ttp.pb.h

.PHONY: all run check clean

all: $(TARGET)

$(TARGET): $(SOURCES) $(HEADERS)
	$(CC) $(CPPFLAGS) $(HOST_CPPFLAGS) $(CFLAGS) $(THREAD_FLAGS) $(LDFLAGS) $(SOURCES) $(LDLIBS) -o $@

run: $(TARGET)
	./$(TARGET)

test_rx.exe: ../../../testharness-c/tests/test_rx.c ../../../testharness-c/src/tzen.c host_critical_section.c $(CODECS) $(HEADERS)
	$(CC) $(CPPFLAGS) $(HOST_CPPFLAGS) -DTZEN_TH_TEST_CONCURRENT $(CFLAGS) $(THREAD_FLAGS) $(LDFLAGS) $< host_critical_section.c $(CODECS) $(LDLIBS) -o $@

test_rx_single.exe: ../../../testharness-c/tests/test_rx.c ../../../testharness-c/src/tzen.c $(CODECS) $(HEADERS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< $(CODECS) $(LDLIBS) -o $@

test_tx.exe: ../../../testharness-c/tests/test_tx.c ../../../testharness-c/src/tzen.c $(CODECS) $(HEADERS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< $(CODECS) $(LDLIBS) -o $@

test_tx_large.exe: ../../../testharness-c/tests/test_tx.c ../../../testharness-c/src/tzen.c $(CODECS) $(HEADERS)
	$(CC) $(CPPFLAGS) -DTZEN_TH_MAX_PACKET_SIZE=600 $(CFLAGS) $(LDFLAGS) $< $(CODECS) $(LDLIBS) -o $@

test_workers.exe: ../../../testharness-c/tests/test_workers.c ../../../testharness-c/src/tzen.c host_critical_section.c $(CODECS) $(HEADERS)
	$(CC) $(CPPFLAGS) $(HOST_CPPFLAGS) -DTZEN_TH_TEST_WORKERS_CONCURRENT $(CFLAGS) $(THREAD_FLAGS) $(LDFLAGS) $< host_critical_section.c $(CODECS) $(LDLIBS) -o $@

test_workers_small.exe: ../../../testharness-c/tests/test_workers.c ../../../testharness-c/src/tzen.c $(CODECS) $(HEADERS)
	$(CC) $(CPPFLAGS) -DTZEN_TH_MAX_WORKERS=1 -DTZEN_TH_RESULT_QUEUE_DEPTH=2 $(CFLAGS) $(LDFLAGS) $< $(CODECS) $(LDLIBS) -o $@

check: $(TARGET) test_rx.exe test_rx_single.exe test_tx.exe test_tx_large.exe test_workers.exe test_workers_small.exe
	./$(TARGET)
	./test_rx.exe
	./test_rx_single.exe
	./test_tx.exe
	./test_tx_large.exe
	./test_workers.exe
	./test_workers_small.exe

clean:
	$(RM) $(TARGET) test_rx.exe test_rx_single.exe test_tx.exe test_tx_large.exe test_workers.exe test_workers_small.exe
