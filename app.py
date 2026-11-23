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

st.set_page_config(page_title='PostgreSQL Navigator v5.1', layout='wide', page_icon='🗺️', initial_sidebar_state='collapsed')
st.markdown("""<style>
.stApp {background: radial-gradient(ellipse at 85% 15%, #44316b66, transparent 35%), radial-gradient(ellipse at 10% 80%, #087e8b44, transparent 40%), #171c23; color: #edf3fb; color-scheme: dark;}
[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 2rem; padding-bottom: 1rem; max-width: 1500px;}
h1 {font-size: 2rem !important; letter-spacing: -.045em; color: #f5f8ff !important;}
h2,h3,h4,p,label,li {color: #edf3fb;}
h4 {font-size: 1.05rem !important;}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {color: #b5c4d7 !important;}
[data-testid="stVerticalBlock"] {gap: .6rem;}
[data-testid="stChatMessage"], [data-testid="stExpander"] {background: linear-gradient(120deg,#ffffff0e,#ffffff04); border: 1px solid #ffffff18; border-radius: 18px; backdrop-filter: blur(18px); box-shadow: 0 12px 30px #00000018;}
[data-testid="stSidebar"] {background: #202733;}
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-testid="stChatInput"] {background: #252e3e !important; color: #edf3fb !important; border-color: #52627a !important; border-radius: 12px;}
input, textarea, [data-baseweb="select"] {color: #edf3fb !important; -webkit-text-fill-color: #edf3fb !important;}
input::placeholder, textarea::placeholder {color: #b5c4d7 !important; -webkit-text-fill-color: #b5c4d7 !important;}
[data-baseweb="popover"], [role="listbox"], [role="option"] {background: #252e3e !important; color: #edf3fb !important;}
[data-baseweb="tag"] {background: #354962 !important; color: #f4f8ff !important;}
.stButton button, .stDownloadButton button {background: #2d3a4c; color: #f5f8ff; border: 1px solid #60758e; border-radius: 12px;}
.stButton button:hover, .stDownloadButton button:hover {border-color: #42ddcf; color: #42ddcf;}
button[kind="primary"] {background: linear-gradient(110deg,#137d80,#7044b9); border-color: #50cabb;}
[data-baseweb="tab-list"] {gap: 1.3rem; border-bottom: 1px solid #ffffff18;}
[data-baseweb="tab"] {color: #b5c4d7;}
[data-baseweb="tab"][aria-selected="true"] {color: #54e0d0;}
[data-baseweb="tab-highlight"] {background: #54e0d0;}
code {color: #8ce6dd !important; background: #263344 !important;}
[data-testid="stGraphVizChart"] {overflow: auto; max-height: 320px; background: #1b2330; border-radius: 14px; padding: 12px;}
[data-testid="stGraphVizChart"] svg {max-height: 290px;}
[data-testid="stDialog"] [role="dialog"] {width: 95vw; max-width: 1600px;}
[data-testid="stDialog"] [data-testid="stGraphVizChart"] {max-height: 75vh; overflow: auto;}
[data-testid="stDialog"] [data-testid="stGraphVizChart"] svg {max-height: none;}
[data-testid="stGraphVizChart"]:fullscreen {max-height: none;}
[data-testid="stGraphVizChart"]:fullscreen svg {max-height: none;}
[data-testid="stBottom"] > div {background: #171c23 !important;}
</style>""", unsafe_allow_html=True)
BASE = Path(__file__).resolve().parent


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
    if st.button('⛶ Раскрыть схему', key=f'expand_diagram_{_diagram_number}'):
        enlarged_diagram(nodes, links, targets, fields)


def show_route(nodes, links, targets, fields=()):
    draw_diagram(nodes, links, targets, fields)
    st.markdown('**Связи и точные поля (из каталога):**')
    for edge in links:
        st.markdown(f'- `{edge.child}` ↔ `{edge.parent}`: '
                    f'`{edge.child_column}` = `{edge.parent_column}`')
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
        variants = snapshot['routes'] if snapshot is not None else join_variants(catalog, requested, limit=4)
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
    if result.get('keywords'):
        with st.expander('Как нейросеть поняла вопрос'):
            st.caption('Поисковые слова: ' + ', '.join(result['keywords']))
            st.caption('Кандидатов по названиям и столбцам: ' + str(len(result.get('candidates', []))))
    for idx, group in enumerate(result.get('groups', [])):
        st.markdown(f'#### {group["title"]}')
        details, drawing = st.columns([1, 2.2], gap='large')
        with details:
            if group.get('why'):
                st.write(group['why'])
            selected = st.multiselect('Таблицы для этой схемы — можно исправить выбор модели', tables,
                                      default=[t for t in group['tables'] if t in tables],
                                      format_func=lambda t: f'{t} — {describe(t)[0]}', key=f'edit_{key}_{idx}')
            chosen_fields = [f for f in group.get('fields', []) if f.rpartition('.')[0] in selected]
            if chosen_fields:
                st.markdown('**Предложенные моделью поля (существуют в каталоге):**')
                for field in chosen_fields:
                    st.write('• `' + field + '`')
            else:
                st.caption('Конкретные поля показателей модель не выбрала. Можно посмотреть их во вкладке «Каталог».')
        with drawing:
            if selected:
                snapshots = result.get('connections', [])
                snapshot = snapshots[idx] if selected == group['tables'] and idx < len(snapshots) else None
                show_connections(selected, chosen_fields, snapshot=snapshot)
            else:
                st.info('Выбери хотя бы одну таблицу.')
    for note in result.get('uncertainties', []):
        st.info(note)
    st.caption('Назначение полей — гипотеза нейросети. Таблицы и поля сверены с каталогом полей, '
               'JOIN — со каталогом связей. Достоверность бизнес-показателей не подтверждена.')


st.title('PostgreSQL Navigator')
st.caption('AI-поиск через локальную Ollama · проверенные схемы по каталогу · без SQL, без доступа к PostgreSQL')
st.write(f'**{len(catalog.known)}** таблиц с описанием столбцов · **{len(catalog.links)}** связей · '
         f'**{len(tables)}** таблиц в общем каталоге')
with st.sidebar:
    st.subheader('Настройки поиска')
    include_1c = st.checkbox('Искать также в данных 1С', value=False)
    st.caption('По умолчанию поиск использует основные данные приложения.')
    ai_model = st.text_input('Модель Ollama', value='qwen2.5:7b', help='Должна быть установлена через ollama list')
    ai_server = st.text_input('Адрес локальной Ollama', value='http://127.0.0.1:11434',
                              help='Только localhost: метаданные не отправляются во внешний сервис')
    st.caption('Запросы к Ollama выполняются только после отправки сообщения в AI-чате. '
               'Облачные модели заблокированы.')
    st.caption('Диагностика каждого вопроса сохраняется локально в diagnostics/*.json. '
               'Файлы содержат вопрос и ответы модели; очистка чата их не удаляет.')

tab_chat, tab_multi, tab_pair, tab_catalog = st.tabs([
    '💬 AI-чат · Ollama', '🧩 Несколько таблиц', '🔗 Две таблицы', '📚 Каталог',
])
with tab_chat:
    st.caption('Опишите нужные данные — получите поля и проверенные схемы соединения.')
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
    prompt = st.chat_input('Например: покажи заказы, цену для поставщика и цену для покупателя')
    if prompt:
        st.session_state.history_v5.append({'role':'user','text':prompt})
        with st.spinner('Ollama анализирует вопрос и каталог; затем Python проверяет таблицы и JOIN...'):
            answer, report = run_request(prompt, catalog, BASE / 'diagnostics',
                                         model=ai_model, server=ai_server,
                                         excluded_schemas=() if include_1c else ('hbpro_1c',))
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

with tab_multi:
    st.write('Ручной выбор 2–10 таблиц. Никакие нестандартные JOIN не добавляются.')
    defaults = [t for t in ('orders.orders', 'dictionary.hotel', 'dictionary.country') if t in tables]
    chosen = st.multiselect('Выбери таблицы', tables, default=defaults,
                            format_func=lambda t: f'{t} — {describe(t)[0]}', key='multi')
    if st.button('Построить варианты JOIN', type='primary'):
        show_connections(chosen)

with tab_pair:
    c1, c2 = st.columns(2)
    with c1:
        a = st.selectbox('Первая таблица', tables, index=tables.index('orders.orders') if 'orders.orders' in tables else 0)
    with c2:
        b = st.selectbox('Вторая таблица', tables, index=tables.index('dictionary.hotel') if 'dictionary.hotel' in tables else min(1, len(tables) - 1))
    if st.button('Найти соединения', key='pair'):
        if a == b:
            st.warning('Выбери разные таблицы.')
        elif shortest_path(catalog, a, b) is None:
            st.warning('В каталоге не найден подтверждённый путь.')
        else:
            show_connections([a, b])

with tab_catalog:
    target = st.selectbox('Таблица', tables, format_func=lambda t: f'{t} — {describe(t)[0]}')
    hint, source = describe(target)
    st.caption(f'Подсказка: {hint} ({source}). Описание может быть предположением.')
    cols = column_view(catalog, target)
    if cols.empty:
        st.warning('Таблица есть в связях, но отсутствует в файле описаний столбцов.')
    else:
        search = st.text_input('Поиск столбца', key='column_search')
        view = cols.copy()
        view['Комментарий'] = 'Описание пока не добавлено'
        comment_columns = [c for c in ('comment', 'column_comment', 'description') if c in view.columns]
        if comment_columns:
            view['Комментарий'] = view[comment_columns[0]]
        def related(column):
            return '; '.join(e.expression for e in catalog.links
                             if (e.child == target and e.child_column == column)
                             or (e.parent == target and e.parent_column == column)) or 'Связи не указаны'
        view['Связи поля'] = view['column_name'].map(related)
        if search:
            view = view[view.column_name.str.contains(search, case=False, regex=False)]
        st.dataframe(view[['column_name','data_type','is_nullable','Комментарий','Связи поля']].rename(
            columns={'column_name':'Столбец','data_type':'Тип','is_nullable':'Может быть пустым'}),
            hide_index=True, use_container_width=True)
        st.caption('В колонке «Связи поля» показано, с какими полями других таблиц оно соединяется.')
