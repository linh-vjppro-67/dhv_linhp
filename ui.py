from pathlib import Path

import streamlit as st

from app.indexer import sync_folder
from app.qwen_chat import chat_search, status as qwen_status
from app.search_engine import search


st.set_page_config(
    page_title="Smart Document Search",
    layout="wide",
)

st.title(
    "Smart Document Search"
)

st.caption(
    "BGE retrieval + Qwen chat completion, chạy local"
)

with st.sidebar:
    mode = st.radio(
        "Chế độ",
        ("Hỏi Qwen", "Tìm trực tiếp"),
    )
    qwen = qwen_status()
    st.caption(
        f"Qwen: {'sẵn sàng' if qwen['ready'] else 'chưa tải'} "
        f"• {qwen['device']}"
    )
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


if mode == "Hỏi Qwen":
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            if message.get("sources"):
                with st.expander("Văn bản nguồn"):
                    for source in message["sources"]:
                        st.markdown(f"**{source['file_name']}**")
                        st.caption(f"{source['category']} • score {source['score']}")
                        st.write(source.get("excerpt", ""))
    prompt = st.chat_input("Hỏi về nội dung, thời gian hoặc quan hệ giữa các văn bản")
    if prompt:
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)
        try:
            with st.chat_message("assistant"):
                with st.spinner("Qwen đang đọc kết quả tra cứu..."):
                    response = chat_search(
                        prompt,
                        history=st.session_state.chat_messages[:-1],
                        top_k=5,
                    )
                st.write(response["answer"])
                with st.expander("Văn bản nguồn"):
                    for source in response["sources"]:
                        st.markdown(f"**{source['file_name']}**")
                        st.caption(f"{source['category']} • score {source['score']}")
                        st.write(source.get("excerpt", ""))
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": response["answer"], "sources": response["sources"]}
            )
        except Exception as exc:
            st.error(str(exc))
else:
    query = st.text_input(
        "Tìm kiếm",
        placeholder="Ví dụ: phạm thị hậu hoặc phạn thị hâuk",
    )
if mode == "Tìm trực tiếp" and query:
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
