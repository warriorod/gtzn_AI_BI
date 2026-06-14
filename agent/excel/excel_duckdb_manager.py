"""
DuckDB 连接管理器
统一管理 Excel Agent 中的 DuckDB 连接和数据注册，避免重复创建和注册
"""

import logging
import re
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import duckdb
import pandas as pd

from agent.excel.excel_agent_state import FileInfo, SheetInfo

logger = logging.getLogger(__name__)


class ExcelDuckDBManager:
    """
    Excel DuckDB 连接管理器
    - 统一管理 DuckDB 连接
    - 避免重复创建连接和注册数据
    - 支持多文件、多Sheet的数据管理
    """

    def __init__(self):
        self._connection: Optional[duckdb.DuckDBPyConnection] = None
        self._registered_catalogs: Dict[str, str] = {}  # {catalog_name: file_path}
        self._registered_tables: Dict[str, SheetInfo] = {}  # {table_name: SheetInfo}
        self._session_id: str = datetime.now().strftime("%Y%m%d_%H%M%S")

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """
        获取 DuckDB 连接，延迟初始化
        """
        if self._connection is None:
            logger.info("创建新的 DuckDB 连接")
            self._connection = duckdb.connect(database=":memory:")

            # 安装并加载必要的扩展
            # self._connection.execute("INSTALL httpfs")
            # self._connection.execute("LOAD httpfs")
            #
            # logger.info("DuckDB 连接创建完成，已加载 httpfs 扩展")

        return self._connection

    def _sanitize_catalog_name(self, file_name: str) -> str:
        """
        清理文件名，生成合法的 DuckDB catalog 名称
        """
        # 移除文件扩展名
        name_without_ext = file_name.split("/")[-1]
        name_without_ext = name_without_ext.rsplit(".", 1)[0]

        # 替换非法字符
        catalog_name = re.sub(r"[^\w\u4e00-\u9fa5]", "_", name_without_ext)
        # 移除开头和结尾的下划线
        catalog_name = catalog_name.strip("_")
        # 确保不以数字开头
        if catalog_name and catalog_name[0].isdigit():
            catalog_name = f"catalog_{catalog_name}"
        return catalog_name or "unknown_catalog"

    def _sanitize_table_name(self, sheet_name: str) -> str:
        """
        清理 Sheet 名称，生成合法的表名
        """
        # 替换非法字符
        table_name = re.sub(r"[^\w\u4e00-\u9fa5]", "_", sheet_name)
        # 移除开头和结尾的下划线
        table_name = table_name.strip("_")
        # 确保不以数字开头
        if table_name and table_name[0].isdigit():
            table_name = f"table_{table_name}"
        return table_name or "unknown_sheet"

    def _sanitize_column_name(self, column_name: str) -> str:
        """
        清理列名，生成合法的列名
        """
        # 替换非法字符
        col_name = re.sub(r"[^\w\u4e00-\u9fa5]", "_", str(column_name))
        # 移除开头和结尾的下划线
        col_name = col_name.strip("_")
        # 确保不以数字开头
        if col_name and col_name[0].isdigit():
            col_name = f"column_{col_name}"
        return col_name or "unknown_column"

    def _register_dataframes_to_catalog(
        self, dataframes: List[Tuple[str, pd.DataFrame]], catalog_name: str, file_name: str
    ) -> Dict[str, SheetInfo]:
        """
        将多个 DataFrame 注册到指定的 catalog 中

        :param dataframes: List[(sheet_name, DataFrame)] - 表名和数据框的列表
        :param catalog_name: 目标 catalog 名称
        :param file_name: 源文件名（用于日志）
        :return: {table_name: SheetInfo}
        """
        conn = self._get_connection()
        registered_tables = {}

        # 创建schema（如果不存在）
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {catalog_name}")

        for sheet_name, df in dataframes:
            try:
                # 生成表名
                table_name = self._sanitize_table_name(sheet_name)
                full_table_name = f'"{catalog_name}"."{table_name}"'

                # 检查表是否已注册
                if full_table_name in self._registered_tables:
                    logger.warning(f"表 '{full_table_name}' 已存在，跳过注册")
                    continue

                if df.empty:
                    logger.warning(f"表 '{sheet_name}' 为空，跳过注册")
                    continue

                # 清理列名
                df.columns = [self._sanitize_column_name(col) for col in df.columns]

                # 创建表并插入数据
                create_sql = f"CREATE TABLE {full_table_name} AS SELECT * FROM df"
                conn.execute(create_sql)

                # 获取表信息
                row_count = len(df)
                column_count = len(df.columns)

                # 获取列信息
                columns_info = {}
                for col in df.columns:
                    dtype = str(df[col].dtype)
                    sql_type = self._map_pandas_dtype_to_sql(dtype)
                    columns_info[col] = {"comment": col, "type": sql_type}

                # 获取样本数据（前5行）
                sample_data = df.head(5).to_dict("records")

                # 创建 SheetInfo
                sheet_info = SheetInfo(
                    sheet_name=sheet_name,
                    table_name=table_name,
                    catalog_name=catalog_name,
                    row_count=row_count,
                    column_count=column_count,
                    columns_info=columns_info,
                    sample_data=sample_data,
                )

                registered_tables[table_name] = sheet_info
                self._registered_tables[full_table_name] = sheet_info

                logger.debug(f"  注册表: {full_table_name} ({row_count} 行, {column_count} 列)")

            except Exception as e:
                logger.error(f"注册表 '{sheet_name}' 失败: {str(e)}")
                traceback.print_exception(e)
                continue

        return registered_tables

    def _get_unique_catalog_name(self, file_name: str) -> str:
        """
        获取唯一的 catalog 名称

        :param file_name: 文件名
        :return: 唯一的 catalog 名称
        """
        catalog_name = self._sanitize_catalog_name(file_name)

        # 确保 catalog 名称唯一
        original_catalog_name = catalog_name
        counter = 1
        while catalog_name in self._registered_catalogs:
            catalog_name = f"{original_catalog_name}_{counter}"
            counter += 1

        return catalog_name

    def register_excel_file(self, file_path: str, file_name: str) -> Tuple[str, Dict[str, SheetInfo]]:
        """
        注册 Excel 文件到 DuckDB，返回 catalog 名称和表信息

        :param file_path: 文件路径或URL
        :param file_name: 文件名
        :return: (catalog_name, {table_name: SheetInfo})
        """
        catalog_name = self._get_unique_catalog_name(file_name)
        logger.info(f"开始注册Excel文件到 catalog '{catalog_name}': {file_name}")

        try:
            # 读取 Excel 文件的所有 sheet
            excel_file_data = pd.ExcelFile(file_path)
            sheet_names = excel_file_data.sheet_names

            # 构建数据框列表
            dataframes = []
            for sheet_name in sheet_names:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                dataframes.append((sheet_name, df))

            # 注册到 catalog
            registered_tables = self._register_dataframes_to_catalog(dataframes, catalog_name, file_name)

            # 记录 catalog 信息
            self._registered_catalogs[catalog_name] = file_path
            logger.info(
                f"成功注册Excel文件: {file_name} -> catalog '{catalog_name}' ({len(registered_tables)} 个表)"
            )

        except Exception as e:
            logger.error(f"注册Excel文件 '{file_name}' 失败: {str(e)}")
            traceback.print_exception(e)
            raise

        return catalog_name, registered_tables

    def register_csv_file(self, file_path: str, file_name: str) -> Tuple[str, Dict[str, SheetInfo]]:
        """
        注册 CSV 文件到 DuckDB

        :param file_path: 文件路径或URL
        :param file_name: 文件名
        :return: (catalog_name, {table_name: SheetInfo})
        """
        catalog_name = self._get_unique_catalog_name(file_name)
        logger.info(f"开始注册CSV文件到 catalog '{catalog_name}': {file_name}")

        try:
            # 读取 CSV 文件
            df = pd.read_csv(file_path)

            if df.empty:
                logger.warning(f"CSV文件 '{file_name}' 为空")
                return catalog_name, {}

            # 生成表名（使用文件名去掉扩展名）
            table_name = self._sanitize_table_name(file_name.rsplit(".", 1)[0])

            # 构建数据框列表
            dataframes = [(table_name, df)]

            # 注册到 catalog
            registered_tables = self._register_dataframes_to_catalog(dataframes, catalog_name, file_name)

            # 记录 catalog 信息
            self._registered_catalogs[catalog_name] = file_path
            logger.info(f"成功注册CSV文件: {file_name} -> catalog '{catalog_name}' ({len(registered_tables)} 个表)")

        except Exception as e:
            logger.error(f"注册CSV文件 '{file_name}' 失败: {str(e)}")
            traceback.print_exception(e)
            raise

        return catalog_name, registered_tables

    def _extract_table_names_from_sql(self, sql: str) -> List[str]:
        """
        从SQL语句中提取表名
        
        :param sql: SQL查询语句
        :return: 表名列表（格式：catalog.table 或 table）
        """
        import re
        # 匹配 "catalog"."table" 或 "table" 格式的表名
        # 支持 FROM, JOIN, UPDATE, INSERT INTO 等语句
        pattern = r'["\']([^"\']+)["\']\s*\.\s*["\']([^"\']+)["\']|FROM\s+["\']([^"\']+)["\']|JOIN\s+["\']([^"\']+)["\']'
        matches = re.findall(pattern, sql, re.IGNORECASE)
        
        table_names = []
        for match in matches:
            if match[0] and match[1]:  # catalog.table 格式
                table_names.append(f'"{match[0]}"."{match[1]}"')
            elif match[2]:  # FROM 后的表名
                table_names.append(f'"{match[2]}"')
            elif match[3]:  # JOIN 后的表名
                table_names.append(f'"{match[3]}"')
        
        # 去重
        return list(set(table_names))
    
    def _check_table_exists(self, table_name: str) -> bool:
        """
        检查表是否存在
        
        :param table_name: 表名（格式："catalog"."table" 或 "table"）
        :return: 表是否存在
        """
        conn = self._get_connection()
        try:
            # 尝试直接查询表，如果失败则表不存在
            # 使用LIMIT 0来避免实际读取数据，只检查表是否存在
            test_sql = f'SELECT 1 FROM {table_name} LIMIT 0'
            try:
                conn.execute(test_sql)
                return True
            except Exception as e:
                error_msg = str(e).lower()
                if "does not exist" in error_msg or "table with name" in error_msg:
                    return False
                # 其他错误也认为表不存在
                return False
        except Exception as e:
            logger.debug(f"检查表是否存在时出错: {str(e)}")
            return False
    
    def _fix_sql_table_names(self, sql: str) -> str:
        """
        修复SQL中的表名，将不存在的表名映射到已注册的表名
        
        :param sql: 原始SQL语句
        :return: 修复后的SQL语句
        """
        # 获取所有已注册的表
        registered_tables = self.get_registered_tables()
        if not registered_tables:
            logger.warning("没有已注册的表，无法修复SQL表名")
            return sql
        
        import re
        
        # 辅助函数：根据catalog和table名找到匹配的注册表名
        def find_matching_table(catalog_part: str, table_part: str) -> str:
            """
            根据catalog和table名找到匹配的注册表名
            :param catalog_part: catalog名称
            :param table_part: table名称
            :return: 匹配的完整表名，如果找不到则返回None
            """
            full_match = f'"{catalog_part}"."{table_part}"'
            
            # 检查这个表是否存在
            if self._check_table_exists(full_match):
                logger.debug(f"表 {full_match} 存在，无需修复")
                return full_match
            
            # 尝试找到匹配的表
            # 1. 先尝试精确匹配 registered_full_name
            for registered_full_name, sheet_info in registered_tables.items():
                if registered_full_name == full_match:
                    logger.debug(f"  精确匹配: {full_match}")
                    return registered_full_name
            
            # 2. 尝试匹配表名（table_name），忽略catalog
            for registered_full_name, sheet_info in registered_tables.items():
                if sheet_info.table_name == table_part:
                    logger.debug(f"  通过表名匹配: {table_part} -> {registered_full_name}")
                    return registered_full_name
            
            # 3. 尝试匹配sheet_name
            for registered_full_name, sheet_info in registered_tables.items():
                if sheet_info.sheet_name == table_part:
                    logger.debug(f"  通过sheet名匹配: {table_part} -> {registered_full_name}")
                    return registered_full_name
            
            # 4. 尝试匹配catalog_name（如果catalog部分包含已注册的catalog）
            for registered_full_name, sheet_info in registered_tables.items():
                if sheet_info.catalog_name == catalog_part:
                    logger.debug(f"  通过catalog名匹配: {catalog_part} -> {registered_full_name}")
                    return registered_full_name
            
            # 5. 如果catalog包含chat_id前缀（如 chat_id__catalog），尝试去掉前缀后匹配
            if "__" in catalog_part:
                catalog_without_prefix = catalog_part.split("__", 1)[-1]
                for registered_full_name, sheet_info in registered_tables.items():
                    if sheet_info.catalog_name == catalog_without_prefix and sheet_info.table_name == table_part:
                        logger.debug(f"  通过去掉chat_id前缀匹配: {catalog_part} -> {registered_full_name}")
                        return registered_full_name
            
            # 6. 如果只有一个表，直接使用它
            if len(registered_tables) == 1:
                registered_full_name = list(registered_tables.keys())[0]
                logger.debug(f"  只有一个表，使用: {registered_full_name}")
                return registered_full_name
            
            # 如果都找不到，返回None
            logger.debug(f"  无法匹配表名: {full_match}")
            logger.debug(f"  可用表列表: {list(registered_tables.keys())}")
            return None
        
        # 匹配 "catalog"."table" 格式的表名
        def replace_table_name(match):
            catalog_part = match.group(1).strip('"\'')
            table_part = match.group(2).strip('"\'')
            full_match = f'"{catalog_part}"."{table_part}"'
            
            matched_table = find_matching_table(catalog_part, table_part)
            if matched_table and matched_table != full_match:
                logger.debug(f"  修复表名: {full_match} -> {matched_table}")
            return matched_table if matched_table else full_match
        
        # 先处理错误的表名格式：整个字符串作为一个表名（如 "chat_id__catalog.table"）
        # 这种格式的点号在引号内，需要先处理
        def replace_wrong_format_table(match):
            keyword = match.group(1)  # FROM, JOIN等关键字
            full_table_name = match.group(2).strip('"\'')
            
            # 如果表名包含 "."，可能是 catalog.table 格式（点号在引号内）
            if "." in full_table_name:
                # 尝试分割：catalog.table -> catalog, table
                parts = full_table_name.split(".", 1)
                if len(parts) == 2:
                    catalog_part = parts[0]
                    table_name = parts[1]
                    
                    # 如果catalog包含 "__"，去掉chat_id前缀
                    if "__" in catalog_part:
                        catalog_name = catalog_part.split("__", 1)[-1]
                    else:
                        catalog_name = catalog_part
                    
                    # 使用find_matching_table函数查找匹配的表（先尝试去掉前缀）
                    matched_table = find_matching_table(catalog_name, table_name)
                    if matched_table:
                        logger.debug(f"  修复错误格式表名（去掉chat_id前缀）: {full_table_name} -> {matched_table}")
                        return f"{keyword} {matched_table}"
                    
                    # 如果catalog包含chat_id前缀，也尝试使用完整的catalog_part匹配
                    if "__" in catalog_part:
                        matched_table = find_matching_table(catalog_part, table_name)
                        if matched_table:
                            logger.debug(f"  修复错误格式表名（使用完整catalog）: {full_table_name} -> {matched_table}")
                            return f"{keyword} {matched_table}"
                        
                        # 如果还是找不到，尝试只匹配table_name
                        for registered_full_name, sheet_info in registered_tables.items():
                            if sheet_info.table_name == table_name:
                                logger.debug(f"  修复错误格式表名（忽略catalog）: {full_table_name} -> {registered_full_name}")
                                return f"{keyword} {registered_full_name}"
            
            # 如果无法修复，返回原始
            return match.group(0)
        
        # 匹配引号内包含点号的表名（可能是错误的格式）
        # 只匹配FROM/JOIN等关键字后的表名
        # 表名后面可能是：表别名（带或不带引号）、ON、WHERE、GROUP BY等关键字、逗号、或结束
        # 使用更宽松的前瞻断言，允许表名后面有任何内容（包括表别名、关键字等）
        wrong_format_pattern = r'(?i)\b(FROM|JOIN|UPDATE|INSERT\s+INTO)\s+["\']([^"\']*\.[^"\']+)["\']'
        fixed_sql = re.sub(wrong_format_pattern, replace_wrong_format_table, sql)
        
        # 替换 "catalog"."table" 格式的表名（点号在引号外）
        # 只匹配FROM/JOIN等关键字后的表名
        def replace_table_name_with_keyword(match):
            keyword = match.group(1)  # FROM, JOIN等关键字
            catalog_part = match.group(2).strip('"\'')
            table_part = match.group(3).strip('"\'')
            
            matched_table = find_matching_table(catalog_part, table_part)
            if matched_table:
                return f"{keyword} {matched_table}"
            else:
                return match.group(0)
        
        # 使用更宽松的模式，不限制表名后面的内容
        pattern = r'(?i)\b(FROM|JOIN|UPDATE|INSERT\s+INTO)\s+["\']([^"\']+)["\']\s*\.\s*["\']([^"\']+)["\']'
        fixed_sql = re.sub(pattern, replace_table_name_with_keyword, fixed_sql)
        
        return fixed_sql

    def execute_sql(self, sql: str) -> Tuple[List[str], List[Dict]]:
        """
        执行 SQL 查询

        :param sql: SQL 查询语句
        :return: (columns, data)
        """
        conn = self._get_connection()

        try:
            logger.info(f"执行SQL查询: {sql[:200]}{'...' if len(sql) > 200 else ''}")
            
            # 尝试执行SQL
            try:
                cursor = conn.execute(sql)
            except Exception as first_error:
                # 如果执行失败，尝试修复表名
                error_msg = str(first_error)
                # 只对表不存在的错误进行修复，其他语法错误直接抛出
                if "does not exist" in error_msg or "Table with name" in error_msg:
                    # 提取表名信息
                    table_match = None
                    if "Table with name" in error_msg:
                        import re
                        match = re.search(r'Table with name ([^\s!]+)', error_msg)
                        if match:
                            table_match = match.group(1)
                    
                    logger.warning(f"检测到表不存在错误，尝试自动修复表名")
                    if table_match:
                        logger.debug(f"  问题表名: {table_match}")
                    
                    # 显示已注册的表信息
                    registered_tables = self.get_registered_tables()
                    if registered_tables:
                        logger.debug(f"  已注册的表数量: {len(registered_tables)}")
                        logger.debug(f"  已注册的表: {list(registered_tables.keys())[:5]}")
                    
                    try:
                        fixed_sql = self._fix_sql_table_names(sql)
                        if fixed_sql != sql:
                            logger.info(f"表名修复成功")
                            logger.debug(f"  修复前: {sql[:150]}{'...' if len(sql) > 150 else ''}")
                            logger.debug(f"  修复后: {fixed_sql[:150]}{'...' if len(fixed_sql) > 150 else ''}")
                            cursor = conn.execute(fixed_sql)
                        else:
                            logger.warning(f"无法修复表名，SQL未发生变化")
                            raise first_error
                    except Exception as fix_error:
                        # 如果修复后的SQL执行失败，记录错误并抛出原始错误
                        fix_error_msg = str(fix_error)
                        logger.error(f"修复后的SQL执行仍然失败")
                        if "does not exist" in fix_error_msg or "Table with name" in fix_error_msg:
                            logger.error(f"  错误原因: 表仍然不存在")
                        else:
                            logger.error(f"  错误原因: {fix_error_msg[:200]}")
                        logger.debug(f"  修复后的SQL: {fixed_sql[:200]}{'...' if len(fixed_sql) > 200 else ''}")
                        raise first_error
                else:
                    # 其他错误（如语法错误）直接抛出，不进行修复
                    logger.debug(f"SQL执行失败（非表不存在错误），直接抛出")
                    raise first_error

            # 获取列名称和查询结果的数据行
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()

            # 构建结果字典
            result = [dict(zip(columns, row)) for row in rows]

            logger.info(f"SQL查询执行成功: 返回 {len(result)} 行数据, {len(columns)} 列")
            return columns, result

        except Exception as e:
            error_msg = str(e)
            # 提取关键错误信息
            if "does not exist" in error_msg or "Table with name" in error_msg:
                import re
                match = re.search(r'Table with name ([^\s!]+)', error_msg)
                if match:
                    table_name = match.group(1)
                    logger.error(f"SQL查询失败: 表 '{table_name}' 不存在")
                    registered_tables = self.get_registered_tables()
                    if registered_tables:
                        logger.error(f"  可用表列表: {list(registered_tables.keys())}")
                    else:
                        logger.error(f"  当前没有已注册的表，请确保文件已正确解析")
                else:
                    logger.error(f"SQL查询失败: {error_msg[:200]}")
            else:
                logger.error(f"SQL查询失败: {error_msg[:200]}")
            raise

    def get_registered_catalogs(self) -> Dict[str, str]:
        """
        获取已注册的 catalog 信息
        """
        return self._registered_catalogs.copy()

    def get_registered_tables(self) -> Dict[str, SheetInfo]:
        """
        获取已注册的表信息
        """
        return self._registered_tables.copy()

    def get_table_schema_info(self) -> List[Dict]:
        """
        获取所有表的架构信息，用于SQL生成
        """
        schema_info = []

        for full_table_name, sheet_info in self._registered_tables.items():
            catalog_name, table_name = full_table_name.split(".", 1)

            table_schema = {
                "table_name": full_table_name,
                "columns": sheet_info.columns_info,
                "foreign_keys": [],
                "table_comment": f"{catalog_name} - {sheet_info.sheet_name}",
                "catalog_name": catalog_name,
            }
            schema_info.append(table_schema)

        return schema_info

    def close(self):
        """
        关闭 DuckDB 连接
        """
        if self._connection is not None:
            self._connection.close()
            self._connection = None
            logger.info("DuckDB 连接已关闭")

    def clear_registered_tables(self):
        """
        清理已注册的表（删除DuckDB中的表，但保持连接）
        用于重新执行时清理旧表
        """
        if not self._registered_tables:
            logger.debug("没有已注册的表需要清理")
            return
        
        try:
            conn = self._get_connection()
            table_count = len(self._registered_tables)
            
            for full_table_name in list(self._registered_tables.keys()):
                try:
                    # 删除表
                    drop_sql = f"DROP TABLE IF EXISTS {full_table_name}"
                    conn.execute(drop_sql)
                    logger.debug(f"已删除表: {full_table_name}")
                except Exception as e:
                    logger.warning(f"删除表失败: {full_table_name}, 错误: {str(e)}")
            
            # 清理管理器中的注册信息
            self._registered_tables.clear()
            self._registered_catalogs.clear()
            logger.info(f"已清理 {table_count} 个已注册的表")
        except Exception as e:
            logger.error(f"清理已注册表时出错: {str(e)}")
            raise

    def clear_session(self):
        """
        清理当前会话数据
        """
        self.close()
        self._registered_catalogs.clear()
        self._registered_tables.clear()
        logger.info(f"会话 {self._session_id} 数据已清理")

    def _map_pandas_dtype_to_sql(self, dtype: str) -> str:
        """
        将 pandas 数据类型映射到 SQL 数据类型
        """
        dtype_mapping = {
            "object": "VARCHAR(255)",
            "int64": "BIGINT",
            "int32": "INTEGER",
            "float64": "FLOAT",
            "float32": "FLOAT",
            "bool": "BOOLEAN",
            "datetime64[ns]": "DATETIME",
            "timedelta64[ns]": "VARCHAR(50)",
        }

        # 处理字符串类型
        if dtype.startswith("object"):
            return "VARCHAR(255)"
        # 处理整数类型
        elif dtype.startswith("int"):
            return dtype_mapping.get(dtype, "BIGINT")
        # 处理浮点数类型
        elif dtype.startswith("float"):
            return dtype_mapping.get(dtype, "FLOAT")
        # 处理日期时间类型
        elif dtype.startswith("datetime"):
            return "DATETIME"
        else:
            return "VARCHAR(255)"


