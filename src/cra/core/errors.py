"""统一异常体系。"""

from __future__ import annotations


class CodeReviewError(Exception):
    """所有自定义异常的基类。"""


class ScmError(CodeReviewError):
    """SCM 平台相关错误（API 失败、权限不足等）。"""


class LlmError(CodeReviewError):
    """LLM 调用错误（超时、限流、上下文超限等）。"""


class ContextError(CodeReviewError):
    """上下文构建错误（AST 解析失败、文件过大等）。"""


class AgentError(CodeReviewError):
    """Agent 执行错误。"""


class ReviewAbortedError(CodeReviewError):
    """审查被中止（预算超限、致命错误等）。"""
