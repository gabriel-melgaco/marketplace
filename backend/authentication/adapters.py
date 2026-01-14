# authentication/adapters.py

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.socialaccount.models import SocialLogin
from typing import Any
import traceback



class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    
    def pre_social_login(self, request, sociallogin: SocialLogin):
        try:
            if request.user.is_authenticated:
                return
            
            email = sociallogin.account.extra_data.get('email')
            
            if not email:
                return
            
            from django.contrib.auth import get_user_model
            User = get_user_model()
            
            try:
                user = User.objects.get(email=email)
                sociallogin.connect(request, user)
            except User.DoesNotExist:
                pass
        except Exception as e:
            traceback.print_exc()
    
    def populate_user(self, request, sociallogin: SocialLogin, data: dict[str, Any]):
        try:
            user = super().populate_user(request, sociallogin, data)
            
            extra_data = sociallogin.account.extra_data
            
            # Nome completo
            full_name = extra_data.get('name', '')
            picture = extra_data.get('picture')
            
            if not full_name:
                given_name = extra_data.get('given_name', '')
                family_name = extra_data.get('family_name', '')
                full_name = f"{given_name} {family_name}".strip()
            
            if full_name:
                user.full_name = full_name
            
            if picture:
                user.picture = picture
            
            
            return user
            
        except Exception as e:
            traceback.print_exc()
            raise
    
    def save_user(self, request, sociallogin: SocialLogin, form=None):
        try:
            user = super().save_user(request, sociallogin, form)
            return user
        except Exception as e:
            traceback.print_exc()
            raise
    
    def post_signup(self, request, sociallogin: SocialLogin, attrs: dict[str, Any]):
        try:
            user = sociallogin.user
            
            # Marcar email como verificado
            from allauth.account.models import EmailAddress
            EmailAddress.objects.filter(
                user=user, 
                email=user.email
            ).update(verified=True, primary=True)
            
        except Exception as e:
            traceback.print_exc()

