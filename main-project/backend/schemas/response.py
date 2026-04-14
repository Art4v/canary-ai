"""
Standardised response helpers.

Every database endpoint returns either ``success_response(data)`` on
success or ``error_response(msg)`` wrapped in a ``JSONResponse`` on
failure, giving the frontend a consistent shape to parse.
"""

from typing import Any


def success_response(data: Any) -> dict:
    """
    Wrap *data* in the canonical success envelope.

    Parameters
    ----------
    data : Any
        The payload (usually a list of row dicts or a single row dict).

    Returns
    -------
    dict
        ``{"success": True, "data": data}``
    """
    return {"success": True, "data": data}


def error_response(msg: str) -> dict:
    """
    Build the canonical error envelope.

    Parameters
    ----------
    msg : str
        Human-readable error description.

    Returns
    -------
    dict
        ``{"success": False, "error": msg}``
    """
    return {"success": False, "error": msg}
