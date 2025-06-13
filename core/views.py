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
from datetime import datetime 
from collections import defaultdict 
from core.utils import * # This imports get_printer_sn_for_item, get_print_content, etc.
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

class PrintersDetail(generics.UpdateAPIView):
  permission_classes = [permissions.PlaceOwnerOrReadOnly]
  serializer_class = serializers.PrinterSerializer
  queryset = models.Printer.objects.all()

def home(request):
   return render(request, 'index.html')

@csrf_exempt
def create_order_intent(request):
    try:
        if not request.body:
            return JsonResponse({"success": False, "error": "Request body is empty."}, status=400)
        
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError as e:
            return JsonResponse({"success": False, "error": f"Invalid JSON format in request body: {str(e)}"}, status=400)

        place_id = data.get("place")
        if place_id is None:
            return JsonResponse({"success": False, "error": "Missing 'place' key in request data."}, status=400)
        
        try:
            place = models.Place.objects.get(id=place_id)
        except models.Place.DoesNotExist:
            return JsonResponse({"success": False, "error": "Place not found."}, status=404)

        today = timezone.now().date()
        max_daily_id_result = models.Order.objects.filter(place_id=place_id, created_at__date=today).aggregate(Max('daily_id'))
        max_id = max_daily_id_result['daily_id__max'] or 0
        daily_order_id = max_id + 1

        order_items_data_from_request = data.get('detail', []) 
        
        if not order_items_data_from_request:
            return JsonResponse({"success": False, "error": "Order must contain at least one item."}, status=400)

        total_order_amount = 0
        processed_order_item_details_for_json = []
        validated_items_for_order = []

        for item_data in order_items_data_from_request:
            menu_item_id_str = str(item_data.get("id"))
            quantity = int(item_data.get('quantity', 0))
            price_from_request = float(item_data.get('price', 0))

            if quantity <= 0:
                return JsonResponse({"success": False, "error": f"Quantity for item id {menu_item_id_str} must be positive."}, status=400)

            try:
                menu_item_obj = models.MenuItem.objects.get(id=menu_item_id_str, place_id=place_id)
            except models.MenuItem.DoesNotExist:
                return JsonResponse({"success": False, "error": f"MenuItem with id {menu_item_id_str} not found for this place."}, status=404)
            
            current_item_price = price_from_request 
            total_order_amount += current_item_price * quantity
            category_name = menu_item_obj.category.name

            processed_order_item_details_for_json.append({
                'id': menu_item_id_str,
                'name': menu_item_obj.name,
                'name_to_print': menu_item_obj.name_to_print or menu_item_obj.name, # Added name_to_print
                'category_name': category_name,
                'quantity': quantity,
                'price': current_item_price 
            })
            
            validated_items_for_order.append({
                'menu_item_obj': menu_item_obj,
                'quantity': quantity,
                'price_at_time_of_order': current_item_price,
                'category_name_at_time_of_order': category_name
            })

        printers_for_place = models.Printer.objects.filter(place_id=place_id)
        main_sn_id = None
        if validated_items_for_order:
            first_item_menu_obj = validated_items_for_order[0]['menu_item_obj']
            main_sn_id = get_printer_sn_for_item(printers_for_place, first_item_menu_obj) # Uses correct function name

        with transaction.atomic():
            order = models.Order.objects.create(
                place=place,
                table=data['table'],
                detail=json.dumps(processed_order_item_details_for_json), 
                amount=total_order_amount, 
                isTakeAway=data.get('isTakeAway', False),
                phoneNumer=data.get('phoneNumber'), 
                comment=data.get('comment'),
                arrival_time=data.get('arrival_time'),
                customer_name=data.get('customer_name'),
                daily_id=daily_order_id,
                isPrinted=False, 
                sn_id=main_sn_id 
            )

            for item_to_create in validated_items_for_order:
                models.OrderItem.objects.create(
                    order=order,
                    menu_item=item_to_create['menu_item_obj'],
                    quantity=item_to_create['quantity'],
                    price_at_time_of_order=item_to_create['price_at_time_of_order'],
                    category_name_at_time_of_order=item_to_create['category_name_at_time_of_order']
                )
            
            grouped_items_for_printing = defaultdict(list)
            for item_instance in order.items.all():
                menu_item_obj = item_instance.menu_item
                sn_id = get_printer_sn_for_item(printers_for_place, menu_item_obj) # Uses correct function name
                if sn_id:
                    name_to_print_for_item = menu_item_obj.name_to_print if menu_item_obj.name_to_print else menu_item_obj.name
                    item_detail_for_print = {
                        'name': menu_item_obj.name, 
                        'name_to_print': name_to_print_for_item, 
                        'quantity': item_instance.quantity
                    }
                    grouped_items_for_printing[sn_id].append(item_detail_for_print)
            
            print_jobs_successful = True
            if not grouped_items_for_printing:
                print_jobs_successful = False 

            if grouped_items_for_printing:
                datetime_to_print_str = order.created_at.strftime("%Y-%m-%d %H:%M:%S")
                for sn_id, items_for_this_printer in grouped_items_for_printing.items():
                    print_content = get_print_content(order.daily_id, data, items_for_this_printer, "B1", datetime_to_print_str)
                    try:
                        print_response = api_print_request(USER_NAME, USER_KEY, sn_id, print_content)
                        # Corrected Xpyun success check: expects 'code': 0 and 'msg': 'ok'
                        if not (print_response.get("code") == 0 and print_response.get("msg") == "ok"):
                            print(f"Warning: Print job to SN {sn_id} failed or had unexpected response. Response: {print_response}")
                            print_jobs_successful = False 
                    except Exception as print_e:
                        print(f"Error sending print job to SN {sn_id}: {print_e}")
                        print_jobs_successful = False 

            if print_jobs_successful and grouped_items_for_printing:
                order.isPrinted = True
            else:
                order.isPrinted = False 
            order.save(update_fields=['isPrinted'])

        update_last_ordering_time(place_id, data["table"])
        
        return JsonResponse({
            "success": True,
            "order_id": order.id,
        })

    except KeyError as e:
        return JsonResponse({"success": False, "error": f"Missing key in request data: {str(e)}"}, status=400)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": f"An unexpected error occurred: {str(e)}", 
        }, status=500)
    
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
            "category_id": category.id
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
            form_data = request.POST
            image_file = request.FILES.get('image')

            place_id_str = form_data.get("place")
            if not place_id_str:
                return JsonResponse({"success": False, "error": "Place ID is required."}, status=400)
            
            place_id = int(place_id_str)
            place = models.Place.objects.get(id=place_id)

            menu_item_name = form_data.get('name')
            if not menu_item_name:
                return JsonResponse({"success": False, "error": "Menu item name is required and cannot be empty."}, status=400)
            
            helper_data = {
                'ordering_timing': form_data.get('ordering_timing', 'lunch_and_dinner'),
                'name': menu_item_name,
                'description': form_data.get('description', '')
            }

            lunch_time_start,lunch_time_end,dinne_time_start,dinne_time_end = handle_lunch_dinner_time(place, helper_data)
            price = float(form_data.get('price', 0))

            name_to_print_from_form = form_data.get("name_to_print")
            if not name_to_print_from_form:
                name_to_print = menu_item_name
            else:
                name_to_print = name_to_print_from_form
            
            if name_to_print is None:
                name_to_print = ""
            
            raw_name_en, raw_name_pt, raw_description_en, raw_description_pt = translate_menu_name_description(form_data)

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
                'name': menu_item_name,
                'description': form_data.get('description', ''),
                'price': price,
                'is_available': form_data.get('is_available', 'true').lower() == 'true',
                'name_en': name_en,
                'name_pt': name_pt,
                'name_to_print': name_to_print,
                'description_en': description_en,
                'description_pt': description_pt,
                'ordering_timing': helper_data['ordering_timing'],
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
    permission_classes = [permissions.IsOwnerOrReadOnly]

    def post(self, request, place_id):
        place = get_object_or_404(models.Place, id=place_id)
        self.check_object_permissions(request, place)

        ordered_category_ids = request.data.get('ordered_category_ids')

        if not isinstance(ordered_category_ids, list):
            return Response({"error": "ordered_category_ids must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                existing_categories = {cat.id: cat for cat in models.Category.objects.filter(place=place)}
                
                if len(ordered_category_ids) != len(existing_categories):
                    return Response({"error": "The number of provided category IDs does not match the number of categories for this place."},
                                    status=status.HTTP_400_BAD_REQUEST)

                for i, category_id in enumerate(ordered_category_ids):
                    if category_id not in existing_categories:
                        return Response({"error": f"Category with ID {category_id} not found for this place or is invalid."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    
                    category = existing_categories[category_id]
                    category.orders_display = i + 1
                    category.save(update_fields=['orders_display'])
            
            return Response({"success": "Categories reordered successfully."}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": f"An error occurred: {str(e)}"},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ReorderMenuItemsView(views.APIView):
    permission_classes = [permissions.PlaceOwnerOrReadOnly]

    def post(self, request, category_id):
        category = get_object_or_404(models.Category, id=category_id)
        self.check_object_permissions(request, category) 

        ordered_item_ids = request.data.get('ordered_item_ids')

        if not isinstance(ordered_item_ids, list):
            return Response({"error": "ordered_item_ids must be a list."},
                            status=status.HTTP_400_BAD_REQUEST)
        
        try:
            with transaction.atomic():
                existing_items = {item.id: item for item in models.MenuItem.objects.filter(category=category)}

                if len(ordered_item_ids) != len(existing_items):
                    return Response({"error": "The number of provided item IDs does not match the number of items in this category."},
                                    status=status.HTTP_400_BAD_REQUEST)

                for i, item_id in enumerate(ordered_item_ids):
                    if item_id not in existing_items:
                        return Response({"error": f"Menu item with ID {item_id} not found in this category or is invalid."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    
                    menu_item = existing_items[item_id]
                    menu_item.item_order = i + 1
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
        printers = models.Printer.objects.filter(place_id=place_id)
        daily_order_id = int(data["daily_id"])
        
        order_detail_str = data.get("detail", "[]") 
        items_to_reprint = json.loads(order_detail_str) if isinstance(order_detail_str, str) else order_detail_str
        
        grouped_for_reprint_by_sn = defaultdict(list)
        for item_detail in items_to_reprint:
            menu_item_id = str(item_detail.get("id"))
            try:
                menu_item_obj = models.MenuItem.objects.get(id=menu_item_id, place_id=place_id)
                sn_id = get_printer_sn_for_item(printers, menu_item_obj) # Uses correct function name
                if sn_id:
                    name_to_print = menu_item_obj.name_to_print if menu_item_obj.name_to_print else menu_item_obj.name
                    item_detail_for_print = {
                        'name': menu_item_obj.name,
                        'name_to_print': name_to_print,
                        'quantity': item_detail.get('quantity', 1) 
                    }
                    grouped_for_reprint_by_sn[sn_id].append(item_detail_for_print)
            except models.MenuItem.DoesNotExist:
                print(f"Warning: MenuItem {menu_item_id} not found during reprint, skipping.")
                continue
        
        order_created_at_str = data.get('order_created_at', timezone.now().strftime("%Y-%m-%d %H:%M:%S"))

        for sn_id, items_for_this_printer in grouped_for_reprint_by_sn.items():
            print_content = get_print_content(daily_order_id, data, items_for_this_printer, "B1", order_created_at_str)
            response = api_print_request(USER_NAME, USER_KEY, sn_id, print_content)

        return JsonResponse({
            "success": True,
            "message": "Reprint request sent successfully.",
        })
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e),
        }, status=500)