class ChatDuckDBManager:
    """
    聊天级别的DuckDB管理器
    为每个chat_id维护独立的ExcelDuckDBManager实例
    """

    def __init__(self):
        # {chat_id: ExcelDuckDBManager}
        self._chat_managers: Dict[str, ExcelDuckDBManager] = {}
        # 会话清理时间配置（秒）
        self._session_timeout = 36000  # 10小时
        # {chat_id: 最后访问时间}
        self._last_access: Dict[str, float] = {}
        logger.info("初始化聊天级别DuckDB管理器")

    def get_manager(self, chat_id: str) -> ExcelDuckDBManager:
        """
        获取指定chat_id的DuckDB管理器实例

        :param chat_id: 聊天ID
        :return: ExcelDuckDBManager实例
        """
        # 检查是否已存在该chat_id的管理器
        if chat_id not in self._chat_managers:
            self._chat_managers[chat_id] = ExcelDuckDBManager()
            logger.info(f"为chat_id '{chat_id}' 创建新的DuckDB管理器实例")

        # 更新最后访问时间
        self._last_access[chat_id] = time.time()

        return self._chat_managers[chat_id]

    def close_manager(self, chat_id: str) -> bool:
        """
        关闭指定chat_id的DuckDB管理器

        :param chat_id: 聊天ID
        :return: 是否成功关闭
        """
        if chat_id in self._chat_managers:
            try:
                self._chat_managers[chat_id].close()
                del self._chat_managers[chat_id]
                if chat_id in self._last_access:
                    del self._last_access[chat_id]
                logger.info(f"已关闭chat_id '{chat_id}' 的DuckDB管理器实例")
                return True
            except Exception as e:
                logger.error(f"关闭chat_id '{chat_id}' 的DuckDB管理器失败: {str(e)}")
                return False
        return False

    def cleanup_expired_sessions(self):
        """
        清理过期的会话
        """
        current_time = time.time()
        expired_chats = []

        for chat_id, last_access in self._last_access.items():
            if current_time - last_access > self._session_timeout:
                expired_chats.append(chat_id)

        for chat_id in expired_chats:
            logger.info(f"清理过期会话: {chat_id}")
            self.close_manager(chat_id)

    def get_active_chat_count(self) -> int:
        """
        获取活跃的聊天数量

        :return: 活跃聊天数量
        """
        return len(self._chat_managers)

    def get_chat_list(self) -> List[str]:
        """
        获取所有活跃的chat_id列表

        :return: chat_id列表
        """
        return list(self._chat_managers.keys())

    def close_all(self):
        """
        关闭所有聊天会话的DuckDB管理器
        """
        for chat_id in list(self._chat_managers.keys()):
            self.close_manager(chat_id)
        logger.info("已关闭所有聊天会话的DuckDB管理器实例")


