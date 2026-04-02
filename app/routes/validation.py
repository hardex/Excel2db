# Validation and correction routes are handled in processing.py.
# This module is reserved for future standalone validation endpoints.

from fastapi import APIRouter

router = APIRouter(prefix="/validation", tags=["validation"])
