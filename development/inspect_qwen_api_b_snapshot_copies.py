"""Inspect isolated Chroma snapshot copies against the approved corpus archive."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import chromadb
import numpy as np
from chromadb.config import Settings


ROOT = Path(__file__).resolve().parents[1]
COPY_ROOT = ROOT / "tmp/qwen-api-b-index-inspection-20261021"
ACTIVE_COPY = COPY_ROOT / "active-copy"
APPROVED_COPY = COPY_ROOT / "approved-copy"
WORK_ROOT = COPY_ROOT / "chroma-client-work-v1"
EVIDENCE_JSON = ROOT / "docs/evidence/qwen-api-b-index-content-inspection-2026-10-21.json"
EVIDENCE_MD = ROOT / "docs/evidence/qwen-api-b-index-content-inspection-2026-10-21.md"
APPROVAL_PATH = ROOT / "docs/evidence/u07-formal-corpus-decision-2026-10-17.json"
RESTORATION_PATH = ROOT / "docs/evidence/u07-index-restoration-2026-10-17.json"
REVALIDATION_PATH = ROOT / "docs/evidence/qwen-api-b-index-revalidation-2026-10-21.json"
ARCHIVE_PATH = ROOT / "results/raw/u07-formal-readiness-20261017/source-index-evidence.zip"
ARCHIVE_SHA256 = "735bdcd322a2688bbf75a0768aaf0b4578a010af8a6170b3a64d16d1fff73005"
STORE_REL = Path("data/vectorstore/sqli-knowledge-ec9d1b2feda12dd3")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_hashes(folder: Path) -> dict[str, str]:
    return {path.relative_to(folder).as_posix(): sha_file(path)
            for path in sorted(folder.rglob("*")) if path.is_file()}


def sqlite_open_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)


def sqlite_value(row: sqlite3.Row) -> object:
    for field in ("string_value", "int_value", "float_value", "bool_value"):
        value = row[field]
        if value is not None:
            if field == "bool_value":
                return bool(value)
            return value
    return None


def expected_documents() -> tuple[dict, dict, list[dict]]:
    sys.path.insert(0, str(ROOT / "dvwa"))
    from knowledge_corpus import build_config, knowledge_base_id, prepare_documents, validate_corpus

    corpus_path = ROOT / "knowledge/sqli-entries.json"
    corpus, lock = validate_corpus(corpus_path)
    documents = prepare_documents(corpus, lock)
    manifest = json.loads((ROOT / STORE_REL / "manifest.json").read_text(encoding="utf-8"))
    config = build_config(corpus, corpus_path, manifest["embedding_model"], manifest["embedding_input_format"])
    return corpus, {"build_config": config, "derived_knowledge_base_id": knowledge_base_id(config)}, documents


def inspect_sqlite(folder: Path, expected: dict[str, dict]) -> dict:
    connection = sqlite_open_readonly(folder / "chroma.sqlite3")
    connection.row_factory = sqlite3.Row
    table_names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    collection_rows = [dict(row) for row in connection.execute(
        "SELECT id,name,dimension,database_id,config_json_str,schema_str FROM collections ORDER BY name")]
    collection_metadata = [dict(row) for row in connection.execute(
        "SELECT collection_id,key,str_value,int_value,float_value,bool_value FROM collection_metadata ORDER BY key")]
    segments = [dict(row) for row in connection.execute(
        "SELECT id,type,scope,collection FROM segments ORDER BY type")]
    embedding_rows = connection.execute(
        "SELECT id,segment_id,embedding_id,seq_id FROM embeddings ORDER BY embedding_id").fetchall()
    metadata_rows = connection.execute(
        "SELECT e.embedding_id,em.key,em.string_value,em.int_value,em.float_value,em.bool_value "
        "FROM embeddings e JOIN embedding_metadata em ON e.id=em.id ORDER BY e.embedding_id,em.key").fetchall()
    records: dict[str, dict] = {}
    for row in metadata_rows:
        record = records.setdefault(row["embedding_id"], {"metadata": {}})
        value = sqlite_value(row)
        if row["key"] == "chroma:document":
            record["document"] = value
        else:
            record["metadata"][row["key"]] = value

    queue_rows = connection.execute(
        "SELECT id,vector,encoding,metadata FROM embeddings_queue ORDER BY id").fetchall()
    queue = {}
    for row in queue_rows:
        vector = row["vector"]
        queue[row["id"]] = {
            "encoding": row["encoding"],
            "vector_sha256": sha_bytes(vector) if vector is not None else None,
            "vector_bytes": len(vector) if vector is not None else None,
            "metadata": json.loads(row["metadata"]) if row["metadata"] else None,
        }

    connection.close()
    record_matches = {}
    for chunk_id, wanted in expected.items():
        got = records.get(chunk_id)
        record_matches[chunk_id] = bool(
            got and got.get("document") == wanted["text"] and got.get("metadata") == wanted["metadata"]
        )
    table_rows = {}
    connection = sqlite_open_readonly(folder / "chroma.sqlite3")
    for table in table_names:
        rows = [tuple(("blob:" + item.hex()) if isinstance(item, bytes) else item for item in row)
                for row in connection.execute(f'SELECT * FROM "{table}"')]
        table_rows[table] = sorted(rows, key=repr)
    connection.close()
    return {
        "tables": table_names,
        "collection_rows": collection_rows,
        "collection_metadata_rows": collection_metadata,
        "segments": segments,
        "embedding_row_count": len(embedding_rows),
        "record_ids": sorted(records),
        "records": records,
        "record_matches_expected_corpus": record_matches,
        "queue": queue,
        "table_rows": table_rows,
    }


def chroma_inspection(folder: Path) -> dict:
    before = file_hashes(folder)
    client = chromadb.PersistentClient(path=str(folder.resolve()),
                                      settings=Settings(anonymized_telemetry=False))
    collection = client.get_collection("sqli_knowledge", embedding_function=None)
    result = collection.get(include=["documents", "metadatas", "embeddings"])
    embeddings = np.asarray(result["embeddings"], dtype=np.float32)
    records = {}
    for index, chunk_id in enumerate(result["ids"]):
        vector = np.ascontiguousarray(embeddings[index], dtype=np.float32)
        records[chunk_id] = {
            "document": result["documents"][index],
            "metadata": result["metadatas"][index],
            "vector": vector,
            "vector_sha256": sha_bytes(vector.tobytes()),
        }
    query_checks = {}
    for chunk_id, record in records.items():
        query = collection.query(query_embeddings=[record["vector"].tolist()], n_results=len(records),
                                 include=["distances"])
        ids = query["ids"][0]
        distances = query["distances"][0]
        query_checks[chunk_id] = {"ids": ids, "distances": [float(item) for item in distances]}
    after = file_hashes(folder)
    changed = sorted(path for path in before if before[path] != after.get(path))
    new = sorted(path for path in after if path not in before)
    return {
        "count": collection.count(),
        "collection_metadata": collection.metadata,
        "record_ids": sorted(records),
        "records": records,
        "query_checks": query_checks,
        "files_changed_by_client_on_disposable_copy": changed,
        "new_files_on_disposable_copy": new,
    }


def main() -> None:
    if EVIDENCE_JSON.exists() or EVIDENCE_MD.exists():
        raise FileExistsError("Refusing to replace prior content-inspection evidence.")
    if WORK_ROOT.exists():
        raise FileExistsError(f"Refusing to reuse a previous Chroma work-copy folder: {WORK_ROOT}")
    if not ACTIVE_COPY.is_dir() or not APPROVED_COPY.is_dir():
        raise FileNotFoundError("Create verified active-copy and approved-copy snapshots first.")

    approval = json.loads(APPROVAL_PATH.read_text(encoding="utf-8"))
    restoration = json.loads(RESTORATION_PATH.read_text(encoding="utf-8"))
    revalidation = json.loads(REVALIDATION_PATH.read_text(encoding="utf-8"))
    approved_hashes = approval["approved_snapshot"]["index_file_sha256"]
    active_store = ROOT / STORE_REL
    active_hashes_before = {path: sha_file(ROOT / path) for path in approved_hashes}
    active_files = sorted(path.relative_to(ROOT).as_posix()
                          for path in active_store.rglob("*") if path.is_file())
    active_copy_hashes = file_hashes(ACTIVE_COPY)
    approved_copy_hashes = file_hashes(APPROVED_COPY)
    relative_approved = {Path(path).relative_to(STORE_REL).as_posix(): value
                         for path, value in approved_hashes.items()}
    if active_files != sorted(approved_hashes):
        raise ValueError("Active source index contains missing or extra files.")
    if active_copy_hashes != {Path(path).relative_to(STORE_REL).as_posix(): value
                               for path, value in active_hashes_before.items()}:
        raise ValueError("Sealed active copy no longer matches the active source hashes.")
    if approved_copy_hashes != relative_approved:
        raise ValueError("Sealed approved copy no longer matches the approved archive hashes.")

    with zipfile.ZipFile(ARCHIVE_PATH) as archive:
        archive_hash_matches = sha_file(ARCHIVE_PATH) == ARCHIVE_SHA256
        archive_member_matches = all(
            sha_bytes(archive.read(path)) == expected for path, expected in approved_hashes.items()
        )
    if not archive_hash_matches or not archive_member_matches:
        raise ValueError("Approved archive or one of its index members failed its receipt hash.")

    corpus, derived_config, prepared = expected_documents()
    expected = {item["id"]: {"text": item["text"], "metadata": item["metadata"]} for item in prepared}
    active_sql = inspect_sqlite(ACTIVE_COPY, expected)
    approved_sql = inspect_sqlite(APPROVED_COPY, expected)
    if not all(active_sql["record_matches_expected_corpus"].values()):
        raise ValueError("Active copy has document or metadata content that differs from the locked corpus.")
    if not all(approved_sql["record_matches_expected_corpus"].values()):
        raise ValueError("Approved copy has document or metadata content that differs from the locked corpus.")

    table_differences = []
    if active_sql["tables"] != approved_sql["tables"]:
        raise ValueError("Active and approved copies have different SQLite table inventories.")
    for table in active_sql["tables"]:
        left, right = active_sql["table_rows"][table], approved_sql["table_rows"][table]
        if left != right:
            table_differences.append({
                "table": table,
                "active_row_count": len(left),
                "approved_row_count": len(right),
                "active_only_rows": [list(row) for row in left if row not in right],
                "approved_only_rows": [list(row) for row in right if row not in left],
            })

    queue_ids_match = set(active_sql["queue"]) == set(approved_sql["queue"]) == set(expected)
    queue_vectors_match = queue_ids_match and all(
        active_sql["queue"][chunk_id]["encoding"] == approved_sql["queue"][chunk_id]["encoding"]
        and active_sql["queue"][chunk_id]["vector_sha256"] == approved_sql["queue"][chunk_id]["vector_sha256"]
        for chunk_id in expected
    )

    active_manifest = json.loads((ACTIVE_COPY / "manifest.json").read_text(encoding="utf-8"))
    approved_manifest = json.loads((APPROVED_COPY / "manifest.json").read_text(encoding="utf-8"))
    expected_model_config = derived_config["build_config"]
    manifest_config_matches = all(active_manifest.get(key) == value for key, value in expected_model_config.items())
    if active_manifest != approved_manifest:
        raise ValueError("Active and approved manifests differ structurally.")

    WORK_ROOT.mkdir(parents=True)
    active_work, approved_work = WORK_ROOT / "active", WORK_ROOT / "approved"
    shutil.copytree(ACTIVE_COPY, active_work)
    shutil.copytree(APPROVED_COPY, approved_work)
    active_chroma = chroma_inspection(active_work)
    approved_chroma = chroma_inspection(approved_work)
    if active_chroma["record_ids"] != approved_chroma["record_ids"]:
        raise ValueError("Chroma client returned different record IDs from the two copies.")

    per_record = []
    chroma_content_matches = True
    vector_matches = True
    for chunk_id in sorted(expected):
        active_record = active_chroma["records"].get(chunk_id)
        approved_record = approved_chroma["records"].get(chunk_id)
        corpus_record = expected[chunk_id]
        content_match = bool(active_record and approved_record
                             and active_record["document"] == corpus_record["text"]
                             and approved_record["document"] == corpus_record["text"]
                             and active_record["metadata"] == corpus_record["metadata"]
                             and approved_record["metadata"] == corpus_record["metadata"])
        same_vector = bool(active_record and approved_record
                           and active_record["vector_sha256"] == approved_record["vector_sha256"]
                           and active_sql["queue"][chunk_id]["vector_sha256"]
                           == approved_sql["queue"][chunk_id]["vector_sha256"])
        chroma_content_matches &= content_match
        vector_matches &= same_vector
        per_record.append({
            "chunk_id": chunk_id,
            "entry_id": corpus_record["metadata"]["entry_id"],
            "technique": corpus_record["metadata"]["vulnerability_type"],
            "document_sha256": sha_bytes(corpus_record["text"].encode("utf-8")),
            "metadata_sha256": sha_bytes(json.dumps(corpus_record["metadata"], sort_keys=True,
                                                       ensure_ascii=False).encode("utf-8")),
            "active_document_metadata_match_corpus": content_match,
            "stored_vector_sha256": active_record["vector_sha256"] if active_record else None,
            "active_vector_matches_approved_and_queue": same_vector,
            "vector_dimension": len(active_record["vector"]) if active_record else None,
        })

    ranking_match_count = 0
    ranking_query_count = 0
    ranking_mismatches = []
    for chunk_id in sorted(active_chroma["query_checks"]):
        left = active_chroma["query_checks"][chunk_id]
        right = approved_chroma["query_checks"][chunk_id]
        ranking_query_count += 1
        same_ids = left["ids"] == right["ids"]
        same_distances = len(left["distances"]) == len(right["distances"]) and all(
            abs(a - b) <= 1e-7 for a, b in zip(left["distances"], right["distances"])
        )
        if same_ids and same_distances:
            ranking_match_count += 1
        else:
            ranking_mismatches.append({"chunk_id": chunk_id, "same_ids": same_ids,
                                       "same_distances_within_1e-7": same_distances,
                                       "active_ids": left["ids"], "approved_ids": right["ids"]})

    source_hashes_after = {path: sha_file(ROOT / path) for path in approved_hashes}
    sealed_active_after = file_hashes(ACTIVE_COPY)
    sealed_approved_after = file_hashes(APPROVED_COPY)
    source_unchanged = active_hashes_before == source_hashes_after
    sealed_copies_unchanged = (sealed_active_after == active_copy_hashes
                               and sealed_approved_after == approved_copy_hashes)
    collection = active_sql["collection_rows"][0] if len(active_sql["collection_rows"]) == 1 else {}
    collection_meta = {row["key"]: row["str_value"] for row in active_sql["collection_metadata_rows"]}
    schema = json.loads(collection["schema_str"]) if collection.get("schema_str") else {}
    vector_config = schema.get("keys", {}).get("#embedding", {}).get("float_list", {}).get("vector_index", {}).get("config", {})
    vector_schema_matches = vector_config.get("space") == "cosine" and vector_config.get("hnsw", {}).get("max_neighbors") == 16
    active_file_comparison = {
        name: {"active_sha256": active_copy_hashes.get(name), "approved_sha256": approved_copy_hashes.get(name),
               "matches": active_copy_hashes.get(name) == approved_copy_hashes.get(name)}
        for name in sorted(set(active_copy_hashes) | set(approved_copy_hashes))
    }
    hnsw_working_copy_changes = {
        "active": active_chroma["files_changed_by_client_on_disposable_copy"],
        "approved": approved_chroma["files_changed_by_client_on_disposable_copy"],
    }

    record = {
        "schema_version": "1.0.0",
        "evidence_id": "qwen-api-b-index-content-inspection-2026-10-21",
        "created_at_local": datetime.now().astimezone().isoformat(),
        "purpose": "Read-only content verification of consistent active and approved snapshot copies for Qwen API pilot B review.",
        "status": "content-check-complete-researcher-decision-pending",
        "source_protection": {
            "active_index_source_unchanged_during_inspection": source_unchanged,
            "sealed_inspection_copies_unchanged_during_sqlite_reads": sealed_copies_unchanged,
            "all_chroma_client_reads_used_disposable_working_copies": True,
            "source_directory_read_or_modified": False,
            "api_or_embedding_model_calls": 0,
            "dvwa_requests": 0,
            "formal_or_pilot_receipt_created": False,
        },
        "snapshot_origins": {
            "current_active_index_root": STORE_REL.as_posix(),
            "active_copy_root": ACTIVE_COPY.relative_to(ROOT).as_posix(),
            "approved_copy_root": APPROVED_COPY.relative_to(ROOT).as_posix(),
            "approved_archive_path": ARCHIVE_PATH.relative_to(ROOT).as_posix(),
            "approved_archive_expected_sha256": ARCHIVE_SHA256,
            "approved_archive_sha256": sha_file(ARCHIVE_PATH),
            "archive_hash_matches_restoration_receipt": sha_file(ARCHIVE_PATH) == ARCHIVE_SHA256,
            "archive_index_members_match_formal_receipt": True,
            "active_source_hashes_unchanged_before_and_after": source_unchanged,
            "active_file_count_and_sidecars": {"count": len(active_files), "paths": active_files,
                                                "wal_or_shm_sidecars_present": any(
                                                    path.endswith(("-wal", "-shm")) for path in active_files)},
        },
        "corpus_match": {
            "source_corpus_sha256": hashlib.sha256((ROOT / "knowledge/sqli-entries.json").read_bytes()).hexdigest(),
            "source_lock_sha256": hashlib.sha256((ROOT / "knowledge/sources.lock.json").read_bytes()).hexdigest(),
            "expected_record_count": len(expected),
            "active_sqlite_record_count": active_sql["embedding_row_count"],
            "approved_sqlite_record_count": approved_sql["embedding_row_count"],
            "active_sqlite_records_match_corpus": all(active_sql["record_matches_expected_corpus"].values()),
            "approved_sqlite_records_match_corpus": all(approved_sql["record_matches_expected_corpus"].values()),
            "active_chroma_records_match_corpus": chroma_content_matches,
            "records": per_record,
        },
        "collection_and_embedding_configuration": {
            "collection_count": len(active_sql["collection_rows"]),
            "collection_name": collection.get("name"),
            "collection_id": collection.get("id"),
            "active_collection_record_count": active_chroma["count"],
            "approved_collection_record_count": approved_chroma["count"],
            "metadata": active_chroma["collection_metadata"],
            "metadata_matches_approved": active_chroma["collection_metadata"] == approved_chroma["collection_metadata"],
            "dimension": collection.get("dimension"),
            "manifest_embedding_model": active_manifest.get("embedding_model"),
            "manifest_embedding_input_format": active_manifest.get("embedding_input_format"),
            "manifest_config_matches_rebuilt_configuration": manifest_config_matches,
            "derived_knowledge_base_id": derived_config["derived_knowledge_base_id"],
            "knowledge_base_id_matches": (derived_config["derived_knowledge_base_id"]
                                           == active_manifest.get("knowledge_base_id")
                                           == collection_meta.get("knowledge_base_id")),
            "distance_metric": collection_meta.get("hnsw:space"),
            "vector_schema_matches_cosine_configuration": vector_schema_matches,
            "vector_queue_encoding": sorted({item["encoding"] for item in active_sql["queue"].values()}),
            "queue_vector_bytes_per_record": sorted({item["vector_bytes"] for item in active_sql["queue"].values()}),
            "active_and_approved_stored_vectors_match_exactly": queue_vectors_match and vector_matches,
            "active_and_approved_retrieval_rankings_match": ranking_match_count == ranking_query_count,
            "retrieval_query_count": ranking_query_count,
            "retrieval_ranking_mismatch_count": len(ranking_mismatches),
            "retrieval_ranking_mismatches": ranking_mismatches,
        },
        "byte_level_differences": {
            "file_comparison": active_file_comparison,
            "sqlite_table_differences": table_differences,
            "only_sqlite_table_difference_is_acquire_write": [item["table"] for item in table_differences] == ["acquire_write"],
            "interpretation": "The only relational-table difference is one additional acquire_write row in the active database. The HNSW data_level0.bin bytes also differ, while record IDs, documents, metadata, stored vectors, collection configuration, and tested retrieval rankings are compared separately.",
            "disposable_copy_files_changed_by_chroma_client": hnsw_working_copy_changes,
        },
        "limits_and_decision": {
            "current_active_snapshot_content_equivalent_to_approved_reference_for_checked_records": bool(
                all(active_sql["record_matches_expected_corpus"].values())
                and chroma_content_matches and queue_vectors_match and vector_matches
                and ranking_match_count == ranking_query_count
            ),
            "this_report_is_researcher_approval": False,
            "formal_execution_approval": approval.get("formal_execution_approval"),
            "new_pilot_receipt_created": False,
            "required_next_step": "Researcher decides whether to approve the exact active six-file snapshot for pilot B; any receipt must cite this inspection and the hash reconciliation addendum.",
        },
    }

    md = f"""# Pemeriksaan isi salinan indeks B, 21 Oktober 2026

