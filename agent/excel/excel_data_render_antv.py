"""
表格问答数据渲染节点 - AntV 格式
根据当前项目前后端协议,返回格式化后的数据
和数据问答的 data_render_antv 保持一致
"""
import json
import logging
import traceback
from typing import Dict, Any, List, Optional

import sqlglot
from sqlglot import parse

from agent.common.json_value import convert_value_for_json
from agent.excel.excel_agent_state import ExcelAgentState, ExecutionResult

logger = logging.getLogger(__name__)

# Excel 使用 DuckDB，映射到 PostgreSQL 方言
DB_TYPE = "postgres"


def convert_value(v):
    """转换数据类型"""
    return convert_value_for_json(v)


def extract_table_names_sqlglot(sql: str) -> List[str]:
    """
    使用 sqlglot 提取 SQL 中的所有表名
    
    Args:
        sql: SQL 语句
    """
    try:
        expression = parse(sql, read=DB_TYPE)[0]
        tables = set()
        for table in expression.find_all(sqlglot.exp.Table):
            tables.add(table.name)
        return list(tables)
    except Exception as e:
        logger.warning(f"SQL 解析错误: {e}")
        return []


def extract_table_alias_mapping(sql: str) -> Dict[str, str]:
    """
    提取SQL中的表别名映射关系
    
    Args:
        sql: SQL语句
    
    Returns:
        别名到真实表名的映射字典 {alias: table_name}
    """
    alias_mapping = {}
    try:
        expressions = parse(sql, read=DB_TYPE)
        
        for expression in expressions:
            if expression:
                for table_exp in expression.find_all(sqlglot.exp.Table):
                    if hasattr(table_exp, "alias") and table_exp.alias:
                        alias_mapping[table_exp.alias] = table_exp.name
                
                for from_exp in expression.find_all(sqlglot.exp.From):
                    if hasattr(from_exp, "expressions"):
                        for expr in from_exp.expressions:
                            if isinstance(expr, sqlglot.exp.Alias) and hasattr(expr.this, "name"):
                                alias_mapping[expr.alias] = expr.this.name
                            elif hasattr(expr, "name") and hasattr(expr, "alias") and expr.alias:
                                alias_mapping[expr.alias] = expr.name
                
                for join_exp in expression.find_all(sqlglot.exp.Join):
                    if hasattr(join_exp, "this"):
                        join_table = join_exp.this
                        if isinstance(join_table, sqlglot.exp.Alias) and hasattr(join_table.this, "name"):
                            alias_mapping[join_table.alias] = join_table.this.name
                        elif hasattr(join_table, "name") and hasattr(join_table, "alias") and join_table.alias:
                            alias_mapping[join_table.alias] = join_table.name
    except Exception as e:
        logger.warning(f"提取表别名映射失败: {e}")
    
    return alias_mapping


