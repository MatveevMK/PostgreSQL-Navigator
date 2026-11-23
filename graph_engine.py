"""Deterministic navigation over user-provided PostgreSQL schema metadata.

No DB connection. No inferred/imaginary JOIN keys. A route is a heuristic
connection between tables, not a guarantee that a report is semantically valid.
"""
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd

COL_HEADERS = {'table_schema', 'table_name', 'column_name', 'data_type', 'is_nullable'}
LINK_HEADERS = {'child_schema', 'child_table', 'child_column', 'parent_schema', 'parent_table', 'parent_column'}


@dataclass(frozen=True)
class Link:
    number: int
    child: str
    parent: str
    child_column: str
    parent_column: str

    @property
    def expression(self):
        return f'{self.child}.{self.child_column} = {self.parent}.{self.parent_column}'

    @property
    def pair(self):
        return tuple(sorted((self.child, self.parent)))


@dataclass
class Catalog:
    columns: pd.DataFrame
    links: List[Link]
    known: set
    tables: List[str]
    adjacency: Dict[str, list]
    links_by_pair: Dict[Tuple[str, str], list]


def load_catalog(folder: Path) -> Catalog:
    f1 = sorted(folder.glob('*первый*.xlsx'))
    f2 = sorted(folder.glob('*второй*.xlsx'))
    if not f1 or not f2:
        raise FileNotFoundError('В папке data отсутствует один из двух Excel: «первый» или «второй».')
    columns = pd.read_excel(f1[0]).fillna('')
    raw = pd.read_excel(f2[0]).fillna('')
    if not COL_HEADERS.issubset(columns.columns):
        raise ValueError(f'Неверные столбцы первого Excel: нужны {sorted(COL_HEADERS)}')
    if not LINK_HEADERS.issubset(raw.columns):
        raise ValueError(f'Неверные столбцы второго Excel: нужны {sorted(LINK_HEADERS)}')
    for field in ('table_schema', 'table_name', 'column_name'):
        columns[field] = columns[field].astype(str).str.strip()
    known = set(columns.table_schema + '.' + columns.table_name)
    all_tables = set(known)
    links = []
    by_pair = defaultdict(list)
    adj = defaultdict(list)
    for _, r in raw.iterrows():
        values = [str(r[k]).strip() for k in ('child_schema', 'child_table', 'child_column', 'parent_schema', 'parent_table', 'parent_column')]
        if not all(values):
            continue
        a, b, ac, c, d, bc = values
        link = Link(len(links), f'{a}.{b}', f'{c}.{d}', ac, bc)
        links.append(link)
        adj[link.child].append((link.parent, link.number))
        adj[link.parent].append((link.child, link.number))
        by_pair[link.pair].append(link.number)
        all_tables.update((link.child, link.parent))
    for node in adj:
        adj[node].sort(key=lambda p: (p[0], p[1]))
    return Catalog(columns, links, known, sorted(all_tables), dict(adj), dict(by_pair))


def shortest_path(catalog: Catalog, source: str, destination: str):
    """Return node list + corresponding link indices, or None."""
    if source == destination:
        return ([source], []) if source in catalog.tables else None
    queue = deque([source])
    previous = {source: None}
    while queue:
        node = queue.popleft()
        for nxt, link_id in catalog.adjacency.get(node, []):
            if nxt in previous:
                continue
            previous[nxt] = (node, link_id)
            if nxt == destination:
                nodes, edges = [destination], []
                x = destination
                while previous[x] is not None:
                    prev, link_index = previous[x]
                    edges.append(link_index)
                    nodes.append(prev)
                    x = prev
                return list(reversed(nodes)), list(reversed(edges))
            queue.append(nxt)
    return None


def _tree_from_root(catalog: Catalog, requested: set, root: str, excluded_links=frozenset()):
    """Incrementally connect closest not-yet-connected requested vertex.

    Computes a small connected subgraph (Steiner-tree approximation). Does not
    claim global mathematical optimality or business-semantic correctness.
    """
    tree_nodes = {root}
    tree_links = set()
    while not requested.issubset(tree_nodes):
        q = deque(sorted(tree_nodes))
        seen = set(tree_nodes)
        previous = {}
        destination = None
        while q and destination is None:
            node = q.popleft()
            for nxt, link_id in catalog.adjacency.get(node, []):
                if link_id in excluded_links or nxt in seen:
                    continue
                previous[nxt] = (node, link_id)
                seen.add(nxt)
                if nxt in requested:
                    destination = nxt
                    break
                q.append(nxt)
        if destination is None:
            return None
        v = destination
        while v not in tree_nodes:
            p, link_id = previous[v]
            tree_links.add(link_id)
            tree_nodes.add(v)
            v = p
    return tree_nodes, tree_links


