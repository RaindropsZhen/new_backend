from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static

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

    path('api/orders/', views.OrderList.as_view()),
    path('api/orders/<pk>', views.OrderDetail.as_view()),

    path('api/tables/<int:pk>/', views.TableBlockedStatusUpdate.as_view()),

    path('api/printers/<pk>', views.PrintersDetail.as_view()),

    path('reset_password/',auth_views.PasswordResetView.as_view(), name='reset_password'),

    path('reset_password_sent/',auth_views.PasswordResetDoneView.as_view(), name='password_reset_done'),

    path('reset/<uidb64>/<token>',auth_views.PasswordResetConfirmView.as_view(), name='password_reset_confirm'),

    path('reset_password_complete/',auth_views.PasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # The catch-all route will be moved down
]

# Add media file serving patterns if in DEBUG mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Add the catch-all frontend route last
# This ensures it only matches if no other pattern (including media) has matched
urlpatterns += [
    re_path(r'^.*$', views.home), # This will serve index.html for any other path
]
