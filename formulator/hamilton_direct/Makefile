# Build hamilton_direct (wrapper around ba-graph is_hamiltonian_basic).
# Mirrors formulator/circular_SAT/Makefile. Override BA_GRAPH_ROOT if needed.

BA_GRAPH_ROOT ?= ../../ba-graph
INCLUDES      := -I$(BA_GRAPH_ROOT)/include
NAUTY_LIB     := $(BA_GRAPH_ROOT)/third_party/nauty/current/nauty.a

CXX      ?= g++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -pedantic
LDFLAGS  ?=

TARGET   := hamilton_direct
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
