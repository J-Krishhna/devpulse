import tree_sitter_python as tspython
from tree_sitter import Language, Parser
from typing import Optional

# Build the Python language parser once at module level
# PY_LANGUAGE = Language(tspython.language(), "python")
# _parser = Parser(PY_LANGUAGE)

PY_LANGUAGE = Language(tspython.language(), "python")

_parser = Parser()
_parser.set_language(PY_LANGUAGE)


def chunk_python_file(file_path: str, source_code: str) -> list[dict]:
    """
    Parse a Python source file and extract one chunk per function/class.

    Returns a list of dicts:
    {
        "file_path": str,
        "function_name": str,
        "start_line": int,       # 1-indexed
        "end_line": int,         # 1-indexed
        "raw_text": str,         # full source text of the function/class
    }
    """

    source_bytes = source_code.encode("utf-8")
    tree = _parser.parse(source_bytes)

    chunks = []
    _extract_nodes(tree.root_node, source_bytes, file_path, chunks)

    return chunks


def _extract_nodes(
    node,
    source_bytes: bytes,
    file_path: str,
    chunks: list,
    parent_name: Optional[str] = None,
):
    """
    Recursively walk the AST.
    Extract function_definition and class_definition nodes.
    For methods inside a class, prefix the name with the class name.
    """
    for child in node.children:

        if child.type == "class_definition":
            class_name = _get_node_name(child, source_bytes)

            # Add the class itself as a chunk
            chunks.append(_make_chunk(child, source_bytes, file_path, class_name))

            # Then recurse into the class body to get its methods too
            _extract_nodes(child, source_bytes, file_path, chunks, parent_name=class_name)

        elif child.type == "function_definition":
            func_name = _get_node_name(child, source_bytes)

            # If this function is inside a class, name it ClassName.method_name
            full_name = f"{parent_name}.{func_name}" if parent_name else func_name

            chunks.append(_make_chunk(child, source_bytes, file_path, full_name))

            # Recurse for nested functions
            _extract_nodes(child, source_bytes, file_path, chunks, parent_name=parent_name)

        else:
            # Keep walking — functions can be nested inside if blocks etc.
            _extract_nodes(child, source_bytes, file_path, chunks, parent_name=parent_name)


def _get_node_name(node, source_bytes: bytes) -> str:
    """
    Extract the identifier (name) of a function or class node.
    The 'identifier' child is always the name — e.g. 'def authenticate_user' → 'authenticate_user'
    """
    for child in node.children:
        if child.type == "identifier":
            return source_bytes[child.start_byte:child.end_byte].decode("utf-8")
    return "unknown"


def _make_chunk(node, source_bytes: bytes, file_path: str, name: str) -> dict:
    """
    Build the chunk dict from a tree-sitter node.
    start_point and end_point are (row, column) tuples — row is 0-indexed, so +1 for humans.
    """
    raw_text = source_bytes[node.start_byte:node.end_byte].decode("utf-8")

    return {
        "file_path": file_path,
        "function_name": name,
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "raw_text": raw_text,
    }