import json
import logging
import traceback

from agent.common.json_value import convert_value_for_json
from agent.excel.excel_agent_state import ExcelAgentState, ExecutionResult
import sqlglot
from sqlglot import parse


"""
表格问答数据渲染节点 - Apache 格式
使用和数据问答一致的渲染方式
"""

logger = logging.getLogger(__name__)


def excel_data_render_apache(state: ExcelAgentState) -> ExcelAgentState:
    """
    渲染表格数据（支持表格数据结构）
    使用和数据问答一致的格式

    :param state: Excel Agent状态对象
    :return: 更新后的 state
    """
    db_info = state.get("db_info", [])
    generated_sql = state.get("generated_sql", "")
    data_result: ExecutionResult = state.get("execution_result")

    if not data_result or not data_result.success or not data_result.data:
        logger.warning("SQL 执行结果为空或失败,跳过数据渲染")
        return state

    data = data_result.data
    if not data:
        logger.warning("数据为空,跳过数据渲染")
        return state

    # 获取实际的列名(从第一条数据中提取)
    actual_columns = list(data[0].keys()) if data else []
    
    if not actual_columns:
        logger.warning("无法从数据中提取列名，跳过数据渲染")
        return state

    logger.info(f"提取到实际列名: {actual_columns}")

    # 使用 excel_data_render_antv 中的映射逻辑
    from agent.excel.excel_data_render_antv import map_columns_to_comments
    
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

    # 构建返回数据格式（和数据问答的 data_render_antv 保持一致）
    render_data = {
        "template_code": "temp01",  # 表格类型
        "columns": column_names_chinese,
        "data": formatted_data,
    }
    
    # 保存到 state（使用 render_data 字段，和数据问答一致）
    state["render_data"] = render_data

    logger.info(f"数据渲染完成,共 {len(formatted_data)} 条记录, {len(column_names_chinese)} 列")

    return state


def convert_value(v):
    return convert_value_for_json(v)


def check_if_select_all(sql: str) -> bool:
    """
    检查 SQL 是否为 SELECT * 查询

    :param sql: SQL 语句
    :return: 是否为 SELECT * 查询
    """
    try:
        expressions = parse(sql)
        for expression in expressions:
            if expression:
                selects = expression.find_all(sqlglot.exp.Select)
                for select in selects:
                    projections = select.expressions if hasattr(select, "expressions") else []
                    for proj in projections:
                        # 检查是否有星号表达式
                        if isinstance(proj, sqlglot.exp.Star):
                            return True
        return False
    except Exception as e:
        logger.info(f"检查 SELECT * 失败: {e}")
        return False


def find_table_in_list(table_name, schema_inspector_list):
    """
    在 list[dict] 类型的 schema 信息中查找指定表的信息

    :param table_name: 表名
    :param schema_inspector_list: schema 信息列表
    :return: 表信息字典或空字典
    """
    for table_info in schema_inspector_list:
        if isinstance(table_info, dict) and table_info.get("table_name") == table_name:
            return table_info
    return {}


def get_all_column_comments_for_tables(table_names: list, schema_inspector: list) -> list:
    """
    为指定表获取所有列的注释信息（用于 SELECT * 查询）

    :param table_names: 表名列表
    :param schema_inspector: schema 信息 (list[dict] 类型)
    :return: 所有列的注释列表
    """
    comments = []
    try:
        for table_name in table_names:
            table_info = find_table_in_list(table_name, schema_inspector)
            if not table_info:
                table_info = schema_inspector[0] if schema_inspector and isinstance(schema_inspector, list) else {}

            columns = table_info.get("columns", {}) if table_info else {}
            for col_name, col_info in columns.items():
                if isinstance(col_info, dict):
                    comment = col_info.get("comment")
                    if comment and comment != "None":
                        comments.append(comment)
                    else:
                        comments.append(col_name)  # 使用列名作为默认值
                else:
                    comments.append(col_name)
    except Exception as e:
        logger.error(f"获取所有列注释失败: {e}")
        return []

    return comments


