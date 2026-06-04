// hamilton_direct: a non-SAT exact Hamiltonicity solver. Thin CLI wrapper
// around ba-graph's is_hamiltonian_basic() backtracking algorithm
// (algorithms/paths.hpp). It reads one graph6 graph and prints a DIMACS-style
// verdict so the framework's standard SAT parser ("s SATISFIABLE" /
// "s UNSATISFIABLE") can read it. SAT == graph is Hamiltonian.
//
// This is the dedicated-algorithm baseline for the Hamiltonicity comparison,
// analogous to how circular_CPSAT is the CP-SAT paradigm for circular colouring:
// it shares no code with the CNF encodings, so a SAT/UNSAT disagreement against
// the SAT solvers implicates an encoding rather than the verdict.
//
// Fed one graph per file (e.g. by formulator/g6_splitter.py).

#include <impl/basic/include.hpp>
#include <io/graph6.hpp>
#include <algorithms/paths.hpp>

#include <exception>
#include <fstream>
#include <iostream>
#include <string>

using ba_graph::Factory;
using ba_graph::Graph;

namespace {

std::string strip(std::string s) {
    while (!s.empty() && (s.back() == '\n' || s.back() == '\r' ||
                          s.back() == ' ' || s.back() == '\t')) {
        s.pop_back();
    }
    return s;
}

}  // namespace

int main(int argc, char **argv) {
    try {
        std::string input_path;
        for (int i = 1; i < argc; ++i) {
            std::string a = argv[i];
            if (a == "-h" || a == "--help") {
                std::cout << "Usage: " << argv[0] << " <input.g6>\n";
                return 0;
            }
            input_path = a;
        }
        if (input_path.empty()) {
            std::cerr << "hamilton_direct: missing input file\n";
            return 1;
        }

        std::ifstream file(input_path);
        if (!file) {
            std::cerr << "hamilton_direct: cannot open " << input_path << "\n";
            return 1;
        }

        std::string line, g6;
        while (std::getline(file, line)) {
            std::string s = strip(line);
            if (!s.empty() && s.rfind(">>", 0) != 0) { g6 = s; break; }
        }
        if (g6.empty()) {
            std::cerr << "hamilton_direct: no graph in input\n";
            return 1;
        }

        Factory factory;
        Graph G = ba_graph::internal_graph6::read_graph6_strict(g6, factory);
        bool hamiltonian = ba_graph::is_hamiltonian_basic(G);

        std::cout << (hamiltonian ? "s SATISFIABLE" : "s UNSATISFIABLE") << "\n";
        return hamiltonian ? 10 : 20;
    } catch (const std::exception &e) {
        std::cerr << "hamilton_direct: " << e.what() << "\n";
        return 1;
    }
}
