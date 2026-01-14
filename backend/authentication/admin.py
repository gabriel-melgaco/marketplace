from django.contrib import admin
from . import models

class CustomUser(admin.ModelAdmin):
    list_display = ('email', 'full_name', 'birthday', 'cpf', 'picture')
    search_fields = ('email', 'full_name', 'birthday', 'cpf', 'picture')

admin.site.register(models.CustomUser, CustomUser)
