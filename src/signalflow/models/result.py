"""Explicit result models for SignalFlow control flow.

This module provides a small `Result` union used to make success and failure
explicit at subsystem boundaries. The result intentionally carries very little
data: successful results hold a value, while failed results signal that callers
must inspect diagnostics or choose another recovery path.

Key components:
    - ResultOk: Successful result carrying a value
    - ResultErr: Failed result carrying no value
    - Result: Union of success and failure results
    - resultOk_build: Helper for constructing a successful result
    - resultErr_build: Helper for constructing a failed result
    - result_isOkCheck: Type guard for successful results
    - result_isErrCheck: Type guard for failed results

Typical usage:
    layoutResult = resultOk_build("done")
    if result_isOkCheck(layoutResult):
        value = layoutResult.value

Dependencies:
    - Uses only standard-library typing helpers
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeAlias, TypeGuard, TypeVar

ResultValueT = TypeVar("ResultValueT")


@dataclass(frozen=True)
class ResultOk(Generic[ResultValueT]):
    """Successful result carrying a value.

    Attributes:
        ok: Always `True` for the success variant.
        value: Value produced by the successful operation.

    Example:
        >>> result = ResultOk(ok=True, value=5)
    """

    ok: bool
    value: ResultValueT


@dataclass(frozen=True)
class ResultErr(Generic[ResultValueT]):
    """Failed result carrying no value.

    Attributes:
        ok: Always `False` for the failure variant.

    Example:
        >>> result = ResultErr[int]()
    """

    ok: bool = False


Result: TypeAlias = ResultOk[ResultValueT] | ResultErr[ResultValueT]


def resultOk_build(value: ResultValueT) -> Result[ResultValueT]:
    """Build a successful result.

    Args:
        value: Success value to wrap in the result.

    Returns:
        Successful `Result` containing the provided value.
    """

    return ResultOk(ok=True, value=value)


def resultErr_build() -> Result[ResultValueT]:
    """Build a failed result.

    Returns:
        Failed `Result` containing no value.
    """

    return ResultErr()


def result_isOkCheck(
    result: Result[ResultValueT],
) -> TypeGuard[ResultOk[ResultValueT]]:
    """Return whether a result is the success variant.

    Args:
        result: Result value being tested.

    Returns:
        `True` when the result is successful and contains a value.
    """

    return result.ok is True


def result_isErrCheck(
    result: Result[ResultValueT],
) -> TypeGuard[ResultErr[ResultValueT]]:
    """Return whether a result is the failure variant.

    Args:
        result: Result value being tested.

    Returns:
        `True` when the result is a failure.
    """

    return result.ok is False
