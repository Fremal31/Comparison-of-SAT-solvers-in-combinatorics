from pathlib import Path
from typing import List, NamedTuple, Union


class CmdResult(NamedTuple):
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
    Resolve option tokens and build the final subprocess command.

    Tokens:
      {input}  — replaced with input_path; auto-appended if absent
      {output} — replaced with output_path; solver writes to file itself
      <        — feed input_path via stdin; suppresses {input} from args if present
      >        — redirect stdout to output_path via pipe

    Priority rule: if both {output} and > are present, {output} wins —
    the solver writes to the file itself and stdout is NOT piped.

    Returns:
        CmdResult(cmd, use_stdin, use_stdout_pipe)
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
