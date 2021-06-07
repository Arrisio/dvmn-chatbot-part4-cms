import logging
from datetime import datetime

import httpx
from aiogram import Dispatcher, Bot, types
from aiogram.contrib.fsm_storage.redis import RedisStorage2
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command, Regexp
from aiogram.dispatcher.filters import CommandStart
from aiogram.dispatcher.filters.state import StatesGroup, State
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.utils import executor
from aiogram.utils.callback_data import CallbackData

from settings import Settings

logger = logging.getLogger(__name__)

settings = Settings()
bot = Bot(settings.TG_BOT_TOKEN, parse_mode=types.ParseMode.HTML)
storage = RedisStorage2(
    host=settings.REDIS_HOST, port=settings.REDIS_PORT, password=settings.REDIS_PASSWORD, db=settings.REDIS_DB
)
dp = Dispatcher(bot, storage=storage)


class ApplicationState(StatesGroup):
    WAITING_EMAIL = State()


MOLTEN_AUTH_DATA: dict = {}


async def get_headers(token_expires_preservation_sec: int = 10):
    global MOLTEN_AUTH_DATA
    if (
        not MOLTEN_AUTH_DATA
        or datetime.utcfromtimestamp(MOLTEN_AUTH_DATA["expires"] - token_expires_preservation_sec)
        > datetime.utcnow()
    ):
        response = httpx.post(
            url=f"{settings.MOLTEN_URL}/oauth/access_token",
            data={"client_id": settings.MOLTEN_CLIENT_ID, "grant_type": "implicit"},
        )
        response.raise_for_status()
        MOLTEN_AUTH_DATA = response.json()

    return {
        "Authorization": f"Bearer {MOLTEN_AUTH_DATA['access_token']}",
        "Content-Type": "application/json",
    }


cb_add_to_cart = CallbackData("add_to_cart", "id")
cb_show_product_details = CallbackData("show_product_details", "id")
cb_remove_item_from_cart = CallbackData("remove_item_from_cart", "id")
cb_goto_main_menu = "goto_main_menu"
cb_goto_cart = "goto_cart"
cb_pay = "pay"


def chunks(lst, size=5):
    return [lst[i : i + size] for i in range(0, len(lst), size)]


@dp.message_handler(CommandStart())
async def show_product_list(message: types.Message):
    logger.debug("start receiving product list")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.MOLTEN_URL}/v2/products",
            headers=await get_headers(),
        )
        response.raise_for_status()
    logger.debug("product list received")
    await message.answer(
        "Список товаров",
        reply_markup=InlineKeyboardMarkup(
            row_width=2,
            inline_keyboard=chunks(
                [
                    InlineKeyboardButton(
                        text=product["name"],
                        callback_data=cb_show_product_details.new(id=product["id"]),
                    )
                    for product in response.json()["data"]
                ]
            )
            + [[InlineKeyboardButton(text="Корзина", callback_data=cb_goto_cart)]],
        ),
    )


@dp.callback_query_handler(text=cb_goto_main_menu)
async def show_product_list_cb(call: CallbackQuery):
    await show_product_list(call.message)
    await call.answer()


@dp.callback_query_handler(cb_show_product_details.filter())
async def show_product_details(call: CallbackQuery, callback_data: dict, state: FSMContext):
    logger.info(f"start showing product details | callback_data={callback_data}")
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.MOLTEN_URL}/v2/products/{callback_data.get('id')}",
            headers=await get_headers(),
        )
        response.raise_for_status()
        product = response.json()["data"]
        main_image_id = product["relationships"]["main_image"]["data"]["id"]
        response = await client.get(
            url=f"https://api.moltin.com/v2/files/{main_image_id}",
            headers=await get_headers(),
        )
        response.raise_for_status()
        image_link = response.json()["data"]["link"]["href"]

    product_description = f"""<b>{product.get("name")}</b>\nЦена: {product['meta']['display_price']['with_tax']['formatted']}\n<i>{product.get("description")}</i>"""

    await call.message.answer_photo(
        photo=image_link,
        caption=product_description,
        reply_markup=InlineKeyboardMarkup(
            row_width=2,
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="1 кг", callback_data=cb_add_to_cart.new(id=product["id"])),
                    InlineKeyboardButton(text="5 кг", callback_data=cb_add_to_cart.new(id=product["id"])),
                    InlineKeyboardButton(text="10 кг", callback_data=cb_add_to_cart.new(id=product["id"])),
                ],
                [
                    InlineKeyboardButton(text="Показать корзину", callback_data=cb_goto_cart),
                    InlineKeyboardButton(text="К списку товаров", callback_data=cb_goto_main_menu),
                ],
            ],
        ),
    )
    await call.answer()


