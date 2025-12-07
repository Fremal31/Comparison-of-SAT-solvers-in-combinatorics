from pathlib import Path
from typing import List, Optional
from .SolverRunner import CNFFile
import subprocess
import tempfile
import sys

class Converter:
    def __init__(self, converter_path: Path, graph_file: Path, use_temp: bool = True, output_path: Optional[Path] = None) -> None:
        self.converter_path: Path = converter_path
        self.cnf_files: List[CNFFile] = []
        self.use_temp:bool = use_temp
        self.output_path: Optional[Path] = output_path
        self.graph_file = graph_file
        self.graphs: List[str] = self.read_graphs(self.graph_file)
    
        
    def read_graphs(self, graph_file: Path) -> List[str]:
        graphs: List[str] = []
        with open(graph_file, "r") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith(">>"):
                    continue
                graphs.append(s)
        return graphs
    
    def run_converter(self) -> List[CNFFile]:

        for i, graph in enumerate(self.graphs):
            if self.use_temp:
                if self.output_path is not None:
                    raise ValueError("Output file specified when using temp files.")

                tmpf = tempfile.NamedTemporaryFile(mode="w+", suffix=".cnf", delete=False)
                tmpf_path = Path(tmpf.name)
                tmpf.close()

                with tempfile.NamedTemporaryFile(mode="w+", suffix=".g6", delete=False) as g6f:
                    g6f.write(graph + "\n")
                    g6f.flush()
                    g6f_path = Path(g6f.name)

                cmd = ["python3", str(self.converter_path), str(g6f_path)]
                proc = subprocess.run(cmd, stdout=open(tmpf_path, "w"), stderr=subprocess.PIPE, text=True)

                if proc.returncode != 0:
                    print(f"Converter failed on graph {i}: {proc.stderr}", file=sys.stderr)
                    continue

                self.cnf_files.append(CNFFile(name=f"{self.graph_file}_{i}", path=tmpf_path))

        print(self.cnf_files)
        return self.cnf_files
