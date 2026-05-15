import numpy as np
import time
import json
from typing import List, Dict, Tuple, Any, Optional

from Embedder.embedder_config import EMBEDDER_CONFIG

import logging
logger = logging.getLogger(__name__)


class Embedder:
    """
    Handles all embedding operations for ClinicalBridge.

    Responsibilities:
    - Load patient JSON files (EHR and Anamnesis)
    - Chunk them dynamically regardless of structure
    - Embed chunks into vectors using SentenceTransformer
    - Build FAISS index for similarity search
    - Search FAISS index given a query string

    Used by:
    - VectorStore  → to build and persist patient indexes
    - EHR Agent    → search(top_k=5)
    - Anamnesis Agent → search(top_k=20)
    """

    # ─────────────────────────────────────────────────────────────────────────
    # MODEL CACHE
    # Load once, reuse forever within the same process
    # ─────────────────────────────────────────────────────────────────────────

    _model = None

    @staticmethod
    def _get_model():
        """
        Loads SentenceTransformer model once and caches it.
        Subsequent calls return the cached model instantly.

        IN  : nothing
        OUT : SentenceTransformer model instance
        """
        if Embedder._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                logger.critical("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise

            model_name = EMBEDDER_CONFIG["MODEL_NAME"]
            cache_dir = EMBEDDER_CONFIG["MODEL_CACHE_DIR"]

            logger.info(f"Loading SentenceTransformer model: {model_name}")
            Embedder._model = SentenceTransformer(model_name, cache_folder=cache_dir)
            logger.info("Model loaded and cached")

        return Embedder._model

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC — EMBED
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def embed_patient_file(file_path: str) -> Tuple[Any, List[Dict]]:
        """
        Master embedding function.
        Reads any patient JSON file → chunks it → embeds → returns FAISS index.

        Handles any JSON structure dynamically:
        - Missing fields     → skipped automatically
        - Empty lists        → skipped automatically
        - Extra/new fields   → handled automatically
        - Nested structures  → recursed into automatically

        Works for BOTH ehr.json AND anamnesis.json.

        IN:
            file_path (str) → full path to patient JSON file
                              e.g. "data/patients/P001/information/ehr.json"

        OUT:
            (faiss_index, chunk_map) on success
            (None, None)             on failure

            faiss_index → FAISS IndexFlatIP object, ready to search
            chunk_map   → List[Dict], each dict:
                          {
                            "index":  int,   position in FAISS index
                            "type":   str,   field name e.g. "conditions"
                            "text":   str,   the searchable text
                            "source": str,   path in JSON e.g. "conditions[0]"
                          }
        """
        # ── CHECK CACHE FIRST ────────────────────────────────────
        if Embedder._is_cached(file_path):
            logger.info(f"Cache hit — loading from disk: {file_path}")
            return Embedder._load_from_disk(file_path)

        try:
            import faiss
        except ImportError:
            logger.critical("faiss-cpu not installed. Run: pip install faiss-cpu")
            return None, None

        # ── 1. Load JSON file ────────────────────────────────────────────────
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return None, None
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {file_path}: {e}")
            return None, None
        except Exception as e:
            logger.error(f"Unexpected error reading {file_path}: {e}")
            return None, None

        # ── 2. Chunk dynamically ─────────────────────────────────────────────
        chunks = Embedder._chunk_dynamic(data)

        if not chunks:
            logger.warning(f"No chunks generated from {file_path}. File may be empty.")
            return None, None

        logger.info(f"Generated {len(chunks)} chunks from {file_path}")

        # ── 3. Load model ────────────────────────────────────────────────────
        try:
            model = Embedder._get_model()
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            return None, None

        # ── 4. Embed each chunk ──────────────────────────────────────────────
        start_time = time.time()
        embeddings_list = []
        faiss_map = []

        for idx, chunk in enumerate(chunks):
            try:
                vector = model.encode([chunk["text"]])[0]
                embeddings_list.append(vector)
                faiss_map.append({
                    "index": idx,
                    "type": chunk["type"],
                    "text": chunk["text"],
                    "source": chunk["source"],
                })
            except Exception as e:
                logger.error(f"Failed to embed chunk {idx} (source={chunk.get('source')}): {e}")
                continue

        if not embeddings_list:
            logger.error(f"All chunks failed to embed for {file_path}")
            return None, None

        # ── 5. Build FAISS index ─────────────────────────────────────────────
        try:
            embeddings_array = np.array(embeddings_list).astype("float32")
            dimension = embeddings_array.shape[1]
            index = faiss.IndexFlatIP(dimension)
            index.add(embeddings_array)
        except Exception as e:
            logger.error(f"Failed to build FAISS index: {e}")
            return None, None

        elapsed = (time.time() - start_time) * 1000
        logger.info(f"Embedding complete. {len(faiss_map)} chunks indexed in {elapsed:.2f}ms")

        # ── SAVE TO DISK BEFORE RETURNING ────────────────────────
        Embedder._save_to_disk(file_path, index, faiss_map)

        return index, faiss_map

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC — SEARCH
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def search(index: Any, chunk_map: List[Dict], query: str, top_k: int = 5) -> List[Dict]:
        """
        Searches a FAISS index for chunks most similar to the query.

        Dynamic — same function used by both agents:
            EHR Agent       → top_k=5  (large file, return only most relevant)
            Anamnesis Agent → top_k=20 (small file, return most or all)

        Automatically caps top_k to available chunks so it never crashes
        if the file has fewer chunks than requested.

        IN:
            index     (Any)       → FAISS index from embed_patient_file()
            chunk_map (List[Dict])→ chunk map from embed_patient_file()
            query     (str)       → search string, comes from triage agent output
                                    e.g. "hypertension history and medications"
            top_k     (int)       → how many results to return (default 5)

        OUT:
            List[Dict] → matched chunks sorted best first, each dict:
                         {
                           "index":  int,   FAISS position
                           "type":   str,   field type e.g. "conditions"
                           "text":   str,   the matched text
                           "source": str,   JSON path e.g. "conditions[0]"
                           "score":  float, similarity score (higher = better)
                           "rank":   int,   1 = best match
                         }
            []         → empty list on failure or no results
        """
        # ── Guards ───────────────────────────────────────────────────────────
        if index is None or not chunk_map:
            logger.warning("search() called with empty index or chunk_map")
            return []

        if not isinstance(query, str) or not query.strip():
            logger.warning("search() called with empty query string")
            return []

        # Cap top_k to what we actually have
        top_k = min(top_k, len(chunk_map))

        # ── Search ───────────────────────────────────────────────────────────
        try:
            model = Embedder._get_model()

            # Embed the query
            query_vector = model.encode([query.strip()])[0]
            query_vector = np.array([query_vector]).astype("float32")

            # Search FAISS
            distances, indices = index.search(query_vector, top_k)

            # Build results
            results = []
            for rank, (dist, idx) in enumerate(zip(distances[0], indices[0])):
                if idx < 0 or idx >= len(chunk_map):
                    continue

                chunk = chunk_map[idx].copy()
                chunk["score"] = float(dist)
                chunk["rank"] = rank + 1
                results.append(chunk)

            logger.info(
                f"Search complete. "
                f"query='{query[:60]}' "
                f"top_k={top_k} "
                f"hits={len(results)}"
            )
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # PRIVATE — DYNAMIC CHUNKER
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _chunk_dynamic(data: Dict) -> List[Dict]:
        """
        Entry point for chunking.
        Walks any JSON dict and returns a flat list of text chunks.

        IN:
            data (Dict) → loaded patient JSON (any structure)

        OUT:
            List[Dict] → list of chunks, each:
                         {"type": str, "text": str, "source": str}
        """
        chunks = []
        Embedder._walk(obj=data, parent_key="", chunks=chunks)

        logger.info(f"Chunking complete. {len(chunks)} chunks generated")

        return chunks

    @staticmethod
    def _walk(obj: Any, parent_key: str, chunks: List[Dict]) -> None:
        """
        Recursive walker. Handles every JSON type.

        Rules:
            None        → skip
            str         → one chunk (if not empty)
            int/float   → one chunk
            bool        → one chunk
            list        → one chunk per item (skip empty lists)
            dict        → recurse into each key (skip metadata keys)

        IN:
            obj        (Any)       → current value being walked
            parent_key (str)       → dot-path of current position
                                     e.g. "conditions", "visit_notes.note"
            chunks     (List[Dict])→ accumulator, appended in place

        OUT:
            None → chunks list modified in place
        """

        # None → skip
        if obj is None:
            return

        # String → one chunk if not empty
        if isinstance(obj, str):
            if obj.strip():
                chunks.append({
                    "type": parent_key or "field",
                    "text": f"{parent_key}: {obj}".strip(),
                    "source": parent_key,
                })
            return

        # Number or bool → one chunk
        if isinstance(obj, (int, float, bool)):
            chunks.append({
                "type": parent_key or "field",
                "text": f"{parent_key}: {obj}".strip(),
                "source": parent_key,
            })
            return

        # List → one chunk per item, skip if empty
        if isinstance(obj, list):
            if not obj:
                return

            for i, item in enumerate(obj):
                source = f"{parent_key}[{i}]"

                if isinstance(item, dict):
                    # Flatten dict to readable text
                    text = Embedder._flatten_dict(item)
                    if text.strip():
                        chunks.append({
                            "type": parent_key,
                            "text": text,
                            "source": source,
                        })
                elif isinstance(item, str) and item.strip():
                    chunks.append({
                        "type": parent_key,
                        "text": f"{parent_key}: {item}",
                        "source": source,
                    })
                else:
                    # Nested list or primitive → recurse
                    Embedder._walk(item, source, chunks)
            return

        # Dict → recurse into each key
        if isinstance(obj, dict):
            # Skip fields that add no clinical search value
            skip_keys = {
                "patient_id", "recorded_at", "id",
                "created_at", "updated_at"
            }

            for key, value in obj.items():
                if key in skip_keys:
                    continue

                full_key = f"{parent_key}.{key}" if parent_key else key
                Embedder._walk(value, full_key, chunks)

    @staticmethod
    def _flatten_dict(d: Dict) -> str:
        """
        Converts a dict into a single readable string.
        Used when a list item is a dict (e.g. one medication, one visit note).

        IN:
            d (Dict) → any flat or nested dict

        OUT:
            str → "key: value | key: value | ..."
                  e.g. "name: Lisinopril | dose: 10mg | frequency: daily"
                  Returns "" if dict is empty or all values are None
        """
        parts = []
        for k, v in d.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                # Nested value — serialize to JSON string
                parts.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
            else:
                parts.append(f"{k}: {v}")

        return " | ".join(parts)

    @staticmethod
    def _save_to_disk(file_path: str, index: Any, chunk_map: List[Dict]) -> None:
        """
        Saves FAISS index and chunk map next to the source file.
        Creates embeddings/ folder if it does not exist.

        IN:
            file_path  → original JSON path
                         e.g. "data/patients/P001/information/ehr.json"
            index      → FAISS index to save
            chunk_map  → chunk map list to save

        OUT:
            None → files written to disk

        Creates:
            data/patients/P001/embeddings/ehr_index.faiss
            data/patients/P001/embeddings/ehr_map.json
            data/patients/P001/embeddings/ehr_checksum.json
        """
        try:
            import faiss
            import hashlib
            import os
            from datetime import datetime

            # ── 1. Build paths ───────────────────────────────────────────────────
            # Go one level up from information/ → patient folder
            # Then into embeddings/
            # file_path = "data/patients/P001/information/ehr.json"
            # parent    = "data/patients/P001/information"
            # base_name = "ehr"  ← from "ehr.json"

            parent = os.path.dirname(file_path)  # .../information
            patient_dir = os.path.dirname(parent)  # .../P001
            embeddings_dir = os.path.join(patient_dir, "embeddings")
            base_name = os.path.splitext(os.path.basename(file_path))[0]  # "ehr"

            # Create embeddings/ folder if not exists
            os.makedirs(embeddings_dir, exist_ok=True)

            index_path = os.path.join(embeddings_dir, f"{base_name}_index.faiss")
            map_path = os.path.join(embeddings_dir, f"{base_name}_map.json")
            checksum_path = os.path.join(embeddings_dir, f"{base_name}_checksum.json")

            # ── 2. Save FAISS index ──────────────────────────────────────────────
            faiss.write_index(index, index_path)

            # ── 3. Save chunk map ────────────────────────────────────────────────
            with open(map_path, "w", encoding="utf-8") as f:
                json.dump(chunk_map, f, indent=2, ensure_ascii=False)

            # ── 4. Save checksum ─────────────────────────────────────────────────
            with open(file_path, "rb") as f:
                checksum = hashlib.md5(f.read()).hexdigest()

            with open(checksum_path, "w", encoding="utf-8") as f:
                json.dump({
                    "checksum": checksum,
                    "source_file": file_path,
                    "total_chunks": len(chunk_map),
                    "embedded_at": datetime.utcnow().isoformat(),
                }, f, indent=2)

            logger.info(f"Saved embeddings to {embeddings_dir}")

        except Exception as e:
            logger.error(f"Failed to save embeddings to disk: {e}")

    @staticmethod
    def _is_cached(file_path: str) -> bool:
        """
        Checks if valid embeddings already exist on disk for this file.
        Compares checksum of current file vs saved checksum.

        IN:
            file_path → original JSON path

        OUT:
            True  → embeddings exist and file has not changed → skip rebuild
            False → embeddings missing or file changed → rebuild needed
        """
        try:
            import hashlib
            import os

            parent = os.path.dirname(file_path)
            patient_dir = os.path.dirname(parent)
            embeddings_dir = os.path.join(patient_dir, "embeddings")
            base_name = os.path.splitext(os.path.basename(file_path))[0]

            index_path = os.path.join(embeddings_dir, f"{base_name}_index.faiss")
            map_path = os.path.join(embeddings_dir, f"{base_name}_map.json")
            checksum_path = os.path.join(embeddings_dir, f"{base_name}_checksum.json")

            # All 3 files must exist
            if not all(os.path.exists(p) for p in [index_path, map_path, checksum_path]):
                return False

            # Compute current file checksum
            with open(file_path, "rb") as f:
                current_checksum = hashlib.md5(f.read()).hexdigest()

            # Compare with saved checksum
            with open(checksum_path, "r") as f:
                saved = json.load(f)

            return saved.get("checksum") == current_checksum

        except Exception as e:
            logger.warning(f"Cache check failed: {e}")
            return False

    @staticmethod
    def _load_from_disk(file_path: str) -> Tuple[Any, List[Dict]]:
        """
        Loads FAISS index and chunk map from disk.
        Called only when _is_cached() returns True.

        IN:
            file_path → original JSON path

        OUT:
            (faiss_index, chunk_map) → loaded from disk
            (None, None)             → on failure
        """
        try:
            import faiss
            import os

            parent = os.path.dirname(file_path)
            patient_dir = os.path.dirname(parent)
            embeddings_dir = os.path.join(patient_dir, "embeddings")
            base_name = os.path.splitext(os.path.basename(file_path))[0]

            index_path = os.path.join(embeddings_dir, f"{base_name}_index.faiss")
            map_path = os.path.join(embeddings_dir, f"{base_name}_map.json")

            index = faiss.read_index(index_path)

            with open(map_path, "r", encoding="utf-8") as f:
                chunk_map = json.load(f)

            logger.info(f"Loaded embeddings from disk for {file_path}")
            return index, chunk_map

        except Exception as e:
            logger.error(f"Failed to load embeddings from disk: {e}")
            return None, None