from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from .serializers import *
from django.conf import settings
from rest_framework import status
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework.permissions import IsAuthenticated


class SignUpView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SignUpSerializer(data=request.data)
    
        if serializer.is_valid():
            user = serializer.save()
            response_data = UserReadSerializer(user).data
            return Response({'message':'성공적으로 회원가입되었습니다.', 'data':response_data})
        return Response({'message':'회원가입에 실패하였습니다.', 'error':serializer.errors})


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    serializer_class = UserLoginSerializer
    def post(self, request):
        # 로그인 시 해당 유저의 OutstandingToken 삭제
        username = request.data.get("username")
        user = User.objects.filter(username=username).first()
        if user:
            OutstandingToken.objects.filter(user=user).delete()

        serializer = UserLoginSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.validated_data
            remember = bool(request.data.get("remember", False))

            resp = Response({"message": "성공적으로 로그인되었습니다.", "data": {
                "id": data["id"],
                "username": data["username"],
                "access_token": data["access_token"],
            }})

            refresh_token = data["refresh_token"]
            max_age = 14 * 24 * 60 * 60 if remember else None
            resp.set_cookie(
                key="refresh_token",
                value=refresh_token,
                max_age=max_age,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
                path="/",
            )
            return resp
        return Response({'message':'로그인에 실패하였습니다.', 'error':serializer.errors})


class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_from_cookie = request.COOKIES.get("refresh_token")
        refresh_in_body = request.data.get("refresh")

        payload = {"refresh": refresh_in_body or refresh_from_cookie}
        if not payload["refresh"]:
            return Response({"detail": "No refresh token."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TokenRefreshSerializer(data=payload)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as e:
            raise InvalidToken(e.args[0])

        data = {"access_token": serializer.validated_data["access"]}

        new_refresh = serializer.validated_data.get("refresh")
        resp = Response(data, status=status.HTTP_200_OK)

        if new_refresh:
            old = request.COOKIES.get("refresh_token")
            is_session_cookie = "Max-Age" not in (request.headers.get("Cookie", ""))
            max_age = None if is_session_cookie else 14 * 24 * 60 * 60

            resp.set_cookie(
                key="refresh_token",
                value=new_refresh,
                max_age=max_age,
                httponly=True,
                samesite="Lax",
                secure=not settings.DEBUG,
                path="/",
            )
        return resp


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data={}, context={"request": request})
        serializer.is_valid(raise_exception=True)

        resp = Response(serializer.validated_data, status=status.HTTP_200_OK)
        resp.delete_cookie(
            key="refresh_token",
            path="/",
            domain=None,
            samesite="Lax",
        )
        return resp


def ok(message, data=None, status_code=status.HTTP_200_OK):
    return Response({"message": message, "data": data}, status=status_code)


def bad(message, error=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"message": message, "error": error}, status=status_code)


class UniversitySearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        keyword = request.query_params.get("q", "").strip()
        queryset = University.objects.all()

        if keyword:
            queryset = queryset.filter(univ_name__icontains=keyword)

        queryset = queryset.order_by("univ_name")

        serializer = UniversityListSerializer(queryset, many=True)
        return ok("본교 목록입니다.", serializer.data)


class CountryListView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        data = [
            {"code": choice[0], "label": choice[1]}
            for choice in CountryOption.choices
        ]
        data = sorted(data, key=lambda x: x["label"])
        return ok("파견 국가 목록입니다.", data)


class ExchangeUniversitySearchView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        keyword = request.query_params.get("q", "").strip()

        queryset = ExchangeUniversity.objects.all()

        if keyword:
            queryset = queryset.filter(univ_name__icontains=keyword)

        queryset = queryset.order_by("univ_name")

        serializer = ExchangeUniversityListSerializer(queryset, many=True)
        return ok("파견 대학 목록입니다.", serializer.data)


def ok(message, data=None, status=200):
    return Response({"message": message, "data": data}, status=status)


def bad(message, error=None, status=400):
    return Response({"message": message, "error": error}, status=status)


class MyProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MyProfileSerializer(request.user)
        return ok("조회 완료", serializer.data, status=200)

    def put(self, request):
        serializer = ExchangeProfileUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        if not serializer.is_valid():
            return bad("유효성 검사 실패", serializer.errors)

        serializer.save()
        refreshed = MyProfileSerializer(request.user)
        return ok("파견 정보 수정 완료", refreshed.data)
