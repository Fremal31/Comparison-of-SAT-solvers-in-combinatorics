from pathlib import Path
from typing import List, NamedTuple, Union


class CmdResult(NamedTuple):
    """Result of build_cmd. *cmd* is the full argument list ready for subprocess.
    *use_stdin* indicates the input file should be fed via stdin. *use_stdout_pipe*
    indicates stdout should be redirected to the output file via a pipe."""
    cmd: List[str]
    use_stdin: bool
    use_stdout_pipe: bool


def build_cmd(
    executable: Union[str, Path],
    options: List[str],
    input_path: Union[str, Path],
    output_path: Union[str, Path],
) -> CmdResult:
    """
    Resolves option tokens and builds the final subprocess command.

    The *options* list may contain the following special tokens alongside
    regular flags:

      {input}  — replaced with the absolute path to *input_path* as a
                 command-line argument. Auto-appended if absent and '<' is
                 not present.
      {output} — replaced with the absolute path to *output_path* as a
                 command-line argument. The solver writes to the file itself
                 via its own flag.
      <        — opens *input_path* and feeds it to the process via stdin.
                 Suppresses any {input} token from the argument list.
      >        — redirects process stdout to *output_path* via a pipe.

    Priority rule: if both '>' and '{output}' are present, '{output}' wins —
    the solver writes to the file itself and stdout is not piped.

    If neither '>' nor '{output}' appear, stdout is captured via subprocess.PIPE
    by default (use_stdout_pipe=True).
    """
    use_stdin: bool = "<" in options
    use_stdout_pipe: bool = ">" in options
    contains_output: bool = any("{output}" in opt for opt in options)
    contains_input: bool = any("{input}" in opt for opt in options)
    raw_args: List[str] = options if (contains_input or use_stdin) else options + ["{input}"]

    final_args: List[str] = []
    for arg in raw_args:
        if arg == "<" or arg == ">":
            continue
        if use_stdin and "{input}" in arg:
            continue
        # only suppress {output} when > is used alone — if {output} is also present,
        # the solver writes to the file itself via its own flag, so keep the arg
        if use_stdout_pipe and not contains_output and "{output}" in arg:
            continue
        processed = arg.replace("{input}", str(input_path)).replace("{output}", str(output_path))
        final_args.append(processed)

    if contains_output:
        use_stdout_pipe = False
    elif not use_stdout_pipe:
        use_stdout_pipe = True  # default: capture stdout via pipe

    return CmdResult([str(executable)] + final_args, use_stdin, use_stdout_pipe)
