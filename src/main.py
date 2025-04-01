from MultipleSolverRunner import MultiSolverManager
import graph

config_path = "./src/solverPaths.json"
cnf_files = [
    "./tests/spyTheory.cnf", "./tests/spyGoal.cnf"
    #"./tests/sudoku_sol1.cnf"
]

manager = MultiSolverManager(config_path, cnf_files)
results = manager.run_all(3)
manager.log_results(results, output_path="results/multi_solver_results.csv")


#for result in results:
#    print(result)
    
csv_path = "results/multi_solver_results.csv"

df = graph.read_results_from_csv(csv_path)
print(df)
    
#if df is not None:
 #   print("Data Summary:")
  #  print(df.describe(include='all'))
  #  print("\nMissing Values:")
  #  print(df.isnull().sum())
    
    #graph.visualize_results(df)