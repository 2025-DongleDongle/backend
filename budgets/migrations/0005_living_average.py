from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [("budgets", "0004_base_average")]

    operations = [
        migrations.RunSQL(
            """
            CREATE TABLE IF NOT EXISTS living_avg_cost (
                id INT AUTO_INCREMENT PRIMARY KEY,
                country VARCHAR(50) UNIQUE,
                transit_avg INT,
                food_avg INT
            );
            """
        ),

        # --- 더미데이터 삽입(KRW 기준) ---
        migrations.RunSQL(
            """
            INSERT INTO living_avg_cost(country, transit_avg, food_avg)
            VALUES
                ('미국', 100000, 500000),
                ('일본', 60000, 400000),
                ('독일', 90000, 550000),
                ('프랑스', 100000, 600000),
                ('중국', 50000, 350000),
                ('대만', 40000, 300000),
                ('캐나다', 90000, 550000),
                ('이탈리아', 80000, 500000),
                ('네덜란드', 110000, 600000),
                ('영국', 120000, 650000)
            ON DUPLICATE KEY UPDATE
                transit_avg = VALUES(transit_avg),
                food_avg = VALUES(food_avg);
            """
        )
    ]
