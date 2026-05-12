from fastapi import APIRouter, Depends

from app.services.auth import AuthenticatedUser, clerk_is_configured, get_current_user


router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me")
def me(current_user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, object]:
    account = current_user.account
    return {
        "user": {
            "id": account.id,
            "clerk_user_id": account.clerk_user_id,
            "email": account.email,
            "display_name": account.display_name,
            "default_provider": account.default_provider,
        },
        "auth": {
            "mode": "dev" if current_user.is_dev else "clerk",
            "clerk_configured": clerk_is_configured(),
        },
    }
