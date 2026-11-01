CC = gcc
CPPFLAGS += -I../../testharness-c/inc -I../../testharness-c/cfg
CFLAGS ?= -std=c11 -Wall -Wextra -Wpedantic -g

TARGET = tzen_host.exe
SOURCES = main.c ../../testharness-c/src/tzen.c
HEADERS = ../../testharness-c/inc/tzen.h ../../testharness-c/cfg/tzen_cfg.h

.PHONY: all run clean

all: $(TARGET)

$(TARGET): $(SOURCES) $(HEADERS)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) $(SOURCES) $(LDLIBS) -o $@

run: $(TARGET)
	./$(TARGET)

clean:
	$(RM) $(TARGET)
