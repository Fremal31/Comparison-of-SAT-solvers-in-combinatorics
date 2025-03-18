import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

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
    sns.distplot(df["memory_peak_mb"])