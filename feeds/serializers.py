from rest_framework import serializers
from .models import FeedFavorite, FeedScrap
from summaries.models import SummarySnapshot


class FeedListSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(source="snapshot_nickname")
    gender = serializers.CharField(source="snapshot_gender")
    country = serializers.CharField(source="snapshot_exchange_country")
    university = serializers.CharField(source="snapshot_exchange_university")
    exchange_type = serializers.CharField(source="snapshot_exchange_type")
    exchange_semester = serializers.CharField(source="snapshot_exchange_semester")
    exchange_period = serializers.CharField(source="snapshot_exchange_period")

    like_count = serializers.SerializerMethodField()
    scrap_count = serializers.SerializerMethodField()
    liked = serializers.SerializerMethodField()
    scrapped = serializers.SerializerMethodField()

    class Meta:
        model = SummarySnapshot
        fields = [
            "id",
            "nickname",
            "gender",
            "country",
            "university",
            "exchange_type",
            "exchange_semester",
            "exchange_period",
            "living_expense_foreign_amount",
            "living_expense_foreign_currency",
            "living_expense_krw_amount",
            "base_dispatch_foreign_amount",
            "base_dispatch_krw_amount",
            "like_count",
            "scrap_count",
            "liked",
            "scrapped",
            "created_at",
        ]

    # 좋아요 / 스크랩 count
    def get_like_count(self, obj):
        return obj.favorited_by.count()

    def get_scrap_count(self, obj):
        return obj.scrapped_by.count()

    # 로그인한 유저가 좋아요 눌렀는지
    def get_liked(self, obj):
        user = self.context.get("user")
        if not user or user.is_anonymous:
            return False
        return obj.favorited_by.filter(user=user).exists()

    # 로그인한 유저가 스크랩 했는지
    def get_scrapped(self, obj):
        user = self.context.get("user")
        if not user or user.is_anonymous:
            return False
        return obj.scrapped_by.filter(user=user).exists()


class FeedDetailSerializer(serializers.ModelSerializer):
    user_info = serializers.SerializerMethodField()
    exchange_info = serializers.SerializerMethodField()
    lifestyle = serializers.SerializerMethodField()

    class Meta:
        model = SummarySnapshot
        fields = [
            "id",
            "user_info",
            "exchange_info",
            "living_expense_foreign_amount",
            "living_expense_foreign_currency",
            "living_expense_krw_amount",
            "base_dispatch_foreign_amount",
            "base_dispatch_krw_amount",
            "created_at",
            "lifestyle",
        ]

    def get_user_info(self, obj):
        return {
            "nickname": obj.snapshot_nickname,
            "gender": obj.snapshot_gender,
        }

    def get_exchange_info(self, obj):
        return {
            "country": obj.snapshot_exchange_country,
            "university": obj.snapshot_exchange_university,
            "exchange_type": obj.snapshot_exchange_type,
            "exchange_semester": obj.snapshot_exchange_semester,
            "exchange_period": obj.snapshot_exchange_period,
        }

    def get_lifestyle(self, obj):
        if not obj.detail_profile:
            return None
        d = obj.detail_profile
        return {
            "meal_frequency": d.get_meal_frequency_display(),
            "dineout_per_week": d.dineout_per_week,
            "coffee_per_week": d.coffee_per_week,
            "smoking_per_day": d.smoking_per_day,
            "drinking_per_week": d.drinking_per_week,
            "shopping_per_month": d.shopping_per_month,
            "culture_per_month": d.culture_per_month,
            "residence_type": d.residence_type,
            "commute": d.commute,
            "summary_note": d.summary_note,
        }


class FeedFavoriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedFavorite
        fields = ["id", "snapshot", "created_at"]
        read_only_fields = ["id", "created_at"]


class FeedScrapSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedScrap
        fields = ["id", "snapshot", "created_at"]
        read_only_fields = ["id", "created_at"]