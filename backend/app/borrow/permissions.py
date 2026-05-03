"""
app/borrow/permissions.py
─────────────────────────
Fine-grained permission helpers for the Borrow module.

Why a separate file?
--------------------
auth/dependencies.py (M2) provides coarse-grained role guards:
    get_current_user  →  any authenticated user
    require_admin     →  admin role only

This module adds *resource-level* checks that depend on borrow-specific
business rules (e.g. "can this user see/cancel this particular borrow?").

Functions
---------
assert_can_view_borrow   – user can see their own borrows; admin sees all
assert_can_return_borrow – only the borrower or an admin can return
assert_can_cancel_borrow – only admin can hard-cancel (delete) a borrow record

Compatibility
-------------
• Imports User from app.models.user  (M1)
• Imports Borrow from app.borrow.model (M4 – this module)
• Raises HTTPException like M2 dependencies do
"""

from fastapi import HTTPException, status

from app.borrow.model import Borrow, BorrowStatus
from app.models.user import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_admin(user: User) -> bool:
    return user.role == UserRole.admin


# ---------------------------------------------------------------------------
# Permission assertions
# (call these inside route handlers; they raise 403/404 on failure)
# ---------------------------------------------------------------------------

def assert_can_view_borrow(borrow: Borrow, current_user: User) -> None:
    """
    Admins can view any borrow record.
    Members can only view their own.
    """
    if _is_admin(current_user):
        return
    if borrow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this borrow record.",
        )


def assert_can_return_borrow(borrow: Borrow, current_user: User) -> None:
    """
    Admins can mark any borrow as returned.
    Members can only return their own borrows.
    Additionally, raises 409 if the borrow is already returned.
    """
    if borrow.status == BorrowStatus.returned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Borrow id={borrow.id} has already been returned.",
        )
    if _is_admin(current_user):
        return
    if borrow.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only return books that you borrowed yourself.",
        )


def assert_can_delete_borrow(current_user: User) -> None:
    """
    Only admins may hard-delete a borrow record.
    Members should use the return endpoint instead.
    """
    if not _is_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges are required to delete borrow records.",
        )


def assert_borrow_limit_not_reached(active_count: int, max_limit: int) -> None:
    """
    Raise 409 if the member has reached their concurrent borrow limit.
    The limit comes from settings.MAX_BORROW_LIMIT (M1 config).
    """
    if active_count >= max_limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Borrow limit reached. "
                f"You currently have {active_count} active borrow(s) "
                f"(max allowed: {max_limit}). "
                "Please return a book before borrowing another."
            ),
        )
