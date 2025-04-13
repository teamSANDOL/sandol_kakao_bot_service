"""This module contains utility functions for the application."""

from .db import get_db
from .http import XUserIDClient
from .kakao import parse_payload, error_message
from .openapi import create_openapi_extra


def get_korean_day(day):
    days = ["월", "화", "수", "목", "금", "토", "일"]
    return days[day]