def get_actual_columns_for_select_all(table_names: list, schema_inspector: list) -> list:
    """
    为 SELECT * 查询获取实际的列名列表

    :param table_names: 表名列表
    :param schema_inspector: schema 信息 (list[dict] 类型)
    :return: 所有列的列名列表
    """
    columns = []
    try:
        for table_name in table_names:
            table_info = find_table_in_list(table_name, schema_inspector)
            if not table_info:
                table_info = schema_inspector[0] if schema_inspector and isinstance(schema_inspector, list) else {}

            table_columns = table_info.get("columns", {}) if table_info else {}
            columns.extend(list(table_columns.keys()))
    except Exception as e:
        logger.info(f"获取 SELECT * 实际列名失败: {e}")
        return []

    return columns


def extract_table_names_sqlglot(sql: str) -> list:
    """
    使用 sqlglot 提取 SQL 中的所有表名（支持复杂语法、多表、子查询、CTE 等）

    :param sql: SQL 语句
    :return: 表名列表（去重）
    """
    try:
        expression = parse(sql)[0]
        tables = set()
        for table in expression.find_all(sqlglot.exp.Table):
            # 取表名（去掉 schema）
            tables.add(table.name)
        return list(tables)
    except Exception as e:
        logger.info(f"SQL 解析错误: {e}")
        return []


def get_column_comments(schema_inspector: list, table_name: str) -> list:
    """
    从 schema_inspector 中提取指定表的所有字段的 comment，放入 list 中。

    :param schema_inspector: 包含数据库 schema 信息的列表 (list[dict])
    :param table_name: 要提取 comment 的表名
    :return: 包含所有字段 comment 的 list
    """
    try:
        table_info = find_table_in_list(table_name, schema_inspector)
        if not table_info:
            table_info = schema_inspector[0] if schema_inspector and isinstance(schema_inspector, list) else {}

        if not table_info:
            logger.info(f"未找到表 {table_name} 的信息")
            return []

        columns = table_info.get("columns", {})
        if not columns:
            logger.info(f"表 {table_name} 没有列信息")
            return []

        comments = []
        for col_name, col_info in columns.items():
            # 确保col_info是字典类型
            if isinstance(col_info, dict):
                comment = col_info.get("comment")
                # 如果 comment 为 'None' 字符串或 None，用空字符串代替
                if comment and comment != "None":
                    comments.append(comment)
                else:
                    comments.append("")  # 使用空字符串作为默认值
            else:
                comments.append("")  # 如果列信息格式不正确，使用空字符串
        return comments
    except Exception as e:
        traceback.print_exception(e)
        logger.info(f"处理表 {table_name} 的列注释时出错: {e}")
        return []


def extract_actual_column_names(sql: str) -> list:
    """
    使用 sqlglot 提取 SQL 中 SELECT 子句的实际列名

    :param sql: SQL 语句
    :return: 实际列名列表
    """
    try:
        expressions = parse(sql)
        columns = []

        for expression in expressions:
            if expression:
                # 查找所有的 SELECT 表达式
                select_expressions = expression.find_all(sqlglot.exp.Select)

                for select_expr in select_expressions:
                    # 获取 projections (SELECT 后面的列)
                    projections = select_expr.expressions if hasattr(select_expr, "expressions") else []

                    for proj in projections:
                        # 处理普通列名
                        if isinstance(proj, sqlglot.exp.Column):
                            # 构造完整的列名（如果有表前缀）
                            if hasattr(proj, "table") and proj.table:
                                columns.append(f"{proj.table}.{proj.name}")
                            else:
                                columns.append(proj.name)
                        # 处理聚合函数等表达式（使用别名）
                        elif isinstance(proj, sqlglot.exp.Alias):
                            columns.append(proj.alias)
                        elif isinstance(
                            proj,
                            (
                                sqlglot.exp.Sum,
                                sqlglot.exp.Count,
                                sqlglot.exp.Avg,
                                sqlglot.exp.Max,
                                sqlglot.exp.Min,
                                sqlglot.exp.Star,
                            ),
                        ):
                            # 对于聚合函数等，如果没有别名，使用生成的名称
                            alias = getattr(proj, "alias", None)
                            name = getattr(proj, "name", None)
                            output_name = getattr(proj, "output_name", None)
                            columns.append(alias or name or output_name or "unknown")
                        # 处理其他情况
                        elif hasattr(proj, "alias") and proj.alias:
                            columns.append(proj.alias)
                        elif hasattr(proj, "name"):
                            columns.append(proj.name)
                        elif hasattr(proj, "output_name"):
                            columns.append(proj.output_name)

        return columns
    except Exception as e:
        logger.info(f"SQL 实际列名解析错误: {e}")
        return []


