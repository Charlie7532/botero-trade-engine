#!/usr/bin/env python3
"""
Graphify Query Tool for Botero Trade
Consulta el grafo de dependencias del proyecto.

Uso:
    python3 query_graphify.py <comando> [argumentos]

Comandos:
    stats                           Estadísticas generales del grafo
    hubs [N]                        Top N nodos más conectados (default: 20)
    module <nombre>                 Información de un módulo específico
    depends <archivo>               Qué archivos dependen de este
    dependson <archivo>             De qué depende este archivo
    community <id>                  Miembros de una comunidad
    path <origen> <destino>         Camino entre dos nodos
    search <término>                Buscar nodos que contengan el término
    interdeps                       Dependencias entre módulos
"""

import json
import sys
from collections import defaultdict, Counter
from pathlib import Path

GRAPH_PATH = Path(__file__).parent / "graphify-out" / "graph.json"


def load_graph():
    """Carga el grafo desde graph.json"""
    with open(GRAPH_PATH, 'r') as f:
        return json.load(f)


def build_indices(graph):
    """Construye índices para búsqueda rápida"""
    nodes = graph['nodes']
    links = graph['links']
    
    node_by_id = {n['id']: n for n in nodes}
    
    # Grado de cada nodo
    degree = defaultdict(int)
    for link in links:
        degree[link['source']] += 1
        degree[link['target']] += 1
    
    # Adyacencia (qué depende de qué)
    depends_on = defaultdict(set)  # nodo -> set de nodos de los que depende
    depended_by = defaultdict(set)  # nodo -> set de nodos que dependen de él
    
    for link in links:
        src = link['source']
        tgt = link['target']
        depends_on[src].add(tgt)
        depended_by[tgt].add(src)
    
    # Comunidades
    communities = defaultdict(list)
    for n in nodes:
        communities[n['community']].append(n['id'])
    
    return {
        'nodes': nodes,
        'links': links,
        'node_by_id': node_by_id,
        'degree': degree,
        'depends_on': depends_on,
        'depended_by': depended_by,
        'communities': communities
    }


def cmd_stats(indices):
    """Muestra estadísticas generales"""
    nodes = indices['nodes']
    links = indices['links']
    communities = indices['communities']
    
    file_types = Counter(n.get('file_type', 'unknown') for n in nodes)
    relations = Counter(link.get('relation', 'unknown') for link in links)
    
    print(f"=== ESTADÍSTICAS DEL GRAFO ===")
    print(f"Nodos: {len(nodes)}")
    print(f"Links: {len(links)}")
    print(f"Comunidades: {len(communities)}")
    print(f"\nTipos de archivo:")
    for ft, count in file_types.most_common():
        print(f"  {ft}: {count}")
    print(f"\nTipos de relación:")
    for rel, count in relations.most_common():
        print(f"  {rel}: {count}")


def cmd_hubs(indices, n=20):
    """Muestra los N nodos más conectados"""
    degree = indices['degree']
    node_by_id = indices['node_by_id']
    
    top = sorted(degree.items(), key=lambda x: x[1], reverse=True)[:n]
    
    print(f"=== TOP {n} HUBS (más conectados) ===")
    for rank, (node_id, deg) in enumerate(top, 1):
        node = node_by_id.get(node_id, {})
        label = node.get('label', 'N/A')
        source = node.get('source_file', 'N/A')
        comm = node.get('community', '?')
        print(f"{rank:2d}. [{deg:3d}] comm={comm} | {label[:55]:55s} | {source}")


