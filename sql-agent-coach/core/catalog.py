from __future__ import annotations

SCENARIOS = {
    "ecommerce": {
        "name": "电商订单分析",
        "description": "围绕客户、商品、订单和订单明细训练筛选、连接、聚合与窗口分析。",
        "schema_sql": """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    join_date TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
""",
        "data_sql": """
INSERT INTO customers VALUES
    (1, 'Alice', 'Shanghai', '2024-01-10'),
    (2, 'Bob', 'Beijing', '2024-03-02'),
    (3, 'Cindy', 'Shanghai', '2024-06-18'),
    (4, 'David', 'Shenzhen', '2023-11-05'),
    (5, 'Eva', 'Hangzhou', '2024-09-21');

INSERT INTO products VALUES
    (1, 'Keyboard', 'Electronics', 199.00),
    (2, 'Mouse', 'Electronics', 99.00),
    (3, 'Notebook', 'Office', 25.00),
    (4, 'Coffee Beans', 'Grocery', 88.00),
    (5, 'Monitor', 'Electronics', 1299.00);

INSERT INTO orders VALUES
    (101, 1, '2025-01-05', 'paid'),
    (102, 2, '2025-01-06', 'paid'),
    (103, 1, '2025-01-20', 'refunded'),
    (104, 3, '2025-02-02', 'paid'),
    (105, 4, '2025-02-11', 'paid'),
    (106, 5, '2025-02-18', 'pending'),
    (107, 3, '2025-03-01', 'paid');

INSERT INTO order_items VALUES
    (1001, 101, 1, 1, 199.00),
    (1002, 101, 2, 2, 99.00),
    (1003, 102, 5, 1, 1299.00),
    (1004, 103, 4, 3, 88.00),
    (1005, 104, 3, 10, 25.00),
    (1006, 104, 2, 1, 99.00),
    (1007, 105, 4, 2, 88.00),
    (1008, 106, 1, 1, 199.00),
    (1009, 107, 5, 1, 1299.00),
    (1010, 107, 2, 1, 99.00);
""",
    },
    "campus": {
        "name": "校园课程管理",
        "description": "围绕学生、课程、教师和选课成绩训练 join、group by、having 与子查询。",
        "schema_sql": """
CREATE TABLE students (
    student_id INTEGER PRIMARY KEY,
    student_name TEXT NOT NULL,
    major TEXT NOT NULL,
    grade INTEGER NOT NULL
);

CREATE TABLE teachers (
    teacher_id INTEGER PRIMARY KEY,
    teacher_name TEXT NOT NULL,
    department TEXT NOT NULL
);

CREATE TABLE courses (
    course_id INTEGER PRIMARY KEY,
    course_name TEXT NOT NULL,
    teacher_id INTEGER NOT NULL,
    credit INTEGER NOT NULL,
    FOREIGN KEY (teacher_id) REFERENCES teachers(teacher_id)
);

CREATE TABLE enrollments (
    enrollment_id INTEGER PRIMARY KEY,
    student_id INTEGER NOT NULL,
    course_id INTEGER NOT NULL,
    score INTEGER NOT NULL,
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);
""",
        "data_sql": """
INSERT INTO students VALUES
    (1, 'Li Hua', 'Computer Science', 2023),
    (2, 'Wang Mei', 'Data Science', 2023),
    (3, 'Zhang Wei', 'Computer Science', 2022),
    (4, 'Chen Yu', 'Finance', 2024),
    (5, 'Zhao Min', 'Data Science', 2022);

INSERT INTO teachers VALUES
    (1, 'Prof. Lin', 'Computer Science'),
    (2, 'Prof. Gao', 'Mathematics'),
    (3, 'Prof. Sun', 'Business');

INSERT INTO courses VALUES
    (1, 'Database Systems', 1, 3),
    (2, 'Linear Algebra', 2, 4),
    (3, 'Business Analytics', 3, 2),
    (4, 'Machine Learning', 1, 4);

INSERT INTO enrollments VALUES
    (1, 1, 1, 92),
    (2, 1, 2, 81),
    (3, 2, 1, 88),
    (4, 2, 4, 95),
    (5, 3, 1, 76),
    (6, 3, 3, 85),
    (7, 4, 3, 91),
    (8, 5, 2, 73),
    (9, 5, 4, 89);
""",
    },
}


