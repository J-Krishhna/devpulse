import sys
sys.path.append(".")

# from app.ingestion.ast_chunker import chunk_python_file

with open("app/ingestion/embedder.py", "r") as f:
    source = f.read()

from app.ingestion.ast_chunker import chunk_python_file
chunks = chunk_python_file("app/ingestion/embedder.py", source)
for c in chunks:
    print(f"{c['function_name']:30} lines {c['start_line']}–{c['end_line']}")

# # A self-contained test file — realistic enough to surface real behaviour
# SAMPLE_CODE = '''
# import jwt
# from datetime import datetime, timedelta

# SECRET_KEY = "supersecret"

# class AuthService:
#     """Handles all authentication logic."""

#     def __init__(self, db):
#         self.db = db

#     def authenticate_user(self, token: str) -> bool:
#         try:
#             payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
#             return payload.get("sub") is not None
#         except jwt.ExpiredSignatureError:
#             return False
#         except jwt.InvalidTokenError:
#             return False

#     def generate_token(self, user_id: str) -> str:
#         payload = {
#             "sub": user_id,
#             "exp": datetime.utcnow() + timedelta(hours=24),
#         }
#         return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


# def calculate_invoice_total(items: list) -> float:
#     subtotal = sum(item["price"] * item["quantity"] for item in items)
#     tax = subtotal * 0.18
#     discount = subtotal * 0.05 if subtotal > 1000 else 0
#     return subtotal + tax - discount
# '''


# chunks = chunk_python_file("app/sample.py", SAMPLE_CODE)

# print(f"Total chunks extracted: {len(chunks)}\n")
# print(f"{'#':<4} {'Function':<35} {'Lines':<12} {'Preview'}")
# print("-" * 80)
# for i, chunk in enumerate(chunks):
#     preview = chunk["raw_text"].split("\n")[0][:45]
#     lines = f"{chunk['start_line']}–{chunk['end_line']}"
#     print(f"{i+1:<4} {chunk['function_name']:<35} {lines:<12} {preview}")

# # Spot check: verify method names are prefixed with class name
# print("\n--- Spot checks ---")
# names = [c["function_name"] for c in chunks]
# assert "AuthService" in names, "❌ Class chunk missing"
# assert "AuthService.authenticate_user" in names, "❌ Method not prefixed with class name"
# assert "AuthService.generate_token" in names, "❌ Method not prefixed with class name"
# assert "calculate_invoice_total" in names, "❌ Module-level function missing"
# print("✅ All spot checks passed")

# # Spot check: line numbers are sane
# for chunk in chunks:
#     assert chunk["start_line"] <= chunk["end_line"], \
#         f"❌ Bad line numbers on {chunk['function_name']}"
# print("✅ Line numbers are valid")

# # Spot check: raw_text starts with def or class
# for chunk in chunks:
#     first_line = chunk["raw_text"].strip().split("\n")[0]
#     assert first_line.startswith("def ") or first_line.startswith("class "), \
#         f"❌ raw_text doesn't start with def/class: {chunk['function_name']}"
# print("✅ All chunks start with def or class")