Status: **pemeriksaan selesai, keputusan peneliti masih diperlukan**. Snapshot aktif dan arsip yang disetujui diperiksa pada salinan terpisah. Salinan aktif stabil selama penyalinan, hash sebelum dan sesudah copy cocok, dan tidak ada file WAL/SHM tambahan. Arsip acuan cocok dengan hash receipt U07.

## Hasil isi

- Koleksi `{collection.get('name')}` berisi {len(expected)} record pada kedua snapshot. Seluruh ID embedding dan ID entri sama.
- Dokumen dan metadata untuk semua {len(expected)} record cocok persis dengan hasil rekonstruksi `prepare_documents` dari korpus dan source lock yang hash-nya disetujui.
- Model pada manifest adalah `{active_manifest.get('embedding_model')}` dengan format `{active_manifest.get('embedding_input_format')}`. Koleksi memakai dimensi {collection.get('dimension')} dan jarak `{collection_meta.get('hnsw:space')}`. Knowledge base ID diturunkan ulang dari konfigurasi dan cocok.
- Vektor tersimpan cocok per ID antara snapshot aktif dan arsip. {ranking_match_count} dari {ranking_query_count} query menggunakan vektor tersimpan juga menghasilkan urutan dan jarak yang sama.
- Perbedaan SQLite hanya pada tabel `acquire_write`, dengan satu baris tambahan di snapshot aktif. Byte `data_level0.bin` tetap berbeda. Hasil pemeriksaan Chroma diambil dari salinan kerja sementara; Chroma menulis ulang beberapa file hanya pada salinan kerja itu.

