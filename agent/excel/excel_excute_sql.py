import logging
import traceback

from agent.excel.excel_agent_state import ExecutionResult
from agent.excel.excel_duckdb_manager import get_duckdb_manager

logger = logging.getLogger(__name__)


def exe_sql_excel_query(state):
    """
    执行SQL查询
    :param state: ExcelAgentState
    :return: 更新后的ExcelAgentState
    """
    try:
        # 检查必要的字段
        if "generated_sql" not in state or not state["generated_sql"]:
            raise ValueError("没有找到有效的SQL查询语句")

        if state["generated_sql"] == "No SQL query generated":
            raise ValueError("SQL生成失败，无法执行查询")

        # 获取chat_id，优先从state中获取，如果没有则使用默认管理器
        chat_id = state.get("chat_id")

        # 获取DuckDB管理器实例
        duckdb_manager = get_duckdb_manager(chat_id=chat_id)

        # 检查是否有已注册的数据
        registered_catalogs = duckdb_manager.get_registered_catalogs()
        if not registered_catalogs:
            raise ValueError("没有已注册的数据，请确保文件解析步骤已成功执行")

        # 获取SQL查询语句
        sql = state["generated_sql"].replace("`", "")  # 移除反引号以避免SQL语法错误

        logger.info(f"准备执行SQL查询")
        logger.debug(f"  SQL语句: {sql[:200]}{'...' if len(sql) > 200 else ''}")
        logger.debug(f"  可用catalog数量: {len(registered_catalogs)}")
        if registered_catalogs:
            logger.debug(f"  Catalog列表: {list(registered_catalogs.keys())}")

        # 执行SQL查询
        columns, data = duckdb_manager.execute_sql(sql)

        # 成功情况
        state["execution_result"] = ExecutionResult(
            success=True,
            columns=columns,
            data=data
        )

        logger.info(f"SQL查询执行成功: 返回 {len(data)} 行数据, {len(columns)} 列")

    except Exception as e:
        error_msg = str(e)
        # 优化错误日志格式
        if "does not exist" in error_msg or "Table with name" in error_msg:
            import re
            match = re.search(r'Table with name ([^\s!]+)', error_msg)
            if match:
                table_name = match.group(1)
                logger.error(f"SQL查询执行失败: 表 '{table_name}' 不存在")
            else:
                logger.error(f"SQL查询执行失败: 表不存在")
        elif "Parser Error" in error_msg or "syntax error" in error_msg.lower():
            logger.error(f"SQL查询执行失败: SQL语法错误")
            logger.debug(f"  错误详情: {error_msg[:300]}")
        else:
            logger.error(f"SQL查询执行失败: {error_msg[:200]}")
        
        # 打印完整堆栈信息（用于调试）
        if logger.isEnabledFor(logging.DEBUG):
            traceback.print_exception(e)

        state["execution_result"] = ExecutionResult(
            success=False,
            columns=[],
            data=[],
            error=error_msg
        )

    return state