def extract_column_names_sqlglot(sql: str) -> list:
    """
    使用 sqlglot 提取 SQL 中 SELECT 子句的所有列名

    :param sql: SQL 语句
    :return: 列名列表
    """
    try:
        expressions = parse(sql)
        columns = []

        for expression in expressions:
            if expression:
                # 查找所有的 SELECT 表达式
                select_expressions = expression.find_all(sqlglot.exp.Select)

                for select_expr in select_expressions:
                    # 获取 projections (SELECT 后面的列)
                    projections = select_expr.expressions if hasattr(select_expr, "expressions") else []

                    for proj in projections:
                        # 处理别名情况
                        if isinstance(proj, sqlglot.exp.Alias):
                            columns.append(proj.alias)
                        # 处理普通列名
                        elif hasattr(proj, "name"):
                            columns.append(proj.name)
                        # 处理其他情况
                        elif hasattr(proj, "output_name"):
                            columns.append(proj.output_name)
                        # 处理字符串形式的表达式
                        elif isinstance(proj, sqlglot.exp.Column):
                            columns.append(proj.name)
                        # 处理星号
                        elif isinstance(proj, sqlglot.exp.Star):
                            columns.append("*")

        # 去重但保持顺序
        unique_columns = []
        for col in columns:
            if col not in unique_columns:
                unique_columns.append(col)

        return unique_columns
    except Exception as e:
        logger.info(f"SQL 列名解析错误: {e}")
        return []


def extract_select_columns_with_comments(sql: str, schema_inspector: list) -> list:
    """
    使用 sqlglot 提取 SQL 中 SELECT 子句的列名，并尝试获取对应的中文注释
    对于带有别名的统计类列（如聚合函数），保留别名不转换为中文

    :param sql: SQL 语句
    :param schema_inspector: 包含数据库 schema 信息的列表 (list[dict])
    :return: 列标题列表（优先使用中文注释，其次使用别名或列名）
    """
    try:
        expressions = parse(sql)
        column_info_list = []

        # 提取表别名映射
        table_alias_mapping = extract_table_alias_mapping(sql)

        for expression in expressions:
            if expression:
                # 查找 SELECT 表达式
                selects = expression.find_all(sqlglot.exp.Select)

                for select in selects:
                    # 获取 projections (SELECT 后面的列)
                    projections = select.expressions if hasattr(select, "expressions") else []

                    for proj in projections:
                        column_info = {"name": None, "alias": None, "is_aggregate": False, "table": None}

                        # 处理带别名的列
                        if isinstance(proj, sqlglot.exp.Alias):
                            column_info["alias"] = proj.alias
                            column_info["name"] = proj.this.name if hasattr(proj.this, "name") else None
                            # 检查是否为聚合函数
                            column_info["is_aggregate"] = isinstance(
                                proj.this,
                                (sqlglot.exp.Sum, sqlglot.exp.Count, sqlglot.exp.Avg, sqlglot.exp.Max, sqlglot.exp.Min),
                            )
                            # 获取表名（如果有）
                            if hasattr(proj.this, "table"):
                                table_ref = proj.this.table
                                # 使用别名映射查找真实表名
                                column_info["table"] = table_alias_mapping.get(table_ref, table_ref)
                        # 处理普通列
                        elif isinstance(proj, sqlglot.exp.Column):
                            column_info["name"] = proj.name
                            if hasattr(proj, "table"):
                                table_ref = proj.table
                                # 使用别名映射查找真实表名
                                column_info["table"] = table_alias_mapping.get(table_ref, table_ref)
                        # 处理聚合函数等表达式
                        elif isinstance(
                            proj,
                            (sqlglot.exp.Sum, sqlglot.exp.Count, sqlglot.exp.Avg, sqlglot.exp.Max, sqlglot.exp.Min),
                        ):
                            column_info["is_aggregate"] = True
                            column_info["alias"] = getattr(proj, "alias", None) or getattr(proj, "name", None)
                        # 处理星号（SELECT *）
                        elif isinstance(proj, sqlglot.exp.Star):
                            # 对于星号，我们稍后会特殊处理
                            column_info["name"] = "*"
                            column_info["alias"] = "*"

                        # 获取列的标准名称
                        if not column_info["name"] and hasattr(proj, "name"):
                            column_info["name"] = proj.name

                        column_info_list.append(column_info)

        # 获取表名用于查找列注释
        table_names = extract_table_names_sqlglot(sql)

        # 生成最终的列标题
        result_columns = []
        for col_info in column_info_list:
            # 处理 SELECT * 的情况
            if col_info["name"] == "*":
                # 这种情况已经在上层函数中特殊处理了，这里只是兜底
                continue

            # 对于聚合函数或带别名的列，优先使用别名
            if col_info["is_aggregate"] or col_info["alias"]:
                result_columns.append(col_info["alias"] or col_info["name"])
            # 对于普通列，尝试获取中文注释
            elif col_info["name"]:
                # 优先使用列中指定的表名查找注释
                comment_found = False

                # 如果列信息中指定了表名
                if col_info["table"]:
                    # 首先尝试使用解析出的真实表名
                    real_table_name = col_info["table"]
                    if real_table_name in table_names:
                        table_info = find_table_in_list(real_table_name, schema_inspector)
                        if not table_info:
                            table_info = (
                                schema_inspector[0] if schema_inspector and isinstance(schema_inspector, list) else {}
                            )

                        columns = table_info.get("columns", {}) if table_info else {}
                        col_schema = columns.get(col_info["name"], {})

                        if isinstance(col_schema, dict):
                            comment = col_schema.get("comment")
                            if comment and comment != "None":
                                result_columns.append(comment)
                                comment_found = True

                    # 如果上面没找到，再遍历所有表查找
                    if not comment_found:
                        for table_name in table_names:
                            table_info = find_table_in_list(table_name, schema_inspector)
                            if not table_info:
                                table_info = (
                                    schema_inspector[0]
                                    if schema_inspector and isinstance(schema_inspector, list)
                                    else {}
                                )

                            columns = table_info.get("columns", {}) if table_info else {}
                            col_schema = columns.get(col_info["name"], {})

                            if isinstance(col_schema, dict):
                                comment = col_schema.get("comment")
                                if comment and comment != "None":
                                    result_columns.append(comment)
                                    comment_found = True
                                    break

                # 如果没找到注释，则使用列名
                if not comment_found:
                    result_columns.append(col_info["name"])
            else:
                # 兜底处理
                result_columns.append(col_info["alias"] or col_info["name"] or "未知列")

        return result_columns
    except Exception as e:
        logger.info(f"SQL 列名及注释解析错误: {e}")
        # 出错时回退到原来的简单实现
        return extract_column_names_sqlglot(sql)


