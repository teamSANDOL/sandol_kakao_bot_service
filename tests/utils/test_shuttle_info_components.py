from kakao_chatbot.response import KakaoResponse

from app.utils.statics import make_shuttle_info_components


def test_make_shuttle_info_components_keeps_simple_images_up_to_three() -> None:
    image_urls = [f"https://example.com/shuttle-{index}.jpg" for index in range(3)]

    response = KakaoResponse(
        component_list=make_shuttle_info_components(image_urls)
    ).get_dict()

    outputs = response["template"]["outputs"]
    assert len(outputs) == 3
    assert all("simpleImage" in output for output in outputs)


def test_make_shuttle_info_components_falls_back_to_list_card_for_four_images() -> None:
    image_urls = [f"https://example.com/shuttle-{index}.jpg" for index in range(4)]

    response = KakaoResponse(
        component_list=make_shuttle_info_components(image_urls)
    ).get_dict()

    outputs = response["template"]["outputs"]
    assert len(outputs) == 1
    assert "listCard" in outputs[0]
    assert len(outputs[0]["listCard"]["items"]) == 4


def test_make_shuttle_info_components_falls_back_to_carousel_for_many_images() -> None:
    image_urls = [f"https://example.com/shuttle-{index}.jpg" for index in range(6)]

    response = KakaoResponse(
        component_list=make_shuttle_info_components(image_urls)
    ).get_dict()

    outputs = response["template"]["outputs"]
    assert len(outputs) == 1
    assert outputs[0]["carousel"]["type"] == "listCard"
    assert len(outputs[0]["carousel"]["items"]) == 2
