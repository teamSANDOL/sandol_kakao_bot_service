"""오픈빌더 폴백 블록으로 떨어진 사용자 발화를 수집하는 라우터 모듈입니다."""

import json
import random
from typing import Any

from fastapi import APIRouter, Request
from kakao_chatbot.response import ActionEnum, KakaoResponse, QuickReply
from kakao_chatbot.response.components import SimpleTextComponent

from app.config import Config, logger
from app.database import AsyncSessionLocal
from app.models.fallback import FallbackUtterance
from app.utils.kakao_route import KakaoTimeoutRoute
from app.utils.openapi import create_openapi_extra

FALLBACK_MESSAGES = (
    "아직 이해하지 못한 말이에요. 도움말에서 사용할 수 있는 기능을 찾아보세요.",
    "앗, 그 말은 아직 어려워요. 도움말을 열어 할 수 있는 일을 확인해 보세요.",
    "무슨 말씀인지 잘 모르겠어요. 아래 도움말에서 쓸 수 있는 기능을 살펴보세요.",
    "아직 배우는 중이라 알아듣지 못했어요. 도움말에 기능 목록이 있으니 참고해 주세요.",
    "죄송해요, 제가 처리하지 못하는 요청이에요. 도움말에서 가능한 기능을 확인해 보세요.",
    "음, 아직 모르는 말이에요. 도움말을 눌러 이용 가능한 기능을 둘러보세요.",
)
MAX_UTTERANCE_LENGTH = 500
MAX_BODY_BYTES = 64 * 1024
# 원본(raw_payload)은 넓게: 본문 상한과 같은 수준까지 허용한다.
MAX_RAW_PAYLOAD_CHARS = MAX_BODY_BYTES
# 파생 필드는 작게: 원본에 같은 내용이 남아 있으므로 넘으면 None으로 저장한다.
MAX_PARAMS_CHARS = 500
MAX_FLOW_CHARS = 500
_SENSITIVE_KEY_PARTS = ("token", "secret", "authorization", "password")

fallback_router = APIRouter(prefix="/fallback", route_class=KakaoTimeoutRoute)


