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
import re
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


# ========================== 风格推断函数 ==========================

def _infer_style_from_keywords(keywords: str) -> str:
    """
    根据关键词自动推断卡片风格（兜底逻辑）
    
    参数：
        keywords: 关键词字符串（用逗号分隔）
    
    返回：
        推断出的风格名称
    """
    # 定义每种风格的关键词映射
    # 👉 就像一个"词典"：告诉电脑什么关键词对应什么风格
    style_keywords = {
        "healing": ["治愈", "疗愈", "温暖", "爱", "情感", "创伤", "心理", "情绪", "陪伴", "关怀"],
        # 👆 healing = 治愈系：关于情感疗愈、心理健康的内容
        
        "philosophy": ["哲学", "存在", "意义", "人生", "思考", "智慧", "真理", "意识", "灵魂", "形而上学"],
        # 👆 philosophy = 哲学系：关于存在、意义、思考的内容
        
        "inspiration": ["长期主义", "励志", "奋斗", "成功", "目标", "行动", "坚持", "梦想", "勇气", "努力", "突破", "成长", "改变", "运气", "因果律", "持续行动"],
        # 👆 inspiration = 励志系：关于奋斗、成长、突破的内容
        
        "eastern": ["禅", "道", "佛", "东方", "太极", "阴阳", "修行", "开悟", "涅槃", "无为", "自然", "天人合一"],
        # 👆 eastern = 东方系：关于禅、道、东方哲学的内容
        
        "minimal": ["极简", "简单", "专注", "效率", "断舍离", "整理", "秩序", "简约", "纯粹", "清净"],
        # 👆 minimal = 极简系：关于极简生活、专注效率的内容
        
        "elegant": ["优雅", "美学", "艺术", "文化", "历史", "经典", "品味", "格调", "精致", "匠心"],
        # 👆 elegant = 优雅系：关于艺术、文化、品味的内容
    }
    
    # 如果没有关键词，直接返回"未分类"
    if not keywords:
        return "未分类"
    
    # 把关键词拆分成列表（支持中英文逗号）
    keyword_list = [k.strip() for k in re.split(r'[,，、]', keywords)]
    # 👆 使用 re.split 支持中英文逗号和顿号
    
    # 统计每种风格匹配了多少个关键词
    style_scores: Dict[str, int] = {}
    for style, style_kws in style_keywords.items():
        score = sum(1 for kw in keyword_list if kw in style_kws)
        # 👆 统计当前关键词列表里有多少个属于这个风格
        style_scores[style] = score
    
    # 找出得分最高的风格
    best_style = max(style_scores, key=style_scores.get)
    best_score = style_scores[best_style]
    
    # 如果得分大于 0，返回该风格；否则返回"未分类"
    return best_style if best_score > 0 else "未分类"


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
        # 👉 style 字段有兜底逻辑：如果为空，就根据关键词自动推断
        keywords = card_data.get("keywords", "")
        style = card_data.get("style", "") or _infer_style_from_keywords(keywords)
        # 👆 如果 style 为空字符串，就调用推断函数；否则用原始值
        
        values = (
            card_data.get("title", ""),
            card_data.get("quote", ""),
            card_data.get("source_quote", ""),
            card_data.get("summary", ""),
            keywords,
            card_data.get("book", ""),
            card_data.get("movie", ""),
            style,
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

    def batch_delete_cards(self, card_ids: List[int]) -> int:
        """
        批量删除卡片（同时删除对应的图片文件）
        
        参数：
            card_ids: 要删除的卡片 ID 列表
        
        返回：
            成功删除的数量
        """
        if not card_ids:
            return 0
        
        # 先获取所有要删除的卡片信息
        deleted_count = 0
        for card_id in card_ids:
            card = self.get_card_by_id(card_id)
            if card:
                # 删除对应的图片文件（如果存在）
                image_path = card.get("card_image_path", "")
                if image_path and os.path.exists(image_path):
                    try:
                        os.remove(image_path)
                    except Exception as e:
                        logger.warning(f"删除图片文件失败: {image_path}, 错误: {e}")
                deleted_count += 1
        
        # 批量删除数据库记录
        placeholders = ",".join(["?" for _ in card_ids])
        delete_sql = f"DELETE FROM cards WHERE id IN ({placeholders})"
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(delete_sql, card_ids)
                conn.commit()
            
            logger.info(f"批量删除完成: 删除了 {deleted_count} 张卡片")
            return deleted_count
        except Exception as e:
            logger.error(f"批量删除卡片失败: {e}")
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

    def get_all_tags(self) -> List[Dict[str, Any]]:
        """
        获取所有标签及其使用次数（从 keywords 字段统计）
        
        返回：
            标签列表，每个元素包含 tag（标签名）和 count（使用次数）
            按使用次数倒序排列
        """
        # 先获取所有卡片的 keywords
        cards = self.get_all_cards(limit=1000)
        
        # 统计每个标签的出现次数
        tag_counts: Dict[str, int] = {}
        for card in cards:
            keywords = card.get("keywords", "")
            if keywords:
                # keywords 可能用中文逗号或英文逗号分隔
                for tag in re.split(r'[,，、]', keywords):
                    tag = tag.strip()  # 去掉空格
                    if tag:
                        tag_counts[tag] = tag_counts.get(tag, 0) + 1
        
        # 转换成列表并排序
        result = [
            {"tag": tag, "count": count}
            for tag, count in tag_counts.items()
        ]
        result.sort(key=lambda x: x["count"], reverse=True)
        # 👆 按使用次数从多到少排序
        
        logger.info(f"统计到 {len(result)} 个标签")
        return result

    def get_all_styles(self) -> List[Dict[str, Any]]:
        """
        获取所有风格分类及其卡片数量
        
        返回：
            风格列表，每个元素包含 style（风格名）和 count（卡片数量）
        """
        # 先获取所有卡片
        cards = self.get_all_cards(limit=1000)
        
        # 统计每个风格的卡片数量
        style_counts: Dict[str, int] = {}
        for card in cards:
            style = card.get("style", "")
            if style:
                style_counts[style] = style_counts.get(style, 0) + 1
            else:
                style_counts["未分类"] = style_counts.get("未分类", 0) + 1
        
        # 转换成列表
        result = [
            {"style": style, "count": count}
            for style, count in style_counts.items()
        ]
        result.sort(key=lambda x: x["count"], reverse=True)
        
        logger.info(f"统计到 {len(result)} 个风格分类")
        return result

    def filter_cards(
        self,
        keyword: str = "",
        tags: List[str] = None,
        style: str = ""
    ) -> List[Dict[str, Any]]:
        """
        组合筛选卡片（支持搜索 + 标签 + 风格的组合筛选）
        
        参数：
            keyword: 搜索关键词（可选）
            tags: 标签列表，卡片需要包含所有指定标签（可选）
            style: 风格筛选（可选）
        
        返回：
            匹配的卡片列表
        """
        # 先获取所有卡片作为基础
        cards = self.get_all_cards(limit=1000)
        
        # 按关键词筛选
        if keyword:
            keyword_lower = keyword.lower()
            cards = [
                card for card in cards
                if (
                    keyword_lower in card.get("title", "").lower() or
                    keyword_lower in card.get("quote", "").lower() or
                    keyword_lower in card.get("summary", "").lower() or
                    keyword_lower in card.get("keywords", "").lower()
                )
            ]
        
        # 按风格筛选
        if style:
            cards = [card for card in cards if card.get("style", "") == style]
        
        # 按标签筛选（卡片需要包含所有指定标签）
        if tags:
            cards = [
                card for card in cards
                if all(
                    tag in card.get("keywords", "")
                    for tag in tags
                )
            ]
        
        logger.info(
            f"组合筛选: keyword='{keyword}', tags={tags}, style='{style}', "
            f"结果: {len(cards)} 张卡片"
        )
        return cards

    def get_cards_grouped_by_style(
        self,
        keyword: str = "",
        tags: List[str] = None
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取按风格分组的卡片（支持关键词和标签筛选）
        
        参数：
            keyword: 搜索关键词（可选）
            tags: 标签列表（可选）
        
        返回：
            字典，key 是风格名，value 是该风格下的卡片列表
        """
        # 先筛选卡片
        cards = self.filter_cards(keyword=keyword, tags=tags)
        
        # 按风格分组
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for card in cards:
            style = card.get("style", "") or "未分类"
            if style not in grouped:
                grouped[style] = []
            grouped[style].append(card)
        
        logger.info(f"按风格分组: {len(grouped)} 个分组")
        return grouped


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
    
    # 测试：标签统计
    tags = db.get_all_tags()
    print(f"\n标签统计: {len(tags)} 个标签")
    for tag_info in tags[:5]:
        print(f"  #{tag_info['tag']}: {tag_info['count']}张")
    
    # 测试：风格统计
    styles = db.get_all_styles()
    print(f"\n风格统计: {len(styles)} 个风格")
    for style_info in styles:
        print(f"  {style_info['style']}: {style_info['count']}张")
    
    # 测试：组合筛选
    filtered = db.filter_cards(keyword="测试", tags=["测试"])
    print(f"\n组合筛选: keyword='测试', tags=['测试'] => {len(filtered)} 张")
    
    # 测试：按风格分组
    grouped = db.get_cards_grouped_by_style(keyword="")
    print(f"\n按风格分组: {len(grouped)} 个分组")
    for style, cards in grouped.items():
        print(f"  {style}: {len(cards)}张")


if __name__ == "__main__":
    main()