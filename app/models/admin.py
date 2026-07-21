"""Admin 모델 뷰 정의 파일."""

from sqladmin import ModelView

from app.models.users import User


class UserAdmin(ModelView, model=User):
    """Admin view를 위한 User 모델 뷰 클래스."""

    name = "User"
    name_plural = "Users"
    icon = "fa-solid fa-user"

    column_list = [
        User.id,
        User.keycloak_id,
        User.kakao_id,
        User.plusfriend_user_key,
        User.app_user_id,
        User.kakao_admin,
        User.refresh_token_expires_at,
    ]
    column_searchable_list = [
        User.keycloak_id,
        User.kakao_id,
        User.app_user_id,
        User.plusfriend_user_key,
    ]
    column_sortable_list = [
        User.id,
        User.keycloak_id,
        User.kakao_id,
        User.plusfriend_user_key,
        User.app_user_id,
        User.kakao_admin,
        User.refresh_token_expires_at,
    ]
    column_default_sort = [(User.id, True)]

    # 암호화된 토큰 블롭은 노출/수정할 이유가 없고,
    # 수기로 편집하면 Fernet 복호화가 깨지므로 상세/폼/내보내기에서 제외한다.
    column_details_exclude_list = [User.access_token, User.refresh_token]
    form_excluded_columns = [
        User.access_token,
        User.refresh_token,
        User.access_token_expires_at,
        User.refresh_token_expires_at,
    ]
    column_export_exclude_list = [User.access_token, User.refresh_token]

    page_size = 25
    page_size_options = [25, 50, 100]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True