def extract_table_alias_mapping(sql: str) -> dict:
    """
    提取SQL中的表别名映射关系

    :param sql: SQL语句
    :return: 别名到真实表名的映射字典
    """
    alias_mapping = {}
    try:
        expressions = parse(sql)

        # 方法1: 直接从表表达式中提取
        for expression in expressions:
            if expression:
                for table_exp in expression.find_all(sqlglot.exp.Table):
                    if hasattr(table_exp, "alias") and table_exp.alias:
                        alias_mapping[table_exp.alias] = table_exp.name

        # 方法2: 从FROM和JOIN子句中提取
        for expression in expressions:
            if expression:
                # 处理 FROM 子句
                for from_exp in expression.find_all(sqlglot.exp.From):
                    if hasattr(from_exp, "expressions"):
                        for expr in from_exp.expressions:
                            if isinstance(expr, sqlglot.exp.Alias) and hasattr(expr.this, "name"):
                                alias_mapping[expr.alias] = expr.this.name
                            elif hasattr(expr, "name") and hasattr(expr, "alias"):
                                alias_mapping[expr.alias] = expr.name

                # 处理 JOIN 子句
                for join_exp in expression.find_all(sqlglot.exp.Join):
                    if hasattr(join_exp, "this"):
                        join_table = join_exp.this
                        if isinstance(join_table, sqlglot.exp.Alias) and hasattr(join_table.this, "name"):
                            alias_mapping[join_table.alias] = join_table.this.name
                        elif hasattr(join_table, "name") and hasattr(join_table, "alias"):
                            alias_mapping[join_table.alias] = join_table.name
    except Exception as e:
        logger.info(f"提取表别名映射失败: {e}")

    logger.info(f"表别名映射: {alias_mapping}")
    return alias_mapping