def extract_select_columns(sql: str, table_alias_mapping: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """
    从 SQL 中提取 SELECT 列的详细信息
    返回格式: [{"name": "column_name", "alias": "alias_name", "table": "table_name", "is_aggregate": False}, ...]
    """
    try:
        expressions = parse(sql, read=DB_TYPE)
        column_info_list = []

        for expression in expressions:
            if not expression:
                continue

            selects = expression.find_all(sqlglot.exp.Select)
            for select in selects:
                projections = select.expressions
                for proj in projections:
                    col_info = {
                        "name": "",
                        "alias": "",
                        "table": "",
                        "is_aggregate": False,
                    }

                    if isinstance(proj, (sqlglot.exp.AggFunc, sqlglot.exp.Sum, sqlglot.exp.Count, sqlglot.exp.Avg, sqlglot.exp.Max, sqlglot.exp.Min)):
                        col_info["is_aggregate"] = True
                        col_info["name"] = str(proj)
                    elif isinstance(proj, sqlglot.exp.Column):
                        col_info["name"] = proj.name
                        table_ref = proj.table or ""
                        if table_ref and table_alias_mapping:
                            col_info["table"] = table_alias_mapping.get(table_ref, table_ref)
                        else:
                            col_info["table"] = table_ref
                    elif isinstance(proj, sqlglot.exp.Star):
                        col_info["name"] = "*"
                    else:
                        col_info["name"] = str(proj)

                    def clean_alias(alias_str: str) -> str:
                        if not alias_str:
                            return alias_str
                        alias_str = alias_str.strip()
                        if alias_str.startswith('`') and alias_str.endswith('`'):
                            alias_str = alias_str[1:-1]
                        if alias_str.startswith('"') and alias_str.endswith('"'):
                            alias_str = alias_str[1:-1]
                        if alias_str.startswith('[') and alias_str.endswith(']'):
                            alias_str = alias_str[1:-1]
                        return alias_str.strip()
                    
                    if isinstance(proj, sqlglot.exp.Alias):
                        col_info["alias"] = clean_alias(proj.alias)
                        if hasattr(proj, "this"):
                            if isinstance(proj.this, (sqlglot.exp.AggFunc, sqlglot.exp.Sum, sqlglot.exp.Count, sqlglot.exp.Avg, sqlglot.exp.Max, sqlglot.exp.Min)):
                                col_info["is_aggregate"] = True
                                if isinstance(proj.this, sqlglot.exp.Column):
                                    col_info["name"] = proj.this.name
                                    table_ref = proj.this.table or ""
                                    if table_ref and table_alias_mapping:
                                        col_info["table"] = table_alias_mapping.get(table_ref, table_ref)
                                    else:
                                        col_info["table"] = table_ref
                    elif hasattr(proj, "alias") and proj.alias:
                        col_info["alias"] = clean_alias(proj.alias)

                    column_info_list.append(col_info)

        return column_info_list
    except Exception as e:
        logger.warning(f"提取 SELECT 列信息失败: {e}")
        return []


def get_column_comment_from_schema(db_info: List[Dict[str, Any]], table_name: str, column_name: str) -> str:
    """
    从 db_info 中获取字段注释（支持大小写不敏感匹配）
    db_info 是列表格式，每个元素包含 table_name, catalog_name, columns 等信息
    """
    try:
        # db_info 是列表格式，需要查找匹配的表
        for table_info in db_info:
            # 表名可能是 catalog.table 格式，需要匹配
            full_table_name = table_info.get("table_name", "")
            catalog_name = table_info.get("catalog_name", "")
            
            # 检查是否匹配表名（支持多种匹配方式）
            # 1. 直接匹配 table_name
            # 2. 匹配 catalog.table_name
            # 3. 匹配 SQL 中可能使用的表名（去掉 catalog 前缀）
            table_name_to_match = table_name
            if "." in table_name:
                # 如果 table_name 包含点，可能是 catalog.table 格式
                parts = table_name.split(".", 1)
                if len(parts) == 2:
                    table_name_to_match = parts[1]  # 只取表名部分
            
            if (table_name_to_match == full_table_name or 
                table_name == full_table_name or
                (catalog_name and table_name == f"{catalog_name}.{full_table_name}")):
                columns = table_info.get("columns", {})
                if not columns:
                    continue

                # 先尝试精确匹配
                col_info = columns.get(column_name, {})
                if col_info:
                    if isinstance(col_info, dict):
                        comment = col_info.get("comment", "")
                        if comment and comment != "None" and comment.strip():
                            return comment
                
                # 如果精确匹配失败，尝试大小写不敏感匹配
                column_name_lower = column_name.lower()
                for col_key, col_val in columns.items():
                    if col_key.lower() == column_name_lower:
                        if isinstance(col_val, dict):
                            comment = col_val.get("comment", "")
                            if comment and comment != "None" and comment.strip():
                                return comment
        
        return ""
    except Exception as e:
        logger.warning(f"获取字段注释失败: {e}", exc_info=True)
        return ""


def map_columns_to_comments(
    sql: str, db_info: List[Dict[str, Any]], actual_columns: List[str], 
    chart_config: Optional[Dict[str, Any]] = None
) -> tuple:
    """
    将 SQL 查询结果的列名映射为中文注释
    
    映射优先级（从高到低）：
    1. chart_config中的name字段
    2. 数据库字段注释（COMMENT）
    3. SQL中的中文别名
    4. 原列名
    
    Args:
        sql: SQL 语句
        db_info: 数据库信息（列表格式）
        actual_columns: 实际列名列表
        chart_config: 图表配置（可选）
    
    Returns:
        (column_names_chinese, column_mapping)
    """
    try:
        # 提取表别名映射
        table_alias_mapping = extract_table_alias_mapping(sql)
        
        # 提取 SELECT 列的详细信息
        column_info_list = extract_select_columns(sql, table_alias_mapping)
        
        # 获取表名
        table_names = extract_table_names_sqlglot(sql)
        
        # 从chart_config中提取映射（包括columns和axis）
        chart_config_mapping = {}
        if chart_config and isinstance(chart_config, dict):
            # 处理columns字段（表格类型）
            columns = chart_config.get("columns", [])
            if isinstance(columns, list):
                for col in columns:
                    if isinstance(col, dict):
                        value = col.get("value", "").strip().lower()
                        name = col.get("name", "").strip()
                        if value and name:
                            chart_config_mapping[value] = name
            
            # 处理axis字段（图表类型：x、y、series）
            axis = chart_config.get("axis", {})
            if isinstance(axis, dict):
                for axis_key in ["x", "y", "series"]:
                    axis_item = axis.get(axis_key)
                    if isinstance(axis_item, dict):
                        value = axis_item.get("value", "").strip().lower()
                        name = axis_item.get("name", "").strip()
                        if value and name:
                            chart_config_mapping[value] = name
                            logger.debug(f"从chart_config提取axis映射: {axis_key}.{value} -> {name}")
        
        column_mapping = {}
        column_names_chinese = []

        # 检查是否有 SELECT *
        has_select_all = any(info.get("name") == "*" for info in column_info_list)

        if has_select_all:
            # SELECT * 的情况,使用第一个表的 schema
            if table_names and db_info:
                target_table = table_names[0]
                for table_info in db_info:
                    if table_info.get("table_name") == target_table or target_table in table_info.get("table_name", ""):
                        columns = table_info.get("columns", {})
                        for col_name in actual_columns:
                            comment = get_column_comment_from_schema(db_info, target_table, col_name)
                            chinese_name = comment if comment else col_name
                            column_mapping[col_name] = chinese_name
                            column_names_chinese.append(chinese_name)
                        break
        else:
            # 正常 SELECT 的情况
            if not column_info_list:
                for col_name in actual_columns:
                    column_mapping[col_name] = col_name
                    column_names_chinese.append(col_name)
            else:
                for i, col_info in enumerate(column_info_list):
                    if i >= len(actual_columns):
                        break

                    actual_col_name = actual_columns[i]
                    col_name = col_info.get("name", "")
                    alias = col_info.get("alias", "")
                    table_name = col_info.get("table", "")
                    is_aggregate = col_info.get("is_aggregate", False)

                    if is_aggregate:
                        # 聚合函数，优先使用chart_config中的name
                        chinese_name = chart_config_mapping.get(actual_col_name.lower()) or chart_config_mapping.get(alias.lower() if alias else "")
                        if not chinese_name and alias:
                            if any('\u4e00' <= char <= '\u9fff' for char in alias):
                                chinese_name = alias
                        if not chinese_name:
                            chinese_name = actual_col_name
                    else:
                        # 普通列，优先使用表的COMMENT
                        comment = ""
                        if table_name:
                            comment = get_column_comment_from_schema(db_info, table_name, col_name)
                        if not comment and col_name:
                            for tbl_name in table_names:
                                comment = get_column_comment_from_schema(db_info, tbl_name, col_name)
                                if comment:
                                    break
                        
                        # 按照优先级确定中文名称
                        chinese_name = chart_config_mapping.get(actual_col_name.lower()) or chart_config_mapping.get(alias.lower() if alias else "")
                        if not chinese_name and comment:
                            chinese_name = comment
                        if not chinese_name and alias and alias != actual_col_name and alias != col_name:
                            if any('\u4e00' <= char <= '\u9fff' for char in alias):
                                chinese_name = alias
                        if not chinese_name:
                            chinese_name = actual_col_name

                    column_mapping[actual_col_name] = chinese_name
                    column_names_chinese.append(chinese_name)

        return column_names_chinese, column_mapping
    except Exception as e:
        logger.error(f"映射列名为中文注释失败: {e}", exc_info=True)
        column_mapping = {col: col for col in actual_columns}
        return actual_columns, column_mapping


def excel_data_render_antv(state: ExcelAgentState):
    """
    数据渲染节点 - 按照当前项目前后端协议返回格式化数据
    和数据问答的 data_render_antv 保持一致
    """
    logger.info("---进入表格问答数据渲染节点---")

    try:
        # 获取执行结果
        execution_result: Optional[ExecutionResult] = state.get("execution_result")
        if not execution_result or not execution_result.success or not execution_result.data:
            logger.warning("SQL 执行结果为空或失败,跳过数据渲染")
            return state

        data: List[Dict[str, Any]] = execution_result.data
        if not data:
            logger.warning("数据为空,跳过数据渲染")
            return state

        # 获取数据库信息和 SQL
        db_info = state.get("db_info", [])
        generated_sql = state.get("generated_sql", "") or state.get("filtered_sql", "")
        
        # 获取实际的列名(从第一条数据中提取)
        actual_columns = list(data[0].keys()) if data else []
        
        if not actual_columns:
            logger.warning("无法从数据中提取列名，跳过数据渲染")
            return state

        logger.info(f"提取到实际列名: {actual_columns}")

        # 获取chart_config
        chart_config = state.get("chart_config", {})
        
        # 映射列名为中文注释
        column_names_chinese, column_mapping = map_columns_to_comments(
            generated_sql, db_info, actual_columns, chart_config
        )
        
        logger.info(f"列名映射结果: 中文列名数量={len(column_names_chinese)}")

        # 转换数据格式: 将英文列名映射为中文列名
        formatted_data = []
        for row in data:
            formatted_row = {}
            for col_name, value in row.items():
                chinese_col_name = column_mapping.get(col_name, col_name)
                formatted_row[chinese_col_name] = convert_value(value)
            formatted_data.append(formatted_row)

        # 确保 columns 字段与 formatted_data 的 key 一致
        if formatted_data and len(formatted_data) > 0:
            actual_chinese_columns = list(formatted_data[0].keys())
            column_names_chinese = actual_chinese_columns

        # 确定图表类型 (template_code)
        chart_type = state.get("chart_type", "")
        chart_config = state.get("chart_config", {})
        template_code = "temp01"  # 默认为表格
        
        # 优先从 chart_config 中获取类型
        if chart_config and isinstance(chart_config, dict):
            chart_type_from_config = chart_config.get("type", "").lower()
            if chart_type_from_config == "pie":
                template_code = "temp02"
            elif chart_type_from_config == "bar" or chart_type_from_config == "column":
                template_code = "temp03"
            elif chart_type_from_config == "line":
                template_code = "temp04"
        # 其次从 chart_type 中推断
        elif chart_type:
            chart_type_lower = chart_type.lower()
            if chart_type_lower == "table":
                template_code = "temp01"
            elif chart_type_lower == "pie":
                template_code = "temp02"
            elif chart_type_lower in ["bar", "column"]:
                template_code = "temp03"
            elif chart_type_lower == "line":
                template_code = "temp04"
        
        # 构建返回数据格式
        render_data = {
            "template_code": template_code,
            "columns": column_names_chinese,
            "data": formatted_data,
        }
        
        # 如果是图表类型（非表格），添加axis信息到render_data，让前端可以直接使用axis.name作为轴标题
        if template_code != "temp01" and chart_config and isinstance(chart_config, dict):
            axis = chart_config.get("axis", {})
            if isinstance(axis, dict) and axis:
                # 提取axis中的name信息，用于前端显示轴标题
                axis_info = {}
                for axis_key in ["x", "y", "series"]:
                    axis_item = axis.get(axis_key)
                    if isinstance(axis_item, dict):
                        value = axis_item.get("value", "").strip().lower()
                        name = axis_item.get("name", "").strip()
                        if value and name:
                            # 直接使用chart_config中的name（LLM生成的中文名称）
                            # 如果name已经是中文，直接使用；否则尝试从column_mapping中获取
                            if any('\u4e00' <= char <= '\u9fff' for char in name):
                                # name已经是中文，直接使用
                                chinese_name = name
                            else:
                                # name不是中文，尝试从column_mapping中获取
                                chinese_name = column_mapping.get(value) or name
                            
                            axis_info[axis_key] = {
                                "value": value,
                                "name": chinese_name,  # 使用中文名称
                            }
                            logger.info(f"添加axis信息到render_data: {axis_key}.{value} -> {chinese_name}")
                
                if axis_info:
                    render_data["axis"] = axis_info
                    logger.info(f"已添加axis信息到render_data: {axis_info}")

        # 保存到 state
        state["render_data"] = render_data

        logger.info(f"数据渲染完成,共 {len(formatted_data)} 条记录, {len(column_names_chinese)} 列, template_code: {template_code}")

    except Exception as e:
        logger.error(f"数据渲染过程中发生错误: {e}", exc_info=True)
        traceback.print_exception(e)

    return state
