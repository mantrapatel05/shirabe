from __future__ import annotations
import os, re, shutil, subprocess, tempfile
from pathlib import Path
from urllib.parse import urlparse

IGNORED_DIRS={".git",".venv","venv","node_modules","__pycache__",".next","dist","build","target"}
TEXT_EXTENSIONS={".py",".js",".jsx",".ts",".tsx",".java",".go",".rs",".cpp",".cc",".c",".h",".hpp",".cs",".rb",".php",".swift",".kt",".kts",".scala",".sql",".md",".txt",".yaml",".yml",".json",".toml",".ini",".cfg",".xml",".html",".css",".sh",".bash"}
MAX_FILE_BYTES=500_000

def clone_repository(repo_url : str) -> str:
    parsed = urlparse(repo_url)

    if parsed.scheme not in {"http","https"}:
        raise ValueError("Repository URL must use http or https")

    if parsed.netloc.lower() not in {"github.com","www.github.com"}:
        raise ValueError("Shirabe currently parses and supports only github urls only!")

    if not re.match(r"^/[^/]+/[^/]+/?$", parsed.path):
        raise ValueError("Expected https://github.com/owner/repository")

    temp_dir = tempfile.mkdtemp(prefix="shirabe_")
    destination = os.path.join(temp_dir,"repo")

    try:
        subprocess.run(["git","clone","--depth","1",repo_url,destination],check=True,capture_output=True,text=True,timeout=120)
    except Exception:
        shutil.rmtree(temp_dir,ignore_errors=True); 
        raise
    return destination

def _iter_text_files(repo_path : str):
    root = Path(repo_path)

    for path in root.rglob("*"):
        if not path.is_file() or any(part in IGNORED_DIRS for part in path.parts) or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            if path.stat().st_size>MAX_FILE_BYTES:
                continue
        except OSError: continue
        yield path

def iter_text_files(repo_path : str):
    yield from _iter_text_files(repo_path)

def search_repository(repo_path : str, query : str, max_results : int=8) -> list[str]:
    terms = [x.lower() for x in query.split() if x.strip()]

    if not terms:
        return []

    results = []

    for path in _iter_text_files(repo_path):
        try:
            lines=path.read_text(encoding="utf-8",errors="ignore").splitlines()
        except OSError:
            continue

        for index,line in enumerate(lines):
            if all(term in line.lower() for term in terms):
                start=max(0,index-2); end=min(len(lines),index+3); relative=path.relative_to(repo_path)
                snippet="\n".join(f"{start+offset+1}: {lines[start+offset]}" for offset in range(end-start))
                results.append(f"FILE: {relative}\nLINES: {start+1}-{end}\n{snippet}")
                if len(results)>=max_results: return results

    return results

def search_repo(repo_path : str, query : str, max_results : int=8) -> list[str]:
    return search_repository(repo_path, query, max_results)

def read_file(repo_path: str, relative_path: str, max_chars: int=8000) -> str:
    root = Path(repo_path).resolve(); 
    candidate = (root/relative_path).resolve()

    if root not in candidate.parents and candidate!=root: 
        raise ValueError("Path escapes repository root.")
    if not candidate.is_file(): 
        raise FileNotFoundError(relative_path)
    return candidate.read_text(encoding="utf-8",errors="ignore")[:max_chars]
