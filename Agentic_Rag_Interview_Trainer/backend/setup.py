#!/usr/bin/env python3
"""
setup.py — Install dependencies and verify the environment.
Run: python setup.py
"""
import subprocess
import sys
import os

REQUIRED_PACKAGES = [
    "fastapi==0.111.0",
    "uvicorn[standard]==0.29.0",
    "python-dotenv==1.0.1",
    "httpx==0.27.0",
    "pydantic==2.7.1",
    "python-multipart==0.0.9",
    "faiss-cpu==1.8.0",
    "numpy==1.26.4",
    "sentence-transformers==3.0.1",
    "aiofiles==23.2.1",
    "PyPDF2==3.0.1",
]

def run(cmd):
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:300]}")
        return False
    return True

def main():
    print("=" * 60)
    print("  Agentic RAG Interview Trainer — Setup")
    print("=" * 60)

    # Install packages
    print("\n[1/3] Installing Python packages...")
    ok = run([sys.executable, "-m", "pip", "install", "--quiet"] + REQUIRED_PACKAGES)
    if not ok:
        print("  Try: pip install -r requirements.txt")
        sys.exit(1)
    print("  ✓ Packages installed")

    # Check .env
    print("\n[2/3] Checking .env configuration...")
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        print("  ✓ .env file found")
    else:
        print("  ✗ .env not found — copy .env.example to .env and fill in credentials")
        sys.exit(1)

    # Check knowledge base
    print("\n[3/3] Checking knowledge base...")
    kb_path = os.path.join(os.path.dirname(__file__), "..", "knowledge_base")
    kb_files = []
    if os.path.exists(kb_path):
        for root, _, files in os.walk(kb_path):
            for f in files:
                if f.endswith((".txt", ".json", ".md")):
                    kb_files.append(f)
    if kb_files:
        print(f"  ✓ Knowledge base: {len(kb_files)} files found")
    else:
        print("  ✗ No knowledge base files found in ../knowledge_base/")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("  ✓ Setup complete!")
    print("")
    print("  Start the server:")
    print("    cd backend")
    print("    python main.py")
    print("")
    print("  Then open: http://localhost:8000")
    print("=" * 60)

if __name__ == "__main__":
    main()
