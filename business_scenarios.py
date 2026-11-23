"""Read-only, provenance-labelled business routes based on user-provided sources.

The first Excel documents columns; the second documents FK-like relations.
Two order -> booking/item joins are absent from the FK Excel but are explicitly
present in the user's original SQL. No query is executed or generated.
"""
from dataclasses import dataclass
import re
from typing import Tuple


@dataclass(frozen=True)
class VerifiedEdge:
    child: str
    parent: str
    child_column: str
    parent_column: str
    source: str  # 'Excel' or 'Исходный SQL'

    @property
    def expression(self):
        return f'{self.child}.{self.child_column} = {self.parent}.{self.parent_column}'


@dataclass(frozen=True)
class BusinessRoute:
    code: str
    title: str
    entities: str
    nodes: Tuple[str, ...]
    edges: Tuple[VerifiedEdge, ...]
    flag_table: str
    flag_field: str
    notes: Tuple[str, ...]


# JOINs directly verified against the user-supplied SQL containing ZAKAZI.
# The two links below are NOT present in the FK Excel.
SQL_VERIFIED = {
    ('booking.booking', 'orders.orders', 'order_id', 'id'),
    ('offline.item', 'orders.orders', 'order_id', 'id'),
}

BRANCHES = {
    'online': {
        'title': 'Онлайн — заказы, номера, гости и дети',
        'entities': 'Отдельные гости доступны в booking.guest',
        'edges': (
            ('booking.booking', 'orders.orders', 'order_id', 'id', 'Исходный SQL'),
            ('booking.booking_item', 'booking.booking', 'booking_id', 'id', 'Excel'),
            ('booking.booking_room', 'booking.booking_item', 'booking_item_id', 'id', 'Excel'),
            ('booking.guest', 'booking.booking_room', 'booking_room_id', 'id', 'Excel'),
        ),
        'flag_table': 'booking.guest',
        'flag_field': 'child',
        'notes': (
            'Поле booking.guest.child отмечает ребёнка у конкретного гостя.',
            'Чтобы получить флаг «есть хотя бы один ребёнок» для позиции бронирования, нужно объединить сведения обо всех гостях её номеров.',
            'Если присоединить гостей напрямую к заказам, один заказ может повториться для каждого гостя. Это важно для подсчёта заказов и сумм.',
        ),
    },
    'offline': {
        'title': 'Офлайн — заказы, отельные позиции и дети',
        'entities': 'В доступной схеме есть количество взрослых и детей, но нет подтверждённого списка отдельных гостей',
        'edges': (
            ('offline.item', 'orders.orders', 'order_id', 'id', 'Исходный SQL'),
            ('offline.item_hotel', 'offline.item', 'id', 'id', 'Excel'),
        ),
        'flag_table': 'offline.item_hotel',
        'flag_field': 'children',
        'notes': (
            'Поле offline.item_hotel.children содержит количество детей: значение больше нуля означает наличие ребёнка.',
            'В offline.item_hotel.adults доступно число взрослых. Имена отдельных гостей в этой подтверждённой цепочке отсутствуют.',
            'Отельные позиции определяются типом offline.item.discr = hotel — это бизнес-ограничение из исходного SQL, а не условие связи.',
        ),
    },
}


def _has_column(catalog, table, column):
    schema, name = table.split('.', 1)
    df = catalog.columns
    return bool(((df.table_schema == schema) & (df.table_name == name) & (df.column_name == column)).any())


def build_business_route(catalog, branch):
    """Validate every relation and every column before producing diagrams.

    Excel edges must be present verbatim in the imported relationships.
    SQL edges must be in the narrowly reviewed whitelist and have real columns.
    """
    if branch not in BRANCHES:
        raise ValueError('Неизвестная ветка бронирований: ' + branch)
    definition = BRANCHES[branch]
    edges = []
    nodes = []
    for child, parent, child_col, parent_col, source in definition['edges']:
        if not _has_column(catalog, child, child_col) or not _has_column(catalog, parent, parent_col):
            raise ValueError(f'В первом Excel отсутствует один из столбцов: {child}.{child_col} / {parent}.{parent_col}')
        if source == 'Excel':
            matching = [e for e in catalog.links if (e.child, e.parent, e.child_column, e.parent_column) ==
                        (child, parent, child_col, parent_col)]
            if not matching:
                raise ValueError(f'Не подтверждён JOIN во втором Excel: {child}.{child_col} → {parent}.{parent_col}')
        else:
            if (child, parent, child_col, parent_col) not in SQL_VERIFIED:
                raise ValueError('JOIN не подтверждён в исходном SQL')
        edges.append(VerifiedEdge(child, parent, child_col, parent_col, source))
        for node in (child, parent):
            if node not in nodes:
                nodes.append(node)
    if not _has_column(catalog, definition['flag_table'], definition['flag_field']):
        raise ValueError('Поле детей не найдено в каталоге столбцов')
    return BusinessRoute(branch, definition['title'], definition['entities'], tuple(nodes), tuple(edges),
                         definition['flag_table'], definition['flag_field'], definition['notes'])


def recognize_business_question(question):
    """Recognize a deliberately narrow request, not free-form LLM inference.

    Returns ('online', 'offline') or a subset. Other queries use ordinary
    schema-name matching. A user has confirmed «клиенты» means guests here.
    """
    text = question.lower().replace('ё', 'е')
    about_orders = bool(re.search(r'\b(заказ\w*|ордер\w*|orders?\b)\b', text))
    about_guests = bool(re.search(r'\b(гост\w*|клиент\w*|постоял\w*|турист\w*|guest\w*)\b', text))
    about_children = bool(re.search(r'\b(дет\w*|ребен\w*|ребят\w*|child\w*|children)\b', text))
    about_online = bool(re.search(r'\b(онлайн\w*|online)\b', text))
    about_offline = bool(re.search(r'\b(офлайн\w*|оффлайн\w*|offline)\b', text))
    if not (about_orders and (about_guests or about_children)):
        return None
    if about_online and not about_offline:
        return ('online',)
    if about_offline and not about_online:
        return ('offline',)
    return ('online', 'offline')
