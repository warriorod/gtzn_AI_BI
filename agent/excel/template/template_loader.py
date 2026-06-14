"""
表格问答 YAML 模板加载器
支持缓存机制，提高性能
"""

import logging
import yaml
from functools import cache
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# 基础路径配置
TEMPLATE_DIR = Path(__file__).parent / "yaml"
BASE_TEMPLATE_PATH = TEMPLATE_DIR / "template.yaml"
SQL_TEMPLATES_DIR = TEMPLATE_DIR / "sql_examples"


@cache
def _load_template_file(file_path: Path) -> Dict[str, Any]:
    """
    内部函数：加载并解析YAML文件（带缓存）
    
    Args:
        file_path: YAML 文件路径
        
    Returns:
        解析后的字典
        
    Raises:
        FileNotFoundError: 文件不存在
        ValueError: YAML 解析错误
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Template file not found at {file_path}")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing YAML file {file_path}: {e}")


class ExcelTemplateLoader:
    """
    表格问答 YAML 模板加载器，支持缓存机制
    """
    
    @staticmethod
    def load_base_template() -> Dict[str, Any]:
        """
        获取基础模板（自动缓存）
        
        Returns:
            基础模板字典，包含所有模板模块
        """
        return _load_template_file(BASE_TEMPLATE_PATH)
    
    @staticmethod
    def load_sql_template() -> Dict[str, Any]:
        """
        获取 SQL 模板（Excel 使用 DuckDB 规则）
        
        Returns:
            SQL 模板字典
        """
        template_path = SQL_TEMPLATES_DIR / "DuckDB.yaml"
        
        # 如果文件不存在，尝试从数据问答模板目录加载
        if not template_path.exists():
            # 尝试从数据问答模板目录加载 PostgreSQL 模板作为备选
            text2sql_template_path = Path(__file__).parent.parent.parent / "text2sql" / "template" / "yaml" / "sql_examples" / "PostgreSQL.yaml"
            if text2sql_template_path.exists():
                logger.info("使用数据问答的 PostgreSQL 模板作为备选")
                return _load_template_file(text2sql_template_path)
            else:
                logger.warning("DuckDB 模板文件不存在，使用空模板")
                return {"template": {}}
        
        return _load_template_file(template_path)
    
    @staticmethod
    def reload_all_templates():
        """
        清空所有模板缓存（用于开发时重新加载模板）
        """
        _load_template_file.cache_clear()
        logger.info("All template caches cleared")

