# app/borrow/__init__.py
# Makes `borrow` a proper Python package.
# Import the Borrow model here so SQLAlchemy's Base.metadata.create_all()
# picks up the table during the startup lifespan in main.py.

from app.borrow.model import Borrow, BorrowStatus  # noqa: F401
