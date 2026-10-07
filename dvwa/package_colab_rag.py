"""Package the proposal RAG files needed by Colab, excluding local runtime data."""

from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "knowledge/sqli-entries.json", "knowledge/sources.lock.json", "knowledge/NOTICE.md",
    "schemas/sqli-knowledge-corpus.schema.json", "dvwa/knowledge_corpus.py",
    "dvwa/rag_pipeline.py", "dvwa/retrieve_structured_knowledge.py",
    "dvwa/fetch_knowledge_sources.py", "dvwa/experiment_scenarios.json",
    "notebooks/colab_langchain_setup.ipynb", "docs/proposal-rag-2026-10-07.md",
)


def main() -> None:
    output = ROOT / "outputs/proposal-rag/colab-proposal-rag.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    # An explicit file list avoids copying .env, PDFs, reports, databases or models.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in FILES:
            archive.write(ROOT / relative, relative)
    with zipfile.ZipFile(output) as archive:
        if tuple(archive.namelist()) != FILES or archive.testzip() is not None:
            raise ValueError("Colab bundle integrity check failed.")
        for relative in FILES:
            if archive.read(relative) != (ROOT / relative).read_bytes():
                raise ValueError(f"Bundled file differs from its source: {relative}")
    print(f"Verified Colab bundle ({len(FILES)} files): {output}")


if __name__ == "__main__":
    main()
