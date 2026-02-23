import math
import os
from typing import Dict, List
from src.services import secret_service

from openai import OpenAI
from pinecone import Pinecone

INDEX_NAME = "my-first-index"
NAMESPACE = "kb"
EMBED_MODEL = os.environ.get("OPENAI_EMBED_MODEL", "text-embedding-3-large")
STRONG_THRESHOLD = float(os.environ.get("STRONG_THRESHOLD", "0.42"))
VOTE_THRESHOLD = float(os.environ.get("VOTE_THRESHOLD", "2.0"))
COVERAGE_THRESHOLD = int(os.environ.get("COVERAGE_THRESHOLD", "2"))
DROP_THRESHOLD = float(os.environ.get("DROP_THRESHOLD", "0.23"))

pc = Pinecone(api_key=secret_service.get_secret("PINECONE_API_KEY"))
index = pc.Index(INDEX_NAME)
openai_client = OpenAI(api_key=secret_service.get_secret("OPENAI_API_KEY"))

def _embed_text(text: str):
    response = openai_client.embeddings.create(model=EMBED_MODEL, input=text)
    embedding = response.data[0].embedding
    return embedding


def _compute_file_stats(matches: List[Dict]) -> List[Dict]:
    if not matches:
        return []

    scores = [m.get("score", 0.0) for m in matches]
    mean = sum(scores) / len(scores)
    variance = sum((score - mean) ** 2 for score in scores) / len(scores)
    std = math.sqrt(variance)
    if std == 0:
        std = 1e-6

    file_stats: Dict[str, Dict] = {}
    for match in matches:
        score = match.get("score", 0.0)
        if score < DROP_THRESHOLD:
            continue
        metadata = match.get("metadata", {}) or {}
        filename = metadata.get("filename")
        if not filename:
            continue

        vote = math.exp((score - mean) / std)
        stats = file_stats.setdefault(
            filename,
            {
                "filename": filename,
                "title": metadata.get("title"),
                "max_score": score,
                "vote_sum": 0.0,
                "coverage": 0,
            },
        )
        stats["max_score"] = max(stats["max_score"], score)
        stats["vote_sum"] += vote
        stats["coverage"] += 1

    return file_stats


def select_top_files(matches: List[Dict]) -> List[Dict]:
    file_stats = _compute_file_stats(matches)
    filtered_stats = {
        fn: stats
        for fn, stats in file_stats.items()
        if stats["max_score"] >= STRONG_THRESHOLD 
            or (stats["vote_sum"] >= VOTE_THRESHOLD and stats["coverage"] >= 2)
    }
    sorted_stats = sorted(
        filtered_stats.values(),
        key=lambda s: (s["max_score"], s["vote_sum"]),
        reverse=True,
    )
    return sorted_stats


def select_relevant_files(question, top_k=5):
    vector = _embed_text(question)
    res = index.query(vector=vector, top_k=top_k, include_metadata=True, namespace=NAMESPACE)
    matches = res["matches"]
    response_lines = [
        f"QUESTION: {question}",
        f"Matches: {len(matches)}",
    ]
    for match in matches:
        metadata = match.get("metadata", {})
        response_lines.append(
            f"- score={match['score']:.3f} title={metadata.get('title')} chunk={metadata.get('chunk_index')} "
            f"filename={metadata.get('filename')}"
        )
        chunk_text = (metadata.get("text") or "").replace("\n", " ").replace("\r", " ").strip()
        response_lines.append(chunk_text)

    print(" | ".join(response_lines))

    selected = select_top_files(matches)

    response_lines = ["Selected files:"]
    if selected:
        for stats in selected:
            response_lines.append(
                f"- {stats['filename']} (max_score={stats['max_score']:.3f}, "
                f"vote_sum={stats['vote_sum']:.3f}, coverage={stats['coverage']})"
            )
    else:
        response_lines.append("- none (below thresholds)")

    print(" | ".join(response_lines))

    return selected
