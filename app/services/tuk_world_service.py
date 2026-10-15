"""static-info의 TUK World 제휴 업체 목록을 가져오는 서비스 모듈."""

from cachetools import TTLCache
from httpx import AsyncClient, HTTPError
from pydantic import TypeAdapter, ValidationError

from app.config import Config, logger
from app.schemas.tuk_world import TukWorldRestaurant
from app.utils.kakao import KakaoError

CACHE_TTL_SECONDS = 600
FETCH_ERROR_MESSAGE = "제휴 업체 정보를 불러오지 못했습니다. 잠시 후 다시 시도해주세요."

_ADAPTER = TypeAdapter(list[TukWorldRestaurant])
_cache: TTLCache[str, list[TukWorldRestaurant]] = TTLCache(
    maxsize=1, ttl=CACHE_TTL_SECONDS
)


async def fetch_tuk_world_restaurants(
    client: AsyncClient,
) -> list[TukWorldRestaurant]:
    """전체 제휴 업체를 id 순으로 가져옵니다. 프로세스 메모리에 10분 캐시합니다.

    분류 필터와 상세 조회는 이 목록에서 로컬로 처리해 요청 수를 줄입니다.

    Args:
        client (AsyncClient): HTTP 클라이언트 인스턴스

    Returns:
        list[TukWorldRestaurant]: 제휴 업체 목록

    Raises:
        KakaoError: static-info 호출이나 응답 해석에 실패한 경우
    """
    cached = _cache.get("all")
    if cached is not None:
        return cached
    try:
        response = await client.get(
            f"{Config.STATIC_INFO_SERVICE_URL}/tuk-world/restaurants",
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        restaurants = _ADAPTER.validate_python(response.json())
    except (HTTPError, ValidationError, ValueError) as exc:
        logger.warning("TUK World 목록 조회 실패: %s", type(exc).__name__)
        raise KakaoError(FETCH_ERROR_MESSAGE) from exc
    _cache["all"] = restaurants
    return restaurants
