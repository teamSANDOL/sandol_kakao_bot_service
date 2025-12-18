"""Admin 모델 뷰 정의 파일."""

from sqladmin import ModelView
from app.models.users import User


class UserAdmin(ModelView, model=User):
    """Admin view를 위한 User 모델 뷰 클래스."""

    column_list = [
        User.id,
        User.keycloak_sub,
        User.kakao_id,
        User.plusfriend_user_key,
        User.app_user_id,
        User.kakao_admin,
    ]
    column_searchable_list = [
        User.keycloak_sub,
        User.kakao_id,
        User.app_user_id,
        User.plusfriend_user_key,
    ]
    column_sortable_list = [
        User.id,
        User.keycloak_sub,
        User.kakao_id,
        User.plusfriend_user_key,
        User.app_user_id,
        User.kakao_admin,
    ]
    can_create = True
    can_edit = True
    can_delete = True
