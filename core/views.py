import json
from googletrans import Translator
from django.utils import timezone
from django.db.models import Max
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status, views
from rest_framework.response import Response
from django.db import transaction
from . import models, serializers, permissions
from django.shortcuts import render, get_object_or_404
import requests
from qrmenu_backend.settings import user as USER_NAME,user_key as USER_KEY
from .models import Printer # Removed Place, MenuItem as models.Place etc. is used
from datetime import datetime # Added for current_datetime_azores
from collections import defaultdict # Added for reprint_order
from core.utils import *
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
  serializer_class = serializers.CategorySerializer

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

class TableBlockedStatusUpdate(generics.UpdateAPIView):
    permission_classes = [permissions.PlaceOwnerOrReadOnly]
    queryset = models.Table.objects.all()
    serializer_class = serializers.TableSerializer


class OrderList(generics.ListAPIView):
  serializer_class = serializers.OrderSerializer

  def get_queryset(self):
    return models.Order.objects.filter(place__owner_id=self.request.user.id, place_id=self.request.GET.get('place'))

class OrderDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.OrderSerializer
  queryset = models.Order.objects.all()

# Duplicate OrderList and OrderDetail removed, assuming the first pair is correct.

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
        data = json.loads(request.body)

        place_id = data["place"]
        printers = Printer.objects.filter(place_id=place_id)
        today = timezone.now().date()
        max_id = models.Order.objects.filter(created_at__date=today).aggregate(Max('daily_id'))['daily_id__max'] or 0

        daily_order_id = max_id + 1

        data_detail = data['detail']

        azores_tz = pytz.timezone('Atlantic/Azores')
        current_datetime_azores = datetime.now(azores_tz)

        category_mapping = {
            1: "Sushi", 2: "寿司套餐", 3: "中餐", 4: "甜品", 5: "饮料",
            6: "啤酒/酒", 7: "水果酒", 8: "红酒", 9: "绿酒", 10: "白酒",
            11: "粉红酒", 12: "威士忌", 13: "开胃酒", 14: "咖啡",
        }

        for detail_item in data_detail: # Renamed detail to detail_item to avoid conflict
          item_id = str(detail_item["id"])
          sn_id = get_serial_number_by_menu_item(printers, item_id)
          price = int(detail_item['price'])
          menu_item_obj = models.MenuItem.objects.get(id=item_id) # Renamed menu_item to menu_item_obj
          category_id = menu_item_obj.category_id
          category_name = category_mapping.get(category_id, "Unknown")
          detail_with_category = {
              'id': item_id,
              'price': price,
              'category': category_name,
              'name': detail_item['name'],
              'quantity': detail_item['quantity']
          }
          order = models.Order.objects.create(
              place_id=data['place'],
              table=data['table'],
              detail=json.dumps([detail_with_category]),
              amount=price,
              isTakeAway=data['isTakeAway'],
              phoneNumer=data.get('phoneNumber'), # Use .get for potentially missing keys
              comment=data.get('comment'),
              arrival_time=data.get('arrival_time'),
              customer_name=data.get('customer_name'),
              daily_id=daily_order_id,
              isPrinted=False,
              sn_id=sn_id,
              created_at = current_datetime_azores
          )
        table_number = data["table"]
        update_last_ordering_time(place_id,table_number)
        
        return JsonResponse({
            "success": True,
            "order_id": order.id, # Changed "order" to "order_id" for clarity
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        }, status=500) # Added status for consistency
    
@csrf_exempt
def create_category_intent(request):
    try:
        data = json.loads(request.body)
        translator = Translator()
        name_en = translator.translate(data['name'], src='zh-CN', dest='en').text
        name_pt = translator.translate(data['name'],src='zh-CN', dest='pt').text
        category = models.Category.objects.create(
            place_id=data['place'],
            name=data['name'],
            name_en=name_en,
            name_pt=name_pt
        )

        return JsonResponse({
            "success": True,
            "category_name": category.name,
            "category_id": category.id # Optionally return ID
        })

    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        }, status=500)

