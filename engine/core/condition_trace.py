from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ConditionTraceNode:
    label: str
    value: bool
    detail: str | None = None
    children: tuple["ConditionTraceNode", ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class ConditionEvaluation:
    value: bool
    trace: ConditionTraceNode


def format_condition_trace(label: str, evaluation: ConditionEvaluation) -> str:
    lines = [f"[Condition Trace] {label}:"]
    lines.extend(_format_trace_node(evaluation.trace, "  ", is_last=False))
    lines.append(f"  └─ Result: {_bool_text(evaluation.value)}")
    return "\n".join(lines)


def _format_trace_node(
    node: ConditionTraceNode,
    prefix: str,
    is_last: bool,
) -> list[str]:
    connector = "└─" if is_last else "├─"
    lines = [f"{prefix}{connector} {node.label}: {_bool_text(node.value)}{_detail(node.detail)}"]
    child_prefix = f"{prefix}{'   ' if is_last else '│  '}"
    child_count = len(node.children)
    for index, child in enumerate(node.children):
        lines.extend(_format_trace_node(child, child_prefix, index == child_count - 1))
    return lines


def _bool_text(value: bool) -> str:
    if value:
        return "TRUE"
    return "FALSE"


def _detail(value: str | None) -> str:
    if value is None:
        return ""
    return f" ({value})"
