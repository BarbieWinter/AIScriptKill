from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScriptEngineGraphError(Exception):
    def __str__(self) -> str:
        return "ScriptEngine graph has not been compiled"


@dataclass(frozen=True, slots=True)
class ScriptEngineGraphResultError(Exception):
    def __str__(self) -> str:
        return "ScriptEngine graph returned a non-state result"
