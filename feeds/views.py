from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Count, Max
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny

from django.db import models
from .models import FeedFavorite, FeedScrap
from .serializers import *
from summaries.models import SummarySnapshot
from ledgers.models import LedgerEntry
from rates.views import convert_to_krw, convert_from_krw
from budgets.models import BaseBudget, Budget, BaseBudgetItem
import re


COUNTRY_TO_CURRENCY = {
    "한국": "KRW",
    "미국": "USD",
    "일본": "JPY",
    "독일": "EUR",
    "프랑스": "EUR",
    "중국": "CNY",
    "대만": "TWD",
    "캐나다": "CAD",
    "이탈리아": "EUR",
    "네덜란드": "EUR",
    "영국": "GBP",
}


# 총 파견비용 합산 -> 가계부 등록 총합 + 기본파견비용
def get_total_expense_with_budget(user):
    living_categories = ["FOOD", "HOUSING", "TRANSPORT", "SHOPPING", "TRAVEL", "STUDY_MATERIALS"]

    exchange_profile = getattr(user, "exchange_profile", None)
    if not exchange_profile:
        return Decimal("0"), Decimal("0")

    exchange_country = exchange_profile.exchange_country
    target_currency = COUNTRY_TO_CURRENCY.get(exchange_country, "KRW")

    # LedgerEntry 지출 합산 (원화 기준)
    entries = LedgerEntry.objects.filter(user=user, entry_type="EXPENSE", category__in=living_categories)

    total_krw = Decimal("0")
    for entry in entries:
        total_krw += convert_to_krw(entry.amount, entry.currency_code)

    # 예산안 기본파견비용 추가
    budget = Budget.objects.filter(user=user).first()
    if budget and hasattr(budget, "base_budget"):
        base_budget = budget.base_budget
        if base_budget.items.exists():
            for item in base_budget.items.all():
                total_krw += item.get_krw_amount()

    # 교환국 화폐 기준으로 변환
    total_foreign = convert_from_krw(total_krw, target_currency)
    return total_foreign, total_krw


# 가계부 등록합산만 (예산안 제외)
def get_total_ledger_expense(user):
    living_categories = ["FOOD", "HOUSING", "TRANSPORT", "SHOPPING", "TRAVEL", "STUDY_MATERIALS"]

    exchange_profile = getattr(user, "exchange_profile", None)
    if not exchange_profile:
        return Decimal("0"), Decimal("0")

    exchange_country = exchange_profile.exchange_country
    target_currency = COUNTRY_TO_CURRENCY.get(exchange_country, "KRW")

    # LedgerEntry 지출 합산 (원화 기준)
    entries = LedgerEntry.objects.filter(user=user, entry_type="EXPENSE", category__in=living_categories)

    total_krw = Decimal("0")
    for entry in entries:
        total_krw += convert_to_krw(entry.amount, entry.currency_code)

    total_foreign = convert_from_krw(total_krw, target_currency)
    return total_foreign, total_krw


def get_months(exchange_period: str) -> int:
    match = re.search(r"(\d+)", exchange_period or "")
    return int(match.group(1)) if match else 1


