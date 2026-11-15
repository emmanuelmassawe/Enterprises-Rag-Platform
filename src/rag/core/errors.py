"""Transport-independent problem exceptions used at API boundaries."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ProblemException(Exception):
    """An expected application failure with a stable RFC 9457 problem code."""

    status: int
    code: str
    title: str
    detail: str
    headers: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.detail
