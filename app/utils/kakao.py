import traceback

from fastapi import Request
from kakao_chatbot import Payload
from kakao_chatbot.response import KakaoResponse
from kakao_chatbot.response.components import TextCardComponent, SimpleTextComponent

from app.config.config import Config


# custom Exception
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


async def parse_payload(request: Request) -> Payload:
    """Request에서 Payload를 추출합니다.

    Request에서 JSON 데이터를 추출하여 Payload 객체로 변환합니다.
    FastAPI의 Dependency Injection을 사용하기 위한 함수입니다.
    """
    data_dict = await request.json()
    return Payload.from_dict(data_dict)


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
