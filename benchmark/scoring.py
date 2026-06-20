"""Scoring utilities adapted from upstream FastContext benchmark/evaluation/utils.py.

Calculates file-level and line-level precision, recall, F1, and explore_score
for citation quality evaluation.
"""

import re


def parse_final_answer(text: str, workspace: str = "") -> list[dict]:
    """Extract citations from a <final_answer> block, stripping workspace prefix."""
    if text is None:
        return []

    fa_match = re.search(r"<final_answer>(.*?)</final_answer>", text, re.DOTALL)
    if fa_match is None:
        return []

    citations = []
    for entry in fa_match.group(1).strip().splitlines():
        entry = entry.strip()
        if not entry:
            continue
        match = re.match(r"(.+?):(\d+(?:-\d+)?)\s*(.*)", entry)
        if match:
            file_path = match.group(1).strip()
            if workspace and file_path.startswith(workspace):
                file_path = file_path[len(workspace):]
            file_path = file_path.lstrip("/")
            line_range = match.group(2).strip()
            start_line, end_line = (
                line_range.split("-") if "-" in line_range else (line_range, line_range)
            )
            citations.append({
                "path": file_path,
                "start_line": int(start_line),
                "end_line": int(end_line),
            })
    return citations


FILE_TYPES = [
    ".c", ".cpp", ".h", ".hpp", ".go", ".java", ".js", ".ts", ".tsx",
    ".php", ".rb", ".rs", ".py", ".md",
]


def parse_patch(patch_text: str, workspace: str = "", file_types: list[str] | None = None) -> list[dict]:
    """Extract edited file+line ranges from a unified diff patch."""
    if file_types is None:
        file_types = FILE_TYPES

    file_pattern = re.compile(r"^diff --git a/(.+) b/(.+)$", re.MULTILINE)
    file_sections = re.split(r"(?=^diff --git a/)", patch_text, flags=re.MULTILINE)
    file_sections = [s for s in file_sections if s]

    edits = []
    for section in file_sections:
        files = file_pattern.findall(section)
        if len(files) != 1:
            continue
        file_path = files[0][0]
        if file_types and not any(file_path.endswith(ft) for ft in file_types):
            continue
        if workspace and file_path.startswith(workspace):
            file_path = file_path[len(workspace):]

        hunks = re.split(r"(?=^@@ -\d+,\d+ \+\d+,\d+ @@)", section, flags=re.MULTILINE)
        for h in hunks:
            hunk_match = re.match(r"^@@ -(\d+),(\d+) \+(\d+),(\d+) @@", h)
            if not hunk_match:
                continue
            old_start = int(hunk_match.group(1))
            old_lines = int(hunk_match.group(2))
            if old_start == 0 and old_lines == 0:
                continue
            edits.append({
                "path": file_path,
                "start_line": old_start,
                "end_line": old_start + old_lines - 1,
            })
    return edits


def calculate_explore_score(precision, recall, n_citation, n_label=3.0, beta=0.5, lmbda=0.1):
    if (precision + recall) == 0:
        return 0.0
    f_beta = (1 + beta**2) * (precision * recall) / ((beta**2 * precision) + recall)
    penalty = lmbda * max(0, (n_citation - n_label) / n_label)
    return f_beta - penalty


def score_file(edit_true: list[dict], citations_pred: list[dict]) -> dict:
    true_files = set(e["path"] for e in edit_true)
    pred_files = set(c["path"] for c in citations_pred)
    overlap = true_files & pred_files

    precision = len(overlap) / len(pred_files) if pred_files else 0.0
    recall = len(overlap) / len(true_files) if true_files else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    score = calculate_explore_score(precision, recall, len(pred_files), n_label=len(true_files))

    return {
        "score": score,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_pred": len(pred_files),
        "n_true": len(true_files),
    }


def score_line(edit_true: list[dict], citations_pred: list[dict]) -> dict:
    true_lines = set()
    for e in edit_true:
        for line in range(e["start_line"], e["end_line"] + 1):
            true_lines.add((e["path"], line))

    pred_lines = set()
    for c in citations_pred:
        for line in range(c["start_line"], c["end_line"] + 1):
            pred_lines.add((c["path"], line))

    overlap = true_lines & pred_lines

    precision = len(overlap) / len(pred_lines) if pred_lines else 0.0
    recall = len(overlap) / len(true_lines) if true_lines else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    score = calculate_explore_score(precision, recall, len(pred_lines), n_label=len(true_lines))

    return {
        "score": score,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "n_pred": len(pred_lines),
        "n_true": len(true_lines),
    }