def safe_divide(amount: Decimal, months: int) -> Decimal:
    if not months or months == 0:
        return Decimal("0")
    return (amount / Decimal(months)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def ok(message, data=None, status=status.HTTP_200_OK):
    return Response({"message": message, "data": data}, status=status)


def bad(message, error=None, status=status.HTTP_400_BAD_REQUEST):
    return Response({"message": message, "error": error}, status=status)


class FeedListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        sort_option = request.query_params.get("sort", "latest")
        search = request.query_params.get("search")
        country = request.query_params.get("country")
        univ = request.query_params.get("univ")
        exchange_type = request.query_params.get("exchange_type")

        latest_ids = (
            SummarySnapshot.objects
            .values("user")
            .annotate(latest_id=Max("id"))
            .values_list("latest_id", flat=True)
        )

        feeds = (
            SummarySnapshot.objects
            .filter(id__in=latest_ids)
            .select_related("user", "exchange_profile")
            .annotate(
                like_count=Count("favorited_by"),
                scrap_count=Count("scrapped_by"),
            )
        )

        if search:
            feeds = feeds.filter(
                models.Q(exchange_profile__exchange_country__icontains=search) |
                models.Q(exchange_profile__exchange_univ__univ_name__icontains=search)
            )

        if country:
            feeds = feeds.filter(exchange_profile__exchange_country__icontains=country)
        if univ:
            feeds = feeds.filter(exchange_profile__exchange_univ__univ_name__icontains=univ)
        if exchange_type:
            feeds = feeds.filter(exchange_profile__exchange_type=exchange_type)

        if sort_option == "popular":
            feeds = feeds.order_by("-scrap_count")
        else:
            feeds = feeds.order_by("-created_at")

        serializer = FeedListSerializer(
            feeds,
            many=True,
            context={"user": request.user}
        )
        data = serializer.data

        # 계산된 비용 추가
        for feed_data, snapshot in zip(data, feeds):
            user = snapshot.user
            months = get_months(snapshot.snapshot_exchange_period)

            total_foreign, total_krw = get_total_expense_with_budget(user)
            ledger_foreign, ledger_krw = get_total_ledger_expense(user)

            avg_foreign = safe_divide(ledger_foreign, months)
            avg_krw = safe_divide(ledger_krw, months)

            feed_data["base_dispatch_foreign_amount"] = str(total_foreign.quantize(Decimal("0.01")))
            feed_data["base_dispatch_krw_amount"] = str(total_krw.quantize(Decimal("0.01")))
            feed_data["living_expense_foreign_amount"] = str(avg_foreign.quantize(Decimal("0.01")))
            feed_data["living_expense_krw_amount"] = str(avg_krw.quantize(Decimal("0.01")))

        return ok("가계부 요약본 목록 조회 성공", data)


class FeedDetailView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, feed_id):
        feed = get_object_or_404(
            SummarySnapshot.objects.select_related("user", "exchange_profile", "detail_profile"),
            id=feed_id
        )

        like_count = feed.favorited_by.count()
        scrap_count = feed.scrapped_by.count()
        user_liked = False
        user_scrapped = False

        if request.user.is_authenticated:
            user_liked = feed.favorited_by.filter(user=request.user).exists()
            user_scrapped = feed.scrapped_by.filter(user=request.user).exists()

        serializer = FeedDetailSerializer(feed)
        data = serializer.data

        user = feed.user
        months = get_months(feed.snapshot_exchange_period)

        # 교환국 화폐
        exchange_profile = getattr(user, "exchange_profile", None)
        if not exchange_profile:
            return bad("교환학생 정보가 없습니다.")
        target_currency = COUNTRY_TO_CURRENCY.get(exchange_profile.exchange_country, "KRW")

        # 한달평균생활비 계산
        living_categories = ["FOOD", "HOUSING", "TRANSPORT", "SHOPPING", "TRAVEL", "STUDY_MATERIALS"]

        ledger_foreign, ledger_krw = get_total_ledger_expense(user)
        avg_foreign = safe_divide(ledger_foreign, months)
        avg_krw = safe_divide(ledger_krw, months)

        # LedgerEntry 지출합
        entries = LedgerEntry.objects.filter(user=user, entry_type="EXPENSE", category__in=living_categories)

        category_totals_krw = {}
        for entry in entries:
            krw_amount = convert_to_krw(entry.amount, entry.currency_code)
            category_totals_krw.setdefault(entry.category, Decimal("0"))
            category_totals_krw[entry.category] += krw_amount

        living_expense_categories = []
        total_krw = Decimal("0")

        for code, krw_amount in category_totals_krw.items():
            label = LedgerEntry.Category(code).label
            foreign_amount = convert_from_krw(krw_amount, target_currency)

            current_krw_amount = convert_to_krw(foreign_amount, target_currency)

            living_expense_categories.append({
                "code": code,
                "label": label,
                "foreign_amount": str(foreign_amount.quantize(Decimal("0.01"))),
                "foreign_currency": target_currency,
                "krw_amount": str(krw_amount.quantize(Decimal("0.01"))),  # 과거 환율 기준 (등록 당시)
                "krw_currency": "KRW",
                "current_rate_krw_amount": str(current_krw_amount.quantize(Decimal("0.01"))) # 현재 환율 기준
            })

            total_krw += krw_amount

        living_expense_summary = {
            "foreign_amount": str(avg_foreign.quantize(Decimal("0.01"))),
            "foreign_currency": target_currency,
            "krw_amount": str(avg_krw.quantize(Decimal("0.01"))),
            "krw_currency": "KRW",
            "categories": living_expense_categories,
        }

        # 기본파견비용
        budget = Budget.objects.filter(user=user).first()
        base_budget = getattr(budget, "base_budget", None)
        base_dispatch_summary = {
            "foreign_amount": "0",
            "foreign_currency": target_currency,
            "krw_amount": "0",
            "krw_currency": "KRW",
            "categories": [],
        }

        if base_budget:
            total_krw = sum(item.get_krw_amount() for item in base_budget.items.all())
            categories = []

            for item in base_budget.items.all():
                label = BaseBudgetItem.BaseItem(item.type).label
                cost_krw = item.get_krw_amount()
                cost_foreign = convert_from_krw(cost_krw, target_currency)
                current_krw = convert_to_krw(cost_foreign, target_currency)

                categories.append({
                    "code": item.type,
                    "label": label,
                    "foreign_amount": str(cost_foreign.quantize(Decimal("0.01"))),
                    "foreign_currency": target_currency,
                    "krw_amount": str(cost_krw.quantize(Decimal("0.01"))),
                    "krw_currency": "KRW",
                    "current_rate_krw_amount": str(current_krw.quantize(Decimal("0.01"))),
                })

            base_dispatch_summary = {
                "foreign_amount": str(convert_from_krw(total_krw, target_currency).quantize(Decimal("0.01"))),
                "foreign_currency": target_currency,
                "krw_amount": str(total_krw.quantize(Decimal("0.01"))),
                "krw_currency": "KRW",
                "categories": categories,
            }

        data["living_expense_summary"] = living_expense_summary
        data["base_dispatch_summary"] = base_dispatch_summary
        data["like_count"] = like_count
        data["scrap_count"] = scrap_count
        data["liked"] = user_liked
        data["scrapped"] = user_scrapped

        return ok("가계부 요약본 상세 조회 성공", data)


class FeedFavoriteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, snapshot_id):
        snapshot = get_object_or_404(SummarySnapshot, id=snapshot_id)

        if FeedFavorite.objects.filter(user=request.user, snapshot=snapshot).exists():
            return bad("이미 좋아요를 누른 요약본입니다.")

        favorite = FeedFavorite.objects.create(user=request.user, snapshot=snapshot)
        serializer = FeedFavoriteSerializer(favorite)

        return ok("가계부 요약본 좋아요 추가 성공", serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, snapshot_id):
        snapshot = get_object_or_404(SummarySnapshot, id=snapshot_id)
        favorite = FeedFavorite.objects.filter(user=request.user, snapshot=snapshot).first()

        if not favorite:
            return bad("좋아요를 누르지 않은 요약본입니다.", status=status.HTTP_404_NOT_FOUND)

        favorite.delete()
        return ok("가계부 요약본 좋아요 삭제 성공", status=status.HTTP_204_NO_CONTENT)


class FeedScrapView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, snapshot_id):
        snapshot = get_object_or_404(SummarySnapshot, id=snapshot_id)

        if FeedScrap.objects.filter(user=request.user, snapshot=snapshot).exists():
            return bad("이미 스크랩한 요약본입니다.")

        scrap = FeedScrap.objects.create(user=request.user, snapshot=snapshot)
        serializer = FeedScrapSerializer(scrap)
        return ok("가계부 요약본 스크랩 추가 성공", serializer.data, status=status.HTTP_201_CREATED)

    def delete(self, request, snapshot_id):
        snapshot = get_object_or_404(SummarySnapshot, id=snapshot_id)
        scrap = FeedScrap.objects.filter(user=request.user, snapshot=snapshot).first()

        if not scrap:
            return bad("스크랩하지 않은 요약본입니다.", status=status.HTTP_404_NOT_FOUND)

        scrap.delete()
        return ok("가계부 요약본 스크랩 삭제 성공", status=status.HTTP_204_NO_CONTENT)


class MyScrapListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        scraps = (
            FeedScrap.objects
            .filter(user=request.user)
            .select_related("snapshot__user", "snapshot__exchange_profile")
            .order_by("-created_at")
        )

        snapshots = [scrap.snapshot for scrap in scraps]

        serializer = FeedListSerializer(
            snapshots,
            many=True,
            context={"user": request.user}
        )
        data = serializer.data

        for feed_data, snapshot in zip(data, snapshots):
            user = snapshot.user
            months = get_months(snapshot.snapshot_exchange_period)

            total_foreign, total_krw = get_total_expense_with_budget(user)
            ledger_foreign, ledger_krw = get_total_ledger_expense(user)

            avg_foreign = safe_divide(ledger_foreign, months)
            avg_krw = safe_divide(ledger_krw, months)

            feed_data["base_dispatch_foreign_amount"] = str(total_foreign.quantize(Decimal("0.01")))
            feed_data["base_dispatch_krw_amount"] = str(total_krw.quantize(Decimal("0.01")))
            feed_data["living_expense_foreign_amount"] = str(avg_foreign.quantize(Decimal("0.01")))
            feed_data["living_expense_krw_amount"] = str(avg_krw.quantize(Decimal("0.01")))

        return ok("내 스크랩 목록 조회 성공", data)


class MyFeedStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        favorite_count = FeedFavorite.objects.filter(user=request.user).count()
        scrap_count = FeedScrap.objects.filter(user=request.user).count()

        data = {
            "favorite_count": favorite_count,
            "scrap_count": scrap_count,
        }
        return ok("내 좋아요 및 스크랩 수 조회 성공", data)
