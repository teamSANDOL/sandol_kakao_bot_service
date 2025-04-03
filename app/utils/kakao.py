from fastapi import Request
from kakao_chatbot import Payload
from kakao_chatbot.response import TextCardComponent

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
        # exception_traceback = "".join(
        #     traceback.format_tb(message.__traceback__))

        detailed_message = (
            f"예외 타입: {exception_type}\n예외 메시지: {exception_message}\n"
            # f"트레이스백:\n{exception_traceback}"
        )
        message = detailed_message
    message += "\n죄송합니다. 서버 오류가 발생했습니다. 오류가 지속될 경우 관리자에게 문의해주세요."
    return TextCardComponent(title="오류 발생", description=message)
