"""
frontend/screens/screen3_package_workspace.py — Screen 3: Knowledge
Package Workspace (Phase 11 / Session 33). [FROZEN] content: knowledge
assets (documents, presentations, runbooks, recordings, notes);
knowledge summary (object count, relationship count, confidence score,
coverage).

Backend gap closed for this screen (documented in schemas/asset.py +
services/routers/assets.py): no router exposed models.asset.KnowledgeAsset
over HTTP before Session 33, so client.list_assets() is a Session 33
addition, the same kind of gap-closing the graph router was for Screen 4.

Object/relationship counts and the mean confidence score come from the
package's latest graph version (client.get_graph) -- a package that
hasn't been extracted yet has no graph, which this screen treats as "not
extracted yet" rather than an error.
"""

import streamlit as st

from frontend.api_client import ApiClient, ApiError
from frontend.theme import inject_global_css


def render(client: ApiClient) -> None:
    inject_global_css()
    st.title("Knowledge Package Workspace")

    packages = client.list_packages()
    if not packages:
        st.info("No knowledge packages exist yet.")
        return

    selected_name = st.selectbox("Package", options=[p.name for p in packages])
    package = next(p for p in packages if p.name == selected_name)

    if package.description:
        st.caption(package.description)

    st.subheader("Knowledge Assets")
    assets = client.list_assets(package.id)
    if assets:
        st.dataframe(
            [{"Filename": a.filename, "Type": a.file_type, "Extraction Status": a.extraction_status} for a in assets],
            use_container_width=True,
        )
    else:
        st.caption("No source documents uploaded yet.")

    st.subheader("Knowledge Summary")
    try:
        graph = client.get_graph(package.id)
    except ApiError as exc:
        if exc.status_code == 404:
            st.caption("No knowledge graph extracted yet for this package.")
            graph = None
        else:
            raise

    if graph is not None:
        mean_confidence = (
            sum(node.confidence for node in graph.nodes) / len(graph.nodes) if graph.nodes else None
        )
        cols = st.columns(4)
        with cols[0]:
            st.metric("Knowledge Objects", len(graph.nodes))
        with cols[1]:
            st.metric("Relationships", len(graph.relationships))
        with cols[2]:
            st.metric("Mean Confidence", f"{mean_confidence:.0%}" if mean_confidence is not None else "—")
        with cols[3]:
            coverage = package.latest_coverage_score
            st.metric("Coverage", f"{coverage * 100:.0f}%" if coverage is not None else "—")