def cmd_module(indices, module_name):
    """Información de un módulo específico"""
    nodes = indices['nodes']
    degree = indices['degree']
    links = indices['links']
    node_by_id = indices['node_by_id']
    
    # Filtrar nodos del módulo
    module_nodes = [n for n in nodes if f'backend/modules/{module_name}/' in n.get('source_file', '')]
    
    if not module_nodes:
        print(f"Módulo '{module_name}' no encontrado")
        return
    
    code_nodes = [n for n in module_nodes if n.get('file_type') == 'code']
    rat_nodes = [n for n in module_nodes if n.get('file_type') == 'rationale']
    
    # Dependencias externas
    external_deps = Counter()
    for link in links:
        src = node_by_id.get(link['source'], {})
        tgt = node_by_id.get(link['target'], {})
        src_file = src.get('source_file', '')
        tgt_file = tgt.get('source_file', '')
        
        if f'backend/modules/{module_name}/' in src_file and f'backend/modules/{module_name}/' not in tgt_file:
            if 'backend/modules/' in tgt_file:
                dep_mod = tgt_file.split('backend/modules/')[1].split('/')[0]
                external_deps[dep_mod] += 1
    
    print(f"=== MÓDULO: {module_name.upper()} ===")
    print(f"Nodos: {len(code_nodes)} code + {len(rat_nodes)} rationale = {len(module_nodes)} total")
    print(f"\nTop 5 dependencias externas:")
    for dep, count in external_deps.most_common(5):
        print(f"  → {dep}: {count} links")
    
    print(f"\nTop 10 nodos internos por conexiones:")
    internal_nodes = [(n['id'], degree.get(n['id'], 0)) for n in module_nodes]
    internal_nodes.sort(key=lambda x: x[1], reverse=True)
    for node_id, deg in internal_nodes[:10]:
        node = node_by_id.get(node_id, {})
        label = node.get('label', 'N/A')
        source = node.get('source_file', 'N/A')
        print(f"  [{deg:3d}] {label[:50]:50s} | {source}")


def cmd_depends(indices, file_path):
    """Qué archivos dependen de este"""
    depended_by = indices['depended_by']
    node_by_id = indices['node_by_id']
    nodes = indices['nodes']
    
    # Buscar nodos que coincidan con el archivo
    matching_nodes = [n for n in nodes if file_path in n.get('source_file', '')]
    
    if not matching_nodes:
        print(f"Archivo '{file_path}' no encontrado")
        return
    
    print(f"=== ARCHIVOS QUE DEPENDEN DE: {file_path} ===")
    for node in matching_nodes[:5]:  # Mostrar primeros 5 matches
        node_id = node['id']
        dependents = depended_by.get(node_id, set())
        print(f"\n{node['label']} ({node_id}):")
        print(f"  {len(dependents)} dependientes:")
        for dep_id in list(dependents)[:10]:
            dep_node = node_by_id.get(dep_id, {})
            print(f"    - {dep_node.get('label', dep_id)[:60]} | {dep_node.get('source_file', '')[:50]}")


def cmd_dependson(indices, file_path):
    """De qué depende este archivo"""
    depends_on = indices['depends_on']
    node_by_id = indices['node_by_id']
    nodes = indices['nodes']
    
    matching_nodes = [n for n in nodes if file_path in n.get('source_file', '')]
    
    if not matching_nodes:
        print(f"Archivo '{file_path}' no encontrado")
        return
    
    print(f"=== DEPENDENCIAS DE: {file_path} ===")
    for node in matching_nodes[:5]:
        node_id = node['id']
        dependencies = depends_on.get(node_id, set())
        print(f"\n{node['label']} ({node_id}):")
        print(f"  Depende de {len(dependencies)} nodos:")
        for dep_id in list(dependencies)[:10]:
            dep_node = node_by_id.get(dep_id, {})
            print(f"    - {dep_node.get('label', dep_id)[:60]} | {dep_node.get('source_file', '')[:50]}")


def cmd_community(indices, comm_id):
    """Miembros de una comunidad"""
    communities = indices['communities']
    node_by_id = indices['node_by_id']
    degree = indices['degree']
    
    comm_id = int(comm_id)
    if comm_id not in communities:
        print(f"Comunidad {comm_id} no encontrada")
        return
    
    members = communities[comm_id]
    print(f"=== COMUNIDAD {comm_id} ({len(members)} miembros) ===")
    
    # Ordenar por grado
    member_data = [(m, node_by_id.get(m, {}), degree.get(m, 0)) for m in members]
    member_data.sort(key=lambda x: x[2], reverse=True)
    
    for node_id, node, deg in member_data[:30]:
        label = node.get('label', 'N/A')
        source = node.get('source_file', 'N/A')
        print(f"  [{deg:3d}] {label[:50]:50s} | {source}")


