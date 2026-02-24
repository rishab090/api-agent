import sqlite3
from faker import Faker
import random
from datetime import datetime, timedelta

fake = Faker()

DB_NAME = "test.db"

def create_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        email TEXT,
        country TEXT,
        signup_date DATE
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS products (
        product_id INTEGER PRIMARY KEY,
        product_name TEXT,
        category TEXT,
        price REAL
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER PRIMARY KEY,
        user_id INTEGER,
        product_id INTEGER,
        order_date DATE,
        quantity INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(user_id),
        FOREIGN KEY(product_id) REFERENCES products(product_id)
    )
    ''')


    users = []
    for _ in range(50):
        users.append((
            fake.name(),
            fake.email(),
            fake.country(),
            fake.date_between(start_date='-2y', end_date='today')
        ))
    cursor.executemany('INSERT INTO users (name, email, country, signup_date) VALUES (?,?,?,?)', users)

    products = [
        ("Athena", "Thermal Plates", 12000.00),
        ("Vesta", "Violet Plates", 25000.50),
        ("Spartan", "UV Plates", 35000.00),
        ("Thermostar T9", "Platesetters", 45000.00),
        ("RAPTOR 85P", "Plate Processors", 29900.99),
        ("Polset", "Printing Blankets", 12000.00),
        ("Rapid-Web", "Printing Blankets", 45000.00),
        ("VioGreen Plus", "Violet Plates", 40000.00),
        ("VioStar Plus", "Violet Plates", 15000.00),
        ("Enfocus Family", "PDF Automation", 5000.00)
    ]
    cursor.executemany('INSERT INTO products (product_name, category, price) VALUES (?,?,?)', products)

    orders = []
    for _ in range(200):
        u_id = random.randint(1, 50)
        p_id = random.randint(1, 10)
        orders.append((
            u_id,
            p_id,
            fake.date_between(start_date='-1y', end_date='today'),
            random.randint(1, 5)
        ))
    cursor.executemany('INSERT INTO orders (user_id, product_id, order_date, quantity) VALUES (?,?,?,?)', orders)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    create_database()