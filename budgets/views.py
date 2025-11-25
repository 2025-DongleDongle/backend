from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from .models import * 
from .serializers import *
from django.conf import settings
from rest_framework import status
from django.db import connection
from accounts.models import ExchangeProfile

# Create your views here.
"""
    views.py
    ├── BudgetView         → 예산안 CRUD
    ├── BaseBudgetView     → 기본 파견비 조회/등록
    ├── BaseBudgetItemView → 기본 파견비 항목 CRUD
    ├── LivingBudgetView   → 생활비 조회/등록
    └── LivingBudgetItemView → 생활비 항목 CRUD
"""

#예산안 전체 조회 및 등록
class BudgetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    #조회
    def get(self, request):
        budget, _ = Budget.objects.get_or_create(user=request.user)

        BaseBudget.objects.get_or_create(budget=budget)
        LivingBudget.objects.get_or_create(budget=budget)

        serilizer = BudgetSerializer(budget)
        return Response(serilizer.data)
    
    #등록
    def post(self, request):
        return self._create_or_update(request, is_create=True)

    #수정 
    def put(self, request):
        return self._create_or_update(request, is_create=False)



    #등록/수정 공통 로직 
    def _create_or_update(self, request, is_create):
        budget, created = Budget.objects.get_or_create(user=request.user)
        data = request.data

        # Base Budget 처리 
        base_budget_data = data.get("base_budget")
        if base_budget_data:
            base_budget, _ = BaseBudget.objects.get_or_create(budget=budget)
            base_serializer = BaseBudgetSerializer(
                base_budget, data=base_budget_data, partial=True
            )
            if base_serializer.is_valid():
                base_serializer.save()
            else:
                return Response(base_serializer.errors, status=status.HTTP_400_BAD_REQUEST)


        # Living Budget 처리
        living_budget_data = data.get("living_budget")
        if living_budget_data:
            living_budget, _ = LivingBudget.objects.get_or_create(budget=budget)
            living_serializer = LivingBudgetSerializer(
                living_budget, data=living_budget_data, partial=True
            )
            if living_serializer.is_valid():
                living_serializer.save()
            else:
                return Response(living_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            

        # Budget 전체 직렬화
        serializer = BudgetSerializer(budget)
        return Response(serializer.data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
    
#기본 파견비 조회 및 등록
class BaseBudgetView(APIView):
    permission_classes = [permissions.AllowAny]

    #조회
    def get(self, request):
        budget = Budget.objects.filter(user=request.user).first()
        base_budget = budget.base_budget
        serializer = BaseBudgetSerializer(base_budget)
        return Response(serializer.data)
    
    #등록
    def post(self, request):
        budget, _ = Budget.objects.get_or_create(user=request.user)
        serializer = BaseBudgetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(budget=budget)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)
    
#생활비 조회 및 등록
class LivingBudgetView(APIView):
    permission_classes = [permissions.AllowAny]

    #조회
    def get(self, request):
        budget = Budget.objects.filter(user=request.user).first()
        living_budget = budget.living_budget
        serializer = LivingBudgetSerializer(living_budget)
        return Response(serializer.data)
    

    #등록
    def post(self, request):
        budget, _ = Budget.objects.get_or_create(user=request.user)
        serializer = LivingBudgetSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(budget=budget)
            return Response(serializer.data, status=201)
        return Response(serializer.errors, status=400)


#기본파견비 평균값 조회 
class BaseAverageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "exchange_profile", None)

        if not profile or not profile.exchange_country:
            return Response({"detail": "파견 국가 정보가 없습니다."}, status=400)

        country = profile.exchange_country

        sql = """
            SELECT country, flight_avg, insurance_avg, visa_avg 
            FROM base_avg_cost 
            WHERE country = %s
            LIMIT 1;
        """

        with connection.cursor() as cursor:
            cursor.execute(sql, [country])
            row = cursor.fetchone()

        if not row:
            return Response({"detail": "해당 국가의 평균값 정보가 없습니다."}, status=404)

        return Response({
            "country": row[0],
            "flight_avg": row[1],
            "insurance_avg": row[2],
            "visa_avg": row[3],
        })


    
#생활비 평균값 조회
class LivingAvgView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # 유저 프로필에서 국가 가져오기
        profile = getattr(user, "exchange_profile", None)
        if not profile or not profile.exchange_country:
            return Response({"detail": "사용자의 교환국가 정보가 없습니다."}, status=400)

        country = profile.exchange_country 

        # Raw SQL 실행
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT transit_avg, food_avg
                FROM living_avg_cost
                WHERE country = %s
            """, [country])

            row = cursor.fetchone()

        if not row:
            return Response({"detail": f"{country}의 평균 데이터가 없습니다."}, status=404)

        transit_avg, food_avg = row

        return Response({
            "country": country,
            "transit_avg": transit_avg,
            "food_avg": food_avg,
        })
    
#총 예상 비용 평균 조회
def get_total_avg_cost(user):
    profile = getattr(user, "exchange_profile", None)
    if not profile:
        return None

    country = profile.exchange_country

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT min_avg, max_avg FROM total_avg_cost WHERE country = %s",
            [country]
        )
        row = cursor.fetchone()

    if not row:
        return None

    min_krw, max_krw = row

    # 환산 통화 계산
    target_currency = COUNTRY_TO_CURRENCY.get(country)

    min_converted = convert_from_krw(min_krw, target_currency)
    max_converted = convert_from_krw(max_krw, target_currency)

    return {
        "country": country,
        "min_krw": min_krw,
        "max_krw": max_krw,
        "min_converted": min_converted,
        "max_converted": max_converted,
        "currency": target_currency,
    }

class TotalAvgView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        data = get_total_avg_cost(request.user)
        if not data:
            return Response({"detail": "데이터 없음"}, status=404)
        return Response(data)