def cmd_search(indices, term):
    """Buscar nodos que contengan el término"""
    nodes = indices['nodes']
    degree = indices['degree']
    
    term_lower = term.lower()
    matches = [n for n in nodes if 
               term_lower in n.get('label', '').lower() or 
               term_lower in n.get('source_file', '').lower()]
    
    if not matches:
        print(f"No se encontraron nodos con '{term}'")
        return
    
    print(f"=== BÚSQUEDA: '{term}' ({len(matches)} resultados) ===")
    
    # Ordenar por grado
    matches.sort(key=lambda x: degree.get(x['id'], 0), reverse=True)
    
    for node in matches[:30]:
        deg = degree.get(node['id'], 0)
        label = node.get('label', 'N/A')
        source = node.get('source_file', 'N/A')
        comm = node.get('community', '?')
        print(f"  [{deg:3d}] comm={comm} | {label[:50]:50s} | {source}")


def cmd_interdeps(indices):
    """Dependencias entre módulos"""
    links = indices['links']
    node_by_id = indices['node_by_id']
    
    inter_module = defaultdict(lambda: defaultdict(int))
    
    for link in links:
        src = node_by_id.get(link['source'], {})
        tgt = node_by_id.get(link['target'], {})
        src_file = src.get('source_file', '')
        tgt_file = tgt.get('source_file', '')
        
        src_mod = None
        tgt_mod = None
        if 'backend/modules/' in src_file:
            src_mod = src_file.split('backend/modules/')[1].split('/')[0]
        if 'backend/modules/' in tgt_file:
            tgt_mod = tgt_file.split('backend/modules/')[1].split('/')[0]
        
        if src_mod and tgt_mod and src_mod != tgt_mod:
            inter_module[src_mod][tgt_mod] += 1
    
    print("=== DEPENDENCIAS INTER-MÓDULO (top 30) ===")
    all_deps = []
    for src_mod, targets in inter_module.items():
        for tgt_mod, count in targets.items():
            all_deps.append((src_mod, tgt_mod, count))
    
    all_deps.sort(key=lambda x: x[2], reverse=True)
    for src, tgt, cnt in all_deps[:30]:
        print(f"  {src:30s} → {tgt:30s} : {cnt} links")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    command = sys.argv[1]
    graph = load_graph()
    indices = build_indices(graph)
    
    if command == 'stats':
        cmd_stats(indices)
    elif command == 'hubs':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        cmd_hubs(indices, n)
    elif command == 'module':
        if len(sys.argv) < 3:
            print("Uso: query_graphify.py module <nombre>")
            sys.exit(1)
        cmd_module(indices, sys.argv[2])
    elif command == 'depends':
        if len(sys.argv) < 3:
            print("Uso: query_graphify.py depends <archivo>")
            sys.exit(1)
        cmd_depends(indices, sys.argv[2])
    elif command == 'dependson':
        if len(sys.argv) < 3:
            print("Uso: query_graphify.py dependson <archivo>")
            sys.exit(1)
        cmd_dependson(indices, sys.argv[2])
    elif command == 'community':
        if len(sys.argv) < 3:
            print("Uso: query_graphify.py community <id>")
            sys.exit(1)
        cmd_community(indices, sys.argv[2])
    elif command == 'search':
        if len(sys.argv) < 3:
            print("Uso: query_graphify.py search <término>")
            sys.exit(1)
        cmd_search(indices, sys.argv[2])
    elif command == 'interdeps':
        cmd_interdeps(indices)
    else:
        print(f"Comando desconocido: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
