from fastapi import Header, HTTPException, status

from app.core.config import settings


async def verify_api_key(
    api_key: str | None = Header(
        default=None,
        alias="X-API-Key",
    ),
) -> None:
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )