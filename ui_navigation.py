import streamlit as st

PAGES = [('Главная', ':material/home:'), ('Найти данные', ':material/search:'),
         ('Связи таблиц', ':material/hub:'), ('Каталог', ':material/table_view:'),
         ('Настройки', ':material/settings:')]

def go(page, question=None, table=None, targets=None):
    st.session_state.page = page
    if question:
        st.session_state.pending_question = question
    if table:
        st.session_state.catalog_target = table
        st.session_state.reset_catalog_query = True
    if targets is not None:
        st.session_state.route_targets = targets
        st.session_state.route_selection = targets


def navigation():
    if 'navigate_to' in st.session_state:
        go(st.session_state.pop('navigate_to'))
    st.session_state.setdefault('page', 'Главная')
    with st.sidebar:
        st.html('''<div class="navigator-brand">
            <img class="navigator-mark" src="./app/static/navigator-mark.svg" alt="">
            <div><strong>Navigator</strong><small>PostgreSQL</small></div>
        </div>''')
        with st.container(key='navigator_menu'):
            for label, icon in PAGES:
                st.button(label, icon=icon, key='nav_' + label, use_container_width=True,
                          type='primary' if st.session_state.page == label else 'secondary',
                          on_click=go, args=(label,))
        with st.container(key='navigator_status'):
            st.caption('Каталог загружен · локальная работа')
            st.caption(st.session_state.get('ollama_status', 'Ollama: соединение не проверялось'))
            st.caption('Модель: ' + st.session_state.get('saved_model', 'qwen2.5:7b'))
    return st.session_state.page
