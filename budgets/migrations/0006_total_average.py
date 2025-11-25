from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [("budgets", "0005_living_average")]

    operations = [
        migrations.RunSQL(
            """
            CREATE TABLE IF NOT EXISTS total_avg_cost (
                id INT AUTO_INCREMENT PRIMARY KEY,
                country VARCHAR(50) UNIQUE,
                min_avg INT,
                max_avg INT
            );
            """
        ),

        # --- 더미데이터 삽입(KRW 기준) ---
        migrations.RunSQL(
            """
            INSERT INTO total_avg_cost(country, min_avg, max_avg)
            VALUES
                ('미국', 5000000, 20000000),
                ('일본', 3000000, 12000000),
                ('독일', 4000000, 15000000),
                ('프랑스', 4500000, 16000000),
                ('중국', 2500000, 9000000),
                ('대만', 2200000, 8000000),
                ('캐나다', 5000000, 18000000),
                ('이탈리아', 4000000, 14000000),
                ('네덜란드', 4500000, 16000000),
                ('영국', 6000000, 20000000)
            ON DUPLICATE KEY UPDATE
                max_avg = VALUES(max_avg),
                min_avg = VALUES(min_avg);
            """
        )
    ]
