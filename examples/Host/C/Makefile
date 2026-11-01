CC = gcc
CPPFLAGS += -I../../../testharness-c/inc -I../../../testharness-c/cfg
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -g
HOST_CPPFLAGS = -include host_critical_section.h
THREAD_FLAGS = -pthread

TARGET = tzen_host.exe
SOURCES = main.c host_critical_section.c ../../../testharness-c/src/tzen.c
HEADERS = host_critical_section.h ../../../testharness-c/inc/tzen.h ../../../testharness-c/cfg/tzen_cfg.h

.PHONY: all run check clean

all: $(TARGET)

$(TARGET): $(SOURCES) $(HEADERS)
	$(CC) $(CPPFLAGS) $(HOST_CPPFLAGS) $(CFLAGS) $(THREAD_FLAGS) $(LDFLAGS) $(SOURCES) $(LDLIBS) -o $@

run: $(TARGET)
	./$(TARGET)

test_rx.exe: ../../../testharness-c/tests/test_rx.c ../../../testharness-c/src/tzen.c host_critical_section.c $(HEADERS)
	$(CC) $(CPPFLAGS) $(HOST_CPPFLAGS) -DTZEN_TH_TEST_CONCURRENT $(CFLAGS) $(THREAD_FLAGS) $(LDFLAGS) $< host_critical_section.c $(LDLIBS) -o $@

test_rx_single.exe: ../../../testharness-c/tests/test_rx.c ../../../testharness-c/src/tzen.c $(HEADERS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< $(LDLIBS) -o $@

test_tx.exe: ../../../testharness-c/tests/test_tx.c ../../../testharness-c/src/tzen.c $(HEADERS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $< $(LDLIBS) -o $@

test_tx_large.exe: ../../../testharness-c/tests/test_tx.c ../../../testharness-c/src/tzen.c $(HEADERS)
	$(CC) $(CPPFLAGS) -DTZEN_TH_MAX_PACKET_SIZE=600 $(CFLAGS) $(LDFLAGS) $< $(LDLIBS) -o $@

check: $(TARGET) test_rx.exe test_rx_single.exe test_tx.exe test_tx_large.exe
	./$(TARGET)
	./test_rx.exe
	./test_rx_single.exe
	./test_tx.exe
	./test_tx_large.exe

clean:
	$(RM) $(TARGET) test_rx.exe test_rx_single.exe test_tx.exe test_tx_large.exe
