"""PostgreSQL Navigator v5 — local Ollama, schema metadata, verified Excel graph.

No DB connection. No SQL generation. No manually injected relations.
"""
import json
from pathlib import Path

import streamlit as st

from diagnostics import report_json, run_request
from diagram_view import diagram
from descriptions import describe
from graph_engine import (
    ambiguous_pairs, column_view, join_variants, load_catalog, shortest_path, unknown_nodes,
)

st.set_page_config(page_title='PostgreSQL Navigator v5.1', layout='wide', page_icon='', initial_sidebar_state='auto')
BASE = Path(__file__).resolve().parent
st.html(BASE / 'navigator.css')


@st.cache_resource(show_spinner='Читаю каталог Excel...')
def load():
    return load_catalog(BASE / 'data')


catalog = load()
tables = catalog.tables


def make_dot(nodes, edges, targets, highlighted=()):
    requested = set(targets)
    marked = {}
    for col in highlighted:
        tab, _, name = col.rpartition('.')
        marked.setdefault(tab, []).append(name)
    out = [
        'graph Relations {',
        'graph [rankdir=LR, bgcolor="transparent", overlap=false, splines=polyline, nodesep=0.6, ranksep=1.0];',
        'node [shape=box, style="rounded,filled", fontname="Arial", fontsize=11, fontcolor="#eef5ff", color="#6f85a3", fillcolor="#29374a"];',
        'edge [fontname="Arial", fontsize=9, fontcolor="#bfcee2", color="#7f9ab8"];',
    ]
    for name in nodes:
        hint, _ = describe(name)
        label = name + '\\n' + hint[:45]
        fields = marked.get(name, [])
        if fields:
            label += '\\nПоля: ' + ', '.join(fields[:4])
        attrs = f'label={json.dumps(label, ensure_ascii=False)}'
        if name in requested:
            attrs += ', fillcolor="#174b50", penwidth=2, color="#52ddcd"'
        out.append(f'{json.dumps(name, ensure_ascii=False)} [{attrs}];')
    for link in edges:
        label = f'{link.child_column} = {link.parent_column}\nКратность: ? : ?'
        out.append(f'{json.dumps(link.child, ensure_ascii=False)} -- {json.dumps(link.parent, ensure_ascii=False)} '
                   f'[label={json.dumps(label, ensure_ascii=False)}];')
    out.append('}')
    return '\n'.join(out)


_diagram_number = 0


@st.dialog('Схема соединений', width='large')
def enlarged_diagram(nodes, links, targets, fields):
    diagram(nodes, links, targets, fields, height=650)


def draw_diagram(nodes, links, targets, fields=()):
    global _diagram_number
    _diagram_number += 1
    diagram(nodes, links, targets, fields)
    if st.button('Раскрыть схему', key=f'expand_diagram_{_diagram_number}'):
        enlarged_diagram(nodes, links, targets, fields)


