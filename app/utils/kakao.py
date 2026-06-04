"""Kakao payload 파싱과 챗봇 에러 응답 유틸을 제공합니다."""

import json
import traceback
from typing import Optional

from fastapi import Request
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse, ActionEnum
from kakao_chatbot.response.components import TextCardComponent, SimpleTextComponent

from app.config import Config, BlockID, logger


class KakaoError(Exception):
    """카카오톡 관련 에러를 나타내는 사용자 정의 예외 클래스입니다.

    이 클래스는 함수 사용중 의도적으로 raise하여 early return을 구현할 경우에 사용됩니다.
    message를 인자로 사용하여, message가 str일 경우에는 그대로 SimpleTextComponent로 변환하고,
    KakaoResponse일 경우에는 그대로 Client에게 반환합니다.
    """

    def __init__(self, message: str | KakaoResponse):
        """KakaoError 객체를 초기화합니다.

        Args:
            message (str | KakaoResponse): 에러 메시지 또는 KakaoResponse 객체
        """
        super().__init__(message)
        self.message = message

    def get_response(self) -> KakaoResponse:
        """KakaoResponse 객체를 반환합니다.

        message가 KakaoResponse일 경우 그대로 반환하고,
        str일 경우에는 SimpleTextComponent로 변환하여 KakaoResponse에 추가합니다.
        """
        if isinstance(self.message, KakaoResponse):
            return self.message
        return KakaoResponse().add_component(SimpleTextComponent(self.message))


class NotAuthenticated(Exception):
    """사용자 로그인(등록) 과정이 진행되지 않아 발생하는 에러입니다."""

    def __init__(self, *args, **kwargs):
        """Initializes the NotAuthenticated instance."""
        super().__init__(*args, **kwargs)

    def get_response(self) -> KakaoResponse:
        """로그인 유도 메시지를 포함한 KakaoResponse 객체를 반환합니다."""
        response = KakaoResponse()
        card = TextCardComponent(
            title="로그인 필요",
            description=(
                "해당 서비스 이용을 위해 로그인이 필요합니다. 아래 버튼을 눌러 로그인해주세요."
            ),
        )
        card.add_button(
            "로그인하기",
            action=ActionEnum.BLOCK,
            block_id=BlockID.LOGIN,
        )
        response.add_component(card)
        return response


class LoginRequiredError(Exception):
    """사용자 인증이 필요한 경우 발생하는 에러입니다."""

    def __init__(self, *args, message: Optional[str] = None, **kwargs):
        """Initializes the LoginRequiredError instance."""
        super().__init__(*args[1:], **kwargs)
        self.message = message

    def get_response(self) -> KakaoResponse:
        """로그인 유도 메시지를 포함한 KakaoResponse 객체를 반환합니다."""
        description = (
            self.message
            if self.message
            else "사용자 인증 과정 중에 문제가 발생했습니다. 아래 버튼을 눌러 다시 로그인해주세요."
        )
        response = KakaoResponse()
        card = TextCardComponent(
            title="로그인 필요",
            description=description,
        )
        card.add_button(
            "로그인하기",
            action=ActionEnum.BLOCK,
            block_id=BlockID.LOGIN,
        )
        response.add_component(card)
        return response


class UserIdentityConflictError(Exception):
    """입력된 식별자들이 서로 다른 사용자에 매칭되는 경우 발생하는 에러입니다.

    이 에러는 사용자 인증 상태 문제가 아니라,
    시스템 내부의 사용자 식별자 정합성 충돌 상황을 의미합니다.
    """

    def __init__(
        self,
        *args,
        message: str | KakaoResponse | None = None,
        **kwargs,
    ):
        """충돌 상황에서 사용자에게 보여줄 메시지를 저장합니다."""
        super().__init__(*args, **kwargs)
        self.message = message

    def get_response(self) -> KakaoResponse:
        """충돌 상황을 사용자에게 안내하는 KakaoResponse를 반환합니다."""
        if isinstance(self.message, KakaoResponse):
            return self.message

        description = (
            self.message
            if self.message
            else "사용자 정보 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요. 계속 문제가 발생할 경우 관리자에게 문의해주세요."
        )

        response = KakaoResponse()
        card = TextCardComponent(
            title="사용자 정보 오류",
            description=description,
        )
        response.add_component(card)
        return response


async def parse_payload(request: Request) -> Payload:
    """Request에서 Payload를 추출합니다.

    Request에서 JSON 데이터를 추출하여 Payload 객체로 변환합니다.
    FastAPI의 Dependency Injection을 사용하기 위한 함수입니다.
    """
    payload = Payload.from_dict(await request.json())
    logger.debug("사용자 요청\n%s", await request.body())
    return payload


def extract_text_value(value: object) -> str | None:
    """detail/client 파라미터 값에서 문자열을 안전하게 추출합니다."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        nested = value.get("value")
        if isinstance(nested, str):
            return nested
    if isinstance(value, object):
        for attr in ("value", "origin"):
            nested = getattr(value, attr, None)
            if isinstance(nested, str):
                return nested
    return None


def to_jsonable_kakao_value(value: object) -> object:
    """Kakao 입력 객체를 로그용 JSON-safe 값으로 변환합니다."""
    if value is None or isinstance(value, str | int | float | bool):
        return value

    if isinstance(value, dict):
        return {
            str(key): to_jsonable_kakao_value(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list | tuple | set):
        return [to_jsonable_kakao_value(item) for item in value]

    if hasattr(value, "__dict__"):
        serialized_attrs = {
            key: to_jsonable_kakao_value(attr_value)
            for key, attr_value in vars(value).items()
            if not key.startswith("_") and not callable(attr_value)
        }
        if serialized_attrs:
            return serialized_attrs

    return str(value)


def dump_kakao_value_json(value: object) -> str:
    """Kakao 입력 객체를 로그용 JSON 문자열로 변환합니다."""
    return json.dumps(to_jsonable_kakao_value(value), ensure_ascii=False)


def error_message(message: str | BaseException) -> TextCardComponent:
    """에러 메시지를 반환합니다.

    에러 메시지를 받아 추가 정보를 덧붙인 후 TextCardComponent로 반환합니다.
    만약 message가 BaseException 객체일 경우 문자열로 변환하여 사용합니다.

    Args:
        message (str): 에러 메시지
    """
    if isinstance(message, BaseException):
        exception_type = type(message).__name__
        exception_message = str(message)
        detailed_message = (
            f"예외 타입: {exception_type}\n예외 메시지: {exception_message}\n"
        )
        if Config.debug:
            exception_traceback = "".join(traceback.format_tb(message.__traceback__))
            detailed_message += f"트레이스백:\n{exception_traceback}"

        message = detailed_message
    message += "\n죄송합니다. 서버 오류가 발생했습니다. 오류가 지속될 경우 관리자에게 문의해주세요."
    return TextCardComponent(title="오류 발생", description=message)
