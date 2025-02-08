from django.contrib import admin
from django.urls import path, include, re_path

from django.contrib.auth import views as auth_views

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),

    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    
    path('api/places/', views.PlaceList.as_view()),
    path('api/places/<pk>', views.PlaceDetail.as_view()),

    path('api/categories/', views.CategoryList.as_view()),
    path('api/categories/<pk>', views.CategoryDetail.as_view()),
    path('api/create_category_intent/', views.create_category_intent),

    path('api/menu_items/', views.MenuItemList.as_view()),
    path('api/menu_items/<pk>', views.MenuItemDetail.as_view()),
    path('api/create_menu_items_intent/', views.create_menu_items_intent),

    path('api/create_order_intent/', views.create_order_intent),
    path('api/reprint_order/', views.reprint_order),

    #path('api/printers/', views.PrintersDetail.as_view()),

    path('api/orders/', views.OrderList.as_view()),
    path('api/orders/<pk>', views.OrderDetail.as_view()),

    #path('delete_image/', views.delete_image, name='delete_image'),
    path('api/printers/<pk>', views.PrintersDetail.as_view()),

    path('reset_password/',auth_views.PasswordResetView.as_view(), name='reset_password'),

    path('reset_password_sent/',auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),

    path('reset/<uidb64>/<token>',auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    path('reset_password_complete/',auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),


    re_path('',views.home),


]
