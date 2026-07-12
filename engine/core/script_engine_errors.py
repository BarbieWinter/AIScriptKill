"""定义剧本状态机抛出的稳定异常。"""


class ScriptEngineGraphError(Exception):
    """报告使用了尚未编译 LangGraph 的引擎。"""

    def __str__(self) -> str:
        return "ScriptEngine graph has not been compiled"


class ScriptEngineGraphResultError(Exception):
    """报告 LangGraph 返回了未预期的非映射结果。"""

    def __str__(self) -> str:
        return "ScriptEngine graph returned a non-state result"


class ScriptEngineActionError(Exception):
    """携带玩家动作被拒绝时的稳定错误码和消息。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
