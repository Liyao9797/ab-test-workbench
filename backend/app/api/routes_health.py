from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, object]:
    return {
        "ok": True,
        "version": "0.1.0",
        "service": "local-ab-test-workbench",
    }
