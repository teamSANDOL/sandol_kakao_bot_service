"""빈 강의실을 조회하는 서비스 모듈"""

import json
from typing import List, Literal
from datetime import datetime, timedelta

from pydantic import TypeAdapter

from app.config import Config, logger
from app.schemas.classroom import EmptyClassroomInfo
from app.utils import get_korean_day

from app.utils.http import XUserIDClient


async def search_empty_classroom_by_time(
    client: XUserIDClient,
    day: Literal["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"],
    start_time: str,
    end_time: str,
):
    """빈 강의실을 조회하는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스
        day (Literal): 요일 (예: "월요일", "화요일" 등)
        start_time (str): 시작 시간 (예: "09:00")
        end_time (str): 종료 시간 (예: "10:00")

    Returns:
        list[EmptyClassroomInfo]: 빈 강의실 정보 리스트
    """
    logger.debug(
        f"search_empty_classroom_by_time called with day={day}, start_time={start_time}, end_time={end_time}"
    )
    response = await client.get(
        f"{Config.CLASSTROOM_TIMETABLE_SERVICE_URL}/classrooms/available/time",
        params={
            "day": day,
            "start_time": start_time,
            "end_time": end_time,
        },
    )
    response.raise_for_status()
    # logger.debug(
    #     f"Response from search_empty_classroom_by_time: {response.status_code}\n"
    #     f"{json.dumps(response.json(), ensure_ascii=False, indent=2)}"
    # )
    adapter = TypeAdapter(List[EmptyClassroomInfo])
    return adapter.validate_python(response.json())


async def search_empty_classroom_by_period(
    client: XUserIDClient,
    day: Literal["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"],
    start_period: int,
    end_period: int,
):
    """빈 강의실을 조회하는 함수 (교시 단위)

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스
        day (Literal): 요일 (예: "월요일", "화요일" 등)
        start_period (int): 시작 교시 (1부터 시작)
        end_period (int): 종료 교시 (1부터 시작)

    Returns:
        list[EmptyClassroomInfo]: 빈 강의실 정보 리스트
    """
    logger.debug(
        f"search_empty_classroom_by_period called with day={day}, start_period={start_period}, end_period={end_period}"
    )
    response = await client.get(
        f"{Config.CLASSTROOM_TIMETABLE_SERVICE_URL}/classrooms/available/periods",
        params={
            "day": day,
            "start_time": str(start_period),
            "end_time": str(end_period),
        },
    )
    response.raise_for_status()
    # logger.debug(
    #     f"Response from search_empty_classroom_by_period: {response.status_code}\n"
    #     f"{json.dumps(response.json(), ensure_ascii=False, indent=2)}"
    # )
    adapter = TypeAdapter(List[EmptyClassroomInfo])
    return adapter.validate_python(response.json())


async def search_empty_classroom_now(
    client: XUserIDClient,
):
    """현재 빈 강의실을 조회하는 함수

    Args:
        client (XUserIDClient): HTTP 클라이언트 인스턴스

    Returns:
        list[EmptyClassroomInfo]: 현재 빈 강의실 정보 리스트
    """
    now = datetime.now(Config.TZ)
    day = f"{get_korean_day(now.weekday())}요일"  # 현재 요일 (예: "월요일")
    start_time = now.strftime("%H:%M")  # 현재 시간 (예: "09:00")
    end_time = (now + timedelta(minutes=1)).strftime(
        "%H:%M"
    )  # 1분 후 시간 (예: "09:30")
    return await search_empty_classroom_by_time(
        client,
        day=day,  # type: ignore[arg-type]
        start_time=start_time,
        end_time=end_time,
    )
