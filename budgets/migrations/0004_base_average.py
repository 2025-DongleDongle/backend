from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [("budgets", "0002_budget_total_budget")]

    operations = [
        migrations.RunSQL(
            """
            CREATE TABLE IF NOT EXISTS base_avg_cost (
                id INT AUTO_INCREMENT PRIMARY KEY,
                country VARCHAR(50) UNIQUE,
                flight_avg INT,
                insurance_avg INT,
                visa_avg INT
            );
            """
        ),

        # --- 더미데이터 삽입(KRW 기준) ---
        migrations.RunSQL(
            """
            INSERT INTO base_avg_cost(country, flight_avg, insurance_avg, visa_avg)
            VALUES
                ('미국', 1700000, 200000, 250000),
                ('일본', 500000, 40000, 30000),
                ('독일', 1600000, 220000, 240000),
                ('프랑스', 1800000, 250000, 260000),
                ('중국', 800000, 50000, 70000),
                ('대만', 900000, 60000, 80000),
                ('캐나다', 1500000, 230000, 260000),
                ('이탈리아', 1400000, 210000, 230000),
                ('네덜란드', 1600000, 220000, 250000),
                ('영국', 1700000, 240000, 260000)
            ON DUPLICATE KEY UPDATE
                flight_avg = VALUES(flight_avg),
                insurance_avg = VALUES(insurance_avg),
                visa_avg = VALUES(visa_avg);
            """
        )
    ]
