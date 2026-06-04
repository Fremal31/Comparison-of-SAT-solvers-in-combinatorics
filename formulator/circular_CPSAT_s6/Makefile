# Build the circular_CPSAT wrapper around ba-graph + Google OR-Tools.
#
# Mirrors circular_SAT/Makefile but adds OR-Tools linkage, since this
# wrapper builds the CP-SAT model in-process rather than emitting a
# file.
#
# Prerequisites:
#   1. ba-graph at ../../ba-graph (override with BA_GRAPH_ROOT=...).
#   2. OR-Tools C++ development files. Either:
#        - install a system package that provides pkg-config 'ortools'
#          (rare), OR
#        - download a release tarball from
#          https://github.com/google/or-tools/releases and set
#          ORTOOLS_ROOT=/path/to/or-tools_<version>
#
# Build:
#   make                                  # uses pkg-config
#   make ORTOOLS_ROOT=/opt/or-tools_9.x   # uses a release tarball
#   make BA_GRAPH_ROOT=/some/path/ba-graph
#   make debug                            # -O0 -g + BA_GRAPH_DEBUG
#
# If neither pkg-config nor ORTOOLS_ROOT is available, the build will
# fail with a clear error message.

BA_GRAPH_ROOT ?= ../../ba-graph
BA_GRAPH_INCLUDES := -I$(BA_GRAPH_ROOT)/include
NAUTY_LIB         := $(BA_GRAPH_ROOT)/third_party/nauty/current/nauty.a

CXX      ?= g++
CXXFLAGS ?= -std=c++20 -O2 -Wall -Wextra -pedantic
LDFLAGS  ?=

# Locate OR-Tools. Order of preference:
#   1. Explicit ORTOOLS_ROOT (a release tarball).
#   2. pkg-config 'ortools'.
ifneq ($(ORTOOLS_ROOT),)
    # These match the flags OR-Tools' own example Makefile passes to the
    # compiler (see or-tools_release/Makefile, target 'build'). The crucial
    # one is -DOR_PROTO_DLL= : without it the generated protobuf headers
    # declare classes with an undefined macro and fail with "incomplete
    # type". -isystem (not -I) suppresses the many warnings the bundled
    # abseil/protobuf headers would otherwise emit.
    ORTOOLS_CFLAGS := -DBA_GRAPH_HAS_ORTOOLS_SUPPORT=1 \
                       -DOR_PROTO_DLL= -DPROTOBUF_USE_DLLS -DEIGEN_MPL2_ONLY \
                       -DUSE_BOP -DUSE_CBC -DUSE_CLP -DUSE_GLOP -DUSE_HIGHS \
                       -DUSE_MATH_OPT -DUSE_PDLP -DUSE_SCIP \
                       -fwrapv -Wno-sign-compare -Wno-invalid-offsetof \
                       -isystem $(ORTOOLS_ROOT)/include \
                       -isystem $(ORTOOLS_ROOT)/include/coin \
                       -isystem $(ORTOOLS_ROOT)/include/highs \
                       -isystem $(ORTOOLS_ROOT)/include/eigen3
    # Release tarballs put .so files in lib64 (Fedora) or lib (Debian).
    ORTOOLS_LIBS   := -L$(ORTOOLS_ROOT)/lib64 -L$(ORTOOLS_ROOT)/lib \
                       -lortools \
                       -Wl,-rpath,$(ORTOOLS_ROOT)/lib64 \
                       -Wl,-rpath,$(ORTOOLS_ROOT)/lib
else ifneq ($(shell pkg-config --exists ortools 2>/dev/null && echo yes),)
    ORTOOLS_CFLAGS := -DBA_GRAPH_HAS_ORTOOLS_SUPPORT=1 $(shell pkg-config --cflags ortools)
    ORTOOLS_LIBS   := $(shell pkg-config --libs ortools)
else
    ORTOOLS_CFLAGS :=
    ORTOOLS_LIBS   :=
endif

TARGET := circular_CPSAT
SRC    := main.cpp

.PHONY: all debug clean check-ortools

all: check-ortools $(TARGET)

check-ortools:
	@if [ -z "$(ORTOOLS_LIBS)" ]; then \
	    echo "ERROR: OR-Tools not found." >&2; \
	    echo "  Set ORTOOLS_ROOT=/path/to/or-tools_release, or install" >&2; \
	    echo "  an ortools package that provides pkg-config 'ortools'." >&2; \
	    echo "  Releases: https://github.com/google/or-tools/releases" >&2; \
	    exit 1; \
	fi

$(TARGET): $(SRC)
	$(CXX) $(CXXFLAGS) $(BA_GRAPH_INCLUDES) $(ORTOOLS_CFLAGS) $(SRC) \
	    -o $(TARGET) $(LDFLAGS) $(ORTOOLS_LIBS) \
	    $(if $(wildcard $(NAUTY_LIB)),$(NAUTY_LIB),)

debug: CXXFLAGS := -std=c++20 -O0 -g -Wall -Wextra -pedantic -DBA_GRAPH_DEBUG
debug: clean $(TARGET)

clean:
	rm -f $(TARGET)
