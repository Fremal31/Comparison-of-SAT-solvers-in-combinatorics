// Hamiltonicity SAT formulator: a thin CLI wrapper around ba-graph's
// cnf_has_circuit(G, k) encoder. A graph is Hamiltonian iff it has a circuit
// of length k = n (the number of vertices), so we emit the CNF for
// cnf_has_circuit(G, G.order(), w) where w fixes the first vertex for symmetry
// breaking (same call is_hamiltonian_sat uses internally).
//
// Encoding (ba-graph cnf_circumference.hpp): positional variables x_{v,i}
// ("v is the i-th vertex of the cycle"). Mirrors how formulator/circular_SAT
// wraps ba-graph's cnf_circular_colouring.
//
// Reads graph6 from a file (or '-' for stdin). With --all every graph in the
// file is emitted; CNFs are separated by a blank line so the framework's
// output_mode="stdout_multi" turns each into its own TestCase. Without --all
// only the first graph is processed.

#include <impl/basic/include.hpp>
#include <io/graph6.hpp>
#include <sat/cnf.hpp>
#include <sat/cnf_circumference.hpp>

#include <cstdlib>
#include <exception>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>

using ba_graph::CNF;
using ba_graph::Factory;
using ba_graph::Graph;
using ba_graph::Number;

namespace {

std::string strip(std::string s) {
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' ||
                          s.back() == ' ' || s.back() == '\t')) {
        s.pop_back();
    }
    return s;
}

// Emits DIMACS asserting "G has a Hamiltonian cycle" to *out*. For n < 3 a
// simple graph has no cycle, so emit a trivially unsatisfiable formula.
void emit_hamiltonicity_dimacs(const Graph &G, std::ostream &out) {
    const int n = G.order();
    if (n < 3) {
        out << "p cnf 1 2\n1 0\n-1 0\n";
        return;
    }
    Number w = G.find(ba_graph::RP::all())->n();  // first vertex (symmetry break)
    CNF cnf = ba_graph::cnf_has_circuit(G, n, w);
    out << ba_graph::cnf_dimacs(cnf);
}

}  // namespace

int main(int argc, char **argv) {
    try {
        bool process_all = false;
        std::string input_path;
        for (int i = 1; i < argc; ++i) {
            std::string a = argv[i];
            if (a == "--all") {
                process_all = true;
            } else if (a == "--mode") {
                ++i;  // only the cycle encoding exists here; accept & ignore
            } else if (a == "-h" || a == "--help") {
                std::cout << "Usage: " << argv[0]
                          << " <input.g6|-> [--all] [--mode cycle]\n";
                return 0;
            } else {
                input_path = a;
            }
        }
        if (input_path.empty()) {
            std::cerr << "hamilton_baSAT: missing input file\n";
            return 1;
        }

        std::istream *in = &std::cin;
        std::ifstream file;
        if (input_path != "-") {
            file.open(input_path);
            if (!file) {
                std::cerr << "hamilton_baSAT: cannot open " << input_path << "\n";
                return 1;
            }
            in = &file;
        }

        std::string line;
        bool emitted = false;
        while (std::getline(*in, line)) {
            std::string g6 = strip(line);
            if (g6.empty() || g6.rfind(">>", 0) == 0) continue;

            if (emitted) std::cout << "\n";  // blank-line separator for stdout_multi

            Factory factory;
            Graph G = ba_graph::internal_graph6::read_graph6_strict(g6, factory);
            emit_hamiltonicity_dimacs(G, std::cout);
            emitted = true;

            if (!process_all) break;
        }
        if (!emitted) {
            std::cerr << "hamilton_baSAT: no graphs in input\n";
            return 1;
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "hamilton_baSAT: " << e.what() << "\n";
        return 1;
    }
}
