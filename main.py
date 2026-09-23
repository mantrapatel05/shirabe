from __future__ import annotations
import argparse, os
from dotenv import load_dotenv
from graph import app
from tools import clone_repository

def main():
    load_dotenv()
    parser=argparse.ArgumentParser(description="Shirabe autonomous codebase investigation agent")
    parser.add_argument("repo_url",nargs="?"); parser.add_argument("question",nargs="?"); args=parser.parse_args()
    repo_url=args.repo_url or input("GitHub repository URL: ").strip(); question=args.question or input("Engineering question: ").strip()
    if not os.getenv("GROQ_API_KEY"): raise RuntimeError("GROQ_API_KEY is not configured.")
    print("\n[1/2] Loading repository..."); repo_path=clone_repository(repo_url)
    print("[2/2] Running investigation...\n")
    result=app.invoke({"repo_url":repo_url,"repo_path":repo_path,"question":question,"plan":[],"evidence":[],"analysis":"","answer":"","iteration":0,"max_iterations":3,"needs_more_evidence":False})
    print("\n"+"="*80); print(result["answer"]); print("="*80)
if __name__=="__main__": main()
