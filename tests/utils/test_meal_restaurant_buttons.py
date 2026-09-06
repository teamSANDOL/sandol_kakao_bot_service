from kakao_chatbot.response import ActionEnum
from kakao_chatbot.response.components import ItemCardComponent

from app.config import BlockID
from app.schemas.meals import Location, RestaurantResponse
from app.utils.meal import apply_restaurant_buttons, build_restaurant_buttons


def _student_restaurant(with_map: bool = True) -> RestaurantResponse:
    map_links = {"kakao": "https://kko.kakao.com/qUpUMrAKti"} if with_map else None
    return RestaurantResponse(
        id=1,
        name="TIP 가가식당",
        establishment_type="student",
        price=6000,
        location=Location(is_campus=True, building="TIP", map_links=map_links),
    )


def _owner_restaurant() -> RestaurantResponse:
    return RestaurantResponse(
        id=2,
        name="미가식당",
        establishment_type="fixed_menu_restaurant",
        location=Location(
            is_campus=False,
            building="외부건물",
            map_links={"naver": "https://naver.me/x"},
        ),
    )


def test_student_restaurant_gets_all_three_buttons_in_order() -> None:
    buttons = build_restaurant_buttons(_student_restaurant())

    assert [button.label for button in buttons] == [
        "메뉴 보기",
        "식당 위치 지도 보기",
        "주간 식단표 보기",
    ]
    assert buttons[2].action == ActionEnum.BLOCK
    assert buttons[2].block_id == BlockID.WEEKLY_MENU


def test_owner_restaurant_has_no_weekly_menu_button() -> None:
    buttons = build_restaurant_buttons(_owner_restaurant())

    assert [button.label for button in buttons] == ["메뉴 보기", "식당 위치 지도 보기"]


def test_weekly_menu_button_moves_up_without_map_link() -> None:
    buttons = build_restaurant_buttons(_student_restaurant(with_map=False))

    assert [button.label for button in buttons] == ["메뉴 보기", "주간 식단표 보기"]


def test_kakao_map_link_wins_over_naver() -> None:
    restaurant = RestaurantResponse(
        id=3,
        name="TIP 가가식당",
        establishment_type="student",
        location=Location(
            is_campus=True,
            building="TIP",
            map_links={
                "naver": "https://naver.me/x",
                "kakao": "https://kko.kakao.com/x",
            },
        ),
    )

    buttons = build_restaurant_buttons(restaurant)

    map_button = next(b for b in buttons if b.label == "식당 위치 지도 보기")
    assert map_button.web_link_url == "https://kko.kakao.com/x"


def test_restaurant_without_location_still_builds_menu_button() -> None:
    restaurant = RestaurantResponse(
        id=4,
        name="미가식당",
        establishment_type="fixed_menu_restaurant",
        location=None,
    )

    buttons = build_restaurant_buttons(restaurant)

    assert [button.label for button in buttons] == ["메뉴 보기"]


def test_three_buttons_force_vertical_layout() -> None:
    item_card = ItemCardComponent([])

    apply_restaurant_buttons(item_card, _student_restaurant())

    assert len(item_card.buttons) == 3
    assert item_card.button_layout == "vertical"
    assert item_card.render()["buttonLayout"] == "vertical"


def test_two_buttons_keep_default_layout() -> None:
    item_card = ItemCardComponent([])

    apply_restaurant_buttons(item_card, _owner_restaurant())

    assert len(item_card.buttons) == 2
    assert item_card.button_layout is None
    assert "buttonLayout" not in item_card.render()
