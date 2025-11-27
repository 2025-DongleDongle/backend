from decimal import Decimal
import re

from django.db import transaction
from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from .models import DetailProfile, SummarySnapshot
from .serializers import (DetailProfileSerializer, LedgerSummarySerializer)
from ledgers.models import LedgerEntry
from rates.views import convert_to_krw, convert_from_krw
from budgets.models import BaseBudget


INCLUDED_CATEGORIES = [
    LedgerEntry.Category.FOOD,
    LedgerEntry.Category.HOUSING,
    LedgerEntry.Category.TRANSPORT,
    LedgerEntry.Category.SHOPPING,
    LedgerEntry.Category.TRAVEL,
    LedgerEntry.Category.STUDY_MATERIALS,
]


KOREAN_COUNTRY_TO_CURRENCY = {
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
    "UK": "GBP",
}


def ok(message, data=None, status_code=status.HTTP_200_OK):
    return Response({"message": message, "data": data}, status=status_code)


def bad(message, error=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"message": message, "error": error}, status=status_code)


def resolve_foreign_currency(exchange_profile):
    if not exchange_profile:
        return "KRW"

    country_name = getattr(exchange_profile, "exchange_country", "") or ""
    name = str(country_name).strip()

    from ledgers.serializers import COUNTRY_TO_CURRENCY
    if name in COUNTRY_TO_CURRENCY:
        return COUNTRY_TO_CURRENCY[name]

    if name in KOREAN_COUNTRY_TO_CURRENCY:
        return KOREAN_COUNTRY_TO_CURRENCY[name]

    return "KRW"


def extract_months(exchange_profile):
    if not exchange_profile:
        return 1

    raw = getattr(exchange_profile, "exchange_period", "") or ""
    matched = re.findall(r"\d+", raw)
    if not matched:
        return 1

    months = int(matched[0])
    if months <= 0:
        return 1
    return months


class DetailProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        detail_profile = self._get_detail_profile_or_none(request.user)
        if not detail_profile:
            return ok("세부 프로필이 없습니다.", None)

        serializer = DetailProfileSerializer(detail_profile)
        return ok("세부 프로필 조회 성공", serializer.data)

    @transaction.atomic
    def post(self, request):
        if self._get_detail_profile_or_none(request.user):
            return bad("이미 세부 프로필이 존재합니다.", status_code=status.HTTP_400_BAD_REQUEST)

        serializer = DetailProfileSerializer(data=request.data)
        if not serializer.is_valid():
            return bad("세부 프로필 생성 실패", serializer.errors)

        detail_profile = serializer.save(user=request.user)
        snapshot = self._create_snapshot(request.user, detail_profile)

        data = {
            "detail_profile_id": detail_profile.id,
            "snapshot_id": snapshot.id,
        }
        return ok("세부 프로필 생성 및 가계부 요약본 스냅샷 생성 완료", data, status.HTTP_201_CREATED)

    @transaction.atomic
    def put(self, request):
        detail_profile = self._get_detail_profile_or_none(request.user)
        if not detail_profile:
            return bad("수정할 세부 프로필이 없습니다.", status_code=status.HTTP_404_NOT_FOUND)

        serializer = DetailProfileSerializer(
            detail_profile,
            data=request.data,
            partial=True,
        )
        if not serializer.is_valid():
            return bad("세부 프로필 수정 실패", serializer.errors)

        detail_profile = serializer.save()
        snapshot = self._create_snapshot(request.user, detail_profile)

        data = {
            "detail_profile_id": detail_profile.id,
            "snapshot_id": snapshot.id,
        }
        return ok("세부 프로필 수정 및 가계부 요약본 스냅샷 생성 완료", data)

    def _sum_ledger_for_user(self, user, foreign_currency):
        entries = (
            LedgerEntry.objects
            .filter(
                user=user,
                entry_type=LedgerEntry.EntryType.EXPENSE,
                category__in=INCLUDED_CATEGORIES,
            )
        )

        total_foreign = Decimal("0")
        total_krw = Decimal("0")

        for entry in entries:
            if entry.amount_converted and entry.converted_currency_code == "KRW":
                krw_at_entry = entry.amount_converted
            else:
                if entry.currency_code == "KRW":
                    krw_at_entry = entry.amount
                else:
                    converted = convert_to_krw(entry.amount, entry.currency_code)
                    if converted is None:
                        continue
                    krw_at_entry = converted
            total_krw += krw_at_entry

            if entry.currency_code == foreign_currency:
                foreign_at_entry = entry.amount
            else:
                foreign_at_entry = convert_from_krw(krw_at_entry, foreign_currency)
            if foreign_at_entry is not None:
                total_foreign += foreign_at_entry

        total_foreign = total_foreign.quantize(Decimal("0.01"))
        total_krw = total_krw.quantize(Decimal("0.01"))
        return total_foreign, total_krw

    def _get_detail_profile_or_none(self, user):
        try:
            return user.summary_detail_profile
        except DetailProfile.DoesNotExist:
            return None

    def _create_snapshot(self, user, detail_profile):
        exchange_profile = getattr(user, "exchange_profile", None)

        foreign_currency = resolve_foreign_currency(exchange_profile)
        total_foreign, total_krw = self._sum_ledger_for_user(user, foreign_currency)

        months = extract_months(exchange_profile)

        monthly_foreign = (total_foreign / months).quantize(Decimal("0.01"))
        monthly_krw = (total_krw / months).quantize(Decimal("0.01"))

        snapshot = SummarySnapshot.objects.create(
            user=user,
            exchange_profile=exchange_profile,
            detail_profile=detail_profile,
            snapshot_nickname=getattr(user, "nickname", "") or "",
            snapshot_gender=user.get_gender_display() if hasattr(user, "get_gender_display") else "",
            snapshot_exchange_country=getattr(exchange_profile, "exchange_country", "") or "",
            snapshot_exchange_university=getattr(getattr(exchange_profile, "exchange_univ", None), "univ_name", "") or "",
            snapshot_exchange_type=(
                exchange_profile.get_exchange_type_display()
                if exchange_profile and exchange_profile.exchange_type
                else ""
            ),
            snapshot_exchange_semester=getattr(exchange_profile, "exchange_semester", "") or "",
            snapshot_exchange_period=getattr(exchange_profile, "exchange_period", "") or "",
            living_expense_foreign_amount=monthly_foreign,
            living_expense_foreign_currency=foreign_currency,
            living_expense_krw_amount=monthly_krw,
            living_expense_krw_currency="KRW",
        )
        return snapshot


class LedgerSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    LABEL_MAP = {
        LedgerEntry.Category.FOOD: "식비",
        LedgerEntry.Category.HOUSING: "주거비",
        LedgerEntry.Category.TRANSPORT: "교통비",
        LedgerEntry.Category.SHOPPING: "쇼핑비",
        LedgerEntry.Category.TRAVEL: "여행비",
        LedgerEntry.Category.STUDY_MATERIALS: "교재비",
    }

    def get(self, request):
        user = request.user

        # if not hasattr(user, "summary_detail_profile"):
        #     return bad("세부 프로필이 등록되어 있지 않습니다.", status_code=status.HTTP_403_FORBIDDEN)

        exchange_profile = getattr(user, "exchange_profile", None)

        foreign_currency = resolve_foreign_currency(exchange_profile)
        months = extract_months(exchange_profile)

        categories_data, total_foreign, total_krw, total_current_krw = self._build_category_summaries(
            user,
            foreign_currency,
        )

        average_monthly = {
            "foreign_amount": (total_foreign / months).quantize(Decimal("0.01")),
            "foreign_currency": foreign_currency,
            "krw_amount": (total_krw / months).quantize(Decimal("0.01")),
            "krw_currency": "KRW",
            "current_rate_krw_amount": (total_current_krw / months).quantize(Decimal("0.01")),
        }

        base_dispatch_cost = self._build_dispatch_cost(user, foreign_currency)

        serializer = LedgerSummarySerializer(
            {
                "average_monthly_living_expense": average_monthly,
                "categories": categories_data,
                "base_dispatch_cost": base_dispatch_cost,
            }
        )
        return ok("가계부 요약본 조회 성공", serializer.data)

    def _build_category_summaries(self, user, foreign_currency):
        grouped = {}
        for code in INCLUDED_CATEGORIES:
            grouped[code] = {
                "code": code,
                "label": self.LABEL_MAP.get(code, code),
                "foreign_amount": Decimal("0"),
                "foreign_currency": foreign_currency,
                "krw_amount": Decimal("0"),
                "krw_currency": "KRW",
                "current_rate_krw_amount": Decimal("0"),
            }

        entries = (
            LedgerEntry.objects
            .filter(
                user=user,
                entry_type=LedgerEntry.EntryType.EXPENSE,
                category__in=INCLUDED_CATEGORIES,
            )
        )

        total_foreign = Decimal("0")
        total_krw = Decimal("0")
        total_current_krw = Decimal("0")

        for entry in entries:
            item = grouped[entry.category]

            if entry.currency_code == "KRW":
                current_krw = entry.amount
            else:
                current_krw = convert_to_krw(entry.amount, entry.currency_code)
            if current_krw is not None:
                item["current_rate_krw_amount"] += current_krw
                total_current_krw += current_krw

            if entry.amount_converted and entry.converted_currency_code == "KRW":
                krw_at_entry = entry.amount_converted
            else:
                if entry.currency_code == "KRW":
                    krw_at_entry = entry.amount
                else:
                    krw_at_entry = convert_to_krw(entry.amount, entry.currency_code)
            if krw_at_entry is not None:
                item["krw_amount"] += krw_at_entry
                total_krw += krw_at_entry

            if entry.currency_code == foreign_currency:
                item["foreign_amount"] += entry.amount
                total_foreign += entry.amount
            else:
                if krw_at_entry is not None:
                    foreign_val = convert_from_krw(krw_at_entry, foreign_currency)
                    if foreign_val is not None:
                        item["foreign_amount"] += foreign_val
                        total_foreign += foreign_val

        result = []
        for code in INCLUDED_CATEGORIES:
            item = grouped[code]
            item["foreign_amount"] = item["foreign_amount"].quantize(Decimal("0.01"))
            item["krw_amount"] = item["krw_amount"].quantize(Decimal("0.01"))
            item["current_rate_krw_amount"] = item["current_rate_krw_amount"].quantize(Decimal("0.01"))
            result.append(item)

        return result, total_foreign, total_krw, total_current_krw

    def _build_dispatch_cost(self, user, foreign_currency):
        base_budget = BaseBudget.objects.filter(budget__user=user).first()
        if not base_budget:
            return self._empty_dispatch_cost(foreign_currency)

        dispatch_items = {
            "flight": self._empty_dispatch_cost_item(foreign_currency),
            "insurance": self._empty_dispatch_cost_item(foreign_currency),
            "visa": self._empty_dispatch_cost_item(foreign_currency),
            "tuition": self._empty_dispatch_cost_item(foreign_currency),
        }

        for item in base_budget.items.all():
            key = item.type.lower()
            if key not in dispatch_items:
                continue

            krw_amount = item.exchange_amount or item.amount
            krw_currency = "KRW"

            if item.currency == foreign_currency:
                foreign_amount = item.amount
            else:
                foreign_amount = convert_from_krw(krw_amount, foreign_currency)
            if foreign_amount is None:
                foreign_amount = Decimal("0.00")

            # 현재 환율 기준
            current_rate_krw_amount = convert_to_krw(foreign_amount, foreign_currency)

            dispatch_items[key] = {
                "foreign_amount": foreign_amount.quantize(Decimal("0.01")),
                "foreign_currency": foreign_currency,
                "krw_amount": krw_amount.quantize(Decimal("0.01")),
                "krw_currency": krw_currency,
                "current_rate_krw_amount": current_rate_krw_amount.quantize(Decimal("0.01"))
                if current_rate_krw_amount
                else None,
            }

        # 총합 계산
        total_foreign = sum(
            (item["foreign_amount"] or Decimal("0")) for item in dispatch_items.values()
        )
        total_krw = sum(
            (item["krw_amount"] or Decimal("0")) for item in dispatch_items.values()
        )
        total_current = sum(
            (item["current_rate_krw_amount"] or Decimal("0")) for item in dispatch_items.values()
        )

        dispatch_items["total"] = {
            "foreign_amount": total_foreign.quantize(Decimal("0.01")),
            "foreign_currency": foreign_currency,
            "krw_amount": total_krw.quantize(Decimal("0.01")),
            "krw_currency": "KRW",
            "current_rate_krw_amount": total_current.quantize(Decimal("0.01")),
        }

        return dispatch_items

    def _empty_dispatch_cost_item(self, foreign_currency):
        return {
            "foreign_amount": None,
            "foreign_currency": foreign_currency,
            "krw_amount": None,
            "krw_currency": "KRW",
            "current_rate_krw_amount": None,
        }

    def _empty_dispatch_cost(self, foreign_currency):
        return {
            "flight": self._empty_dispatch_cost_item(foreign_currency),
            "insurance": self._empty_dispatch_cost_item(foreign_currency),
            "visa": self._empty_dispatch_cost_item(foreign_currency),
            "tuition": self._empty_dispatch_cost_item(foreign_currency),
            "total": {
                "foreign_amount": Decimal("0.00"),
                "foreign_currency": foreign_currency,
                "krw_amount": Decimal("0.00"),
                "krw_currency": "KRW",
                "current_rate_krw_amount": Decimal("0.00"),
            },
        }


class HasSummarySnapshotView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        has_snapshot = SummarySnapshot.objects.filter(user=user).exists()

        data = {
            "user_id": user.username,
            "has_summary_snapshot": has_snapshot,
        }

        return ok("가계부 요약본 생성 여부 조회 성공", data)


class LatestSummarySnapshotView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 최신 스냅샷으로 (수정했으면 계속 누적되어서 최신 걸로 가져오기)
        snapshot = (
            SummarySnapshot.objects
            .filter(user=user)
            .order_by('-created_at')
            .first()
        )

        if not snapshot:
            return ok("가계부 요약본이 없습니다.", None)

        data = {
            "snapshot_id": snapshot.id
        }

        return ok("가계부 요약본 ID 조회 성공", data)
