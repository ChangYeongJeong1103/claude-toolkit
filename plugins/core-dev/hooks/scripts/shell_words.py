"""Shared shell-command splitting for core-dev guards (a heuristic, not a full shell parser).

Quoted strings and heredoc bodies are treated as data, so text inside a commit message,
PR body, or heredoc is never mistaken for a command.
"""
import os
import re
import shlex

SEP_CHARS = set(";&|()`\n")
REDIR_OP_RE = re.compile(r"[<>&|]*[<>][<>&|]*")
HEREDOC_RE = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)([A-Za-z_]\w*)\1")
FALLBACK_SEP_RE = re.compile(r"&&|\|\||\$\(|[;&|\n()`]")
FALLBACK_REDIRECT_RE = re.compile(r">>?\|?\s*([^\s;&|<>()`]+)")
ASSIGN_RE = re.compile(r"^\w+=")
KEYWORDS = {"{", "}", "!", "if", "then", "else", "elif", "do", "while", "until"}
WRAPPERS = {  # wrapper command -> (options that take a value, positional args before the command)
    "sudo": ({"-u", "-g", "-C", "-D", "-U"}, 0),
    "env": ({"-u", "-C"}, 0),
    "nice": ({"-n"}, 0),
    "timeout": ({"-s", "-k"}, 1),
    "caffeinate": ({"-t", "-w"}, 0),
    "time": (set(), 0),
    "nohup": (set(), 0),
    "exec": (set(), 0),
}


def strip_prefix(words):
    """Drop leading variable assignments, shell keywords, and wrappers with their options."""
    i = 0
    while i < len(words):
        name = os.path.basename(words[i])
        if ASSIGN_RE.match(words[i]) or words[i] in KEYWORDS:
            i += 1
        elif name in WRAPPERS:
            opts, positional = WRAPPERS[name]
            i += 1
            while i < len(words) and words[i].startswith("-"):
                i += 2 if words[i] in opts else 1
            i += positional
        else:
            break
    return words[i:]


def strip_heredocs(cmd):
    """Drop heredoc bodies (data, not commands), keeping the line that opens each heredoc."""
    lines, out, i = cmd.split("\n"), [], 0
    while i < len(lines):
        out.append(lines[i])
        delims = [m.group(2) for m in HEREDOC_RE.finditer(lines[i])]
        i += 1
        for delim in delims:
            while i < len(lines) and lines[i].strip() != delim:
                i += 1
            i += 1  # the closing delimiter line
    return "\n".join(out)


def split_redirects(words):
    """Separate redirection operators and their operands; return (argv, write targets)."""
    argv, targets, i = [], [], 0
    while i < len(words):
        if REDIR_OP_RE.fullmatch(words[i]):
            if ">" in words[i] and i + 1 < len(words):
                targets.append(words[i + 1])
            i += 2
        else:
            argv.append(words[i])
            i += 1
    return argv, targets


def tokenize(cmd):
    """Quote-aware tokens; operators and newlines come out as separate punctuation tokens."""
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>`\n")
    lex.whitespace = " \t\r"  # a newline separates commands
    lex.whitespace_split = True
    lex.commenters = ""
    return list(lex)


def segments(cmd):
    """Yield (argv, write targets) for each simple command in a shell string."""
    cmd = strip_heredocs(cmd.replace("\\\n", " ")).replace("$(", "(")  # `$(` opens a subshell like `(`
    try:
        tokens = tokenize(cmd)
    except ValueError:  # unbalanced quotes: split on operators regardless of quoting (errs toward detection)
        for part in FALLBACK_SEP_RE.split(cmd):
            targets = [m.group(1) for m in FALLBACK_REDIRECT_RE.finditer(part)]
            argv = strip_prefix(FALLBACK_REDIRECT_RE.sub(" ", part).split())
            if argv or targets:
                yield argv, targets
        return
    words = []
    for tok in tokens + [";"]:
        if tok and set(tok) <= SEP_CHARS:
            argv, targets = split_redirects(words)
            argv = strip_prefix(argv)
            if argv or targets:
                yield argv, targets
            words = []
        else:
            words.append(tok)
