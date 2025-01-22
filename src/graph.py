import pandas as pd
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

def read_results_from_csv(csv_path):
    try:
        # Read the CSV file into a pandas DataFrame
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
    
    # Set up the figure size and style
    plt.figure(figsize=(12, 8))
    
    # Bar plot for CPU Time, Conflicts, and Decisions for each solver
    df.set_index('solver', inplace=True)  # Make solver names the index
    df[['time', 'conflicts', 'decisions']].plot(kind='bar', figsize=(12, 8))

    # Customizing the plot
    plt.title('Performance Comparison of SAT Solvers')
    plt.ylabel('Metrics')
    plt.xlabel('Solvers')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    plt.show()

def main():
    csv_path = "results/multi_solver_results.csv"

    # Read results from the CSV file
    df = read_results_from_csv(csv_path)

    # Visualize the results
    visualize_results(df)

if __name__ == "__main__":
    main()