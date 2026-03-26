from dotenv import load_dotenv
import os

load_dotenv()  # <-- THIS LINE IS REQUIRED

print("HF TOKEN:", os.getenv("HF_TOKEN")[:10])