def _scrub(value: Any) -> Any:
    """토큰/비밀값으로 보이는 키를 재귀적으로 제거한 사본을 반환합니다."""
    if isinstance(value, dict):
        return {
            key: _scrub(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


def _get_dict(source: Any, key: str) -> dict[str, Any]:
    """dict에서 하위 dict를 꺼내고, 없거나 형식이 다르면 빈 dict를 반환합니다."""
    value = source.get(key) if isinstance(source, dict) else None
    return value if isinstance(value, dict) else {}


def _get_str(source: dict[str, Any], key: str, limit: int) -> str | None:
    """dict에서 문자열 값을 꺼내 길이 상한으로 자릅니다."""
    value = source.get(key)
    return value[:limit] if isinstance(value, str) else None


def _cap(value: dict[str, Any], limit: int) -> dict[str, Any] | None:
    """비어 있거나 직렬화 길이가 limit을 넘으면 None, 아니면 value를 반환합니다."""
    if not value or len(json.dumps(value, ensure_ascii=False)) > limit:
        return None
    return value


def build_record(body: Any) -> FallbackUtterance:
    """카카오 payload(dict)에서 저장할 FallbackUtterance를 만듭니다.

    누락/비정상 필드는 None으로 두며 예외를 내지 않습니다.
    원본 payload에서는 callbackUrl과 토큰류 키를 제외하고,
    userRequest.user.properties는 제외합니다.
    params, detailParams, flow, 원본은 직렬화 길이가 상한을 넘으면 None으로 저장합니다.

    Args:
        body (Any): 요청 JSON 본문.

    Returns:
        FallbackUtterance: 저장할 레코드.
    """
    user_request = _get_dict(body, "userRequest")
    action = _get_dict(body, "action")

    raw: dict[str, Any] | None = None
    if isinstance(body, dict):
        scrubbed: dict[str, Any] = _scrub(body)
        if isinstance(scrubbed.get("userRequest"), dict):
            scrubbed["userRequest"].pop("callbackUrl", None)
            _get_dict(scrubbed["userRequest"], "user").pop("properties", None)
        raw = _cap(scrubbed, MAX_RAW_PAYLOAD_CHARS)

    flow = _cap(_scrub(_get_dict(body, "flow")), MAX_FLOW_CHARS)
    trigger = _get_dict(flow, "trigger")
    referrer = _get_dict(trigger, "referrerBlock")

    return FallbackUtterance(
        utterance=_get_str(user_request, "utterance", MAX_UTTERANCE_LENGTH) or "",
        kakao_user_id=_get_str(_get_dict(user_request, "user"), "id", 64),
        block_id=_get_str(_get_dict(user_request, "block"), "id", 64),
        block_name=_get_str(_get_dict(user_request, "block"), "name", 255),
        bot_id=_get_str(_get_dict(body, "bot"), "id", 64),
        params=_cap(_scrub(_get_dict(action, "params")), MAX_PARAMS_CHARS),
        detail_params=_cap(_scrub(_get_dict(action, "detailParams")), MAX_PARAMS_CHARS),
        flow=flow,
        trigger_type=_get_str(trigger, "type", 64),
        trigger_referrer_block_id=_get_str(referrer, "id", 64),
        trigger_referrer_block_name=_get_str(referrer, "name", 255),
        raw_payload=raw,
    )


def build_help_quick_reply() -> QuickReply:
    """도움말 바로가기 버튼을 만듭니다.

    HELP_BLOCK_ID가 설정되어 있으면 block 액션으로 해당 블록에 연결하고,
    없으면 "도움말" 메시지를 보내는 message 액션으로 대체합니다.
    """
    if Config.HELP_BLOCK_ID:
        return QuickReply(
            label="도움말",
            action=ActionEnum.BLOCK,
            block_id=Config.HELP_BLOCK_ID,
        )
    return QuickReply(label="도움말", action=ActionEnum.MESSAGE, message_text="도움말")


@fallback_router.post(
    "",
    openapi_extra=create_openapi_extra(utterance="알 수 없는 발화"),
)
async def fallback(request: Request):
    """폴백 블록으로 들어온 발화를 DB에 저장하고 안내 메시지를 반환합니다.

    저장에 실패하더라도 카카오는 200 외 응답을 무시하므로
    항상 200으로 폴백 안내 메시지를 반환합니다.
    payload가 비정상이어도 가능한 필드만 저장합니다.

    ## 카카오 챗봇  연결 정보
    ---
    - 동작방식: 폴백 블록

    - OpenBuilder:
        - 블럭: "폴백 블록"
        - 스킬: "폴백 발화 수집"

    - 설정 방법:
        1. 오픈빌더 > 시나리오 > 폴백 블록 선택
        2. 봇 응답을 "스킬 데이터 사용"으로 설정
        3. 스킬 URL을 `{BASE_URL}/kakao-bot/fallback` 으로 지정한 스킬 선택
    ---

    Returns:
        JSONResponse: 폴백 안내 SimpleText
    """
    try:
        raw_body = await request.body()
        if len(raw_body) > MAX_BODY_BYTES:
            logger.warning(
                "폴백 본문이 너무 커서 저장하지 않음: %d바이트", len(raw_body)
            )
        else:
            record = build_record(json.loads(raw_body))
            async with AsyncSessionLocal() as session:
                session.add(record)
                await session.commit()
    except Exception as exc:  # noqa: BLE001 # pylint: disable=W0718
        # 수집 실패가 사용자 응답을 막지 않도록 모든 예외를 삼킨다.
        # 발화/토큰이 섞일 수 있는 원문은 남기지 않고 예외 타입만 기록한다.
        logger.error("폴백 발화 저장 실패: %s", type(exc).__name__)

    response = KakaoResponse(
        component_list=[SimpleTextComponent(random.choice(FALLBACK_MESSAGES))]  # noqa: S311
    )
    response += build_help_quick_reply()
    return response.get_dict()