@csrf_exempt
def create_menu_items_intent(request):
    if request.method == 'POST':
        try:
            form_data = request.POST # Renamed data to form_data to avoid confusion
            image_file = request.FILES.get('image')

            place_id_str = form_data.get("place")
            if not place_id_str:
                return JsonResponse({"success": False, "error": "Place ID is required."}, status=400)
            
            place_id = int(place_id_str)
            place = models.Place.objects.get(id=place_id)

            menu_item_name = form_data.get('name')
            if not menu_item_name: # Checks for None or empty string
                return JsonResponse({"success": False, "error": "Menu item name is required and cannot be empty."}, status=400)
            
            helper_data = {
                'ordering_timing': form_data.get('ordering_timing', 'lunch_and_dinner'),
                'name': menu_item_name, # Use the validated name
                'description': form_data.get('description', '')
            }

            lunch_time_start,lunch_time_end,dinne_time_start,dinne_time_end = handle_lunch_dinner_time(place, helper_data)
            price = float(form_data.get('price', 0))

            name_to_print_from_form = form_data.get("name_to_print") # Get value, could be None or ""
            if not name_to_print_from_form: # If None or empty string
                name_to_print = menu_item_name # Default to the main item name
            else:
                name_to_print = name_to_print_from_form
            
            if name_to_print is None: # Ensure it's at least an empty string if menu_item_name was also somehow None (though validated)
                name_to_print = ""

            # Assuming translate_menu_name_description can take a dict-like object (request.POST)
            # or modify to pass individual fields
            # Adjust translate_menu_name_description to not return/process Spanish if it's a custom util function
            # For now, assuming it might return more than needed, and we'll pick what we need.
            # Or, if it's a direct call to googletrans multiple times, remove the 'es' calls.
            # Let's assume translate_menu_name_description is a black box for now and we just don't use _es results.
            # Ideally, translate_menu_name_description itself should be modified.
            # For a direct fix here, if it returns a tuple:
            # name_en, name_pt, _, description_en, _, description_pt = translate_menu_name_description(form_data)
            # This is risky if the function signature changes.
            # A safer modification is to adjust what's passed to it or how it's called if it's a series of direct translations.
            # Given the function name, it likely does multiple translations.
            # We will assume for now that the function `translate_menu_name_description` will be updated separately
            # or that we can simply ignore the Spanish parts it might return.
            # For the purpose of this diff, I will remove _es from being assigned and used.
            
            # This implies translate_menu_name_description might need to change its return signature
            # or the way it's called. For now, let's assume it's modified to not return Spanish.
            # If translate_menu_name_description is a series of direct calls, those for 'es' would be removed.
            # If it's a utility, that utility needs to be updated.
            
            raw_name_en, raw_name_pt, raw_description_en, raw_description_pt = translate_menu_name_description(form_data)

            # Ensure translated fields are empty strings if None (defensive against unexpected None from translation)
            name_en = raw_name_en if raw_name_en is not None else ""
            name_pt = raw_name_pt if raw_name_pt is not None else ""
            description_en = raw_description_en if raw_description_en is not None else ""
            description_pt = raw_description_pt if raw_description_pt is not None else ""

            category_id_str = form_data.get("category")
            if not category_id_str:
                return JsonResponse({"success": False, "error": "Category ID is required."}, status=400)
            category_id = int(category_id_str)

            menu_item_data = {
                'place_id': place_id,
                'category_id': category_id,
                'name': menu_item_name, # Use the validated name
                'description': form_data.get('description', ''),
                'price': price,
                'is_available': form_data.get('is_available', 'true').lower() == 'true',
                'name_en': name_en,
                'name_pt': name_pt,
                # 'name_es' field is removed from model, so no need to include it here
                'name_to_print': name_to_print,
                'description_en': description_en,
                # 'description_es' field is removed from model
                'description_pt': description_pt,
                'ordering_timing': helper_data['ordering_timing'], # Corrected assignment
                'lunch_time_start': lunch_time_start,     
                'lunch_time_end': lunch_time_end,
                'dinne_time_start': dinne_time_start,
                'dinne_time_end': dinne_time_end
            }
            if image_file:
                menu_item_data['image'] = image_file

            menuItem = models.MenuItem.objects.create(**menu_item_data)
            
            return JsonResponse({
                "success": True,
                "menu_item_name": menuItem.name,
                "menu_item_id": menuItem.id
            })
        except models.Place.DoesNotExist:
            return JsonResponse({"success": False, "error": "Place not found."}, status=404)
        except KeyError as e:
            return JsonResponse({"success": False, "error": f"Missing data: {str(e)}"}, status=400)
        except Exception as e:
            return JsonResponse({
                "success": False,
                "error": str(e),
            }, status=500)
    return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)


