from pathlib import Path
from typing import List, Optional
from .SolverRunner import TestCase
import subprocess
import tempfile
import sys
import os

class Converter:
    def __init__(self, converter_path: Path, input_path: Path, use_temp: bool = True, output_path: Optional[Path] = None) -> None:
        self.input_path = input_path
        if not os.path.exists(self.input_path):
            raise FileNotFoundError(f"Input path not found: {self.input_path}")
        self.converter_path: Path = converter_path
        if not os.path.exists(self.converter_path):
            raise FileNotFoundError(f"Converter path not found: {self.converter_path}")
        self.cnf_files: List[TestCase] = []
        self.use_temp:bool = use_temp
        self.output_path: Optional[Path] = output_path
        self.inputs: List[str] = self.read_inputs(self.input_path)
    
        
    def read_inputs(self, input_path: Path) -> List[str]:
        inputs: List[str] = []
        with open(input_path, "r") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith(">>"):
                    continue
                inputs.append(s)
        return inputs
    
    def convert_all(self) -> List[TestCase]:
        for i, _input in enumerate(self.inputs):
            TestCase = self.convert(_input, i)
            if TestCase is not None:
                self.cnf_files.append(TestCase)

        print(self.cnf_files)
        return self.cnf_files
    
    def convert(self, _input: str, index: Optional[int] = None) -> Optional[TestCase]:
        if self.use_temp:
            if self.output_path is not None:
                raise ValueError("Output file specified when using temp files.")

            tmpf = tempfile.NamedTemporaryFile(mode="w+", suffix=".cnf", delete=False)
            tmpf_path = Path(tmpf.name)
            tmpf.close()

            with tempfile.NamedTemporaryFile(mode="w+", suffix=".g6", delete=False) as g6f:
                g6f.write(_input + "\n")
                g6f.flush()
                g6f_path = Path(g6f.name)

            cmd = ["python3", str(self.converter_path), str(g6f_path)]
            proc = subprocess.run(cmd, stdout=open(tmpf_path, "w"), stderr=subprocess.PIPE, text=True)

            if proc.returncode != 0:
                print(f"Converter failed on graph {index if index is not None else ""}: {proc.stderr}", file=sys.stderr)
                return None
            return TestCase(name=f"{self.input_path}_{index}", path=tmpf_path) if index is not None else TestCase(name=f"{self.input_path}")
            
