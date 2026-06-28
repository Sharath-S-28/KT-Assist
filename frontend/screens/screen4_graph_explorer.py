"""
frontend/screens/screen4_graph_explorer.py — Screen 4: Knowledge Graph
Explorer (Phase 11 / Session 33). [FROZEN] content: embeds the S9 PyVis
viewer (Phase 3) via st.components.v1.html from client.get_graph_html;
zoom/search/filter/node-selection/relationship-highlighting are the PyVis
viewer's own built-in interactions (services/graph_viewer.py, Phase 3 /
Session 9) -- this screen does not re-render the graph engine, exactly as
the spec requires. Node detail panel (type, description, criticality,
confidence, relationships, source references) is rendered separately
below the embed via client.get_graph_node, since PyVis's embedded HTML
cannot call back into Streamlit.
"""

import streamlit as st
from streamlit.components.v1 import html as st_html

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Knowledge Graph Explorer")

    packages = client.list_packages()
    if not packages:
        st.info("No knowledge packages exist yet.")
        return

    selected_name = st.selectbox("Package", options=[p.name for p in packages])
    package = next(p for p in packages if p.name == selected_name)

    try:
        graph_html = client.get_graph_html(package.id)
        graph = client.get_graph(package.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No knowledge graph extracted yet for this package.")
            return
        raise

    st.caption(f"Version {graph.version} · {len(graph.nodes)} objects · {len(graph.relationships)} relationships")
    st_html(graph_html, height=600, scrolling=True)

    st.subheader("Node Detail")
    node_options = {f"{n.name} ({n.object_type})": n.id for n in graph.nodes}
    if not node_options:
        st.caption("This graph has no nodes yet.")
        return

    selected_label = st.selectbox("Select a node", options=list(node_options))
    node_id = node_options[selected_label]
    detail = client.get_graph_node(package.id, node_id)

    cols = st.columns(3)
    with cols[0]:
        st.write(f"**Type:** {detail.object_type}")
    with cols[1]:
        st.write(f"**Criticality:** {detail.criticality}")
    with cols[2]:
        st.write(f"**Confidence:** {detail.confidence:.0%}")

    st.write(f"**Description:** {detail.description or '—'}")
    st.write(f"**Source Reference:** {detail.source_reference or '—'}")

    rel_cols = st.columns(2)
    with rel_cols[0]:
        st.write("**Outgoing relationships**")
        if detail.outgoing_relationships:
            st.table([
                {"Type": r.relationship_type, "Target": r.target_name} for r in detail.outgoing_relationships
            ])
        else:
            st.caption("None.")
    with rel_cols[1]:
        st.write("**Incoming relationships**")
        if detail.incoming_relationships:
            st.table([
                {"Type": r.relationship_type, "Source": r.source_name} for r in detail.incoming_relationships
            ])
        else:
            st.caption("None.")
