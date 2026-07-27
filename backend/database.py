"""
================================================================================
                            AI 知识卡片 · 数据库模块
                      (SQLite Database - MVP Version)
================================================================================
这个文件的作用：
    管理卡片数据的存储和读取，就像一个"卡片盒子"，
    可以把生成的卡片放进去，以后随时拿出来看。

打个比方：
    这个文件 = "卡片收藏夹"
    - database.db 文件 = "收藏夹本体"（存放所有卡片）
    - save_card() = "把卡片放进收藏夹"
    - get_all_cards() = "把收藏夹里的卡片都拿出来看"
    - search_cards() = "在收藏夹里找特定的卡片"
    - delete_card() = "从收藏夹里移除一张卡片"

技术说明：
    SQLite 是一个轻量级数据库，不需要单独安装服务器，
    数据就存在一个 .db 文件里，非常适合开发和测试。
================================================================================
"""

import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from loguru import logger


# ========================== 数据库配置 ==========================

# 数据库文件路径：项目根目录下的 data/ 文件夹里
DATA_DIR = Path(__file__).parent.parent / "data"
# 👆 当前文件 backend/database.py → 往上走两层到根目录 → 进入 data 文件夹
DB_PATH = DATA_DIR / "cards.db"
# 👆 数据库文件：data/cards.db

# 卡片图片保存目录
GENERATED_DIR = Path(__file__).parent.parent / "assets" / "generated"
# 👆 生成的卡片图片保存在 assets/generated/ 文件夹里


# ========================== 数据库操作类 ==========================

