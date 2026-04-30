# app/models/__init__.py
# Import all models here so Base.metadata.create_all() discovers every table.
from app.models.user import User  # noqa: F401