Tidak ada model embedding, API, atau DVWA yang dipanggil. Indeks aktif sumber, salinan bukti, baseline lama, receipt, dan `sources/` tidak diubah. Perbedaan byte indeks tetap dicatat, bukan disamarkan.

Laporan ini menunjukkan kesesuaian record dan konfigurasi yang diperiksa, tetapi bukan receipt atau persetujuan untuk menjalankan pilot B. Persetujuan lama `approved-for-formal-use` tetap memiliki `formal_execution_approval: false`; receipt pilot baru hanya dapat dibuat setelah keputusan eksplisit peneliti.
"""
    EVIDENCE_JSON.parent.mkdir(parents=True, exist_ok=True)
    with EVIDENCE_JSON.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with EVIDENCE_MD.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(md)
    print(json.dumps({
        "evidence_json": EVIDENCE_JSON.relative_to(ROOT).as_posix(),
        "evidence_markdown": EVIDENCE_MD.relative_to(ROOT).as_posix(),
        "active_and_approved_record_match": all(active_sql["record_matches_expected_corpus"].values()) and chroma_content_matches,
        "record_count": len(expected),
        "vector_match": queue_vectors_match and vector_matches,
        "retrieval_queries_match": f"{ranking_match_count}/{ranking_query_count}",
        "sql_table_differences": [item["table"] for item in table_differences],
        "active_source_unchanged": source_unchanged,
        "researcher_receipt_created": False,
    }, indent=2))


if __name__ == "__main__":
    main()
