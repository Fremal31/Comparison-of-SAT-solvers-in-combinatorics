import csv
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from dataclasses import asdict
from typing import List
from pathlib import Path

from custom_types import Result


def log_results(results: List[Result], fieldnames: List[str], output_path: str) -> None:
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for res in results:
            res_dict = asdict(res) if isinstance(res, Result) else res
            if 'metrics' in res_dict:
                metrics = res_dict.pop('metrics')
                res_dict.update(metrics)
            row = {field: res_dict.get(field, "") for field in fieldnames}
            writer.writerow(row)


def read_results_from_csv(csv_path):
    try:
        df = pd.read_csv(csv_path)
        return df
    except FileNotFoundError:
        print(f"File {csv_path} not found.")
        return None
    except pd.errors.EmptyDataError:
        print(f"File {csv_path} is empty.")
        return None
    except pd.errors.ParserError:
        print(f"Could not parse the file {csv_path}.")
        return None
    
    
"""TODO: Not working yet"""
def visualize_results(df):
    if df is None or df.empty:
        print("Invalid data")
        return
    