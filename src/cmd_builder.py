import re
from pathlib import Path
from typing import Any, NamedTuple, Optional, Union

_PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")
"""Matches a single ``{name}`` placeholder. Used to detect unresolved tokens
left behind after substitution."""


class CmdResult(NamedTuple):
    """Result of build_cmd. *cmd* is the full argument list ready for subprocess.
    *use_stdin* indicates the input file should be fed via stdin. *use_stdout_pipe*
    indicates stdout should be redirected to the output file via a pipe."""
    cmd: list[str]
    use_stdin: bool
    use_stdout_pipe: bool


def build_cmd(
    executable: Union[str, Path],
    options: list[str],
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    parameters: Optional[dict[str, Any]] = None,
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
      {key}    — for each entry ``key -> value`` in *parameters*, replaced with
                 ``str(value)``. Lets formulators receive instance parameters
                 (e.g. p, q for circular colouring) on their command line.
      <        — opens *input_path* and feeds it to the process via stdin.
                 Suppresses any {input} token from the argument list.
      >        — redirects process stdout to *output_path* via a pipe.

    Priority rule: if both '>' and '{output}' are present, '{output}' wins —
    the solver writes to the file itself and stdout is not piped.

    If neither '>' nor '{output}' appear, stdout is captured via subprocess.PIPE
    by default (use_stdout_pipe=True).

    Raises ValueError if any ``{name}`` placeholder remains in an option after
    substitution — typically a typo or a parameter the caller forgot to declare.
    """
    parameters = parameters or {}
    use_stdin: bool = "<" in options
    use_stdout_pipe: bool = ">" in options
    contains_output: bool = any("{output}" in opt for opt in options)
    contains_input: bool = any("{input}" in opt for opt in options)
    raw_args: list[str] = options if (contains_input or use_stdin) else options + ["{input}"]

    final_args: list[str] = []
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
        for key, value in parameters.items():
            processed = processed.replace("{" + key + "}", str(value))
        leftover = _PLACEHOLDER_RE.search(processed)
        if leftover is not None:
            raise ValueError(
                f"Unresolved placeholder '{{{leftover.group(1)}}}' in option {arg!r}; "
                f"available parameters: {sorted(parameters)}"
            )
        final_args.append(processed)

    if contains_output:
        use_stdout_pipe = False
    elif not use_stdout_pipe:
        use_stdout_pipe = True  # default: capture stdout via pipe

    return CmdResult([str(executable)] + final_args, use_stdin, use_stdout_pipe)