def show_route(nodes, links, targets, fields=()):
    draw_diagram(nodes, links, targets, fields)
    with st.expander('Точные поля соединений'):
        for edge in links:
            st.code(edge.expression, language=None)
    with st.expander('Кратность и выбор типа JOIN'):
        st.info('Кратность ? : ? — неизвестна. В каталоге нет PRIMARY KEY / UNIQUE и состава ограничений. '
                'Названия child/parent сами по себе не доказывают 1:1 или N:1.')
        st.markdown('**Для каждой линии направление читается child → parent:**')
        for edge in links:
            st.write(f'`{edge.child}` → `{edge.parent}`: N:1 возможно, если ключ parent уникален; '
                     '1:1 возможно, если оба ключа уникальны. Это условия, а не подтверждённые свойства.')
        st.markdown('**Как выбрать соединение:**\n\n'
                    '- **LEFT JOIN** — если нужно сохранить все строки основной таблицы, даже без совпадения. Основная таблица должна стоять слева.\n'
                    '- **INNER JOIN** — если нужны только строки с совпадением в обеих таблицах.\n'
                    '- **RIGHT JOIN** — сохранить все строки справа; обычно удобнее поменять таблицы местами и использовать LEFT.\n'
                    '- **FULL JOIN** — для сверки двух наборов, включая несовпадения с обеих сторон.\n'
                    '- **UNION / UNION ALL** — сложить строки совместимых наборов, например онлайн и офлайн; это не JOIN. UNION удаляет дубли целых строк, UNION ALL сохраняет их.')
        st.caption('Рекомендация условная: для списка заявок с дополнительными сведениями обычно подходит LEFT от таблицы заявок. '
                   'В цепочке соединений выбор делается отдельно для каждого шага. LEFT не защищает от размножения строк; '
                   'фильтры по присоединённой таблице могут исключить строки без совпадений.')
    alternatives = ambiguous_pairs(catalog, links)
    if alternatives:
        with st.expander('У этих пар таблиц есть разные ключи — нельзя автоматически использовать все сразу'):
            for pair, expressions in alternatives.items():
                st.markdown('**' + ' ↔ '.join(f'`{x}`' for x in pair) + '**')
                for expression in expressions:
                    st.write('• `' + expression + '`')
    missing_columns = unknown_nodes(catalog, nodes)
    if missing_columns:
        st.warning('Есть таблицы без полного описания столбцов в каталоге полей: '
                   + ', '.join(f'`{x}`' for x in missing_columns))


def show_connections(requested, fields=(), snapshot=None):
    if len(requested) == 1:
        st.info(f'Для `{requested[0]}` не требуется JOIN: выбрана одна таблица.')
        draw_diagram(requested, [], requested, fields)
        return
    if not 2 <= len(requested) <= 10:
        st.warning('Для схемы выбери от 2 до 10 таблиц.')
        return
    try:
        if snapshot is not None and snapshot.get('warning'):
            raise ValueError(snapshot['warning'])
        if snapshot is not None:
            variants = snapshot['routes']
        else:
            route_cache = st.session_state.setdefault('route_cache', {})
            signature = (tuple(requested), len(catalog.links), len(catalog.columns))
            if signature not in route_cache:
                route_cache[signature] = join_variants(catalog, requested, limit=4)
            variants = route_cache[signature]
    except ValueError as exc:
        st.warning(str(exc))
        st.caption('Это означает, что в каталоге связей нет связного пути. '
                   'Navigator не добавляет связи из догадок нейросети или других SQL.')
        return
    st.success(f'Найдено {len(variants)} технических варианта(ов) связей из каталога.')
    panels = st.tabs([f'Вариант {i} · {len(links)} JOIN' for i, (_, links) in enumerate(variants, 1)]) \
        if len(variants) > 1 else [st.container()]
    first_conditions = {link.expression for link in variants[0][1]}
    for number, (panel, (nodes, links)) in enumerate(zip(panels, variants)):
        with panel:
            st.caption(f'Промежуточные таблицы: {", ".join(sorted(set(nodes) - set(requested))) or "не нужны"}')
            if number:
                conditions = {link.expression for link in links}
                st.caption('Отличия от варианта 1: добавлены связи: '
                           + ('; '.join(sorted(conditions - first_conditions)) or 'нет')
                           + '. Исключены связи: '
                           + ('; '.join(sorted(first_conditions - conditions)) or 'нет'))
            show_route(nodes, links, requested, fields)
    st.warning('Все показанные JOIN технически существуют в каталоге, но их бизнес-смысл, '
               'кратность и корректность сумм не проверены. Альтернативные пути могут означать разные вещи.')


