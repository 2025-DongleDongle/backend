from rest_framework import serializers
from .models import *
from accounts.models import ExchangeProfile
from rates.views import convert_to_krw, convert_from_krw


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
    "USA": "USD",
    "JAPAN": "JPY",
    "KOREA": "KRW",
    "CHINA": "CNY",
    "TAIWAN": "TWD",
    "CANADA": "CAD",
    "UK": "GBP",
    "FRANCE": "EUR",
    "GERMANY": "EUR",
    "NETHERLANDS": "EUR",
    "ITALY": "EUR",
}

#기본 파견비 내 아이템 시리얼라이저 
class BaseBudgetItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = BaseBudgetItem
        fields = ["id", "type", "amount", "currency", "exchange_amount", "created_at", "updated_at"]


#기본 파견비 시리얼라이저(*Nested Serializer)
class BaseBudgetSerializer(serializers.ModelSerializer):
    items = BaseBudgetItemSerializer(many=True)

    class Meta:
        model = BaseBudget
        fields = ["id", "total_amount_krw", "items", "created_at", "updated_at" ]

    def validate_items(self, value):
        """기본 파견비 항목은 FLIGHT, INSURANCE, VISA, TUITION 모두 필수"""
        required_types = {"FLIGHT", "INSURANCE", "VISA", "TUITION"}
        provided_types = {item.get("type") for item in value}

        missing = required_types - provided_types
        extra = provided_types - required_types

        if missing:
            raise serializers.ValidationError(
                f"다음 항목이 누락되었습니다: {', '.join(missing)}"
            )
        if extra:
            raise serializers.ValidationError(
                f"유효하지 않은 항목이 포함되어 있습니다: {', '.join(extra)}"
            )

        if len(value) != 4:
            raise serializers.ValidationError("기본 파견비 항목은 정확히 4개여야 합니다.")

        return value

    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        base_budget = BaseBudget.objects.create(**validated_data)

        for item_data in items_data:
            BaseBudgetItem.objects.create(base_budget=base_budget, **item_data)

        base_budget.update_total()
        return base_budget
    
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for item_data in items_data:
            item_type = item_data.get("type")
            item_obj = instance.items.filter(type=item_type).first()

            if item_obj:
                for attr, value in item_data.items():
                    setattr(item_obj, attr, value)
                item_obj.save()
            else:
                BaseBudgetItem.objects.create(base_budget=instance, **item_data)

        instance.update_total()
        return instance



#생활비 내 아이템 시리얼라이저 
class LivingBudgetItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LivingBudgetItem
        fields = ["id", "type", "custom_name", "amount", "created_at", "updated_at"]

    def get_display_name(self, obj):
        return obj.get_display_name()
    
    #사용자 정의 항목이면 ETC로 설정
    def validate(self, data):
        custom_name = data.get("custom_name")
        if custom_name:
            data["type"] = "ETC"
        return data
        

#생활비 시리얼라이저(*Nested Serializer)
class LivingBudgetSerializer(serializers.ModelSerializer):
    items = LivingBudgetItemSerializer(many=True)

    class Meta:
        model = LivingBudget
        fields = ["id", "total_amount", "items", "created_at", "updated_at"]
        
    def validate(self, attrs):
        if attrs.get("total_amount") in [None, ""]:
            raise serializers.ValidationError({
                "total_amount": "total_amount는 필수 값입니다."
            })
        return attrs

    def create(self, validated_data):
        base_budget_data = validated_data.pop("base_budget", None)
        living_budget_data = validated_data.pop("living_budget", None)

        budget = Budget.objects.create(**validated_data)

        # ---- BaseBudget 처리 ----
        if base_budget_data:
            items_data = base_budget_data.pop("items", [])
            base_budget = BaseBudget.objects.create(budget=budget, **base_budget_data)
            for item_data in items_data:
                BaseBudgetItem.objects.create(base_budget=base_budget, **item_data)
            base_budget.update_total()

        # ---- LivingBudget 처리 ----
        if living_budget_data:
            items_data = living_budget_data.pop("items", [])
            living_budget = LivingBudget.objects.create(budget=budget, **living_budget_data)
            for item_data in items_data:
                custom_name = item_data.get("custom_name")
                #사용자 입력 항목이면 ETC로 강제
                if custom_name:
                    item_data["type"] = "ETC"
                LivingBudgetItem.objects.create(living_budget=living_budget, **item_data)

        return budget

        
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", [])

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        for item_data in items_data:
            item_type = item_data.get("type")
            custom_name = item_data.get("custom_name")

            #사용자 정의 항목이면 ETC로 강제
            if custom_name:
                item_type = "ETC"

            # 기존 항목 조회
            item_obj = instance.items.filter(type=item_type, custom_name=custom_name).first()

            if item_obj:
                # 기존 항목 수정
                for attr, value in item_data.items():
                    setattr(item_obj, attr, value)
                item_obj.save()
            else:
                # 새 항목 생성 (amount 포함 후에 저장)
                LivingBudgetItem.objects.create(
                    living_budget=instance,
                    type=item_type,
                    custom_name=custom_name,
                    amount=item_data.get("amount", 0)
                )

        return instance

            
#예산안 시리얼라이저(*Nested Serializer)
class BudgetSerializer(serializers.ModelSerializer):
    total_budget_value = serializers.SerializerMethodField()
  
    base_budget = BaseBudgetSerializer(required=False)
    living_budget = LivingBudgetSerializer(required=False)

    class Meta:
        model = Budget
        fields = ["id", "user", "total_budget_value", "base_budget", "living_budget", "created_at", "updated_at"]
    
    
    def create(self, validated_data):
        base_budget_data = validated_data.pop("base_budget", None)
        living_budget_data = validated_data.pop("living_budget", None)

        budget = Budget.objects.create(**validated_data)

        base_budget_data["budget"] = budget
        living_budget_data["budget"] = budget

        if base_budget_data:
            base_budget_data["budget"] = budget
            BaseBudgetSerializer().create(base_budget_data)

        if living_budget_data:
            living_budget_data["budget"] = budget
            LivingBudgetSerializer().create(living_budget_data)

        return budget
    
    

    def update(self, instance, validated_data):
        base_budget_data = validated_data.pop("base_budget", None)
        living_budget_data = validated_data.pop("living_budget", None)

        if base_budget_data:
            base_budget_serializer = BaseBudgetSerializer(instance.base_budget, data=base_budget_data, partial=True)
            base_budget_serializer.is_valid(raise_exception=True)
            base_budget_serializer.save()

        if living_budget_data:
            living_budget_serializer = LivingBudgetSerializer(instance.living_budget, data=living_budget_data, partial=True)
            living_budget_serializer.is_valid(raise_exception=True)
            living_budget_serializer.save()

        instance.save()
        return instance
    

    #총 예상 금액 변환 
    def get_total_budget_value(self, obj):
        #1) KRW 총액
        total_krw = obj.get_total_budget()

        #2) 파견 통화 가져오기 
        profile = getattr(obj.user, "exchange_profile", None)

        country_name = profile.exchange_country
        target_currency = COUNTRY_TO_CURRENCY.get(country_name)
        converted = convert_from_krw(total_krw, target_currency)

        return{
            "krw": total_krw,
            "converted": converted
        }

        

