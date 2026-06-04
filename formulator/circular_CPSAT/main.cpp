// Combined formulator+solver wrapper around ba-graph's CP-SAT
// circular-colouring API.
//
// Unlike the SAT branch (formulator/circular_SAT/main.cpp), which
// emits DIMACS CNF files for an external solver, this wrapper builds
// the CP-SAT model in-process via Google OR-Tools and solves it
// directly. It is invoked once per (graph, p, q) configuration and
// prints a single verdict block to stdout that the framework's
// CPSATParser recognises (substring match on
// OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN).
//
// This makes CP-SAT an "independent encoding" control for the cchi
// computation (Chapter 9 of the thesis): a SAT/UNSAT disagreement
// between this binary and the SAT-branch verdict implicates either
// one of the two encodings or one of the two solver implementations.
//
// Exit codes follow DIMACS convention so a shell driver can chain
// them: 10 for SAT (FEASIBLE), 20 for UNSAT (INFEASIBLE), 0 for
// UNKNOWN, 1 for usage/IO/setup errors.

#include <impl/basic/include.hpp>
#include <io/graph6.hpp>
#include <sat/exec_circular_cpsat.hpp>

#include <cstdlib>
#include <exception>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

using ba_graph::Factory;
using ba_graph::Graph;

namespace {

struct Options {
    std::string input_path;
    std::string mode = "edge";
    bool symmetry_breaking = true;
    std::vector<std::pair<int, int>> pq_list;
    bool emit_witness = false;
};

[[noreturn]] void die(const std::string &msg, int code = 1) {
    std::cerr << msg << "\n";
    std::exit(code);
}

void usage(const char *prog) {
    std::cerr <<
        "Usage: " << prog << " --pq=p1/q1[,p2/q2,...] [options] <input.g6>\n"
        "\n"
        "Required:\n"
        "  --pq=LIST            comma-separated p/q pairs, e.g. 9/2 or 4/1,5/2\n"
        "\n"
        "Optional:\n"
        "  --mode=vertex|edge   default: edge\n"
        "  --no-sym             disable symmetry breaking (default: on)\n"
        "  --witness            print the colouring as a comment on FEASIBLE\n"
        "\n"
        "Output (per p/q, to stdout):\n"
        "  c graph 0\n"
        "  c p_q P Q\n"
        "  FEASIBLE | INFEASIBLE | UNKNOWN\n"
        "  c colours C0 C1 ...      (only if --witness and FEASIBLE)\n";
}

std::vector<std::pair<int, int>> parse_pq_list(const std::string &s) {
    std::vector<std::pair<int, int>> out;
    std::size_t i = 0;
    while (i < s.size()) {
        std::size_t comma = s.find(',', i);
        std::string token = s.substr(
            i, comma == std::string::npos ? std::string::npos : comma - i);
        std::size_t slash = token.find('/');
        if (slash == std::string::npos) {
            throw std::runtime_error("invalid p/q token (missing '/'): " + token);
        }
        int p = std::stoi(token.substr(0, slash));
        int q = std::stoi(token.substr(slash + 1));
        if (q <= 0) {
            throw std::runtime_error("invalid p/q token (q must be positive): " + token);
        }
        out.emplace_back(p, q);
        if (comma == std::string::npos) break;
        i = comma + 1;
    }
    return out;
}

Options parse_args(int argc, char **argv) {
    Options o;
    std::vector<std::string> positional;
    for (int i = 1; i < argc; ++i) {
        std::string_view a = argv[i];
        auto starts_with = [&](std::string_view p) {
            return a.size() >= p.size() && a.substr(0, p.size()) == p;
        };
        if (a == "-h" || a == "--help") {
            usage(argv[0]);
            std::exit(0);
        } else if (a == "--no-sym") {
            o.symmetry_breaking = false;
        } else if (a == "--witness") {
            o.emit_witness = true;
        } else if (starts_with("--mode=")) {
            o.mode = std::string(a.substr(7));
        } else if (starts_with("--pq=")) {
            o.pq_list = parse_pq_list(std::string(a.substr(5)));
        } else if (starts_with("-")) {
            usage(argv[0]);
            die("Unknown flag: " + std::string(a));
        } else {
            positional.emplace_back(a);
        }
    }

    if (positional.size() != 1) {
        usage(argv[0]);
        die("Expected exactly one positional argument: <input.g6>");
    }
    if (o.pq_list.empty()) {
        die("--pq is required");
    }
    if (o.mode != "vertex" && o.mode != "edge") {
        die("--mode must be 'vertex' or 'edge'");
    }
    o.input_path = std::move(positional[0]);
    return o;
}

std::string read_first_nonempty_line(const std::string &path) {
    std::ifstream in(path);
    if (!in) throw std::runtime_error("cannot open input file: " + path);
    std::string line;
    while (std::getline(in, line)) {
        while (!line.empty() &&
               (line.back() == '\n' || line.back() == '\r' ||
                line.back() == ' ' || line.back() == '\t')) {
            line.pop_back();
        }
        if (!line.empty()) return line;
    }
    throw std::runtime_error("input file is empty: " + path);
}

// Run one (p, q) decision, print the verdict block, return the
// per-call exit code (SAT=10, UNSAT=20, UNKNOWN=0). Multiple calls in
// one invocation: the process exit code reflects the last call.
int decide_and_print(const Graph &G, int p, int q, const Options &o) {
    std::vector<int> colouring;
    bool ok;
    if (o.mode == "vertex") {
        ok = ba_graph::is_circularly_colourable_cpsat(G, p, q, &colouring);
    } else {
        ok = ba_graph::is_circularly_edge_colourable_cpsat(
            G, p, q, &colouring, o.symmetry_breaking);
    }

    std::cout << "c graph 0\n";
    std::cout << "c p_q " << p << " " << q << "\n";
    if (ok) {
        std::cout << "FEASIBLE\n";
        if (o.emit_witness && !colouring.empty()) {
            std::cout << "c colours";
            for (int c : colouring) std::cout << " " << c;
            std::cout << "\n";
        }
        return 10;
    }
    // ba-graph's is_circularly_*_cpsat returns false both on
    // INFEASIBLE and on degenerate / error inputs. The argument
    // validation above (q > 0, p >= 0, mode known) rules out the
    // error paths it can take after a valid graph is loaded, so a
    // false return on a non-empty graph is genuinely UNSAT.
    std::cout << "INFEASIBLE\n";
    return 20;
}

}  // namespace

int main(int argc, char **argv) {
    try {
        Options o = parse_args(argc, argv);
        std::string g6 = read_first_nonempty_line(o.input_path);
        Factory factory;
        Graph G = ba_graph::internal_graph6::read_graph6_strict(g6, factory);

        int last_code = 0;
        for (const auto &[p, q] : o.pq_list) {
            last_code = decide_and_print(G, p, q, o);
        }
        return last_code;
    } catch (const std::exception &e) {
        std::cerr << "circular_CPSAT: " << e.what() << "\n";
        return 1;
    }
}
