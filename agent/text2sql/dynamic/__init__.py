"""
动态 SQL 生成模块
用于处理动态数据源场景，将 SQL 查询中的表名替换为对应的子查询
"""

from agent.text2sql.dynamic.generator import dynamic_sql_generator

__all__ = ["dynamic_sql_generator"]
