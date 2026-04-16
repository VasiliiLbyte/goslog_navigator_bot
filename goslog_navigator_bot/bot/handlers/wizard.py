from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from loguru import logger
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from goslog_navigator_bot.bot.keyboards.inline import (
    wizard_confirm_keyboard,
    wizard_finish_keyboard,
    wizard_pdf_keyboard,
)
from goslog_navigator_bot.bot.states.user import GoslogWizardState
from goslog_navigator_bot.core.config import settings
from goslog_navigator_bot.database.repositories.wizard_sessions import (
    get_or_create_by_user_id,
    mark_finished,
    merge_data,
    update_step,
)

wizard_router = Router(name="wizard")

DISCLAIMER = "Это помощник, не юридическая консультация."


def _disclaimer_line() -> str:
    # Требование: дисклеймер в каждом сообщении.
    return f"\n\n{DISCLAIMER}"


def _normalize_inn(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    return digits


def _inn_expected_len(business_type: str | None) -> int | None:
    # ИНН для ИП чаще 12 цифр, для ООО чаще 10 цифр.
    # На практике встречаются особенности, поэтому мы оставляем валидацию мягкой
    # через возврат ожидаемой длины и последующее уточнение пользователем.
    if business_type == "ip":
        return 12
    if business_type == "ooo":
        return 10
    return None


def _is_okved_5229_present(okved_codes: list[str]) -> bool:
    normalized = {c.replace(",", ".").strip() for c in okved_codes}
    return "52.29" in normalized or any(c.startswith("52.29") for c in normalized)


def _join_address(parts: list[str]) -> str:
    return ", ".join([p.strip() for p in parts if p and p.strip()])


def _parse_okved_codes_from_ofdata(payload_data: dict[str, Any]) -> list[dict[str, str]]:
    """
    Унифицированный извлекатель ОКВЭД-кодов из Ofdata ответа.

    Возвращает список dict вида: [{"code": "...", "name": "..."}, ...]
    """

    okved: dict[str, Any] = payload_data.get("ОКВЭД") or payload_data.get("okved") or {}
    okved_additional: list[dict[str, Any]] = payload_data.get("ОКВЭДДоп") or payload_data.get(
        "okved_additional"
    ) or []

    items: list[dict[str, str]] = []

    if isinstance(okved, dict) and okved:
        code = str(okved.get("Код") or okved.get("code") or "").strip()
        name = str(okved.get("Наим") or okved.get("name") or "").strip()
        if code:
            items.append({"code": code, "name": name})

    if isinstance(okved_additional, list):
        for row in okved_additional:
            if not isinstance(row, dict):
                continue
            code = str(row.get("Код") or row.get("code") or "").strip()
            name = str(row.get("Наим") or row.get("name") or "").strip()
            if code:
                items.append({"code": code, "name": name})

    # Убираем дубликаты по коду (сохраняем первый name).
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for it in items:
        if it["code"] in seen:
            continue
        seen.add(it["code"])
        unique.append(it)
    return unique


def _build_fns_lookup_payload(
    *,
    business_type: str,
    inn: str,
    response_json: dict[str, Any],
) -> dict[str, Any]:
    """
    Нормализуем ответ Ofdata под единую структуру для wizard.
    """

    response_data = response_json.get("data") if isinstance(response_json, dict) else None
    if not isinstance(response_data, dict):
        response_data = {}

    if business_type == "ip":
        name = str(response_data.get("ФИО") or response_data.get("fio") or "").strip()
        ogrn = str(response_data.get("ОГРНИП") or response_data.get("ogrnip") or "").strip()
        address = str(response_data.get("НасПункт") or response_data.get("address") or "").strip()
        okved_items = _parse_okved_codes_from_ofdata(response_data)
        okved_codes = [it["code"] for it in okved_items]
        has_5229 = _is_okved_5229_present(okved_codes)

        return {
            "inn": inn,
            "business_type": "ip",
            "name": name or None,
            "ogrn": ogrn or None,
            "address": address or None,
            "okved": okved_items,
            "has_okved_5229": has_5229,
        }

    # ooo
    name = str(
        response_data.get("НаимПолн")
        or response_data.get("name_full")
        or response_data.get("Наименование")
        or response_data.get("name")
        or ""
    ).strip()
    ogrn = str(response_data.get("ОГРН") or response_data.get("ogrn") or "").strip()

    jur_addr = response_data.get("ЮрАдрес") if isinstance(response_data.get("ЮрАдрес"), dict) else {}
    nas_point = str(jur_addr.get("НасПункт") or "").strip()
    addr_rf = str(jur_addr.get("АдресРФ") or "").strip()
    address = _join_address([nas_point, addr_rf]) or None

    okved_items = _parse_okved_codes_from_ofdata(response_data)
    okved_codes = [it["code"] for it in okved_items]
    has_5229 = _is_okved_5229_present(okved_codes)

    return {
        "inn": inn,
        "business_type": "ooo",
        "name": name or None,
        "ogrn": ogrn or None,
        "address": address,
        "okved": okved_items,
        "has_okved_5229": has_5229,
    }


async def _fetch_ofdata_egrip_egul(business_type: str, inn: str) -> dict[str, Any]:
    """
    GET-запрос к Ofdata:
    - ИП -> /v2/entrepreneur
    - ООО -> /v2/company
    """

    if not settings.fns_api_key:
        raise RuntimeError("FNS_API_KEY not configured")

    key = settings.fns_api_key.get_secret_value()
    if business_type == "ip":
        endpoint = f"{settings.fns_api_base_url}/entrepreneur"
    else:
        endpoint = f"{settings.fns_api_base_url}/company"

    params = {"key": key, "inn": inn, "source": "true"}

    async with httpx.AsyncClient(timeout=settings.fns_http_timeout_sec) as client:
        resp = await client.get(endpoint, params=params)
        resp.raise_for_status()
        return resp.json()


def _format_okved_preview(okved_items: list[dict[str, str]]) -> str:
    if not okved_items:
        return "—"
    # Покажем до 10 кодов.
    items = okved_items[:10]
    return ", ".join([f"{it.get('code')}" for it in items if it.get("code")])


def _register_pdf_font() -> tuple[str, str]:
    """
    Регистрируем Unicode-шрифт для корректной кириллицы в PDF.
    Возвращает (normal_font_name, bold_font_name).
    """
    regular_name = "GoslogSans"
    bold_name = "GoslogSansBold"

    if regular_name in pdfmetrics.getRegisteredFontNames() and bold_name in pdfmetrics.getRegisteredFontNames():
        return regular_name, bold_name

    candidates: list[tuple[str, str]] = [
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/Library/Fonts/DejaVuSans.ttf",
            "/Library/Fonts/DejaVuSans-Bold.ttf",
        ),
        (
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ),
    ]

    for regular_path, bold_path in candidates:
        if Path(regular_path).exists() and Path(bold_path).exists():
            pdfmetrics.registerFont(TTFont(regular_name, regular_path))
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
            return regular_name, bold_name

    # Фолбэк (может не отрисовать кириллицу в некоторых окружениях)
    return "Helvetica", "Helvetica-Bold"


