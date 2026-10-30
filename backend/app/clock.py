"""Today's date, as a FastAPI dependency.

Endpoints ask for `today: Today` instead of calling dt.date.today() themselves.
Tests override get_today to freeze the date, like they override get_db.
"""

import datetime as dt
from typing import Annotated

from fastapi import Depends


def get_today() -> dt.date:
    return dt.date.today()


Today = Annotated[dt.date, Depends(get_today)]