def show_analysis(result, key):
    for idx, group in enumerate(result.get('groups', [])):
        st.subheader(group['title'])
        if group.get('why'):
            st.caption('Предположение AI: ' + group['why'])
        with st.expander('Таблицы и подходящие поля', expanded=True):
            selected = st.multiselect('Таблицы для схемы', tables,
                default=group['tables'], key=f'edit_{key}_{idx}', max_selections=10)
            for table in selected:
                with st.container(key=f'found_{key}_{idx}_{table}'):
                    st.markdown(f'**`{table}`**')
                    st.caption('Подсказка по названию: ' + describe(table)[0])
                    relevant = [f for f in group.get('fields', []) if f.rpartition('.')[0] == table]
                    if relevant:
                        with st.container(key=f'field_codes_{key}_{idx}_{table}'):
                            st.code('\n'.join(relevant), language=None)
                    st.button('Открыть в каталоге', key=f'catalog_{key}_{idx}_{table}',
                              on_click=go, kwargs={'page':'Каталог','table':table})
            st.button('Исследовать связи', key=f'route_{key}_{idx}', on_click=go,
                      kwargs={'page':'Связи таблиц','targets':selected}, disabled=len(selected)<2)
        snapshots = result.get('connections', [])
        snapshot = snapshots[idx] if selected == group['tables'] and idx < len(snapshots) else None
        if selected:
            show_connections(selected, group.get('fields', []), snapshot=snapshot)
    with st.expander('Ограничения и дополнительные сведения'):
        for note in result.get('uncertainties', []):
            st.info('Предположение AI: ' + note)
        st.caption('Имена полей и связи проверены по каталогу. Бизнес-смысл и кратность требуют проверки.')


from ui_navigation import navigation, go
page = navigation()
ai_model = st.session_state.get('saved_model', 'qwen2.5:7b')
ai_server = st.session_state.get('saved_server', 'http://127.0.0.1:11434')
include_1c = st.session_state.get('saved_include_1c', False)

if page == 'Главная':
    st.html('''<header class="navigator-hero">
        <div class="hero-copy">
            <h1>Какие данные<br>вы <span>ищете?</span></h1>
            <p>Найдите таблицы, изучите поля и соберите схему соединений.</p>
        </div>
        <img class="hero-graph" src="./app/static/hero-graph.svg" alt="">
    </header>''')
    with st.form('home_search'):
        question = st.text_input('Опишите задачу', placeholder='Например: заказы, клиенты и позиции')
        submit = st.form_submit_button('Найти данные', type='primary')
    if submit and question.strip():
        st.session_state.pending_question = question
        st.session_state.navigate_to = 'Найти данные'
        st.rerun()
    st.markdown('#### Попробуйте пример')
    examples = st.columns(3)
    for col, example in zip(examples, ('Заказы, клиенты и позиции', 'Клиенты и их заказы', 'Количество в позициях заказа')):
        if col.button(example, key='example_' + example, use_container_width=True):
            st.session_state.pending_question = example
            st.session_state.navigate_to = 'Найти данные'
            st.rerun()
    actions = st.columns(3)
    for col, title, destination in zip(actions, ('Найти таблицу', 'Проверить связи', 'Открыть каталог'), ('Каталог','Связи таблиц','Каталог')):
        if col.button(title, use_container_width=True):
            st.session_state.navigate_to = destination
            st.rerun()
    a,b,c = st.columns(3)
    a.metric('Таблиц', len(tables)); b.metric('С описанием полей', len(catalog.known)); c.metric('Проверенных связей', len(catalog.links))
