"""This module contains utility functions for the application."""

from .db import get_db
from .http import XUserIDClient
from .kakao import parse_payload, error_message
from .openapi import create_openapi_extra


def get_korean_day(day):
    """요일 인덱스를 한글 요일 약어로 변환합니다."""
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[day]
