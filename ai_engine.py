"""Two-stage local Ollama discovery; never asks the model to invent JOINs.

Language model: intent / candidate fields only. Python graph: relations in uploaded Excel only.
There are no prewritten question-specific business rules or supplemental links.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import re
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class AIError(RuntimeError):
    pass


def check_local_server(server: str) -> str:
    """Don't silently send a schema to a remote Ollama endpoint."""
    server = server.strip().rstrip('/')
    parsed = urlsplit(server)
    if parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
        raise AIError('Разрешена только локальная Ollama: http://127.0.0.1:11434')
    if parsed.path not in ('', '/') or parsed.username or parsed.password:
        raise AIError('Неожиданный адрес Ollama. Используй http://127.0.0.1:11434')
    return server


def local_model(model: str) -> str:
    model = model.strip()
    if not model or len(model) > 100 or 'cloud' in model.lower():
        raise AIError('Выбери локальную модель (например, qwen2.5:7b), не cloud-модель.')
    return model


def parse_json_answer(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.I)
        raw = re.sub(r'\s*```$', '', raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIError('Модель вернула ответ не в JSON. Попробуй ещё раз или выбери другую модель.') from exc
    if not isinstance(result, dict):
        raise AIError('Ожидался JSON-объект от модели.')
    return result


def ollama_chat(messages: list[dict], model='qwen2.5:7b', server='http://127.0.0.1:11434', timeout=180, capture=None) -> dict:
    server = check_local_server(server)
    model = local_model(model)
    payload = json.dumps({
        'model': model, 'messages': messages, 'stream': False, 'format': 'json',
        'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 850},
        'keep_alive': '10m',
    }).encode('utf-8')
    request = Request(server + '/api/chat', data=payload,
                      headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            raw_response = response.read().decode('utf-8')
            if capture is not None:
                capture(raw_response)
            result = json.loads(raw_response)
    except HTTPError as exc:
        details = exc.read().decode('utf-8', 'replace')[:350]
        if capture is not None:
            capture(details)
        raise AIError(f'Ollama вернула ошибку HTTP {exc.code}: {details}') from exc
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise AIError('Нет соединения с локальной Ollama. Проверь, что она запущена на 127.0.0.1:11434. '
                      f'Подробности: {exc}') from exc
    try:
        answer = result['message']['content']
    except (KeyError, TypeError):
        raise AIError('Ответ Ollama не содержит текста модели.')
    return parse_json_answer(answer)


def column_index(catalog) -> dict[str, list[str]]:
    grouped = defaultdict(list)
    for row in catalog.columns.itertuples(index=False):
        name = str(row.table_schema) + '.' + str(row.table_name)
        grouped[name].append(str(row.column_name))
    return dict(grouped)


def normalized_tokens(text: str) -> list[str]:
    return [token for token in re.split(r'[^a-z0-9]+', text.lower()) if len(token) >= 2]


def _strings(value, limit=30) -> list[str]:
    if not isinstance(value, list):
        return []
    return [x.strip()[:120] for x in value[:limit] if isinstance(x, str) and x.strip()]


def interpret_intent(question: str, catalog, chat: Callable = ollama_chat) -> dict:
    """Stage 1: the model reads ALL table identifiers, but no large column list."""
    listing = ', '.join(catalog.tables)
    system = (
        'You are a PostgreSQL *schema discovery* assistant. Translate Russian business '
        'question into English PostgreSQL identifier keywords. Do not generate SQL or JOINs. '
        'Output ONLY JSON object with keys: keywords (array of 8-20 English words, variants '
        'of DB identifier terms such as price, gross, net, cost, customer, supplier), '
        'table_hints (array of 0-7 exact schema.table identifiers FROM THE LIST ONLY), '
        'question_parts (array of 1-3 independent aspects of the user question, Russian). '
        'Do not assume that price and net are certified business definitions. '
        'Do not invent relations. If online/offline are requested, reflect both as separate question_parts.'
    )
    data = chat([{'role': 'system', 'content': system},
                 {'role': 'user', 'content': 'Existing tables: ' + listing + '\n\nUser question: ' + question}])
    keywords = []
    for raw in _strings(data.get('keywords'), 25):
        for token in normalized_tokens(raw):
            if token not in keywords:
                keywords.append(token)
    hints = [t for t in _strings(data.get('table_hints'), 10) if t in catalog.tables]
    return {'keywords': keywords[:30], 'hints': hints,
            'parts': _strings(data.get('question_parts'), 3) or [question]}


def rank_candidates(question: str, intent: dict, catalog, max_tables=36) -> list[str]:
    """Metadata-only lexical retrieval. Uses LLM-proposed terms, not per-question rules."""
    index = column_index(catalog)
    keyword_set = set(intent.get('keywords', [])) | set(normalized_tokens(question))
    hints = set(intent.get('hints', [])) & set(catalog.tables)
    scores = []
    for table in catalog.tables:
        parts = set(normalized_tokens(table))
        name_matches = keyword_set & parts
        col_hits = set()
        hits = 0
        for c in index.get(table, []):
            matched = keyword_set & set(normalized_tokens(c))
            if matched:
                hits += 1
                col_hits |= matched
        exact_user_mention = table.lower() in question.lower()
        score = len(name_matches) * 15 + len(col_hits) * 6 + min(hits, 12) * 0.5
        score += len((name_matches | col_hits)) * 3
        if table in hints:
            score += 65
        if exact_user_mention:
            score += 125
        if score:
            scores.append((-score, table))
    scores.sort()
    result = [t for _, t in scores[:max_tables]]
    # Model-proposed precise matches are always included (up to configured cap).
    for table in intent.get('hints', []):
        if table in catalog.tables and table not in result:
            if len(result) >= max_tables:
                result.pop()
            result.append(table)
    return result


def candidate_text(catalog, selected: list[str], intent: dict, max_columns=24) -> str:
    index = column_index(catalog)
    terms = set(intent.get('keywords', []))
    lines = []
    for table in selected:
        columns = index.get(table, [])
        scored = sorted(columns, key=lambda x: (
            -len(terms & set(normalized_tokens(x))),
            -int(x.lower() in terms), x,
        ))
        excerpt = scored[:max_columns]
        remainder = len(columns) - len(excerpt)
        lines.append(f'{table}: ' + ', '.join(excerpt) + (f' [...+{remainder} columns]' if remainder else ''))
    return '\n'.join(lines)


def select_schema(question: str, catalog, intent: dict, candidates: list[str], chat: Callable = ollama_chat, diagnostic=None) -> dict:
    """Stage 2: only metadata-extracted candidates can be selected."""
    system = (
        'You are a schema catalog analyst. Choose tables and informative field names from '
        'the candidate schema below to HELP a person DRAW entity connection diagrams. '
        'Reply ONLY JSON: {"groups":[{"title":"Russian title","tables":["exact schema.table"], '
        '"fields":["exact schema.table.column"],"why":"short Russian reason"}], '
        '"uncertainties":["Russian warning"]}. '
        'Use ONE group for entities requested together in a connected report. Do not split orders, hotels and guests into separate groups merely because they are different entities. Use 2-3 groups only for genuinely separate alternatives such as online/offline. '
        'Usually 1-5 distinct tables per group, no more than 8, and 1-8 fields per group. '
        'SELECT ONLY table and column identifiers explicitly provided in the catalog; '
        'DO NOT fabricate missing columns, JOIN conditions or SQL. '
        'Multiple price fields may be alternatives; never claim which equals supplier/buyer '
        'cost unless documented. If a fact cannot be identified from names, say uncertain. '
        'Do not write SQL. A group may have only one table if appropriate.'
    )
    context = candidate_text(catalog, candidates, intent)
    # Supply actual reachability, not just lexical resemblance, to the model.
    components = {}
    for table in catalog.tables:
        if table in components:
            continue
        component = len(set(components.values()))
        pending = [table]
        components[table] = component
        while pending:
            current = pending.pop()
            for other, _ in catalog.adjacency.get(current, []):
                if other not in components:
                    components[other] = component
                    pending.append(other)
    context += '\nConnectivity components (different numbers cannot be joined):\n'
    context += '\n'.join(t + ': ' + str(components[t]) for t in candidates)
    context += '\nConfirmed direct relations:\n' + '\n'.join(
        e.expression for e in catalog.links if e.child in candidates and e.parent in candidates)
    system += (' Prefer a minimal set of tables covering the request. Do not include price, hotel details or audit tables unless needed. '
               'Use connectivity information: do not claim disconnected tables can be joined. '
               'Audit records are not evidence of client chat. A comment is not necessarily a conversation. '
               'For missing concepts explicitly state what cannot be identified. Never suggest joining arbitrary id fields. '
               'Keep entities requested together in one group; separate groups only for alternative interpretations.')
    data = chat([{'role':'system', 'content':system},
                 {'role':'user', 'content': 'User request: '+question + '\n'
                  'Aspects: ' + '; '.join(intent['parts']) + '\n'
                  'Candidate tables with real column names:\n' + context}])
    index = column_index(catalog)
    allowed = set(candidates) & set(catalog.known)
    def reject(kind, value, reason):
        if diagnostic is not None:
            diagnostic['rejected_candidates'].append({'stage': 'selection', 'kind': kind,
                                                       'value': value, 'reason': reason})
    groups = []
    for candidate in data.get('groups', [])[:3] if isinstance(data.get('groups'), list) else []:
        if not isinstance(candidate, dict):
            continue
        proposed_tables = _strings(candidate.get('tables'), 8)
        tables = list(dict.fromkeys(t for t in proposed_tables if t in allowed))
        for table in proposed_tables:
            if table not in allowed:
                reject('table', table, 'not_in_column_catalog' if table not in catalog.known else 'not_in_candidates')
        selected_fields = []
        for field in _strings(candidate.get('fields'), 15):
            if '.' not in field:
                matches = [t + '.' + field for t in tables if field in index.get(t, [])]
                if len(matches) == 1:
                    if diagnostic is not None:
                        diagnostic.setdefault('normalized_fields', []).append({'original': field, 'resolved': matches[0]})
                    field = matches[0]
            table, sep, col = field.rpartition('.')
            if sep and table in tables and col in index.get(table, []) and field not in selected_fields:
                selected_fields.append(field)
            elif field not in selected_fields:
                reject('field', field, 'table_not_selected' if table not in tables else 'column_not_in_catalog')
        if not tables:
            continue
        groups.append({'title': str(candidate.get('title') or 'Вариант')[:130],
                       'tables': tables, 'fields': selected_fields[:10],
                       'why': str(candidate.get('why') or '')[:550]})
    if diagnostic is not None:
        selected = {t for group in groups for t in group['tables']}
        for table in candidates:
            if table not in selected:
                reject('table', table, 'not_selected_in_validated_result')
    if not groups:
        raise AIError('Модель не выбрала подтверждённые таблицы из каталога. Попробуй переформулировать вопрос.')
    return {'groups': groups, 'uncertainties': _strings(data.get('uncertainties'), 8),
            'keywords': intent['keywords'], 'candidates': candidates}


def analyze(question: str, catalog, model='qwen2.5:7b', server='http://127.0.0.1:11434', chat=None, diagnostic=None, excluded_schemas=()) -> dict:
    if not question or not question.strip():
        raise AIError('Напиши вопрос.')
    if len(question) > 2500:
        raise AIError('Вопрос слишком длинный. Сократи до 2500 символов.')
    # Reusing a test/mock transport is deliberate: no external Ollama is needed for unit tests.
    check_local_server(server)
    local_model(model)
    transport = chat
    stage = 'intent'
    def monitored_chat(messages):
        event = {'stage': stage}
        if diagnostic is not None:
            diagnostic['ollama'].append(event)
        def capture(raw):
            event['raw_response'] = raw
        try:
            data = (transport(messages) if transport is not None else
                    ollama_chat(messages, model=model, server=server, capture=capture))
            event['parsed_response'] = data
            return data
        except Exception as exc:
            event['error'] = {'type': type(exc).__name__, 'message': str(exc)}
            raise
    if excluded_schemas:
        from dataclasses import replace
        allowed = [t for t in catalog.tables if t.split('.', 1)[0] not in excluded_schemas]
        catalog = replace(catalog, tables=allowed, known=catalog.known & set(allowed),
                          columns=catalog.columns[~catalog.columns.table_schema.isin(excluded_schemas)])
        if diagnostic is not None:
            diagnostic['excluded_schemas'] = list(excluded_schemas)
    intent = interpret_intent(question, catalog, chat=monitored_chat)
    if diagnostic is not None:
        diagnostic['intent'] = intent
        for table in _strings(diagnostic['ollama'][-1]['parsed_response'].get('table_hints'), 10):
            if table not in catalog.tables:
                diagnostic['rejected_candidates'].append({'stage': 'intent', 'kind': 'table',
                                                           'value': table, 'reason': 'not_in_catalog'})
    candidates = rank_candidates(question, intent, catalog)
    if diagnostic is not None:
        diagnostic['candidates'] = candidates
    if not candidates:
        raise AIError('По каталогу не найдено подходящих таблиц и полей. Попробуй точнее описать данные.')
    stage = 'selection'
    result = select_schema(question, catalog, intent, candidates, chat=monitored_chat, diagnostic=diagnostic)
    return result
