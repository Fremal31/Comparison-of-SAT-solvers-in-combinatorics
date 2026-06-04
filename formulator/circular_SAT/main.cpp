// Wrapper around ba-graph's circular-colouring CNF generators.
//
// Reads one graph (graph6) from --input, and for every (p, q) pair in --pq
// emits one DIMACS CNF file into --output describing the decision problem
// "does this graph admit a (p, q)-circular X-colouring?", where X = vertex
// or edge depending on --mode. Optional flags --precolouring and
// --without-tight-cycles select encoding variants from
// ba-graph/include/sat/cnf_circular_colouring.hpp.
//
// One invocation -> one (graph, mode, precolouring, tight-cycles) configuration,
// fanning out across the --pq list. The benchmarking framework's
// output_mode="directory" then turns each emitted file into its own TestCase.

#include <impl/basic/include.hpp>
#include <io/graph6.hpp>
#include <sat/cnf.hpp>
#include <sat/cnf_circular_colouring.hpp>

#include <cstdlib>
#include <exception>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace fs = std::filesystem;
using ba_graph::CNF;
using ba_graph::Edge;
using ba_graph::Factory;
using ba_graph::Graph;
using ba_graph::Vertex;

namespace {

struct Options {
    std::string input_path;
    std::string output_dir;
    std::string mode = "vertex";
    bool precolouring = false;
    bool without_tight_cycles = false;
    std::vector<std::pair<int, int>> pq_list;
};

[[noreturn]] void die(const std::string &msg, int code = 2) {
    std::cerr << msg << "\n";
    std::exit(code);
}

void usage(const char *prog) {
    std::cerr <<
        "Usage: " << prog << " --pq=p1/q1,p2/q2,... [options] <input.g6> <output_dir>\n"
        "\n"
        "Required:\n"
        "  --pq=LIST         comma-separated p/q pairs, e.g. 4/1,5/2,7/3\n"
        "\n"
        "Optional:\n"
        "  --mode=vertex|edge          (default: vertex)\n"
        "  --precolouring              auto-precolouring on (default: off)\n"
        "  --without-tight-cycles      use the _without_tight_cycles encoding\n";
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
        } else if (a == "--precolouring") {
            o.precolouring = true;
        } else if (a == "--without-tight-cycles") {
            o.without_tight_cycles = true;
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

    if (positional.size() != 2) {
        usage(argv[0]);
        die("Expected <input.g6> <output_dir>");
    }
    if (o.pq_list.empty()) {
        die("--pq is required");
    }
    if (o.mode != "vertex" && o.mode != "edge") {
        die("--mode must be 'vertex' or 'edge'");
    }
    o.input_path = std::move(positional[0]);
    o.output_dir = std::move(positional[1]);
    return o;
}

CNF build_cnf(const Graph &G, int p, int q, const Options &o) {
    if (o.mode == "vertex") {
        if (o.without_tight_cycles) {
            return ba_graph::cnf_circular_vertex_colouring_without_tight_cycles(
                G, p, q, o.precolouring);
        }
        return ba_graph::cnf_circular_vertex_colouring(G, p, q, o.precolouring);
    }
    // edge mode
    if (o.without_tight_cycles) {
        return ba_graph::cnf_circular_edge_colouring_without_tight_cycles(
            G, p, q, o.precolouring);
    }
    return ba_graph::cnf_circular_edge_colouring(G, p, q, o.precolouring);
}

std::string variant_tag(const Options &o) {
    std::string tag = (o.mode == "vertex" ? "v" : "e");
    if (o.without_tight_cycles) tag += "_notc";
    if (o.precolouring) tag += "_pre";
    return tag;
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

}  // namespace

int main(int argc, char **argv) {
    try {
        Options o = parse_args(argc, argv);
        fs::create_directories(o.output_dir);

        std::string g6 = read_first_nonempty_line(o.input_path);
        Factory factory;
        Graph G = ba_graph::internal_graph6::read_graph6_strict(g6, factory);

        const std::string tag = variant_tag(o);
        for (const auto &[p, q] : o.pq_list) {
            CNF cnf = build_cnf(G, p, q, o);
            std::string filename =
                "circ_" + tag + "_p" + std::to_string(p) +
                "_q" + std::to_string(q) + ".cnf";
            fs::path outpath = fs::path(o.output_dir) / filename;
            std::ofstream out(outpath);
            if (!out) {
                throw std::runtime_error(
                    "cannot open output file: " + outpath.string());
            }
            out << ba_graph::cnf_dimacs(cnf);
        }
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "circular_SAT: " << e.what() << "\n";
        return 1;
    }
}
