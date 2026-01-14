# authentication/views.py

from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import get_user_model
from .serializers import CustomUserSerializer
from auth_kit.views.login import LoginView as BaseLoginView
from drf_spectacular.utils import extend_schema
from .serializers import LoginResponseSerializer



User = get_user_model()

class CustomUserView(RetrieveUpdateAPIView):
    """View de User customizada que retorna os dados completos modificados do usuário"""

    serializer_class = CustomUserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user
    
@extend_schema(
    responses={200: LoginResponseSerializer},
)
   

    
class CustomLoginView(BaseLoginView):
    """View de login customizada que retorna os dados completos do usuário"""
    
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        
        if response.status_code == 200:
            email = request.data.get('email') or request.data.get('username')
            user = User.objects.get(email=email)
            
            user_serializer = CustomUserSerializer(user)
            
            response.data['user'] = user_serializer.data
        
        return response
    

'''
#Views only for documentation
@extend_schema(
    responses={200: LoginResponseSerializer},
)
class CustomLoginView(BaseLoginView):
    def get_response_data(self, user, access, refresh):
        data = super().get_response_data(user, access, refresh)
        data["user"] = CustomUserSerializer(user).data
        return data
'''