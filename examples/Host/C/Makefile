CC = gcc
PYTHON ?= python
CPPFLAGS += -I. -I../../../testharness-c/inc
CPPFLAGS += '-DTZEN_CONFIG_HEADER="tzen_host_cfg.h"'
CPPFLAGS += -I../../../ttp/C/inc -I../../../ttp/C/generated -I../../../nanopb
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -g
TARGET = tzen_host.exe
SOURCES = main.c testcases.c tzen_host_cfg.c ../../../testharness-c/src/tzen.c ../../../ttp/C/src/ttp.c ../../../ttp/C/generated/ttp.pb.c ../../../nanopb/pb_common.c ../../../nanopb/pb_encode.c ../../../nanopb/pb_decode.c
HEADERS = testcases.h tzen_host_cfg.h ../../../testharness-c/inc/tzen.h ../../../testharness-c/inc/tzen_types.h ../../../testharness-c/inc/tzen_context.h ../../../ttp/C/inc/ttp.h ../../../ttp/C/generated/ttp.pb.h
.PHONY: all run check clean
all: $(TARGET)
$(TARGET): $(SOURCES) $(HEADERS) Makefile
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(SOURCES) $(LDLIBS) -o $@
run check: $(TARGET)
	$(PYTHON) ../python/run.py --executable ./$(TARGET)
clean:
	$(RM) $(TARGET)
