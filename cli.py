import argparse
import json

from app.config import DEFAULT_TOP_K
from app.db import get_stats
from app.indexer import (
    rebuild_search_indexes,
    sync_folder,
)
from app.search_engine import (
    debug_search,
    search,
)
from app.qwen_chat import chat_search


def _print_json(data):
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Smart Document Search PRO"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    p_sync = sub.add_parser(
        "sync"
    )
    p_sync.add_argument(
        "folder"
    )
    p_sync.add_argument(
        "--workers",
        type=int,
        default=2,
    )
    p_sync.add_argument(
        "--no-cache",
        action="store_true",
    )

    p_search = sub.add_parser(
        "search"
    )
    p_search.add_argument(
        "query"
    )
    p_search.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
    )
    p_search.add_argument(
        "--category"
    )
    p_search.add_argument(
        "--folder-prefix"
    )
    p_search.add_argument(
        "--extension"
    )
    p_search.add_argument(
        "--min-score",
        type=float,
    )

    p_debug = sub.add_parser(
        "debug-search"
    )
    p_debug.add_argument(
        "query"
    )

    p_chat = sub.add_parser("chat")
    p_chat.add_argument("message")
    p_chat.add_argument("--top-k", type=int, default=5)
    p_debug.add_argument(
        "--top-k",
        type=int,
        default=10,
    )

    sub.add_parser(
        "stats"
    )

    sub.add_parser(
        "rebuild-search-indexes"
    )

    args = parser.parse_args()

    if args.command == "sync":
        _print_json(
            sync_folder(
                folder=args.folder,
                workers=args.workers,
                use_cache=not args.no_cache,
            )
        )

    elif args.command == "search":
        _print_json(
            {
                "query": args.query,
                "results": search(
                    args.query,
                    top_k=args.top_k,
                    category=args.category,
                    folder_prefix=args.folder_prefix,
                    extension=args.extension,
                    min_score=args.min_score,
                ),
            }
        )

    elif args.command == "debug-search":
        _print_json(
            debug_search(
                args.query,
                top_k=args.top_k,
            )
        )

    elif args.command == "chat":
        _print_json(chat_search(args.message, top_k=args.top_k))

    elif args.command == "stats":
        _print_json(
            get_stats()
        )

    elif (
        args.command
        == "rebuild-search-indexes"
    ):
        _print_json(
            rebuild_search_indexes()
        )


if __name__ == "__main__":
    main()
