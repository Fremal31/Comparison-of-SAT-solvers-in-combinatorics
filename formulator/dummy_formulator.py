#!/usr/bin/env python3
import sys
import shutil
import os

def main():
    # Frameworks usually call: formulator <input_path> <output_path>
    if len(sys.argv) < 3:
        print("Usage: dummy_formulator.py <input> <output>")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    try:
        # Just copy the .g6 file to the 'model' location
        shutil.copy(input_path, output_path)
    except Exception as e:
        print(f"Error copying file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()