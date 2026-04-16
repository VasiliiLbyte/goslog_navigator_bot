"""
Модуль 3: проверка ИНН через Ofdata + публичную страницу ГосЛог.

Логика Ofdata переиспользует функции из wizard (единый источник запросов).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from goslog_navigator_bot.bot.handlers.wizard import (
    _build_fns_lookup_payload,
    _fetch_ofdata_egrip_egul,
    _normalize_inn,
    _okved_main_and_extra,
)
from goslog_navigator_bot.core.config import settings


@dataclass(slots=True)
class InnCheckResult:
    """Снимок проверки для карточки пользователя и сохранения в БД."""

    inn: str
    business_type_used: str
    display_name: str | None
    okved_main: str | None
    okved_extra: str | None
    status_text: str | None
    reg_date: str | None
    in_goslog_registry: bool | None
    goslog_check_note: str | None
    needs_attention: bool
    raw_ofdata: dict[str, Any] | None
    ofdata_error: str | None


def _infer_business_type(inn: str) -> str:
    """По длине ИНН выбираем endpoint Ofdata: ИП (12) или юрлицо (10)."""
    if len(inn) == 12:
        return "ip"
    if len(inn) == 10:
        return "ooo"
    raise ValueError("ИНН должен содержать 10 (ООО) или 12 (ИП) цифр.")


def _response_data(ofdata_json: dict[str, Any]) -> dict[str, Any]:
    data = ofdata_json.get("data")
    return data if isinstance(data, dict) else {}


def _extract_status_line(response_data: dict[str, Any]) -> str | None:
    """Достаём человекочитаемый статус из сырого блока Ofdata (ключи могут отличаться)."""
    for key in ("Статус", "Статуса", "СвСтатус", "status"):
        v = response_data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict):
            text = v.get("Наим") or v.get("name") or v.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    return None


def _extract_reg_date(response_data: dict[str, Any]) -> str | None:
    for key in ("ДатаОГРН", "ДатаРег", "ДатаРегистрации", "ДатаОГРНИП", "date_reg"):
        v = response_data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _needs_attention_from_status(status: str | None) -> bool:
    if not status:
        return False
    s = status.lower()
    return any(
        w in s
        for w in (
            "ликвидац",
            "прекращ",
            "банкрот",
            "исключен",
            "недейств",
        )
    )


def _parse_goslog_from_json(payload: Any) -> tuple[bool | None, str | None]:
    """Если ответ JSON — пробуем извлечь признак присутствия в реестре."""
    if not isinstance(payload, dict):
        return None, None
    for key_true in ("in_registry", "inRegistry", "registered", "found", "exists"):
        if key_true in payload and isinstance(payload[key_true], bool):
            return payload[key_true], None
    for key_str in ("status", "result", "message"):
        val = payload.get(key_str)
        if isinstance(val, str):
            low = val.lower()
            if "не найден" in low or "отсутств" in low:
                return False, val[:200]
            if "найден" in low and "реестр" in low:
                return True, val[:200]
    return None, None


def _parse_goslog_from_text(text: str) -> tuple[bool | None, str | None]:
    """Эвристика по HTML/тексту публичной страницы (структура сайта может меняться)."""
    low = text.lower()
    # Явные отрицания
    if "не найден" in low or "отсутствует в реестре" in low or "нет в реестре" in low:
        return False, None
    if "не зарегистрирован" in low and "реестр" in low:
        return False, None
    # Положительные формулировки
    if ("найден" in low or "присутствует" in low) and "реестр" in low:
        return True, None
    if "зарегистрирован" in low and "гослог" in low:
        return True, None
    return None, None


async def check_goslog_public(inn: str) -> tuple[bool | None, str | None]:
    """
    Запрос к публичной проверке goslog.ru (best-effort).

    Возвращает (в_реестре_или_None, заметка).
    """
    base = settings.goslog_public_check_url.rstrip("/")
    urls = [
        f"{base}?inn={inn}",
        f"{base}/{inn}",
        f"https://goslog.ru/check?inn={inn}",
    ]
    # Убираем дубликаты, сохраняя порядок
    seen: set[str] = set()
    unique_urls: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            unique_urls.append(u)

    timeout = settings.goslog_http_timeout_sec
    last_err: str | None = None
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        for url in unique_urls:
            try:
                resp = await client.get(url)
                if resp.status_code >= 500:
                    last_err = f"http_{resp.status_code}"
                    continue
                ctype = (resp.headers.get("content-type") or "").lower()
                text = resp.text or ""
                if "json" in ctype or text.strip().startswith("{"):
                    try:
                        payload = json.loads(text)
                        hit, note = _parse_goslog_from_json(payload)
                        if hit is not None:
                            logger.info(
                                "goslog check JSON inn={inn} url={url} hit={hit}",
                                inn=inn,
                                url=url,
                                hit=hit,
                            )
                            return hit, note
                    except json.JSONDecodeError:
                        pass
                hit, note = _parse_goslog_from_text(text)
                if hit is not None:
                    logger.info(
                        "goslog check TEXT inn={inn} url={url} hit={hit}",
                        inn=inn,
                        url=url,
                        hit=hit,
                    )
                    return hit, note
                last_err = "ambiguous_body"
            except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError) as e:
                logger.warning("goslog check network inn={inn} err={e!s}", inn=inn, e=e)
                last_err = "network"
            except httpx.HTTPError as e:
                logger.warning("goslog check http inn={inn} err={e!s}", inn=inn, e=e)
                last_err = "http_error"

    logger.info("goslog check inconclusive inn={inn} last={last}", inn=inn, last=last_err)
    return None, last_err


async def run_inn_check(inn_raw: str) -> InnCheckResult:
    """
    Полная проверка: Ofdata (если есть ключ) + публичный ГосЛог.

    Ошибки внешних сервисов не бросаем наружу — упаковываем в поля результата.
    """
    inn = _normalize_inn(inn_raw)
    ofdata_error: str | None = None
    raw_ofdata: dict[str, Any] | None = None
    business_type = _infer_business_type(inn)
    display_name = None
    okved_main = None
    okved_extra = None
    status_text = None
    reg_date = None

    if settings.fns_api_key:
        try:
            raw_ofdata = await _fetch_ofdata_egrip_egul(business_type, inn)
            built = _build_fns_lookup_payload(
                business_type=business_type, inn=inn, response_json=raw_ofdata
            )
            display_name = built.get("name")
            okved_items = built.get("okved") or []
            if isinstance(okved_items, list):
                okved_main, okved_extra = _okved_main_and_extra(
                    [x for x in okved_items if isinstance(x, dict)]
                )
            rd = _response_data(raw_ofdata)
            status_text = _extract_status_line(rd)
            reg_date = _extract_reg_date(rd)
        except Exception as e:
            logger.exception("Ofdata check failed inn={inn}", inn=inn)
            ofdata_error = str(e)[:300]
            raw_ofdata = None
    else:
        ofdata_error = "Ключ Ofdata не настроен (FNS_API_KEY)."
        logger.warning("Ofdata skipped: no API key inn={inn}", inn=inn)

    goslog_note: str | None = None
    in_goslog: bool | None = None
    try:
        in_goslog, goslog_note = await check_goslog_public(inn)
    except Exception as e:
        logger.exception("Goslog public check unexpected inn={inn}", inn=inn)
        goslog_note = str(e)[:200]
        in_goslog = None

    needs = _needs_attention_from_status(status_text) or (in_goslog is None)

    return InnCheckResult(
        inn=inn,
        business_type_used=business_type,
        display_name=display_name,
        okved_main=okved_main,
        okved_extra=okved_extra,
        status_text=status_text,
        reg_date=reg_date,
        in_goslog_registry=in_goslog,
        goslog_check_note=goslog_note,
        needs_attention=needs,
        raw_ofdata=raw_ofdata,
        ofdata_error=ofdata_error,
    )


def format_registry_line(flag: bool | None) -> str:
    """Строка для карточки: в реестре / не найден / не удалось проверить."""
    if flag is True:
        return "В реестре ГосЛог ✅"
    if flag is False:
        return "В реестре ГосЛог — не найден ❌"
    return "В реестре ГосЛог — не удалось определить ⚠️"


def format_inn_card(result: InnCheckResult) -> str:
    """HTML-текст карточки для Telegram."""
    reg = format_registry_line(result.in_goslog_registry)
    ok_main = result.okved_main or "—"
    ok_extra = (result.okved_extra or "—")[:400]
    st = result.status_text or "—"
    rd = result.reg_date or "—"
    name = result.display_name or "—"
    lines = [
        f"<b>Проверка ИНН</b> <code>{result.inn}</code>",
        "",
        reg,
        f"ОКВЭД (осн.): <b>{ok_main}</b>",
        f"ОКВЭД (доп.): {ok_extra}",
        f"Статус (ЕГРЮЛ/ЕГРИП): {st}",
        f"Дата регистрации: {rd}",
        f"Наименование: {name}",
    ]
    if result.ofdata_error:
        lines.append("")
        lines.append(f"⚠️ Данные Ofdata: {result.ofdata_error}")
    if result.goslog_check_note and result.in_goslog_registry is None:
        lines.append("")
        lines.append(f"ℹ️ Примечание по ГосЛог: {result.goslog_check_note}")
    return "\n".join(lines)