EXERCISES = [
    {
        "id": "eco-basic-where",
        "scenario": "ecommerce",
        "difficulty": "入门",
        "kind": "筛选查询",
        "title": "找到上海客户",
        "prompt": "查询所有城市为 Shanghai 的客户姓名和加入日期，按加入日期升序排列。",
        "expected_sql": """
SELECT name, join_date
FROM customers
WHERE city = 'Shanghai'
ORDER BY join_date;
""",
        "concepts": ["SELECT", "WHERE", "ORDER BY"],
        "hints": ["先从 customers 表取 name 和 join_date。", "筛选条件是 city = 'Shanghai'。"],
    },
    {
        "id": "eco-basic-join",
        "scenario": "ecommerce",
        "difficulty": "入门",
        "kind": "连接查询",
        "title": "订单对应客户",
        "prompt": "查询已支付订单的订单号、客户姓名、订单日期，按订单号升序排列。",
        "expected_sql": """
SELECT o.order_id, c.name, o.order_date
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.status = 'paid'
ORDER BY o.order_id;
""",
        "concepts": ["JOIN", "WHERE", "ORDER BY"],
        "hints": ["orders 需要和 customers 按 customer_id 连接。", "只保留 status = 'paid'。"],
    },
    {
        "id": "eco-mid-aggregate",
        "scenario": "ecommerce",
        "difficulty": "进阶",
        "kind": "聚合统计",
        "title": "客户支付总额",
        "prompt": "统计每个客户已支付订单的总消费金额，输出客户姓名和 total_amount，按 total_amount 降序排列。",
        "expected_sql": """
SELECT c.name, ROUND(SUM(oi.quantity * oi.unit_price), 2) AS total_amount
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN order_items oi ON o.order_id = oi.order_id
WHERE o.status = 'paid'
GROUP BY c.customer_id, c.name
ORDER BY total_amount DESC;
""",
        "concepts": ["JOIN", "SUM", "GROUP BY", "ORDER BY"],
        "hints": ["金额来自 quantity * unit_price。", "只统计 paid 订单。", "按客户分组。"],
    },
    {
        "id": "eco-hard-subquery",
        "scenario": "ecommerce",
        "difficulty": "挑战",
        "kind": "子查询",
        "title": "高于平均订单额的订单",
        "prompt": "查询已支付订单中，订单金额高于所有已支付订单平均金额的订单号和 order_amount，按 order_amount 降序排列。",
        "expected_sql": """
WITH paid_order_amount AS (
    SELECT o.order_id, SUM(oi.quantity * oi.unit_price) AS order_amount
    FROM orders o
    JOIN order_items oi ON o.order_id = oi.order_id
    WHERE o.status = 'paid'
    GROUP BY o.order_id
)
SELECT order_id, ROUND(order_amount, 2) AS order_amount
FROM paid_order_amount
WHERE order_amount > (SELECT AVG(order_amount) FROM paid_order_amount)
ORDER BY order_amount DESC;
""",
        "concepts": ["WITH", "AVG", "子查询", "GROUP BY"],
        "hints": ["先计算每个 paid 订单的金额。", "再和平均订单金额比较。"],
    },
    {
        "id": "campus-basic-select",
        "scenario": "campus",
        "difficulty": "入门",
        "kind": "筛选查询",
        "title": "计算机专业学生",
        "prompt": "查询 Computer Science 专业学生的姓名和入学年级，按 student_id 升序排列。",
        "expected_sql": """
SELECT student_name, grade
FROM students
WHERE major = 'Computer Science'
ORDER BY student_id;
""",
        "concepts": ["SELECT", "WHERE"],
        "hints": ["目标表是 students。", "major 字段保存专业名称。"],
    },
    {
        "id": "campus-mid-join",
        "scenario": "campus",
        "difficulty": "进阶",
        "kind": "连接查询",
        "title": "课程教师列表",
        "prompt": "查询每门课程的课程名、教师姓名和学分，按学分降序、课程名升序排列。",
        "expected_sql": """
SELECT c.course_name, t.teacher_name, c.credit
FROM courses c
JOIN teachers t ON c.teacher_id = t.teacher_id
ORDER BY c.credit DESC, c.course_name ASC;
""",
        "concepts": ["JOIN", "ORDER BY"],
        "hints": ["courses 与 teachers 通过 teacher_id 关联。"],
    },
    {
        "id": "campus-mid-having",
        "scenario": "campus",
        "difficulty": "进阶",
        "kind": "聚合统计",
        "title": "平均分超过 85 的课程",
        "prompt": "查询平均分超过 85 的课程名和 avg_score，avg_score 保留 2 位小数，按 avg_score 降序排列。",
        "expected_sql": """
SELECT c.course_name, ROUND(AVG(e.score), 2) AS avg_score
FROM courses c
JOIN enrollments e ON c.course_id = e.course_id
GROUP BY c.course_id, c.course_name
HAVING AVG(e.score) > 85
ORDER BY avg_score DESC;
""",
        "concepts": ["AVG", "GROUP BY", "HAVING"],
        "hints": ["先按课程分组。", "过滤聚合结果需要 HAVING。"],
    },
    {
        "id": "campus-hard-window",
        "scenario": "campus",
        "difficulty": "挑战",
        "kind": "窗口函数",
        "title": "每个专业的最高分学生",
        "prompt": "查询每个专业中单科最高分记录，输出 major、student_name、course_name、score，按 major 升序排列。",
        "expected_sql": """
WITH ranked_scores AS (
    SELECT s.major, s.student_name, c.course_name, e.score,
           RANK() OVER (PARTITION BY s.major ORDER BY e.score DESC) AS score_rank
    FROM students s
    JOIN enrollments e ON s.student_id = e.student_id
    JOIN courses c ON e.course_id = c.course_id
)
SELECT major, student_name, course_name, score
FROM ranked_scores
WHERE score_rank = 1
ORDER BY major;
""",
        "concepts": ["窗口函数", "RANK", "PARTITION BY"],
        "hints": ["用 RANK() OVER 按专业分区。", "最高分对应 score_rank = 1。"],
    },
]


DIFFICULTIES = ["入门", "进阶", "挑战"]
KINDS = ["筛选查询", "连接查询", "聚合统计", "子查询", "窗口函数"]
