import sqlite3
from datetime import datetime, timedelta
import json
import sys

# 连接到SQLite数据库
conn = sqlite3.connect('keyboard_monitor.db')
c = conn.cursor()

# 获取命令行参数来确定查询的日期范围
try:
    days_ago = int(sys.argv[1])
except (IndexError, ValueError):
    print("Please provide the number of days ago as an integer.")
    sys.exit(1)

# 计算开始和结束日期
end_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)
start_date = end_date - timedelta(days=1)


# 1. 统计按键频率最高和最低的单键
def count_key_hits(start_date, end_date):
    c.execute('''
        SELECT hits, COUNT(*) as cnt 
        FROM keyboard_monitor 
        WHERE ts BETWEEN ? AND ? AND hits NOT LIKE '%+%' 
        GROUP BY hits 
        ORDER BY cnt DESC
    ''', (start_date.isoformat(), end_date.isoformat()))
    results = c.fetchall()
    top_hits = [{"key": row[0], "count": row[1]} for row in results[:10]]
    least_hits = [{"key": row[0], "count": row[1]} for row in results[-10:]]
    return {"top_hits": top_hits, "least_hits": least_hits}


# 2. 统计快捷键组合
def count_combinations_hits(start_date, end_date):
    c.execute('''
        SELECT hits, COUNT(*) as cnt 
        FROM keyboard_monitor 
        WHERE ts BETWEEN ? AND ? AND hits LIKE '%+%' 
        GROUP BY hits 
        ORDER BY cnt DESC
    ''', (start_date.isoformat(), end_date.isoformat()))
    results = c.fetchall()
    top_combinations = [{"combination": row[0], "count": row[1]} for row in results[:5]]
    least_combinations = [{"combination": row[0], "count": row[1]} for row in results[-5:]]
    return {"top_combinations": top_combinations, "least_combinations": least_combinations}


# 3. 按小时统计按键次数并进行时间段聚合
def hits_over_time(start_date, end_date):
    c.execute('''
        SELECT strftime('%Y-%m-%d %H', ts) as hour, COUNT(*) 
        FROM keyboard_monitor 
        WHERE ts BETWEEN ? AND ?
        GROUP BY hour
    ''', (start_date.isoformat(), end_date.isoformat()))
    hourly_results = c.fetchall()
    hourly_counts = [{"hour": hour, "count": count} for hour, count in hourly_results]

    # 时间段聚合统计
    time_periods = {
        'Morning': range(5, 12),
        'Afternoon': range(12, 17),
        'Daytime': range(5, 17),
        'Evening': range(17, 21),
        'Night': range(21, 24),
        'Late Night': range(0, 5)
    }
    period_counts = {period: 0 for period in time_periods}
    for hour, count in hourly_results:
        hour = int(hour[-2:])
        for period, hours in time_periods.items():
            if hour in hours:
                period_counts[period] += count
    return {"hourly_counts": hourly_counts, "period_counts": period_counts}


# 每次按键操作的平均耗时（秒）
average_key_press_duration = 0.2


# 统计所有按键的预计消耗时间
def calculate_total_time_spent(start_date, end_date):
    c.execute('''
        SELECT COUNT(*) 
        FROM keyboard_monitor 
        WHERE ts BETWEEN ? AND ?
    ''', (start_date.isoformat(), end_date.isoformat()))
    total_hits = c.fetchone()[0]
    total_time_spent = total_hits * average_key_press_duration
    return total_time_spent


# 主函数，接收日期范围参数
def main(start_date, end_date):
    data = {}
    data.update(count_key_hits(start_date, end_date))
    data.update(count_combinations_hits(start_date, end_date))
    data.update(hits_over_time(start_date, end_date))

    total_time_spent = calculate_total_time_spent(start_date, end_date)
    data["total_time_spent_sec"] = total_time_spent
    # 将数据转换为JSON格式
    json_data = json.dumps(data, indent=4)
    print(json_data)


# 调用主函数
if __name__ == "__main__":
    main(start_date, end_date)

# 关闭数据库连接
conn.close()
