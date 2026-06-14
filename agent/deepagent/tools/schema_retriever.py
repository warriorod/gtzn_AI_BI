"""
DeepAgent 专用 BM25 表检索模块

独立实现，不依赖 text2sql 任何模块（遵循各 Agent 系统相互独立原则）。
提供基于 BM25 的表元数据检索，将用户问题映射到相关表名列表。
"""

import logging
import os
import re
from typing import Dict, List

import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# 预热 jieba，避免首次调用时约 0.5-1 秒的词典加载延迟
jieba.initialize()

DEFAULT_TOP_K = int(os.getenv("DEEP_AGENT_BM25_TOP_K", "20"))


def tokenize_text(text_str: str) -> List[str]:
    """中英文分词，过滤标点符号。"""
    filtered = re.sub(r"[^一-龥a-zA-Z0-9]", " ", text_str)
    return [t.strip() for t in jieba.lcut(filtered, cut_all=False) if t.strip()]


def build_document(table_name: str, table_info: dict) -> str:
    """
    构建检索文档：表名 + 表注释 + 字段名 + 字段注释拼接为一段文本。

    table_info 格式与 _get_table_info_from_metadata() 返回一致：
    {
      "columns": {"col": {"type": "...", "comment": "..."}},
      "table_comment": "...",
      "foreign_keys": []
    }
    """
    parts = [table_name]
    if table_info.get("table_comment"):
        parts.append(table_info["table_comment"])
    for col_name, col_info in table_info.get("columns", {}).items():
        parts.append(col_name)
        if col_info.get("comment"):
            parts.append(col_info["comment"])
    return " ".join(parts)


def bm25_retrieve_tables(
    table_info: Dict[str, dict],
    user_query: str,
    top_k: int = DEFAULT_TOP_K,
) -> List[str]:
    """
    使用 BM25 从 table_info 中检索与 user_query 最相关的 Top-K 表名。

    含表注释增强：查询词命中表注释时，额外叠加 1.5 倍分数加成。

    Args:
        table_info: _get_table_info_from_metadata() 返回的全量表信息
        user_query: 用户原始问题文本
        top_k: 返回前 K 个结果

    Returns:
        按相关性排序的表名列表（长度 <= top_k）。
        BM25 全零分时降级返回全量前 top_k 个。
    """
    if not table_info:
        return []
    if not user_query or not user_query.strip():
        return list(table_info.keys())[:top_k]

    table_names = list(table_info.keys())
    corpus = [build_document(name, table_info[name]) for name in table_names]
    tokenized_corpus = [tokenize_text(doc) for doc in corpus]
    query_tokens = tokenize_text(user_query)

    logger.info("🔍 用户查询: %s", user_query)
    logger.info("🔑 查询分词: %s", query_tokens)
    if not query_tokens:
        logger.warning("⚠️ 分词为空，降级返回全量前 %d 张表", top_k)
        return table_names[:top_k]

    bm25 = BM25Okapi(tokenized_corpus)
    doc_scores = bm25.get_scores(query_tokens)

    # 表注释增强：查询词与表注释有交集时，提升该表得分
    enhanced_scores = doc_scores.copy()
    for i, name in enumerate(table_names):
        if enhanced_scores[i] <= 0:
            continue
        comment_tokens = tokenize_text(table_info[name].get("table_comment", ""))
        overlap = set(query_tokens) & set(comment_tokens)
        if overlap:
            overlap_ratio = len(overlap) / max(len(set(query_tokens)), 1)
            enhanced_scores[i] += doc_scores[i] * overlap_ratio * 1.5

    scored = sorted(enumerate(enhanced_scores), key=lambda x: x[1], reverse=True)

    # 全零分时降级
    if scored[0][1] <= 0:
        logger.warning("⚠️ BM25 全零分，降级返回全量前 %d 张表", top_k)
        return table_names[:top_k]

    result = [table_names[idx] for idx, score in scored if score > 0][:top_k]

    logger.info("📊 BM25 检索结果（共 %d 张表，Top-%d）:", len(table_names), len(result))
    for rank, (idx, score) in enumerate(scored[: len(result)], 1):
        raw = doc_scores[idx]
        boost = score - raw
        boost_str = f" +{boost:.3f}" if boost > 0 else ""
        logger.info("  %2d. %-30s | BM25: %.4f%s", rank, table_names[idx], score, boost_str)

    return result


def format_schema_text(table_names: List[str], table_info: Dict[str, dict]) -> str:
    """
    将指定表名的 schema 格式化为与 sql_db_schema 工具相同格式的文本。
    供 sql_db_smart_search 工具一次性返回。
    """
    schema_parts = []
    for table_name in table_names:
        if table_name not in table_info:
            continue
        info = table_info[table_name]
        columns = info.get("columns", {})
        table_comment = info.get("table_comment", "")

        schema_text = f"\n表 '{table_name}':"
        if table_comment:
            schema_text += f"\n注释: {table_comment}"
        schema_text += "\n列:"
        for col_name, col_info in columns.items():
            col_type = col_info.get("type", "")
            col_comment = col_info.get("comment", "")
            schema_text += f"\n  - {col_name} ({col_type})"
            if col_comment:
                schema_text += f" - {col_comment}"

        schema_parts.append(schema_text)

    return "\n".join(schema_parts) if schema_parts else "未找到相关表信息"