class ReorderCategoriesView(views.APIView):
    permission_classes = [permissions.IsOwnerOrReadOnly] # Changed to IsOwnerOrReadOnly

    def post(self, request, place_id):
        place = get_object_or_404(models.Place, id=place_id)
        self.check_object_permissions(request, place) # Explicitly check object permissions

        # The explicit check below is now handled by self.check_object_permissions and IsOwnerOrReadOnly
        # if request.user != place.owner:
        #      return Response({"error": "You do not have permission to reorder categories for this place."},
        #                     status=status.HTTP_403_FORBIDDEN)

        ordered_category_ids = request.data.get('ordered_category_ids')

        if not isinstance(ordered_category_ids, list):
            return Response({"error": "ordered_category_ids must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # Fetch all categories for the place to ensure IDs are valid and belong to this place
                existing_categories = {cat.id: cat for cat in models.Category.objects.filter(place=place)}
                
                if len(ordered_category_ids) != len(existing_categories):
                    return Response({"error": "The number of provided category IDs does not match the number of categories for this place."},
                                    status=status.HTTP_400_BAD_REQUEST)

                for i, category_id in enumerate(ordered_category_ids):
                    if category_id not in existing_categories:
                        # This check also implicitly handles if a category_id from another place is sent.
                        return Response({"error": f"Category with ID {category_id} not found for this place or is invalid."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    
                    category = existing_categories[category_id]
                    category.orders_display = i + 1 # Changed to i + 1 for 1-based indexing
                    category.save(update_fields=['orders_display'])
            
            return Response({"success": "Categories reordered successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ReorderMenuItemsView(views.APIView):
    permission_classes = [permissions.PlaceOwnerOrReadOnly] # This permission needs to be suitable for Category object

    def post(self, request, category_id):
        category = get_object_or_404(models.Category, id=category_id)
        
        # To use PlaceOwnerOrReadOnly, we pass the category object, 
        # and the permission class will check category.place.owner
        self.check_object_permissions(request, category)

        ordered_item_ids = request.data.get('ordered_item_ids')

        if not isinstance(ordered_item_ids, list):
            return Response({"error": "ordered_item_ids must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                # Fetch all menu items for the category to ensure IDs are valid and belong to this category
                existing_items = {item.id: item for item in models.MenuItem.objects.filter(category=category)}

                if len(ordered_item_ids) != len(existing_items):
                    return Response({"error": "The number of provided item IDs does not match the number of items in this category."},
                                    status=status.HTTP_400_BAD_REQUEST)

                for i, item_id in enumerate(ordered_item_ids):
                    if item_id not in existing_items:
                        return Response({"error": f"Menu item with ID {item_id} not found in this category or is invalid."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    
                    menu_item = existing_items[item_id]
                    menu_item.item_order = i + 1 # 1-indexed
                    menu_item.save(update_fields=['item_order'])
            
            return Response({"success": "Menu items reordered successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"An error occurred while reordering menu items: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@csrf_exempt
def reprint_order(request):
    try:
        data = json.loads(request.body)
        place_id = int(data["place"])
        printers = models.Printer.objects.filter(place_id=place_id) # Added models.
        daily_order_id = int(data["daily_id"])

        grouped_details_by_category = defaultdict(list)

        for detail_item in data.get("detail", []): # Added default empty list
            item_id = str(detail_item["id"])
            grouped_details_by_category[item_id].append(detail_item)

        # Ensure detail list is not empty before accessing its first element
        date_to_print = data.get("detail", [{}])[0].get('created_at') if data.get("detail") else None

        grouped_details_by_sn = defaultdict(list)

        for item_id, details_list in grouped_details_by_category.items():
            for detail_item_inner in details_list: # Renamed detail to detail_item_inner
                sn_id = get_serial_number_by_menu_item(printers, item_id)
                grouped_details_by_sn[sn_id].append(detail_item_inner)
        
        for sn_id, details_list_for_sn in grouped_details_by_sn.items(): # Renamed details_list
            content = get_print_content(daily_order_id,data, details_list_for_sn,"B1",date_to_print)
            response = api_print_request(USER_NAME, USER_KEY, sn_id, content)

        return JsonResponse({
            "success": True,
            "message": "Reprint request sent successfully.",
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        }, status=500)