def _safe(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return text or "—"


def _okved_main_and_extra(okved_items: list[dict[str, str]]) -> tuple[str, str]:
    if not okved_items:
        return "—", "—"
    main = _safe(okved_items[0].get("code"))
    extra_codes = [_safe(it.get("code")) for it in okved_items[1:] if it.get("code")]
    return main, ", ".join(extra_codes) if extra_codes else "—"


def _draw_labeled_block(
    c: canvas.Canvas,
    *,
    left: float,
    top: float,
    width: float,
    label: str,
    value: str,
    label_font: str,
    text_font: str,
) -> float:
    """
    Рисует поле с подписью и значением в рамке.
    Возвращает новую Y-координату (top следующего блока).
    """
    label_size = 9
    text_size = 10
    pad_x = 8
    pad_y = 6

    c.setFont(label_font, label_size)
    c.drawString(left, top, label)

    max_text_width = width - (pad_x * 2)
    words = value.split()
    lines: list[str] = []
    current = ""

    for w in words:
        candidate = f"{current} {w}".strip()
        if pdfmetrics.stringWidth(candidate, text_font, text_size) <= max_text_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    if not lines:
        lines = ["—"]

    text_height = len(lines) * 14
    box_height = max(26, text_height + (pad_y * 2))
    box_top = top - 4
    box_bottom = box_top - box_height

    c.rect(left, box_bottom, width, box_height, stroke=1, fill=0)
    c.setFont(text_font, text_size)

    y = box_top - pad_y - 10
    for line in lines:
        c.drawString(left + pad_x, y, line)
        y -= 14

    return box_bottom - 12


def _generate_pdf_sync(pdf_path: Path, data: dict[str, Any]) -> None:
    """
    Синхронная генерация PDF через reportlab.
    Вызываем из async-контекста через asyncio.to_thread().
    """

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    page_width, page_height = A4
    margin = 40
    content_width = page_width - (margin * 2)

    font_regular, font_bold = _register_pdf_font()

    now_local = datetime.now(timezone.utc).astimezone()
    date_str = now_local.strftime("%d.%m.%Y")
    doc_number = f"GL-{now_local.strftime('%Y%m%d')}-{now_local.strftime('%H%M%S')}"

    okved_items = data.get("okved") or []
    main_okved, extra_okved = _okved_main_and_extra(okved_items if isinstance(okved_items, list) else [])

    # Header
    c.setFont(font_bold, 13)
    c.drawCentredString(page_width / 2, page_height - margin, "УВЕДОМЛЕНИЕ о включении в реестр транспортных экспедиторов")
    c.setFont(font_regular, 11)
    c.drawCentredString(page_width / 2, page_height - margin - 18, "Государственная информационная платформа ГосЛог")
    c.setFont(font_regular, 10)
    c.drawRightString(page_width - margin, page_height - margin - 36, f"Дата: {date_str}")
    c.drawRightString(page_width - margin, page_height - margin - 50, f"№ {doc_number}")

    y = page_height - margin - 78
    c.line(margin, y, page_width - margin, y)
    y -= 18

    legal_title = "Полное наименование организации" if data.get("business_type") == "ooo" else "ФИО индивидуального предпринимателя"
    y = _draw_labeled_block(
        c,
        left=margin,
        top=y,
        width=content_width,
        label=legal_title,
        value=_safe(data.get("name")),
        label_font=font_bold,
        text_font=font_regular,
    )

    half_gap = 12
    half_w = (content_width - half_gap) / 2
    y_row_top = y
    y_left = _draw_labeled_block(
        c,
        left=margin,
        top=y_row_top,
        width=half_w,
        label="ИНН",
        value=_safe(data.get("inn")),
        label_font=font_bold,
        text_font=font_regular,
    )
    y_right = _draw_labeled_block(
        c,
        left=margin + half_w + half_gap,
        top=y_row_top,
        width=half_w,
        label="ОГРН / ОГРНИП",
        value=_safe(data.get("ogrn")),
        label_font=font_bold,
        text_font=font_regular,
    )
    y = min(y_left, y_right)

    y = _draw_labeled_block(
        c,
        left=margin,
        top=y,
        width=content_width,
        label="Юридический адрес",
        value=_safe(data.get("address")),
        label_font=font_bold,
        text_font=font_regular,
    )
    y = _draw_labeled_block(
        c,
        left=margin,
        top=y,
        width=content_width,
        label="Фактический адрес",
        value=_safe(data.get("fact_address")),
        label_font=font_bold,
        text_font=font_regular,
    )

    y_row_top = y
    y_left = _draw_labeled_block(
        c,
        left=margin,
        top=y_row_top,
        width=half_w,
        label="Контактный телефон",
        value=_safe(data.get("phone")),
        label_font=font_bold,
        text_font=font_regular,
    )
    y_right = _draw_labeled_block(
        c,
        left=margin + half_w + half_gap,
        top=y_row_top,
        width=half_w,
        label="Email",
        value=_safe(data.get("email")),
        label_font=font_bold,
        text_font=font_regular,
    )
    y = min(y_left, y_right)

    y = _draw_labeled_block(
        c,
        left=margin,
        top=y,
        width=content_width,
        label="Основной ОКВЭД",
        value=main_okved,
        label_font=font_bold,
        text_font=font_regular,
    )
    y = _draw_labeled_block(
        c,
        left=margin,
        top=y,
        width=content_width,
        label="Дополнительные ОКВЭД",
        value=extra_okved,
        label_font=font_bold,
        text_font=font_regular,
    )
    y = _draw_labeled_block(
        c,
        left=margin,
        top=y,
        width=content_width,
        label="Дата начала деятельности",
        value=date_str,
        label_font=font_bold,
        text_font=font_regular,
    )

    # Signature + footer
    signature_y = max(y - 8, 115)
    c.setFont(font_regular, 10)
    c.drawString(margin, signature_y, "Подписано собственноручно / КЭП")
    c.line(margin + 210, signature_y - 2, page_width - margin, signature_y - 2)

    c.setFont(font_regular, 7.5)
    c.drawString(
        margin,
        55,
        "Сформировано с помощью ИИ-помощника ГосЛог Навигатор. Не является юридической консультацией.",
    )

    c.showPage()
    c.save()


@wizard_router.message(GoslogWizardState.waiting_for_inn)
async def on_waiting_for_inn(message: Message, state: FSMContext) -> None:
    """
    Шаг 1 wizard:
    - принимаем ИНН
    - делаем автозаполнение через Ofdata
    - сохраняем в WizardSession.data
    - переходим к шагу 2 (waiting_for_confirmation)
    """

    user_id = message.from_user.id  # type: ignore[union-attr]
    raw_inn = message.text or ""
    business_type = (await state.get_data()).get("business_type")

    logger.info("wizard step1: input inn uid={uid}", uid=user_id)

    expected_len = _inn_expected_len(str(business_type) if business_type else None)
    inn = _normalize_inn(raw_inn)

    if not inn or not inn.isdigit():
        await message.answer(
            "Введите корректный ИНН (только цифры)."
            + _disclaimer_line()
        )
        return

    if expected_len is not None and len(inn) != expected_len:
        await message.answer(
            f"Похоже, ИНН должен содержать {expected_len} цифр для выбранной формы бизнеса. "
            "Проверьте, пожалуйста, и попробуйте снова."
            + _disclaimer_line()
        )
        return

    # Создаём/берём wizard сессию и сохраняем base-данные.
    fsm_data = await state.get_data()
    await get_or_create_by_user_id(
        user_id,
        initial_step="waiting_for_inn",
        initial_data={
            "business_type": fsm_data.get("business_type"),
            "has_okved_5229": fsm_data.get("has_okved_5229"),
        },
    )

    await update_step(user_id, "waiting_for_inn")
    await merge_data(user_id, {"inn": inn})
    # Сбрасываем автозаполненные поля, чтобы не осталось "хвостов" от предыдущего ИНН
    # (актуально для кейса "Исправить", когда Ofdata может быть недоступен).
    await merge_data(
        user_id,
        {
            "name": None,
            "ogrn": None,
            "address": None,
            "okved": [],
            "has_okved_5229": None,
            "fns_autofill": {},
        },
    )

    lookup: dict[str, Any] | None = None
    lookup_error: str | None = None

    if not isinstance(business_type, str) or business_type not in {"ip", "ooo"}:
        lookup_error = "Не удалось определить форму бизнеса для wizard. Запустите `/start` заново."
        logger.warning("wizard step1: missing business_type uid={uid}", uid=user_id)
    else:
        try:
            ofdata_payload = await _fetch_ofdata_egrip_egul(business_type, inn)
            lookup = _build_fns_lookup_payload(
                business_type=business_type,
                inn=inn,
                response_json=ofdata_payload,
            )
            lookup_error = None
        except Exception as e:  # noqa: BLE001 - fallback обязателен
            lookup_error = f"Автозаполнение по ИНН сейчас недоступно: {type(e).__name__}"
            logger.exception("wizard step1: ofdata lookup failed uid={uid}", uid=user_id)

    # В любом случае двигаемся к шагу 2: подтверждение.
    await update_step(user_id, "waiting_for_confirmation")

    if lookup is not None:
        await merge_data(user_id, {"fns_autofill": lookup, **lookup})
    else:
        # Сохраняем хотя бы inn; остальные поля будут пустыми.
        await merge_data(
            user_id,
            {
                "fns_autofill": {
                    "inn": inn,
                    "business_type": business_type,
                }
            },
        )

    await state.set_state(GoslogWizardState.waiting_for_confirmation)

    name = (lookup or {}).get("name") if lookup else None
    ogrn = (lookup or {}).get("ogrn") if lookup else None
    address = (lookup or {}).get("address") if lookup else None
    okved_items = (lookup or {}).get("okved") if lookup else []
    has_5229 = (lookup or {}).get("has_okved_5229") if lookup else None

    biz_label = "ИП" if str(business_type) == "ip" else "ООО"
    warning_5229 = (
        ""
        if has_5229 is None or has_5229
        else "\n\n⚠️ В автоданных нет ОКВЭД 52.29. Проверьте корректность или подготовьте ручное уточнение."
    )

    fallback_line = ""
    if lookup_error:
        fallback_line = f"\n\n⚠️ {lookup_error}\nПереходим к шагу подтверждения — заполните данные вручную на следующем шаге."

    text = (
        "Шаг 2 из 5\n"
        "\n"
        "Подтвердите данные, найденные по ИНН.\n\n"
        "Я нашёл/попробовал найти данные по ИНН.\n\n"
        f"Форма бизнеса: <b>{biz_label}</b>\n"
        f"ИНН: <b>{inn}</b>\n"
        f"Наименование: <b>{name or '—'}</b>\n"
        f"ОГРН/ОГРНИП: <b>{ogrn or '—'}</b>\n"
        f"Адрес: <b>{address or '—'}</b>\n"
        f"ОКВЭДы (превью): <b>{_format_okved_preview(okved_items)}</b>"
        + warning_5229
        + fallback_line
        + _disclaimer_line()
    )

    await message.answer(text, reply_markup=wizard_confirm_keyboard())


@wizard_router.callback_query(
    GoslogWizardState.waiting_for_confirmation,
    F.data == "wizard_confirm:ok",
)
async def on_confirmation_ok(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 2: всё верно — переходим к сбору телефона/email/адреса."""

    user_id = callback.from_user.id
    logger.info("wizard step2 ok: uid={uid}", uid=user_id)

    await update_step(user_id, "waiting_for_phone_email")
    await state.set_state(GoslogWizardState.waiting_for_phone_email)

    await callback.message.edit_text(
        "Шаг 3 из 5\n\n"
        "Введите данные одним сообщением в формате:\n"
        "Телефон: +7...\n"
        "Email: name@domain.ru\n"
        "Фактический адрес: ...\n"
        + _disclaimer_line(),
    )
    await callback.answer()


@wizard_router.callback_query(
    GoslogWizardState.waiting_for_confirmation,
    F.data == "wizard_confirm:edit",
)
async def on_confirmation_edit(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 2: исправить — возвращаемся к вводу ИНН."""

    user_id = callback.from_user.id
    logger.info("wizard step2 edit: uid={uid}", uid=user_id)

    await update_step(user_id, "waiting_for_inn")
    await merge_data(
        user_id,
        {
            "inn": None,
            "name": None,
            "ogrn": None,
            "address": None,
            "okved": [],
            "has_okved_5229": None,
            "fns_autofill": {},
        },
    )
    await state.set_state(GoslogWizardState.waiting_for_inn)

    await callback.message.edit_text(
        "Шаг 1 из 5\n\n"
        "Введите ИНН (только цифры)."
        + _disclaimer_line()
    )
    await callback.answer()


@wizard_router.message(GoslogWizardState.waiting_for_phone_email)
async def on_waiting_for_phone_email(message: Message, state: FSMContext) -> None:
    """Шаг 3: получаем телефон, email и фактический адрес."""

    user_id = message.from_user.id
    logger.info("wizard step3 input phone/email/address uid={uid}", uid=user_id)

    text = message.text or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    phone: str | None = None
    email: str | None = None
    fact_address: str | None = None

    for ln in lines:
        lower = ln.lower()
        if "телефон" in lower:
            phone = ln.split(":", 1)[1].strip() if ":" in ln else ln
        elif "email" in lower or "почта" in lower:
            email = ln.split(":", 1)[1].strip() if ":" in ln else ln
        elif "адрес" in lower or "фактическ" in lower:
            fact_address = ln.split(":", 1)[1].strip() if ":" in ln else ln

    # fallback парсинг по позициям
    if not phone and lines:
        phone = lines[0]
    if not email and len(lines) > 1:
        email = lines[1]
    if not fact_address and len(lines) > 2:
        fact_address = "\n".join(lines[2:])

    email_re = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    if not phone or not email or not fact_address or not email_re.match(email):
        await message.answer(
            "Не получилось разобрать данные. Пожалуйста, пришлите в формате:\n"
            "Телефон: +7...\n"
            "Email: name@domain.ru\n"
            "Фактический адрес: ...\n"
            + _disclaimer_line()
        )
        return

    await update_step(user_id, "generating_pdf")
    await merge_data(
        user_id,
        {
            "phone": phone,
            "email": email,
            "fact_address": fact_address,
        },
    )

    # Собираем preview из уже сохранённых в wizard.data полей.
    fsm_data = await state.get_data()
    biz_label = "ИП" if str(fsm_data.get("business_type")) == "ip" else "ООО"
    await state.set_state(GoslogWizardState.generating_pdf)

    await message.answer(
        "Шаг 4 из 5\n\n"
        "Данные получены. Сейчас сгенерирую PDF и отправлю его вам.\n"
        + _disclaimer_line(),
        reply_markup=wizard_pdf_keyboard(),
    )


@wizard_router.callback_query(
    GoslogWizardState.generating_pdf,
    F.data == "wizard_pdf:generate",
)
async def on_generate_pdf(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 4: генерация PDF и отправка пользователю."""

    user_id = callback.from_user.id
    logger.info("wizard step4 generate pdf uid={uid}", uid=user_id)

    # Берём актуальные данные из БД.
    # Для MVP: вытаскиваем из БД через get_or_create_by_user_id и используем row.data.
    row = await get_or_create_by_user_id(user_id, initial_step="generating_pdf")
    wizard_data: dict[str, Any] = dict(row.data or {})

    inn = str(wizard_data.get("inn") or wizard_data.get("fns_autofill", {}).get("inn") or "")
    business_type = str(wizard_data.get("business_type") or wizard_data.get("fns_autofill", {}).get("business_type") or "")

    fns_autofill = wizard_data.get("fns_autofill") or {}
    merged = {
        **wizard_data,
        **(fns_autofill if isinstance(fns_autofill, dict) else {}),
        "inn": inn or None,
        "business_type": business_type if business_type in {"ip", "ooo"} else wizard_data.get("business_type"),
    }

    pdf_dir = Path("goslog_navigator_bot/bot/temp_pdfs")
    pdf_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    pdf_filename = f"{user_id}_{timestamp}.pdf"
    pdf_path = pdf_dir / pdf_filename

    await update_step(user_id, "generating_pdf")
    await merge_data(user_id, {"pdf": {"filename": pdf_filename, "generated_at": timestamp}})

    try:
        await asyncio.to_thread(_generate_pdf_sync, pdf_path, merged)
    except Exception:  # noqa: BLE001 - нужна fallback-ошибка
        logger.exception("wizard step4 pdf generation failed uid={uid}", uid=user_id)
        await callback.message.answer(
            "Не удалось сгенерировать PDF сейчас. Попробуйте повторить шаг позже."
            + _disclaimer_line()
        )
        await callback.answer()
        return

    await callback.message.answer_document(
        document=FSInputFile(str(pdf_path)),
        caption="Готово. Вот ваш PDF-документ." + _disclaimer_line(),
    )

    instruction = (
        "Шаг 5 из 5\n\n"
        "Как отправить уведомление через Госуслуги:\n\n"
        "1) Откройте Госуслуги и перейдите в раздел, связанный с подачей уведомлений.\n"
        "2) Выберите организацию/ИП и загрузите файл PDF.\n"
        "3) Проверьте реквизиты (ИНН, адрес, ОКВЭД) и подтвердите отправку.\n"
        "4) Сохраните номер/статус отправки.\n\n"
        "Подсказки (превью):\n"
        f"1) https://placehold.co/800x450?text=Gosuslugi+Step+1\n"
        f"2) https://placehold.co/800x450?text=Gosuslugi+Step+2\n"
        f"3) https://placehold.co/800x450?text=Gosuslugi+Step+3\n"
        f"4) https://placehold.co/800x450?text=Gosuslugi+Step+4\n"
        + _disclaimer_line()
    )

    await merge_data(
        user_id,
        {
            "pdf": {
                "filename": pdf_filename,
                "generated_at": timestamp,
                "sent_to_user": True,
            }
        },
    )

    await update_step(user_id, "finished")
    await state.set_state(GoslogWizardState.finished)
    await callback.message.answer(instruction, reply_markup=wizard_finish_keyboard())
    await callback.answer()


@wizard_router.callback_query(
    GoslogWizardState.generating_pdf,
    F.data == "wizard_pdf:cancel",
)
async def on_pdf_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    """Отмена wizard на шаге генерации PDF."""

    user_id = callback.from_user.id
    logger.info("wizard cancelled in generating_pdf uid={uid}", uid=user_id)

    await merge_data(user_id, {"status": "cancelled"})
    await state.clear()
    await update_step(user_id, "finished")

    await callback.message.edit_text(
        "Wizard отменён. Если захотите продолжить — отправьте /start снова."
        + _disclaimer_line()
    )
    await callback.answer()


@wizard_router.callback_query(
    GoslogWizardState.finished,
    F.data == "wizard_finish:done",
)
async def on_finish_done(callback: CallbackQuery, state: FSMContext) -> None:
    """Шаг 5 завершение: пользователь подтвердил, что отправил в Госуслугах."""

    user_id = callback.from_user.id
    logger.info("wizard done uid={uid}", uid=user_id)

    now = datetime.now(timezone.utc).isoformat()
    await merge_data(
        user_id,
        {
            "sent_to_gosuslugi": True,
            "sent_at": now,
        },
    )
    await mark_finished(user_id, status="completed")
    await state.clear()

    await callback.message.edit_text(
        "Спасибо! Я отметил, что вы отправили уведомление через Госуслуги."
        + _disclaimer_line()
    )
    await callback.answer()