elif page == 'Найти данные':
    st.title('Найти данные')

    st.caption('Опишите нужные данные — получите поля и проверенные схемы соединения.')
    if not st.session_state.get('history_v5'):
        st.info('Начните с задачи: например, «Заказы, клиенты и позиции». Значение бизнес-терминов модель может определить лишь предположительно.')
    if 'history_v5' not in st.session_state:
        st.session_state.history_v5 = []
    history = st.session_state.history_v5
    questions = [i for i, item in enumerate(history) if item['role'] == 'user']
    if questions:
        selected_request = st.selectbox('История запросов', questions, index=len(questions)-1,
                                        format_func=lambda i: history[i]['text'][:100])
    else:
        selected_request = 0
    with st.container(border=False):
        for i, entry in list(enumerate(history))[selected_request:selected_request + 2]:
            with st.chat_message(entry['role']):
                st.markdown(entry['text'])
                if entry.get('diagnostic'):
                    st.caption(f"Выполнено за {entry['diagnostic'].get('duration_ms', 0) / 1000:.1f} с")
                if entry.get('result'):
                    show_analysis(entry['result'], key=i)
                if entry.get('diagnostic'):
                    report = entry['diagnostic']
                    with st.expander('Диагностика исходного запроса'):
                        st.caption('Отчёт фиксирует первоначальный выбор модели. Ручные изменения таблиц в него не входят.')
                        for warning in report['warnings']:
                            st.warning(warning)
                        st.download_button('Скачать диагностический отчёт (JSON)',
                                           data=report_json(report),
                                           file_name=f"navigator_{report['request_id']}.json",
                                           mime='application/json', key=f"diagnostic_{report['request_id']}")
    prompt = st.chat_input('Какие данные вам нужны?') or st.session_state.pop('pending_question', None)
    if prompt:
        st.session_state.history_v5.append({'role':'user','text':prompt})
        with st.spinner('Ollama анализирует вопрос и каталог; затем Python проверяет таблицы и JOIN...'):
            answer, report = run_request(prompt, catalog, BASE / 'diagnostics',
                                         model=ai_model, server=ai_server,
                                         excluded_schemas=() if include_1c else ('integration_1c',))
            if answer is not None:
                new_item = {'role':'assistant','text':'Нашёл таблицы и поля-кандидаты. '
                            'Ниже схемы соединения и ограничения:', 'result':answer}
            else:
                new_item = {'role':'assistant','text':'⚠️ ' + report['errors'][-1]['message']}
            new_item['diagnostic'] = report
        st.session_state.history_v5.append(new_item)
        st.rerun()
    if st.session_state.history_v5 and st.button('Очистить историю', key='clear_v5'):
        st.session_state.history_v5 = []
        st.rerun()

elif page == 'Связи таблиц':
    st.title('Связи таблиц')
    st.caption('Выберите от 2 до 10 таблиц. Покажем доступные пути и точные поля соединения.')
    chosen = st.multiselect('Таблицы', tables, default=st.session_state.get('route_targets', []), key='route_selection', max_selections=10)
    st.caption(f'Выбрано {len(chosen)} из 10. ' + ('Добавьте ещё таблицу для поиска связей.' if len(chosen) < 2 else 'Можно искать связи.'))
    if st.button('Найти связи', type='primary', disabled=len(chosen) < 2):
        st.session_state.route_targets = chosen
    requested = st.session_state.get('route_targets', [])
    if requested:
        st.caption('Результат для: ' + ', '.join(requested))
        show_connections(requested)
    else:
        st.info('Начните с двух таблиц, связь между которыми хотите проверить.')