class CardDatabase:
    """
    卡片数据库操作类（就像一个智能卡片管理员）
    
    这个类提供了所有数据库操作方法，包括：
    - 创建数据库表
    - 保存卡片
    - 查询卡片
    - 删除卡片
    """

    def __init__(self, db_path: Path = DB_PATH):
        """
        初始化数据库连接
        
        参数：
            db_path: 数据库文件路径（默认 data/cards.db）
        """
        # 确保 data 文件夹存在
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        # 👆 如果文件夹不存在就创建，exist_ok=True 表示如果存在也不报错
        
        # 确保生成图片的文件夹存在
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        
        self.db_path = db_path
        # 👆 数据库文件的路径
        
        # 创建数据库表（如果表不存在）
        self._create_table()
        logger.info(f"CardDatabase 初始化完成, 数据库路径: {db_path}")

    def _create_table(self):
        """
        创建卡片表（如果表不存在）
        
        表结构说明：
        - id: 主键，自增编号（每张卡片唯一的身份证号）
        - title: 卡片标题
        - quote: 用户输入的金句原文
        - source_quote: 相关名人名言
        - summary: AI深度解读
        - keywords: 关键词（逗号分隔）
        - book: 推荐书籍
        - movie: 推荐电影
        - style: 卡片风格
        - card_image_path: 生成的图片文件路径
        - created_at: 创建时间（自动记录）
        """
        create_sql = """
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            quote TEXT NOT NULL,
            source_quote TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            keywords TEXT DEFAULT '',
            book TEXT DEFAULT '',
            movie TEXT DEFAULT '',
            style TEXT DEFAULT '',
            card_image_path TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
        # 👆 IF NOT EXISTS = 如果表已经存在就不创建，避免报错
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # 👆 建立数据库连接，with 语句会自动关闭连接
                cursor = conn.cursor()
                # 👆 创建一个"游标"，用来执行 SQL 语句
                cursor.execute(create_sql)
                # 👆 执行建表 SQL
                conn.commit()
                # 👆 提交修改
            logger.debug("cards 表创建成功（或已存在）")
        except Exception as e:
            logger.error(f"创建表失败: {e}")
            raise

    def save_card(self, card_data: Dict[str, Any], image_path: str = "") -> int:
        """
        保存一张卡片到数据库
        
        参数：
            card_data: 卡片数据字典（包含 title、quote、summary 等字段）
            image_path: 卡片图片的文件路径（可选）
        
        返回：
            新插入卡片的 ID（整数）
        """
        insert_sql = """
        INSERT INTO cards (
            title, quote, source_quote, summary, keywords, book, movie, style, card_image_path
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # 👆 ? 是占位符，防止 SQL 注入攻击
        
        # 提取字段值，如果字段不存在就用空字符串
        values = (
            card_data.get("title", ""),
            card_data.get("quote", ""),
            card_data.get("source_quote", ""),
            card_data.get("summary", ""),
            card_data.get("keywords", ""),
            card_data.get("book", ""),
            card_data.get("movie", ""),
            card_data.get("style", ""),
            image_path,
        )

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(insert_sql, values)
                # 👆 执行插入语句，把 values 传给占位符
                conn.commit()
                # 👆 提交保存
                
                card_id = cursor.lastrowid
                # 👆 获取刚插入的记录的 ID
                logger.info(f"卡片保存成功, ID={card_id}, title='{card_data.get('title', '')[:20]}...'")
                return card_id
        except Exception as e:
            logger.error(f"保存卡片失败: {e}")
            raise

    def get_all_cards(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """
        查询所有卡片（按创建时间倒序，最新的在前）
        
        参数：
            limit: 返回多少条（默认 100）
            offset: 跳过前多少条（用于分页）
        
        返回：
            卡片列表，每个元素是一个字典
        """
        select_sql = """
        SELECT id, title, quote, source_quote, summary, keywords, book, movie, style, card_image_path, created_at
        FROM cards
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # 设置返回结果为字典格式（默认是元组）
                conn.row_factory = sqlite3.Row
                # 👆 这样查询结果可以用 row['title'] 而不是 row[0]
                
                cursor = conn.cursor()
                cursor.execute(select_sql, (limit, offset))
                rows = cursor.fetchall()
                # 👆 获取所有查询结果
                
                # 把 Row 对象转换成字典列表
                cards = [dict(row) for row in rows]
                logger.info(f"查询到 {len(cards)} 张卡片")
                return cards
        except Exception as e:
            logger.error(f"查询卡片失败: {e}")
            raise

    def get_card_by_id(self, card_id: int) -> Optional[Dict[str, Any]]:
        """
        根据 ID 查询单张卡片
        
        参数：
            card_id: 卡片 ID
        
        返回：
            卡片字典；如果没找到，返回 None
        """
        select_sql = """
        SELECT id, title, quote, source_quote, summary, keywords, book, movie, style, card_image_path, created_at
        FROM cards
        WHERE id = ?
        """

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(select_sql, (card_id,))
                row = cursor.fetchone()
                # 👆 获取一条记录
                
                if row:
                    return dict(row)
                else:
                    logger.warning(f"未找到卡片, ID={card_id}")
                    return None
        except Exception as e:
            logger.error(f"查询卡片失败: {e}")
            raise

    def search_cards(self, keyword: str) -> List[Dict[str, Any]]:
        """
        按关键词搜索卡片（在 title、quote、summary、keywords 中搜索）
        
        参数：
            keyword: 搜索关键词
        
        返回：
            匹配的卡片列表
        """
        search_sql = """
        SELECT id, title, quote, source_quote, summary, keywords, book, movie, style, card_image_path, created_at
        FROM cards
        WHERE title LIKE ? OR quote LIKE ? OR summary LIKE ? OR keywords LIKE ?
        ORDER BY created_at DESC
        """
        
        # 构建模糊查询模式：%keyword%
        pattern = f"%{keyword}%"
        # 👆 % 是通配符，匹配任意字符
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(search_sql, (pattern, pattern, pattern, pattern))
                rows = cursor.fetchall()
                
                cards = [dict(row) for row in rows]
                logger.info(f"搜索关键词 '{keyword}', 找到 {len(cards)} 张卡片")
                return cards
        except Exception as e:
            logger.error(f"搜索卡片失败: {e}")
            raise

    def delete_card(self, card_id: int) -> bool:
        """
        删除一张卡片（同时删除对应的图片文件）
        
        参数：
            card_id: 要删除的卡片 ID
        
        返回：
            删除成功返回 True，没找到返回 False
        """
        # 先获取卡片信息（包括图片路径）
        card = self.get_card_by_id(card_id)
        if not card:
            return False
        
        # 删除数据库记录
        delete_sql = "DELETE FROM cards WHERE id = ?"

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(delete_sql, (card_id,))
                conn.commit()
                
                # cursor.rowcount 表示受影响的行数
                if cursor.rowcount > 0:
                    logger.info(f"卡片删除成功, ID={card_id}")
                    
                    # 删除对应的图片文件（如果存在）
                    image_path = card.get("card_image_path", "")
                    if image_path and os.path.exists(image_path):
                        os.remove(image_path)
                        logger.info(f"图片文件删除成功: {image_path}")
                    
                    return True
                else:
                    logger.warning(f"未找到要删除的卡片, ID={card_id}")
                    return False
        except Exception as e:
            logger.error(f"删除卡片失败: {e}")
            raise

    def get_card_count(self) -> int:
        """
        获取卡片总数
        
        返回：
            卡片数量（整数）
        """
        count_sql = "SELECT COUNT(*) FROM cards"

        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(count_sql)
                result = cursor.fetchone()
                # 👆 fetchone() 返回一个元组，第一个元素就是数量
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"获取卡片数量失败: {e}")
            raise


# ========================== 便捷函数 ==========================

def get_db() -> CardDatabase:
    """
    获取数据库实例（快捷方式）
    
    返回：
        CardDatabase 实例
    """
    return CardDatabase()


# ========================== 自测代码 ==========================

def main():
    """直接运行时的测试代码"""
    # 创建数据库实例
    db = CardDatabase()
    
    # 测试：获取卡片数量
    count = db.get_card_count()
    print(f"当前卡片数量: {count}")
    
    # 测试：如果没有卡片，插入一张测试卡片
    if count == 0:
        test_card = {
            "title": "测试卡片",
            "quote": "这是一张测试卡片",
            "source_quote": "测试引用",
            "summary": "这是测试摘要",
            "keywords": "测试,示例",
            "book": "《测试之书》",
            "movie": "《测试电影》",
            "style": "minimal",
        }
        card_id = db.save_card(test_card)
        print(f"测试卡片已保存, ID={card_id}")
    
    # 测试：查询所有卡片
    cards = db.get_all_cards()
    print(f"\n查询到 {len(cards)} 张卡片:")
    for card in cards:
        print(f"  ID={card['id']}, title={card['title']}, created_at={card['created_at']}")
    
    # 测试：搜索功能
    search_result = db.search_cards("测试")
    print(f"\n搜索 '测试' 找到 {len(search_result)} 张卡片")


if __name__ == "__main__":
    main()