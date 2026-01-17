from django.contrib import admin
from . import models

class Category(admin.ModelAdmin):
    list_display = ('name', 'slug', 'parent', 'is_active')
    search_fields = ('name', 'slug', 'parent', 'is_active')

admin.site.register(models.Category, Category)


class Series(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')

admin.site.register(models.Series, Series)


class Products(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'series', 'code', 'description')
    search_fields = ('name', 'slug', 'category', 'series', 'code', 'description')

admin.site.register(models.Products, Products)


class Condition(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name', 'slug')

admin.site.register(models.Condition, Condition)


class MarketPlaceListing(admin.ModelAdmin):
    list_display = ('product', 'seller', 'price', 'brand', 'quantity', 'is_active', 'description', 'condition', 'views_count', 'weight_kg', 'height_cm', 'width_cm', 'length_cm', 'created_at', 'updated_at', 'sold_at')
    search_fields = ('product', 'seller', 'price', 'brand', 'quantity', 'is_active', 'description', 'condition', 'views_count', 'weight_kg', 'height_cm', 'width_cm', 'length_cm', 'created_at', 'updated_at', 'sold_at')

admin.site.register(models.MarketplaceListing, MarketPlaceListing)


class Brand(admin.ModelAdmin):
    list_display = ('name', 'slug', 'logo', 'website')
    search_fields = ('name', 'slug','logo', 'website')

admin.site.register(models.Brand, Brand)