# Build the circular_SAT formulator wrapper around ba-graph.
#
# Assumes ba-graph is cloned as a sibling of this repository (i.e. that
# ../../ba-graph/include exists). Override BA_GRAPH_ROOT on the command line
# if you keep ba-graph elsewhere:
#   make BA_GRAPH_ROOT=/some/path/ba-graph
#
# We do NOT link a SAT solver: the wrapper only emits DIMACS CNF on disk.
# Nauty is added because some ba-graph internals transitively reach into
# the bundled nauty headers; if your build does not need it the linker will
# silently drop the unused symbols.

BA_GRAPH_ROOT ?= ../../ba-graph
INCLUDES      := -I$(BA_GRAPH_ROOT)/include
NAUTY_LIB     := $(BA_GRAPH_ROOT)/third_party/nauty/current/nauty.a

CXX      ?= g++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -pedantic
LDFLAGS  ?=

TARGET   := circular_SAT
SRC      := main.cpp

.PHONY: all debug clean

all: $(TARGET)

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(INCLUDES) $(SRC) -o $(TARGET) $(LDFLAGS) \
		$(if $(wildcard $(NAUTY_LIB)),$(NAUTY_LIB),)

debug: CXXFLAGS := -std=c++20 -O0 -g -Wall -Wextra -pedantic -DBA_GRAPH_DEBUG
debug: clean $(TARGET)

clean:
	rm -f $(TARGET)