# 全局聊天级别管理器实例
_chat_duckdb_manager: Optional[ChatDuckDBManager] = None


def get_chat_duckdb_manager() -> ChatDuckDBManager:
    """
    获取全局聊天级别DuckDB管理器实例（单例模式）

    :return: ChatDuckDBManager实例
    """
    global _chat_duckdb_manager
    if _chat_duckdb_manager is None:
        _chat_duckdb_manager = ChatDuckDBManager()
        logger.info("创建全局聊天级别DuckDB管理器实例")
    return _chat_duckdb_manager


def get_duckdb_manager(chat_id: str = None) -> ExcelDuckDBManager:
    """
    获取DuckDB管理器实例

    :param chat_id: 聊天ID，如果提供则获取chat_id级别的管理器，否则使用全局默认管理器
    :return: ExcelDuckDBManager实例
    """
    if chat_id:
        # 使用chat_id级别的管理器
        chat_manager = get_chat_duckdb_manager()
        return chat_manager.get_manager(chat_id)
    else:
        # 向后兼容：如果没有提供chat_id，使用默认的全局管理器
        return get_default_duckdb_manager()


def get_default_duckdb_manager() -> ExcelDuckDBManager:
    """
    获取默认的全局DuckDB管理器实例（向后兼容）

    :return: ExcelDuckDBManager实例
    """
    # 创建一个默认的管理器实例
    if not hasattr(get_default_duckdb_manager, "_default_manager"):
        get_default_duckdb_manager._default_manager = ExcelDuckDBManager()
        logger.info("创建默认全局DuckDB管理器实例")
    return get_default_duckdb_manager._default_manager


def close_duckdb_manager(chat_id: str = None):
    """
    关闭DuckDB管理器

    :param chat_id: 聊天ID，如果提供则关闭指定chat_id的管理器，否则关闭默认管理器
    """
    if chat_id:
        # 关闭指定chat_id的管理器
        chat_manager = get_chat_duckdb_manager()
        chat_manager.close_manager(chat_id)
    else:
        # 向后兼容：关闭默认管理器
        if hasattr(get_default_duckdb_manager, "_default_manager"):
            get_default_duckdb_manager._default_manager.close()
            get_default_duckdb_manager._default_manager = None
            logger.info("默认全局DuckDB管理器已关闭")
