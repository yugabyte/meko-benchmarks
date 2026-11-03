"""Plain-text score tables: markdown for docs, Unicode boxes for the terminal."""

import re

RULE = None  # a row equal to RULE draws a horizontal line in boxed(); markdown() skips it
_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def visible(s):
    """Length of a cell as printed, ignoring colour codes."""
    return len(_ANSI.sub("", str(s)))


class Table:
    """Columns may be grouped: groups = [(label, span), ...] draws a header line above."""

    def __init__(self, title, columns, rows, groups=None, wrap=None):
        """wrap: cells longer than this many characters continue on extra lines inside the same row."""
        self.title, self.columns, self.groups, self.wrap = title, columns, groups, wrap
        self.rows = [self._wrap_row(r) for r in rows] if wrap else rows

    def _wrap_row(self, row):
        if row is RULE:
            return row
        return [_wrap(str(c), self.wrap) if visible(c) > self.wrap else [str(c)] for c in row]

    @staticmethod
    def _flat(rows):
        """Expand wrapped rows (lists of lines per cell) into printable line rows."""
        out = []
        for r in rows:
            if r is RULE or not any(isinstance(c, list) for c in r):
                out.append(r)
                continue
            depth = max(len(c) if isinstance(c, list) else 1 for c in r)
            for i in range(depth):
                out.append([(c[i] if i < len(c) else "") if isinstance(c, list) else (c if i == 0 else "") for c in r])
        return out

    def markdown(self):
        rows = [r if r is RULE else [" ".join(c) if isinstance(c, list) else c for c in r] for r in self.rows]
        head = self.columns
        if self.groups:  # markdown can't merge cells: fold the group into each column name
            head, i = [], 0
            for label, span in self.groups:
                head += [f"{label} {c}".strip() for c in self.columns[i:i + span]]
                i += span
        lines = [f"### {self.title}", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        lines += ["| " + " | ".join(_ANSI.sub("", c) for c in r) + " |" for r in rows if r is not RULE]
        return "\n".join(lines)

    def boxed(self):
        rows = self._flat(self.rows)
        w = [max(visible(c) for c in col) for col in zip(self.columns, *[r for r in rows if r is not RULE])]
        if self.groups:  # widen columns so each group label fits across its span
            i = 0
            for label, span in self.groups:
                need = len(label) - (sum(w[i:i + span]) + 3 * (span - 1))
                for j in range(span):
                    w[i + j] += max(0, (need + span - 1) // span)
                i += span
        line = lambda l, m, r: l + m.join("─" * (x + 2) for x in w) + r
        cell = lambda vals: "│" + "│".join(f" {v}{' ' * (x - visible(v))} " for v, x in zip(vals, w)) + "│"
        out = [self.title] if self.title else []
        if self.groups:  # top border only breaks at group edges, since the group row has merged cells
            i, parts, spans = 0, [], []
            for label, span in self.groups:
                width = sum(w[i:i + span]) + 3 * (span - 1)
                parts.append(f" {label:^{width}} ")
                spans.append("─" * (width + 2))
                i += span
            out += ["┌" + "┬".join(spans) + "┐", "│" + "│".join(parts) + "│", line("├", "┼", "┤")]
        else:
            out.append(line("┌", "┬", "┐"))
        out += [cell(self.columns), line("├", "┼", "┤")]
        out += [line("├", "┼", "┤") if r is RULE else cell(r) for r in rows]
        out.append(line("└", "┴", "┘"))
        return "\n".join(out)


def kv_table(title, sections, columns=("setting", "value")):
    """A two-column box. `sections` is a list of lists of (key, value); a rule separates sections.
    Long values wrap onto continuation rows so the box stays narrow."""
    rows = []
    for i, section in enumerate(sections):
        if i:
            rows.append(RULE)
        for key, value in section:
            parts = _wrap(str(value), 96)
            rows.append([key, parts[0]])
            rows += [["", part] for part in parts[1:]]
    return Table(title, list(columns), rows)


def _wrap(text, width):
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}" if cur else w
    return lines + [cur] if cur or not lines else lines