@dp.callback_query_handler(cb_add_to_cart.filter())
async def add_to_cart(
    call: CallbackQuery,
    callback_data: dict,
):
    logger.debug(f"start adding to cart | callback_data={callback_data}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.MOLTEN_URL}/v2/carts/{call.from_user.id}/items",
                headers=await get_headers(),
                json={"data": {"id": callback_data["id"], "type": "cart_item", "quantity": 1}},
            )
            response.raise_for_status()
        await call.message.answer("товар добавлен")
        await show_product_list(message=call.message)
    except httpx.HTTPStatusError as err:
        logger.error(err)
        await call.message.answer(
            "При добавлени товара в корзину произошла ошибка. Попробуйте позже или обратитесь в тех.поддержку по тел xxxx"
        )
    finally:
        await call.answer()


@dp.callback_query_handler(text=cb_goto_cart)
async def show_cart_items(call: CallbackQuery):
    logger.debug("start adding to cart")
    async with httpx.AsyncClient() as client:
        response_cart = await client.get(
            f"{settings.MOLTEN_URL}/v2/carts/{call.from_user.id}",
            headers=await get_headers(),
        )
        response_cart.raise_for_status()

        response_cart_items = await client.get(
            f"{settings.MOLTEN_URL}/v2/carts/{call.from_user.id}/items",
            headers=await get_headers(),
        )
        response_cart_items.raise_for_status()

    items_in_cart = response_cart_items.json()["data"]

    cart_items_description = "\n".join(
        [f"""<b>{item.get("name")}</b>\nКоличество: {item['quantity']}""" for item in items_in_cart]
    )
    cart_items_description += (
        f"\n\n<b>Итого: {response_cart.json()['data']['meta']['display_price']['with_tax']['formatted']}</b>"
    )

    logger.debug("cart items received")
    await call.message.answer(
        cart_items_description,
        reply_markup=InlineKeyboardMarkup(
            row_width=6,
            inline_keyboard=chunks(
                [
                    InlineKeyboardButton(
                        text=f'Убрать из корзины {item["name"]}',
                        callback_data=cb_remove_item_from_cart.new(id=item["id"]),
                    )
                    for item in items_in_cart
                ]
            )
            + [
                [
                    InlineKeyboardButton(text="В меню", callback_data=cb_goto_main_menu),
                    InlineKeyboardButton(text="Оплатить", callback_data=cb_pay),
                ]
            ],
        ),
    )
    await call.answer()


@dp.callback_query_handler(cb_remove_item_from_cart.filter())
async def remove_item_from_cart(
    call: CallbackQuery,
    callback_data: dict,
):
    logger.debug(f"start removing item from cart | callback_data={callback_data}")
    async with httpx.AsyncClient() as client:
        response = await client.delete(
            f"{settings.MOLTEN_URL}/v2/carts/{call.from_user.id}/items/{callback_data['id']}",
            headers=await get_headers(),
        )
        response.raise_for_status()
    await call.message.answer("товар товар убран")
    await call.answer()


@dp.callback_query_handler(text=cb_pay)
async def pay(call: CallbackQuery):
    logger.debug("start pay")
    await ApplicationState.WAITING_EMAIL.set()
    await call.message.answer("Для оплаты пришлите ваш email")


@dp.message_handler(Regexp(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"), state=ApplicationState.WAITING_EMAIL)
async def receive_email(message: types.Message, state: FSMContext):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url=f"{settings.MOLTEN_URL}/v2/customers/{message.from_user.id}",
                headers=await get_headers(),
                json={
                    "data": {
                        "type": "customer",
                        "name": message.text,
                        "email": message.text,
                    }
                },
            )
            if not response.status_code != 409:  # 409 возвращается, если клиент уже существует, что не является ошибкой
                response.raise_for_status()
            await message.answer(f"Вы прислили мне эту почту {message.text}")

    except httpx.HTTPStatusError as e:
        logger.error(e)
        await message.answer(
            f"При записи вашего адреса произошла ошибка, но мы все равно впарим вам нашу рыбу, не беспокойтесь"
        )
    finally:
        await state.finish()
        await message.answer(f"Показать список товаров /start")


@dp.message_handler(state=ApplicationState.WAITING_EMAIL)
async def answer_if_sent_email_is_not_ok(message: types.Message):
    await message.answer(f"Присланный вами email некорректен")


@dp.message_handler(Command("clear_state"), state="*")
async def clear_state(message: types.Message, state: FSMContext):
    await message.answer(f"state cleared")
    await state.finish()


async def on_startup(dp):
    await get_headers()
    await dp.bot.send_message(settings.TG_BOT_ADMIN_ID, "Бот Запущен и готов к работе!")


if __name__ == "__main__":
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s - [%(levelname)s] -  %(name)s - (%(filename)s).%(funcName)s(%(lineno)d) - %(message)s",
    )
    logger.info("telegram service started")
    executor.start_polling(dp, on_startup=on_startup)
    logger.info("service service stopped")
