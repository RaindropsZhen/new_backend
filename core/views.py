import json
from googletrans import Translator
from django.utils import timezone
from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics
from django.conf import settings
from . import models, serializers, permissions
from django.shortcuts import render
import requests
from django.utils import timezone
from qrmenu_backend.settings import user as USER_NAME,user_key as USER_KEY
import requests
from .models import Printer,Place,MenuItem
from core.utils import *
import json
import xpyunopensdk.model.model as model
import xpyunopensdk.service.xpyunservice as service
import pytz

# Create your views here.
class PlaceList(generics.ListCreateAPIView):
  serializer_class = serializers.PlaceSerializer


  
  def get_queryset(self):
    return models.Place.objects.filter(owner_id=self.request.user.id)

  def perform_create(self, serializer):
    serializer.save(owner=self.request.user)

class PlaceDetail(generics.RetrieveUpdateDestroyAPIView):
  permission_classes = [permissions.IsOwnerOrReadOnly]
  serializer_class = serializers.PlaceDetailSerializer
  queryset = models.Place.objects.all()

class CategoryList(generics.CreateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.CategorySerializer

class CategoryDetail(generics.UpdateAPIView, generics.DestroyAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  queryset = models.Category.objects.all()

class MenuItemList(generics.CreateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.MenuItemSerializer

class MenuItemDetail(generics.UpdateAPIView, generics.DestroyAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.MenuItemSerializer
  queryset = models.MenuItem.objects.all()

class TableDetail(generics.UpdateAPIView, generics.DestroyAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.TableSerializer
  queryset = models.Table.objects.all()


class OrderList(generics.ListAPIView):
  serializer_class = serializers.OrderSerializer

  def get_queryset(self):
    return models.Order.objects.filter(place__owner_id=self.request.user.id, place_id=self.request.GET.get('place'))

class OrderDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.OrderSerializer
  queryset = models.Order.objects.all()

class OrderList(generics.ListAPIView):
  serializer_class = serializers.OrderSerializer

  def get_queryset(self):
    return models.Order.objects.filter(place__owner_id=self.request.user.id, place_id=self.request.GET.get('place'))

class OrderDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.OrderSerializer
  queryset = models.Order.objects.all()


class PrintersDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.PrinterSerializer
  queryset = models.Printer.objects.all()

def home(request):
   return render(request, 'index.html')

@csrf_exempt
def create_order_intent(request):
    try:
        
        client_ip = get_client_ip(request)
        print(client_ip)
        if not is_ip_allowed(client_ip, allowed_ips):
            return JsonResponse({
                "success": False,
                "error": "ERROR WIFI"
            })
        data = json.loads(request.body)
        place_id = data["place"]
        printers = Printer.objects.filter(place_id=place_id)
        today = timezone.now().date()
        max_id = models.Order.objects.filter(created_at__date=today).aggregate(Max('daily_id'))['daily_id__max'] or 0

        daily_order_id = max_id + 1

        data_detail = data['detail']

        # Define the Azores timezone
        azores_tz = pytz.timezone('Atlantic/Azores')

        # Get the current datetime in the Azores timezone
        current_datetime_azores = datetime.now(azores_tz)

        #print(data_detail)
        for detail in data_detail:
          item_id = str(detail["id"])
          sn_id = get_serial_number_by_menu_item(printers, item_id)
          price = int(detail['price'])
          order = models.Order.objects.create(
              place_id=data['place'],
              table=data['table'],
              detail=[detail],
              amount=price,
              isTakeAway=data['isTakeAway'],
              phoneNumer=data['phoneNumber'],
              comment=data['comment'],
              arrival_time=data['arrival_time'],
              customer_name=data['customer_name'],
              daily_id=daily_order_id,
              isPrinted=False,  # is_printed
              sn_id=sn_id,
              created_at = current_datetime_azores
          )
        table_number = data["table"]
        update_last_ordering_time(place_id,table_number)
        
        return JsonResponse({
            "success": True,
            "order": order.id,
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        })
    
@csrf_exempt
def create_category_intent(request):
    try:
        data = json.loads(request.body)
        translator = Translator()
        # Translation
        name_en = translator.translate(data['name'], src='zh-CN', dest='en').text
        name_pt = translator.translate(data['name'],src='zh-CN', dest='pt').text
        name_es = translator.translate(data['name'], src='zh-CN',dest='es').text
        # Create category
        category = models.Category.objects.create(
            place_id=data['place'],  # Using the place ID directly
            name=data['name'],
            name_en=name_en,
            name_pt=name_pt,
            name_es=name_es
        )

        return JsonResponse({
            "success": True,
            "category_name": category.name,
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        })
@csrf_exempt
def create_menu_items_intent(request):
    try:
        data = json.loads(request.body)
        place_id = data["place"]
        place = Place.objects.get(id=place_id)

        lunch_time_start,lunch_time_end,dinne_time_start,dinne_time_end = handle_lunch_dinner_time(place,data)
        price = int(data['price'])

        name_to_print = data["name_to_print"]
        ordering_timing = str(data["ordering_timing"])
        name_en,name_pt,name_es,description_en,description_es,description_pt = translate_menu_name_description(data)
        menuItem = models.MenuItem.objects.create(
            place_id=int(data['place']),  # Convert to int
            category_id=int(data['category']),  # Convert to int
            name=data['name'],
            description=data['description'],
            price=price,
            image=data['image'],
            is_available=data['is_available'],
            name_en=name_en,
            name_pt=name_pt,
            name_es=name_es,
            name_to_print=name_to_print,
            description_en=description_en,
            description_es=description_es,
            description_pt=description_pt,
            ordering_timing=ordering_timing,
            lunch_time_start = lunch_time_start,     
            lunch_time_end = lunch_time_end,
            dinne_time_start = dinne_time_start,
            dinne_time_end = dinne_time_end
        )
        
        return JsonResponse({
            "success": True,
            "menu_item_name": menuItem.name,
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        })


def xpYunQueryPrinterStatus(requests):
  request = model.PrinterRequest(USER_NAME, USER_KEY)
  request.user = USER_NAME
  request.userKey = USER_KEY
  OK_PRINTER_SN = request.POST.get('sn')
  request.sn = OK_PRINTER_SN
  request.generateSign()

  result = service.xpYunQueryPrinterStatus(request)

  # resp.data:Return to the printer status value, three types in total:
  # 0 indicates offline status.
  # 1 indicates online and normal status.
  # 2 indicates online and abnormal status.
  # Remarks: Abnormal status means lack of paper, if the printer has been out of contact with the server for more than 30s, it can be confirmed to be offline status.

@csrf_exempt
def reprint_order(request):
    try:
        data = json.loads(request.body)
        place_id = data["place"]
        printers = Printer.objects.filter(place_id=place_id)
        daily_order_id = data["daily_id"]  # Get daily_id from request
        # Assuming the detail structure is the same as in create_order_intent
        data_detail = data['detail']
        
        grouped_details_by_sn = grouped_details(data, printers)
        for sn_id, details_list in grouped_details_by_sn.items():
            content = get_print_content(daily_order_id,data, details_list,"B2")
            printer_response = api_print_request(USER_NAME, USER_KEY, sn_id, content)

        return JsonResponse({
            "success": True,
            "message": "Reprint request sent successfully.",
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        })
