"""样本代码：包含若干典型缺陷，用于 Spike 验证。"""

import os
import sqlite3


# 缺陷 1: 硬编码 API 密钥（安全）
API_KEY = "sk_live_1234567890abcdef"
DB_URL = "sqlite:///app.db"


def get_user(user_id):
    """根据 ID 查询用户。"""
    # 缺陷 2: SQL 注入（安全 - critical）
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)
    return cursor.fetchone()


def list_orders(user_id):
    """查询用户所有订单。"""
    # 缺陷 3: N+1 查询（性能 - medium）
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute(f"SELECT id FROM orders WHERE user_id = {user_id}")
    order_ids = cursor.fetchall()
    results = []
    for oid in order_ids:
        # 循环内查询，N+1 模式
        cursor.execute(f"SELECT * FROM order_items WHERE order_id = {oid[0]}")
        results.append(cursor.fetchone())
    return results


def process_order(order):
    """处理订单并发送邮件。"""
    # 缺陷 4: 空值未检查（正确性 - high）
    send_email(order.user.email)
    return True


def send_email(address):
    """发送邮件。"""
    # 缺陷 5: 宽泛异常捕获（正确性 - medium）
    try:
        # 发送逻辑
        pass
    except Exception:
        pass  # 吞掉异常
    return True


class UserService:
    """用户服务。"""

    def __init__(self, db_url):
        self.db_url = db_url

    def find_by_name(self, name):
        # 同样存在 SQL 注入
        conn = sqlite3.connect(self.db_url)
        cursor = conn.cursor()
        cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
        return cursor.fetchone()

    def update_balance(self, user_id, amount):
        # 缺陷 6: 未校验金额非负（正确性）
        conn = sqlite3.connect(self.db_url)
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE users SET balance = balance + {amount} WHERE id = {user_id}"
        )
        conn.commit()
