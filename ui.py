from pathlib import Path

import streamlit as st

from app.indexer import sync_folder
from app.search_engine import search


st.set_page_config(
    page_title="Smart Document Search",
    layout="wide",
)

st.title(
    "Smart Document Search"
)

st.caption(
    "Exact + typo tolerant + semantic + reranker"
)

with st.sidebar:
    folder = st.text_input(
        "Folder tài liệu",
        value=str(
            (
                Path.cwd()
                / "documents"
            ).resolve()
        ),
    )

    workers = st.slider(
        "Workers",
        1,
        8,
        2,
    )

    if st.button(
        "Sync documents",
        use_container_width=True,
    ):
        try:
            with st.spinner(
                "Đang sync..."
            ):
                result = sync_folder(
                    folder,
                    workers=workers,
                    use_cache=True,
                )

            st.success(
                "Sync xong"
            )
            st.json(result)

        except Exception as exc:
            st.error(
                str(exc)
            )


query = st.text_input(
    "Tìm kiếm",
    placeholder=(
        "Ví dụ: phạm thị hậu "
        "hoặc phạn thị hâuk"
    ),
)

if query:
    try:
        results = search(
            query,
            top_k=3,
        )

        if not results:
            st.info(
                "Không tìm thấy kết quả."
            )

        for item in results:
            st.subheader(
                f"{item['rank']}. "
                f"{item['file_name']}"
            )

            st.caption(
                f"{item['category']} "
                f"• score {item['score']}"
            )

            st.write(
                item["excerpt"]
            )

            st.divider()

    except Exception as exc:
        st.error(
            str(exc)
        )
