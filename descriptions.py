"""Name-based hints for catalog tables."""

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

def describe(table):
    last = table.rsplit('.', 1)[-1]
    translated = [GLOSSARY.get(t, t) for t in last.split('_')]
    if any(a != b for a, b in zip(translated, last.split('_'))):
        return ' / '.join(translated), 'предположение по названию'
    return 'Описание не задано', 'неизвестно'