elif page == 'Каталог':
    st.title('Каталог')

    left, right = st.columns([1, 2.5], gap='large')
    with left:
        if st.session_state.pop('reset_catalog_query', False):
            st.session_state.catalog_query = ''
            st.session_state.catalog_schema = 'Все схемы'
        query = st.text_input('Найти таблицу', key='catalog_query')
        schema = st.selectbox('Схема', ['Все схемы'] + sorted({t.split('.')[0] for t in tables}), key='catalog_schema')
        available = [t for t in tables if query.lower() in t.lower() and (schema == 'Все схемы' or t.split('.')[0] == schema)]
        if not available:
            st.info('Таблицы не найдены. Измените поиск.')
            st.stop()
        preferred = st.session_state.get('catalog_target')
        target = st.selectbox('Таблицы', available, index=available.index(preferred) if preferred in available else 0)
        st.session_state.catalog_target = target
    with right:
        st.subheader(f'`{target}`')
        st.code(target, language=None)

        hint, source = describe(target)
        st.caption(f'Подсказка: {hint} ({source}). Описание может быть предположением.')
        cols = column_view(catalog, target)
        if cols.empty:
            st.warning('Таблица есть в связях, но отсутствует в файле описаний столбцов.')
        else:
            search = st.text_input('Поиск столбца', key='column_search')
            view = cols.copy()
            view['Комментарий'] = ''
            comment_columns = [c for c in ('comment', 'column_comment', 'description') if c in view.columns]
            if comment_columns:
                view['Комментарий'] = view[comment_columns[0]]
            def related(column):
                return sum(1 for e in catalog.links
                                 if (e.child == target and e.child_column == column)
                                 or (e.parent == target and e.parent_column == column))
            view['Связи поля'] = view['column_name'].map(related)
            if search:
                view = view[view.column_name.str.contains(search, case=False, regex=False)]
            fields_view = view[['column_name', 'data_type', 'is_nullable', 'Комментарий', 'Связи поля']].rename(
                columns={'column_name': 'Столбец', 'data_type': 'Тип', 'is_nullable': 'Может быть пустым'})
            nullable_styles = {'YES': 'color: #d8f87a; background-color: #2a3425',
                               'NO': 'color: #a0dfd4; background-color: #1e302d'}
            st.dataframe(fields_view.style.map(
                lambda value: nullable_styles.get(str(value).upper(), ''), subset=['Может быть пустым']),
                hide_index=True, use_container_width=True)
            st.caption('Число в колонке «Связи поля» — количество подтверждённых связей. Условия приведены ниже.')
        st.caption('Пустое описание означает, что комментарий к полю пока отсутствует. Название поля можно скопировать из блока ниже.')
        with st.expander('Названия полей для копирования'):
            for name in cols.column_name:
                st.code(target + '.' + name, language=None)
        with st.expander('Связанные таблицы', expanded=True):
            for other, link_id in catalog.adjacency.get(target, []):
                st.code(catalog.links[link_id].expression, language=None)
                if st.button(other, key=f'catalog_link_{target}_{link_id}_{other}'):
                    st.session_state.catalog_target = other
                    st.session_state.reset_catalog_query = True
                    st.rerun()
elif page == 'Настройки':
    st.title('Настройки')
    with st.container(key='settings_model'):
        st.subheader('Локальная AI-модель')
        model_value = st.text_input('Локальная модель', value=ai_model, key='model_setting')
        st.session_state.saved_model = model_value
        server_value = st.text_input('Адрес Ollama', value=ai_server, key='server_setting')
        st.session_state.saved_server = server_value
    with st.container(key='settings_sources'):
        st.subheader('Источники данных')
        st.session_state.saved_include_1c = st.toggle('Включать данные 1С в AI-поиск', value=include_1c, key='include_1c_setting')
        st.caption('Включает таблицы 1С и пути через них. Основные данные доступны при выключенном переключателе.')
    with st.container(key='settings_connection'):
        st.subheader('Состояние соединения')
        if st.button('Проверить соединение'):
            from urllib.request import urlopen
            from ai_engine import check_local_server
            try:
                with urlopen(check_local_server(server_value) + '/api/tags', timeout=3) as response:
                    models = json.load(response)
                installed = [m['name'] for m in models.get('models', [])]
                if model_value in installed:
                    st.session_state.ollama_status = 'Ollama доступна · модель установлена'
                    st.success(st.session_state.ollama_status)
                else:
                    st.warning('Ollama доступна, но выбранная модель не найдена.')
            except Exception as exc:
                st.session_state.ollama_status = 'Ollama недоступна'
                st.error('Ollama недоступна. Запустите Ollama и проверьте локальный адрес. Затем повторите проверку.')
