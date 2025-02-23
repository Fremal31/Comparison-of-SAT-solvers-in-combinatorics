#!/usr/bin/python3
import sys
D = 3    # Subgrid dimension
N = D*D  # Grid dimension

# The symbols allowed in the Sudoku instance text file
DIGITS = {'1':1, '2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9}
NOCLUE = '.'

def read_clues(filename: str):
    """Read a Sudoku instance (a set of clues) from a file."""
    clues = []
    with open(filename, 'r', encoding='UTF-8') as handle:
        for line in handle.readlines():
            line = line.strip()
            assert len(line) == N, f'Malformed line "{line}"'
            for column in range(0, N):
                assert line[column] in DIGITS.keys() or line[column] == NOCLUE
            clues.append(line.strip())
    assert len(clues) == N
    return clues

def encode(clues):
    """Encode the given clueas as DIMACS CNF SAT instance
    in the standard output."""

    def var(row: int, column: int, value: int):
        """A helper: get the DIMACS CNF variable number for
        the variable v_{row,column,value} encoding the fact that
        the cell at (row,column) has the value "value"."""
        assert 1 <= row <= N and 1 <= column <= N and 1 <= value <= N
        return (row-1)*N*N+(column-1)*N+(value-1)+1

    # Build the clauses in a list
    clauses = []  # The clauses: a list of integer lists
    for row in range(1, N+1): # row runs over 1,...,N
        for column in range(1, N+1):
            # The cell at (row,column) has at least one value
            clauses.append([var(row, column, value) for value in range(1, N+1)])
            # The cell at (row,column) has at most one value
            for value in range(1, N+1):
                for walue in range(value+1, N+1):
                    clauses.append([-var(row, column, value),
                                    -var(row, column, walue)])
    for value in range(1, N+1):
        # Each row has the value
        for row in range(1, N+1):
            clauses.append([var(row, column, value) for column in range(1, N+1)])
        # Each column has the value
        for column in range(1, N+1):
            clauses.append([var(row, column, value) for row in range(1, N+1)])
        # Each subgrid has the value
        for sr in range(0, D):
            for sc in range(0, D):
                clauses.append([var(sr*D+rd, sc*D+cd, value)
                                for rd in range(1, D+1)
                                for cd in range(1, D+1)])
    # The clues must be respected
    for row in range(1, N+1):
        for column in range(1, N+1):
            clue = clues[row-1][column-1]
            if clue in DIGITS.keys():
                clauses.append([var(row, column, DIGITS[clue])])

    # Output the DIMACS CNF representation
    # Print the header line
    with open("sudoku_sol1.cnf", "w") as f:
        f.write('p cnf %d %d\n' % (N*N*N, len(clauses)))
        # Print the clauses
        for clause in clauses:
            f.write(' '.join([str(lit) for lit in clause])+' 0\n')

if __name__ == '__main__':
    # Read the clues from the file given as the first argument,
    # and encode them as a CNF SAT instance
    encode(read_clues(sys.argv[1]))