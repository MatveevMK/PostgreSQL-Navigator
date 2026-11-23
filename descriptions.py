"""Manually reviewed hints + explicitly labelled name-based guesses.

Descriptions are labels, NOT authoritative business documentation.
"""
import re

# Meaning is informed by names / earlier SQL, not approved data dictionary.
EXPLICIT = {
    'orders.orders': 'Заказы (основная таблица)',
    'booking.booking': 'Онлайн-бронирования, связанные с заказами',
    'booking.booking_item': 'Позиции онлайн-бронирований (порции)',
    'booking.booking_room': 'Номера в онлайн-бронировании',
    'booking.guest': 'Гости онлайн-бронирований; поле child отмечает ребёнка',
    'dictionary.hotel': 'Справочник отелей',
    'dictionary.city': 'Справочник городов',
    'dictionary.country': 'Справочник стран',
    'dictionary.region': 'Справочник регионов',
    'offline.item': 'Позиции офлайн-заказов',
    'offline.item_hotel': 'Отельные данные офлайн-позиции; количества adults и children',
    'orders.curator': 'Связи заказов с кураторами / менеджерами',
    'currency.currency_rates': 'Курсы валют',
    'hotel.provider': 'Поставщики отелей',
    'hotel.provider_translation': 'Локализованные названия поставщиков',
}

GLOSSARY = {
    'orders': 'заказы', 'order': 'заказ', 'booking': 'бронирования',
    'hotel': 'отель', 'hotels': 'отели', 'room': 'номер', 'rooms': 'номера',
    'guest': 'гости', 'guests': 'гости', 'city': 'город', 'country': 'страна',
    'region': 'регион', 'currency': 'валюта', 'currencies': 'валюты',
    'rate': 'курс/тариф', 'rates': 'курсы/тарифы', 'manager': 'менеджер',
    'account': 'аккаунт/учётная запись', 'user': 'пользователь',
    'client': 'клиент', 'supplier': 'поставщик', 'provider': 'поставщик',
    'contract': 'договор', 'payment': 'платёж', 'invoice': 'счёт',
    'item': 'позиция', 'status': 'статус', 'category': 'категория',
}

# A small, consciously controlled language layer before adding Ollama.
# Priority: unambiguous, verified full table names where present.
ALIASES = [
    (r'\b(заказ\w*|ордер\w*|orders?\b)\b', ('orders.orders',)),
    (r'\b(бронирован\w*|брон\w*|booking\b)\b', ('booking.booking',)),
    (r'\b(отел\w*|гостиниц\w*|hotel\w*)\b', ('dictionary.hotel',)),
    (r'\b(стран\w*|государств\w*|countr\w*)\b', ('dictionary.country',)),
    (r'\b(город\w*|city\b|cities\b)\b', ('dictionary.city',)),
    (r'\b(регион\w*|region\w*)\b', ('dictionary.region',)),
    (r'\b(гост\w*|guest\w*)\b', ('booking.guest',)),
    (r'\b(номер\w*|комнат\w*|room\w*)\b', ('booking.booking_room',)),
    (r'\b(курс\w*\s+валют\w*|валютн\w*\s+курс\w*)\b', ('currency.currency_rates',)),
]


def describe(table):
    if table in EXPLICIT:
        return EXPLICIT[table], 'ориентир по исходному SQL; бизнес-смысл уточнять'
    last = table.rsplit('.', 1)[-1]
    translated = [GLOSSARY.get(t, t) for t in last.split('_')]
    if any(a != b for a, b in zip(translated, last.split('_'))):
        return ' / '.join(translated), 'предположение по названию'
    return 'Описание не задано', 'неизвестно'


def resolve_question(text, catalog):
    """Only maps explicit table mentions and known words to known tables.

    Unsupported wording causes no invented semantic matches.
    """
    prompt = text.lower().strip().replace('ё', 'е')
    present = {t.lower(): t for t in catalog.tables}
    matches = []
    # User can explicitly say schema.table regardless of glossary.
    for lowered, original in present.items():
        if re.search(r'(?<![\w.])' + re.escape(lowered) + r'(?![\w.])', prompt):
            matches.append((prompt.index(lowered), original))
    for pattern, candidates in ALIASES:
        for hit in re.finditer(pattern, prompt, flags=re.I):
            for candidate in candidates:
                if candidate in catalog.tables:
                    matches.append((hit.start(), candidate))
    matches.sort(key=lambda x: x[0])
    ordered = []
    for _, table in matches:
        if table not in ordered:
            ordered.append(table)
    return ordered
