from fastapi import APIRouter, Query, Request
from app.api.dependencies import get_repo

router = APIRouter()


@router.get("/verifications")
def list_verifications(
    request: Request,
    status: str | None = None,
    beverage_type: str | None = None,
    brand: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    repo = get_repo(request)
    items, total = repo.list_verifications(
        status=status, beverage_type=beverage_type, brand=brand,
        page=page, per_page=per_page,
    )

    return {
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
        }
    }
