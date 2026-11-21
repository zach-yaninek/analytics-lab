"""Errors with stable codes. Messages give codes, counts, column names and Excel row numbers, never cell values.

Exit codes of the command line (documented in trends/README.md): 0 OK or skipped; 1 a runtime check (C01) or the
privacy scan (P01) failed; 2 an input, parameter or output-folder problem (E01-E31); 3 unexpected (E99).
"""
import re

CODE_RE = re.compile(r'\b([ECP]\d{2})\b')        # a whole code in an error text: E01, E10, C01, P01, E99


def exit_code_for(code):
    """The exit code of an error code: 1 for C and P codes, 2 for E01-E98, 3 for E99 and anything else."""
    code = str(code or '')
    if re.fullmatch(r'[CP]\d{2}', code):
        return 1
    return 2 if re.fullmatch(r'E\d{2}', code) and code != 'E99' else 3


def stage_for(code, default='run'):
    """Where an error code stops a run, for the failure record: inputs (E01-E19), parameters (E20-E29), publish
    (E30-E39, the output folder), checks (C), privacy scan (P); `default` for anything else (E99)."""
    code = str(code or '')
    if re.fullmatch(r'E[01]\d', code):
        return 'inputs'
    if re.fullmatch(r'E2\d', code):
        return 'parameters'
    if re.fullmatch(r'E3\d', code):
        return 'publish'
    if re.fullmatch(r'C\d{2}', code):
        return 'checks'
    if re.fullmatch(r'P\d{2}', code):
        return 'privacy scan'
    return default


class TrendsError(Exception):
    """Base class. `code` is stable (documented in trends/README.md); `fix` tells the analyst what to do. Raised as
    such only for E99 (unexpected, exit 3). `stage` says where the run stopped; `failure_record` is set to
    (path or None, note) once the failure has been recorded in OUTPUT_DIR/failed/ (or deliberately not)."""
    exit_code = 3

    def __init__(self, code, message, fix=None, stage=None):
        self.code, self.message, self.fix = code, message, fix
        self.stage = stage
        self.failure_record = None
        super().__init__(self.text())

    def text(self):
        return f'{self.code}: {self.message}' + (f'\n  Fix: {self.fix}' if self.fix else '')


class ConfigError(TrendsError):
    """A parameter is missing, misspelt or invalid (exit 2)."""
    exit_code = 2

    def __init__(self, problems):
        self.problems = list(problems)       # [(code, message, fix)]
        first = self.problems[0]
        super().__init__(first[0], first[1], first[2])

    def text(self):
        lines = [f'{len(self.problems)} parameter problem(s):'] if len(self.problems) > 1 else []
        for code, message, fix in self.problems:
            lines.append(f'{code}: {message}' + (f'\n  Fix: {fix}' if fix else ''))
        return '\n'.join(lines)


class InputError(TrendsError):
    """An input file is missing or cannot be read as expected (exit 2)."""
    exit_code = 2


class OutputError(TrendsError):
    """OUTPUT_DIR cannot take the run: a file in it is locked (E30), or it is inside a git work tree that does not
    ignore it (E31) (exit 2)."""
    exit_code = 2


class CheckError(TrendsError):
    """A runtime invariant failed: the numbers would not add up, so nothing is published (exit 1)."""
    exit_code = 1


class PrivacyError(TrendsError):
    """The privacy scan found a real identifier in an output; nothing is published (exit 1)."""
    exit_code = 1


class NotebookError(TrendsError):
    """`ipa-trends run --engine notebook`: the notebook stopped with `code`. text() is the notebook's own error
    message; the exit code is the code's (E99, exit 3, when the notebook stopped on anything but a coded error)."""

    def __init__(self, code, text, stage=None):
        self._text = text
        super().__init__(code, text, stage=stage)
        self.exit_code = exit_code_for(code)

    def text(self):
        return self._text
