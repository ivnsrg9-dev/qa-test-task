import datetime as dt
import re

import pytest
from playwright.sync_api import Page, expect

SUCCESS_TITLE = "Бронирование создано"

# Корректная бронь; тесты меняют только нужные поля через overrides.
VALID_BOOKING = {
    "room": "Средняя · до 10 человек",
    "start": "10:00",
    "end": "11:00",
    "participants": "6",
    "name": "Иван Петров",
    "email": "ivan.petrov@company.ru",
}


def tomorrow(page: Page) -> str:
    """Завтра относительно «сегодня» страницы (атрибут min поля даты).

    Страница считает дату в часовом поясе браузера, поэтому дату берём у неё,
    а не из date.today(): тест не зависит от TZ контейнера и времени запуска.
    """
    today = dt.date.fromisoformat(page.get_by_label("Дата").get_attribute("min"))
    return (today + dt.timedelta(days=1)).isoformat()


def fill_booking_form(page: Page, **overrides: str) -> dict:
    """Заполняет форму и нажимает «Забронировать». Только действия, без проверок:
    при сбое окружения Playwright бросит Error/TimeoutError, а не AssertionError."""
    data = {**VALID_BOOKING, "date": tomorrow(page), **overrides}
    page.get_by_label("Переговорная").select_option(label=data["room"])
    page.get_by_label("Дата").fill(data["date"])
    page.get_by_label("Начало").fill(data["start"])
    page.get_by_label("Окончание").fill(data["end"])
    page.get_by_label("Участники").fill(data["participants"])
    page.get_by_label("Ваше имя").fill(data["name"])
    page.get_by_label("Рабочая почта").fill(data["email"])
    page.get_by_role("button", name="Забронировать").click()
    return data


@pytest.fixture
def booking_page(page: Page, base_url: str) -> Page:
    page.goto(base_url)
    return page


def test_successful_booking(booking_page: Page):
    """Корректная бронь: сообщение с комнатой, датой, временем и именем, ошибок нет."""
    data = fill_booking_form(booking_page)

    status = booking_page.get_by_role("status")
    expect(status).to_have_class(re.compile(r"\bsuccess\b"))
    expect(status).to_contain_text(SUCCESS_TITLE)
    expect(status).to_contain_text("Средняя")
    expect(status).to_contain_text(data["date"])
    expect(status).to_contain_text("10:00–11:00")  # длинное тире U+2013, как на странице
    expect(status).to_contain_text("Иван Петров")
    expect(booking_page.locator(".field.has-error")).to_have_count(0)


def test_invalid_booking(booking_page: Page):
    """Участников больше вместимости комнаты: «Малая» вмещает 4, указано 5 — бронь не создаётся."""
    fill_booking_form(booking_page, room="Малая · до 4 человек", participants="5")

    status = booking_page.get_by_role("status")
    expect(status).to_have_class(re.compile(r"\berror\b"))
    expect(status).not_to_contain_text(SUCCESS_TITLE)
    expect(booking_page.locator('[data-error-for="participants"]')).to_contain_text("максимум 4")


@pytest.mark.xfail(
    strict=True,
    reason="BUG-01: длительность брони не проверяется (допустимо от 30 минут до 4 часов)",
    raises=AssertionError,
)
@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param("10:00", "10:00", id="zero-minutes"),
        pytest.param("10:00", "10:10", id="10-minutes"),
        pytest.param("09:00", "14:00", id="5-hours"),
    ],
)
def test_discovered_defect(booking_page: Page, start: str, end: str):
    """Бронь с длительностью вне диапазона 30 мин – 4 ч не должна создаваться.

    Где именно выводится ошибка, требования не задают, поэтому проверяем сам факт:
    сообщения об успешном бронировании нет.
    """
    fill_booking_form(booking_page, start=start, end=end)

    expect(booking_page.get_by_role("status")).not_to_contain_text(SUCCESS_TITLE)
