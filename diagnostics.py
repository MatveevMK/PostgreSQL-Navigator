"""One independent UTF-8 JSON report per submitted AI question, including failures."""
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4
import json
import os

from ai_engine import analyze, column_index
from graph_engine import ambiguous_pairs, join_variants, unknown_nodes


BUSINESS_WARNING = ('Назначение полей — предположение модели. Бизнес-смысл JOIN, '
                    'кратность и корректность сумм не проверены.')


def report_json(report):
    return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)


def save_report(report, folder):
    """Unique request IDs avoid shared append files; replace publishes complete JSON."""
    folder = Path(folder)
    temporary = folder / (report['request_id'] + '.tmp')
    destination = folder / (report['request_id'] + '.json')
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with temporary.open('x', encoding='utf-8') as stream:
            stream.write(report_json(report))
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def run_request(question, catalog, folder, model='qwen2.5:7b',
                server='http://127.0.0.1:11434', chat=None, excluded_schemas=()):
    """Return (analysis or None, diagnostic). Never lose a report on analysis failure.

    Route snapshots belong to the initial model selection. UI edits do not modify
    the saved request or cause another Ollama call.
    """
    if excluded_schemas:
        from dataclasses import replace
        from collections import defaultdict
        allowed = {t for t in catalog.tables if t.split('.', 1)[0] not in excluded_schemas}
        links = [replace(e, number=i) for i, e in enumerate(
            e for e in catalog.links if e.child in allowed and e.parent in allowed)]
        adjacency, pairs = defaultdict(list), defaultdict(list)
        for e in links:
            adjacency[e.child].append((e.parent, e.number))
            adjacency[e.parent].append((e.child, e.number))
            pairs[e.pair].append(e.number)
        catalog = replace(catalog, tables=sorted(allowed), known=catalog.known & allowed,
                          columns=catalog.columns[~catalog.columns.table_schema.isin(excluded_schemas)],
                          links=links, adjacency={k: sorted(v) for k,v in adjacency.items()}, links_by_pair=dict(pairs))
    started = perf_counter()
    report = {
        'report_version': '1.0', 'app_version': '5.1', 'request_id': uuid4().hex,
        'started_at': datetime.now(timezone.utc).isoformat(),
        'question': question, 'model': model, 'server': server, 'status': 'running',
        'scope': 'original_ai_request',
        'catalog': {'tables': len(catalog.tables), 'columns': len(catalog.columns),
                    'links': len(catalog.links)},
        'ollama': [], 'intent': {}, 'candidates': [], 'selected_groups': [],
        'rejected_candidates': [], 'join_variants': [], 'errors': [], 'warnings': [],
    }
    result = None
    try:
        result = analyze(question, catalog, model=model, server=server, chat=chat, diagnostic=report, excluded_schemas=excluded_schemas)
        report['selected_groups'] = result['groups']
        report['warnings'] = [BUSINESS_WARNING, *result['uncertainties']]
        index = column_index(catalog)
        connections = []
        for group_index, group in enumerate(result['groups']):
            targets = group['tables']
            item = {'group_index': group_index, 'requested_tables': targets, 'variants': []}
            report['join_variants'].append(item)
            try:
                routes = [(targets, [])] if len(targets) == 1 else join_variants(catalog, targets, limit=4)
            except ValueError as exc:
                item['warning'] = str(exc)
                report['warnings'].append(str(exc))
                connections.append({'routes': [], 'warning': str(exc)})
                continue
            connections.append({'routes': routes})
            first_edges = {link.expression for link in routes[0][1]}
            for nodes, links in routes:
                expressions = {link.expression for link in links}
                variant = {
                    'nodes': list(nodes), 'intermediate_tables': sorted(set(nodes) - set(targets)),
                    'joins': [{'link_id': link.number, 'child': link.child, 'parent': link.parent,
                               'child_column': link.child_column, 'parent_column': link.parent_column,
                               'condition': link.expression, 'source': 'relations_excel'} for link in links],
                    'difference_from_first': {'added_conditions': sorted(expressions - first_edges),
                                              'removed_conditions': sorted(first_edges - expressions)},
                    'alternative_keys': [{'tables': list(pair), 'conditions': values}
                                         for pair, values in ambiguous_pairs(catalog, links).items()],
                    'tables_without_columns': unknown_nodes(catalog, nodes),
                }
                item['variants'].append(variant)
                if variant['alternative_keys']:
                    report['warnings'].append('У пары таблиц есть альтернативные ключи; их нельзя автоматически объединять.')
                for table in variant['tables_without_columns']:
                    report['warnings'].append('Нет описания столбцов таблицы: ' + table)
                for link in links:
                    for table, column in ((link.child, link.child_column), (link.parent, link.parent_column)):
                        if column not in index.get(table, []):
                            report['warnings'].append('Ключ JOIN есть во втором Excel, но не подтверждён первым: '
                                                      + table + '.' + column)
        result['connections'] = connections
        report['status'] = 'success'
    except Exception as exc:
        report['status'] = 'error'
        report['errors'].append({'type': type(exc).__name__, 'message': str(exc)})
        result = None
    finally:
        report['warnings'] = list(dict.fromkeys(report['warnings']))
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        report['duration_ms'] = round((perf_counter() - started) * 1000)
        try:
            save_report(report, folder)
        except OSError as exc:
            report['warnings'].append('Не удалось сохранить диагностику на диск: '
                                      + str(exc) + '. Скачайте отчёт в интерфейсе.')
    return result, report
