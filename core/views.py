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

# Create your views here.
class PlaceList(generics.ListCreateAPIView):
  serializer_class = serializers.PlaceSerializer


  
  def get_queryset(self):
    print('fefe')
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

# Create Orders
@csrf_exempt
def create_order_intent(request):

  try:
    data = json.loads(request.body)
    place_id = data["place"]
    printers = Printer.objects.filter(place_id=place_id)
    comments = data["comment"]
    # Create a defaultdict to store comments grouped by category ID
    grouped_comments = defaultdict(str)
    # Iterate over the items in the comments dictionary
    for menu_id, comment_data in comments.items():
        # Extract category ID from the first element of the value list
        category_id = comment_data[0]
        
        # Look up the menu item in the MenuItem model
        try:
            menu_item = MenuItem.objects.get(pk=int(menu_id))
            menu_name =  menu_item.name

        except MenuItem.DoesNotExist:
            # Handle the case where the menu item does not exist
            menu_name = "Unknown Menu"
        
        # Concatenate the menu ID and comment with the existing comments for the category
        grouped_comments[category_id] += f"{menu_name}: {comment_data[1]}  "
    
    # Convert the defaultdict to a regular dictionary
    grouped_comments_dict = dict(grouped_comments)
    
    table_number = data["table"]
    update_last_ordering_time(place_id,table_number)

    # Verify reCAPTCHA token
    recaptcha_secret = '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'  # Replace with your actual reCAPTCHA secret key
    recaptcha_response = data.get('recaptchaToken')

    verification_url = 'https://www.google.com/recaptcha/api/siteverify'
    payload = {
        'secret': recaptcha_secret,
        'response': recaptcha_response
    }

    response = requests.post(verification_url, data=payload)
    result = response.json()

    if not result['success']:
        return JsonResponse({
            "success": False,
            "error": "reCAPTCHA verification failed"
        })
    
    today = timezone.now().date()
    max_id = models.Order.objects.filter(created_at__date=today).aggregate(Max('daily_id'))['daily_id__max'] or 0


    grouped_details_by_sn = grouped_details(data,printers,grouped_comments_dict)

    daily_order_id = max_id + 1
    
    for sn_id, details_list in grouped_details_by_sn.items():
      content_to_print = get_print_content(daily_order_id,data,details_list)
      try:
        response_print = api_print_request(USER_NAME, USER_KEY, sn_id,content_to_print)  
        response_check_printer = api_check_printer_request(USER_NAME, USER_KEY, sn_id)
        update_printer_status(sn_id,response_check_printer["data"])

      except:
         continue
      
    if response_print["code"] == 0:
       is_printed = True
    else:
       is_printed = False

    order = models.Order.objects.create(
      place_id = data['place'],
      table = data['table'],
      detail = json.dumps(data['detail']),
      amount = data['amount'],
      isTakeAway = data['isTakeAway'],
      phoneNumer = data['phoneNumber'],
      comment = data['comment'],
      arrival_time = data['arrival_time'],
      customer_name = data['customer_name'],
      daily_id = daily_order_id,
      isPrinted = is_printed
    )

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


# def delete_image(request):
#     data = json.loads(request.body)
#     public_id = data['public_id']

#     try:
#         result = cloudinary.uploader.destroy(public_id)
#         if result.get('result') == 'ok':
#             return JsonResponse({'message': 'Image deleted successfully.'})
#         else:
#             return JsonResponse({'error': 'Failed to delete image.'}, status=400)
#     except Exception as e:
#         return JsonResponse({'error': str(e)}, status=500)
    
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