def connect_tables(catalog: Catalog, requested: Sequence[str], excluded_links=frozenset()):
    """Connect 2-10 distinct targets; result is (nodes, Link objects).

    Raises ValueError for invalid input/unconnected components. Every produced
    link is present in the user's Excel.
    """
    targets = list(dict.fromkeys(requested))
    excluded_links = frozenset(excluded_links)
    if not 2 <= len(targets) <= 10:
        raise ValueError('Выбери от 2 до 10 разных таблиц.')
    absent = [n for n in targets if n not in catalog.tables]
    if absent:
        raise ValueError('Таблицы отсутствуют в Excel: ' + ', '.join(absent))
    attempts = []
    for root in targets:
        result = _tree_from_root(catalog, set(targets), root, excluded_links)
        if result is None:
            continue
        nodes, indices = result
        ambiguous = sum(len(catalog.links_by_pair[catalog.links[i].pair]) > 1 for i in indices)
        score = (len(indices), ambiguous, tuple(sorted(nodes)), tuple(sorted(indices)))
        attempts.append((score, nodes, indices))
    if not attempts:
        reachable = {targets[0]}
        q = deque([targets[0]])
        while q:
            for nxt, _ in catalog.adjacency.get(q.popleft(), []):
                if nxt not in reachable:
                    reachable.add(nxt)
                    q.append(nxt)
        missing = [x for x in targets if x not in reachable]
        raise ValueError('В Excel нет подтверждённого пути до: ' + ', '.join(missing))
    _, nodes, indices = min(attempts, key=lambda x: x[0])
    return sorted(nodes), [catalog.links[i] for i in sorted(indices)]


def unknown_nodes(catalog: Catalog, nodes: Sequence[str]):
    return [n for n in nodes if n not in catalog.known]


def ambiguous_pairs(catalog: Catalog, links: Sequence[Link]):
    """Alternative keys between a chosen pair must NOT be combined by AND."""
    found = {}
    for link in links:
        pool = catalog.links_by_pair.get(link.pair, [])
        if len(pool) > 1:
            found[link.pair] = [catalog.links[i].expression for i in pool]
    return found


def column_view(catalog: Catalog, table: str):
    schema, name = table.split('.', 1)
    return catalog.columns[(catalog.columns.table_schema == schema) & (catalog.columns.table_name == name)]



def join_variants(catalog: Catalog, requested: Sequence[str], limit: int = 4):
    """Generic bounded alternative JOIN-tree enumeration, with no business hardcodes.

    All returned edges are literally present in the uploaded second Excel.
    Trees are connectivity suggestions only; they DO NOT verify business meaning.
    """
    from itertools import count
    import heapq

    base_nodes, base_edges = connect_tables(catalog, requested)
    base_key = frozenset(e.number for e in base_edges)
    seen = set()
    unique = {}
    serial = count()
    pending = [(0, next(serial), frozenset())]
    max_tries = 140
    tries = 0
    while pending and tries < max_tries:
        _, _, excluded = heapq.heappop(pending)
        if excluded in seen:
            continue
        seen.add(excluded)
        tries += 1
        try:
            nodes, links = connect_tables(catalog, requested, excluded_links=excluded)
        except ValueError:
            continue
        key = frozenset(edge.number for edge in links)
        if len(links) <= len(base_edges) + 4:
            unique[key] = (nodes, links)
        if len(excluded) < 3:
            for edge in links:
                child = excluded | {edge.number}
                if child not in seen:
                    heapq.heappush(pending, (len(child), next(serial), child))

    if not unique:
        raise ValueError('В Excel нет подтверждённых связей между выбранными таблицами.')
    candidates = list(unique.values())
    first = unique.get(base_key, (base_nodes, base_edges))
    chosen = [first]
    chosen_keys = {frozenset(e.number for e in first[1])}
    # Pick differing routes instead of near-identical duplicates, but prefer shorter ones.
    while len(chosen) < limit:
        best = None
        best_score = None
        for route in candidates:
            ids = frozenset(e.number for e in route[1])
            if ids in chosen_keys:
                continue
            difference = min(len(ids ^ frozenset(e.number for e in old[1])) for old in chosen)
            score = (difference, -len(route[1]), tuple(sorted(ids)))
            if best_score is None or score > best_score:
                best, best_score = route, score
        if best is None:
            break
        chosen.append(best)
        chosen_keys.add(frozenset(e.number for e in best[1]))
    return chosen
