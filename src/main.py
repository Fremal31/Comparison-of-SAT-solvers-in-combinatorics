from MultipleSolverRunner import MultiSolverManager

config_path = "./src/solverPaths.json"
cnf_files = [
    "./tests/spyTheory.cnf", "./tests/spyGoal.cnf"
]

manager = MultiSolverManager(config_path, cnf_files)
results = manager.run_all(timeout=300)
manager.log_results(results, output_path="results/multi_solver_results.csv")

for result in results:
    print(result)