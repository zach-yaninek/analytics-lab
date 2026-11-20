"""Errors with stable codes. Messages give codes, counts, column names and Excel row numbers, never cell values."""


class TrendsError(Exception):
    """Base class. `code` is stable (documented in trends/README.md); `fix` tells the analyst what to do."""
    exit_code = 3

    def __init__(self, code, message, fix=None):
        self.code, self.message, self.fix = code, message, fix
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


class CheckError(TrendsError):
    """A runtime invariant failed: the numbers would not add up, so nothing is published (exit 1)."""
    exit_code = 1


class PrivacyError(TrendsError):
    """The privacy scan found a real identifier in an output; nothing is published (exit 1)."""
    exit_code = 1
