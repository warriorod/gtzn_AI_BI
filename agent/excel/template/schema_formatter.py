"""
表格问答 Schema 格式化工具
将表格问答的 db_info 列表格式转换为 M-Schema 字符串格式
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def format_excel_schema_to_m_schema(
    db_info: List[Dict[str, Any]],
) -> str:
    """
    将 Excel 的 db_info 列表格式转换为 M-Schema 字符串格式
    
    Args:
        db_info: Excel 数据库信息列表，格式为：
            [
                {
                    "table_name": "table_name",
                    "catalog_name": "catalog_name",
                    "columns": {
                        "column_name": {
                            "type": "VARCHAR(255)",
                            "comment": "列注释"
                        }
                    },
                    "table_comment": "表注释",
                    "foreign_keys": []
                }
            ]
    
    Returns:
        M-Schema 格式的字符串
    """
    if not db_info:
        return ""
    
    schema_str = "【DB_ID】 Excel_Files\n【Schema】\n"
    
    for table_info in db_info:
        # 获取表名和catalog名
        table_name = table_info.get("table_name", "")
        catalog_name = table_info.get("catalog_name", "")
        
        # 构建表定义行（使用 catalog.table 格式）
        if catalog_name:
            schema_table = f"# Table: {catalog_name}.{table_name}"
        else:
            schema_table = f"# Table: {table_name}"
        
        # 添加表注释
        table_comment = table_info.get("table_comment", "").strip()
        if table_comment:
            schema_table += f", {table_comment}"
        
        schema_table += "\n[\n"
        
        # 添加字段定义
        columns = table_info.get("columns", {})
        if columns:
            field_list = []
            for column_name, column_info in columns.items():
                column_type = column_info.get("type", "VARCHAR")
                column_comment = column_info.get("comment", "").strip()
                
                if column_comment:
                    field_list.append(f"({column_name}:{column_type}, {column_comment})")
                else:
                    field_list.append(f"({column_name}:{column_type})")
            
            schema_table += ",\n".join(field_list)
        
        schema_table += "\n]\n"

        # 添加表级外键关系
        foreign_keys = table_info.get("foreign_keys") or []
        if foreign_keys:
            for fk in foreign_keys:
                schema_table += f"{fk}\n"

        schema_str += schema_table
    
    return schema_str


def get_excel_engine_info() -> str:
    """
    获取 Excel/DuckDB 引擎信息字符串
    
    Returns:
        引擎信息字符串，格式如 "DuckDB 0.9.0"
    """
    return "DuckDB 0.9.0"

